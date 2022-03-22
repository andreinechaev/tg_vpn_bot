# Telegram bot for Outline VPN

A bot for issuing VPN access keys through Telegram

Bot relies on two channels for communication.
Main Chat to hold users with access to VPN.
You can create a channel or a group from Telegram UI. After creation you can use [ID Bot](https://t.me/username_to_id_bot).

It is suggested to have a private channel so you are in control of who joins the chat.

Dev Chat: to accept feedback and warnings. It is highly recommended to have a private channel. Feedback contains users' Ids and names. This information is private. Respect it.

## Build

`python3 setup.py install` will build and install the bot's wheel.

## Running

The service issues Outline VPN access keys.
To obtain Outline Apps follow the [instructions](https://getoutline.org/get-started/)

After you have Outline server running somewhere in the Cloud, you can create and configure the bot.
To register the bot can follow the official Telegram [documentation](https://core.telegram.org/bots#3-how-do-i-create-a-bot).

Since Telegram bot is constantly polling the message queue of the Telegram services, you can host the bot locally.
For simpicity clone the repository build and install.

Despite that it is recommended to host the bot on a dedicated server.
Add systemd service by adding the following file to /etc/systemd/system/outline_vpn.service

```bash
[Unit]
Description=VPN TG Service
After=network.target

[Service]
User=root
Environment="TELEGRAM_TOKEN=YOUR:TOKEN"
Environment="OUTLINE_VPN_ADDRESS=https://YOUR_SERVER/outline_vpn"
WorkingDirectory=/home/user/tg_vpn_bot
ExecStart=/usr/bin/python3 -c "from vpn_bot.main import launch; launch()" --chat_id=MAIN_CHAT_ID --dev_chat_id=DEV_CHAT_ID --limit=LIMIT
ExecReload=/bin/kill -HUP $MAINPID

[Install]
WantedBy=multi-user.target
```

### Parameters

TELEGRAM_TOKEN - Telegram bot token, obtained from [Telegram Botfather](https://t.me/botfather)
OUTLINE_VPN_ADDRESS - Outline VPN server address, obtained from Outline App installed on your maching in the server settings
chat_id: string - ID of the main chat
dev_chat_id: string - ID of the dev chat
limit: int - GBs allowed to use per user
