# Security & Functionality Audit

**Date:** 2026-04-10
**Scope:** Full repository review of `andreinechaev/tg_vpn_bot`

---

## Summary

This is a Telegram bot that distributes Outline VPN access keys to members of a
Telegram channel. The bot supports multi-server configurations, per-user
bandwidth limits, user statistics, and a feedback mechanism.

The audit identified **4 critical bugs**, **6 security vulnerabilities**, and
several dependency/infrastructure concerns.

---

## Critical Bugs (Fixed)

### 1. `NameError` in `stats()` — undefined variable `user`

**File:** `bot/vpn_bot.py:236`

When `getChatMember()` fails, the except block references `user.id`, but `user`
is not defined until line 246. This causes a `NameError`, crashing the error
handler instead of returning a friendly error message.

```python
# BEFORE (broken)
except Exception as e:
    self.logger.error(f'Error getting chat info: {e}')
    context.bot.sendMessage(
        chat_id=user.id, ...)  # 'user' is not defined here
```

### 2. `AttributeError` in `start_feedback()` — double `.id`

**File:** `bot/vpn_bot.py:193`

`update.effective_user.id` returns an `int`. Calling `.id` on an `int` raises
`AttributeError`, making the feedback error path always crash.

```python
# BEFORE (broken)
context.bot.sendMessage(
    chat_id=update.effective_user.id.id, ...)  # int has no .id
```

### 3. Feedback forwarded to dev chat before validation

**File:** `bot/vpn_bot.py:207-215`

User feedback is sent to the dev chat (line 210) *before* `_clean_text()`
validates the text (line 212). Empty or whitespace-only feedback gets forwarded
to developers regardless.

### 4. Incorrect type annotation in `stats()`

**File:** `bot/vpn_bot.py:260`

`user_vpn` is annotated as `OutlineVPN` but it's actually an `OutlineKey`.

---

## Security Vulnerabilities

### CRITICAL: SSL/TLS Verification Disabled Globally

**File:** `outline/outline_vpn.py` (all HTTP calls) and `vpn_bot/main.py:10`

Every HTTP request to the Outline VPN API uses `verify=False`, disabling
certificate validation. `urllib3` warnings are also suppressed. This makes all
API traffic vulnerable to man-in-the-middle attacks.

**Impact:** An attacker on the network path could intercept API tokens, VPN
access keys, and user data.

**Recommendation:** Use proper CA certificates. Outline VPN servers use
self-signed certificates — configure a custom CA bundle or pin the certificate
fingerprint instead of disabling verification entirely.

### HIGH: VPN Access URLs Logged in Plaintext

**File:** `bot/vpn_bot.py:177`

```python
self.logger.info(url)
```

The full VPN invite URL (containing the access key credentials) is written to
the log file. Anyone with log access gains access to every VPN key ever issued.

**Fixed:** Changed to log only that a URL was generated, not the URL itself.

### HIGH: Server API Credentials Logged in Debug Output

**File:** `bot/vpn_bot.py:47`

```python
self.logger.debug(f'Loaded servers: {servers}')
```

Server URLs contain embedded API tokens
(`https://HOST:PORT/SECRET_TOKEN`). Debug logging exposes these tokens.

**Fixed:** Changed to log only the server count.

### HIGH: Unencrypted HTTP Response Cache

**File:** `outline/outline_vpn.py:11`

```python
requests_cache.install_cache('outline_vpn_cache', backend='sqlite', ...)
```

API responses (containing VPN keys, passwords, access URLs) are cached in an
unencrypted SQLite file at the working directory. The cache filename is
predictable (`outline_vpn_cache.sqlite`).

**Recommendation:** Set restrictive file permissions on the cache file, or
disable caching for sensitive endpoints.

### MEDIUM: Error Handler Leaks Sensitive Context

**File:** `bot/vpn_bot.py:276-303`

The error handler logs the full update JSON, `chat_data`, and `user_data` plus a
full traceback to the log file. While this is useful for debugging, it can
expose user PII and potentially sensitive Telegram metadata.

**Recommendation:** Sanitize or truncate update data before logging. Avoid
logging full `chat_data`/`user_data` in production.

### MEDIUM: No Rate Limiting on Bot Commands

There is no rate limiting on `/start`, `/stats`, or `/feedback`. A malicious
user could spam commands to generate excessive API calls to Outline VPN servers
or trigger resource exhaustion.

**Recommendation:** Add per-user rate limiting using telegram-bot's built-in
mechanisms or a decorator.

---

## Dependency & Infrastructure Concerns

### Severely Outdated Dependencies

| Package | Pinned | Latest | Notes |
|---------|--------|--------|-------|
| `requests` | 2.26.0 | 2.32+ | Security patches missing |
| `python-telegram-bot` | 13.11 | 20+ | Major API rewrite; v13 is EOL |
| `numpy` | 1.20 | 2.0+ | Only used for median/mean — could use `statistics` stdlib |
| `watchdog` | 2.1.6 | 4.0+ | |
| `requests-cache` | 0.9 | 1.2+ | |

### `numpy` is a Heavy Dependency for Simple Math

`numpy` is imported solely for `np.median()` and `np.mean()` in `stats()`.
Python's built-in `statistics` module provides `median()` and `mean()` with zero
extra dependencies.

### CI/CD Pipeline Gaps

- **No tests run in CI** — the workflow builds a wheel but never runs pytest
- **Python 3.8 is EOL** (October 2024)
- **Outdated GitHub Actions** — uses `actions/checkout@v2` and
  `actions/setup-python@v2` (current: v4)
- **No linting, type checking, or security scanning**

### `setup.py` Deprecated

Modern Python packaging uses `pyproject.toml`. `setup.py` with
`python setup.py install` is deprecated by pip/setuptools.

### Duplicate `ArgumentParser` in `main.py`

Line 17 creates an `ArgumentParser` that is immediately discarded. Line 18
creates the one that's actually used.

### Mismatched `--help` Descriptions

`--log_file` and `--log_level` both have the help string "absolute path to JSON
File with the servers list" — copy-paste from `--servers`.

---

## Race Conditions

### Server Selection Can Exceed `max_users`

**File:** `bot/vpn_bot.py:110-130`

`get_client()` selects the server with the fewest users, then `generate_url()`
re-fetches keys and checks `max_users`. Between these calls, another request
could add a user, exceeding the limit.

**Recommendation:** Use an atomic check-and-create pattern, or accept the race
as a soft limit.

---

## Additional Observations

- **`generate_url()` can return `None` silently** (line 134) if `get_client()`
  returns `None` — though in practice it raises an exception instead.
- **`get_client()` raises `IndexError`** if all servers fail to connect (empty
  `vpns` list sorted and indexed at `[0]`).
- **Mixed language in user-facing strings** — some messages are in Russian,
  others in English, with no i18n framework.
- **`_clean_text()` is a naive sanitizer** — only strips whitespace characters
  but doesn't limit length or filter control characters.
