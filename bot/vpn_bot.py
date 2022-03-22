import os
import traceback
import json
import logging
import urllib.parse

import numpy as np

from outline.outline_vpn import OutlineVPN
from telegram import ChatMember, Update, User, ReplyKeyboardRemove
from telegram.ext import ConversationHandler, CallbackContext

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

VPN_URL_PREFIX = 'https://s3.amazonaws.com/outline-vpn/invite.html#'


def bytes_to_MB(bytes):
    return round(bytes / 1024 / 1024, 2)

def MB_to_bytes(MB):
    return MB * 1024 * 1024

def GB_to_MB(GB):
    return round(GB * 1024, 2)


class UserLimitReached(Exception):
    pass


class ServersConfigurator(FileSystemEventHandler):

    def __init__(self, url_path, url_filename):
        self.logger = logging.getLogger(__name__)
        self.url_path = url_path
        self.url_filename = url_filename
        self.path = os.path.join(url_path, url_filename)
        self.servers = {}
        self.update()

    def on_modified(self, event):
        if event.event_type == 'modified' and event.src_path == self.path:
            with open(self.path, 'r') as f:
                servers = json.load(f)['servers']
                self.logger.debug(f'Loaded servers: {servers}')
                if servers != self.servers:
                    self.servers = servers
                    self.logger.debug(
                        f'Updated servers on: {event.event_type}  path : {event.src_path}')

    def update(self):
        with open(self.path, 'r') as f:
            self.servers = json.load(f)['servers']


class VPNProvider:

    def __init__(self, vpn_urls: str, max_users: int = 100, bytes_limit: int = 1000000):
        self.logger = logging.getLogger(__name__)
        self.url_path, self.url_filename = os.path.split(vpn_urls)
        self.max_users = max_users
        self.bytes_limit = bytes_limit

        self.logger.debug(
            f'Watching {self.url_path} for changes in {self.url_filename}')
        self.configurator = ServersConfigurator(
            self.url_path, self.url_filename)

        self.observer = Observer()
        self.observer.schedule(
            self.configurator, self.url_path, recursive=False)
        self.observer.start()

    def __del__(self):
        """
        Destroy the observer
        """
        self.observer.stop()
        self.observer.join()

    def get_client(self, username: str) -> OutlineVPN:
        """
        Get Outline VPN client for a given username
        :param username:
        :return: OutlineVPN client

        If user belongs to a server return OutlineVPN client for that server,
        otherwise return the client with the least amount of users
        """
        if len(self.configurator.servers) == 0:
            self.logger.error('No VPN servers found')
            raise Exception('No VPN servers found')

        vpns: list[OutlineVPN] = []
        for server in self.configurator.servers:
            vpn = OutlineVPN(api_url=server)
            try:
                for key in vpn.get_keys():
                    if key.name == username:
                        return vpn
            except Exception as e:
                self.logger.error(
                    f'Could not connect to {server} with error: {e}')
                continue

            vpns.append(vpn)

        return sorted(vpns, key=lambda vpn: len(vpn.get_keys()))[0]

    def generate_url(self, username: str):
        """
        Generate VPN invite URL for a given username
        :param username:
        :return: new URL if user doesn't have a VPN, 
        or the existing URL if user has been assigned one already
        """
        client = self.get_client(username)
        if client is not None:
            for key in client.get_keys():
                if key.name == username:
                    return VPN_URL_PREFIX + urllib.parse.quote(key.access_url)

            if len(client.get_keys()) >= self.max_users:
                raise UserLimitReached

            new_key = client.create_key()
            client.rename_key(new_key.key_id, username)
            client.add_data_limit(new_key.key_id, self.bytes_limit)
            return VPN_URL_PREFIX + urllib.parse.quote(new_key.access_url)
        else:
            self.logger.error(f'Could not find a client for {username}')


class VPNBot:

    def __init__(self, chat_id: str, dev_chat_id: str, vpn_urls: str, limit: int = 8, max_users: int = 100):
        self.logger = logging.getLogger(__name__)
        self.chat_id = chat_id
        self.dev_chat_id = dev_chat_id
        self.limit = limit
        self.provider = VPNProvider(vpn_urls, max_users=max_users, bytes_limit=MB_to_bytes(GB_to_MB(limit)))

    def start(self, update: Update, context: CallbackContext):
        user = update.effective_user
        try:
            chat = context.bot.get_chat(chat_id=self.chat_id)
            member = context.bot.getChatMember(
                chat_id=self.chat_id, user_id=user.id)
        except Exception as e:
            self.logger.error(f'Error getting chat info: {e}')
            context.bot.sendMessage(
                chat_id=user.id, text='Не удалось получить доступ к каналу; попробуйте через несколько секунд')
            return

        if not self._is_member(member):
            self.logger.info('User does not belong to the group')
            context.bot.sendMessage(chat_id=update.effective_chat.id,
                                    text='You do not belong to the group. Ask You Know Who to join.')
            return

        self.logger.info(f'User belongs to the {chat.title}')

        vpn_name = self._create_name(user=user)
        try:
            url = self.provider.generate_url(vpn_name)
        except UserLimitReached:
            self.logger.error(f'User limit reached for {vpn_name}')
            context.bot.sendMessage(chat_id=update.effective_chat.id,
                                    text='Превышен лимит пользователей в прокси; попробуйте позже.')
            context.bot.sendMessage(chat_id=self.dev_chat_id,
                                    text='No more available VPN resources')
            return

        if url is not None:
            self.logger.info(url)
            context.bot.sendMessage(
                chat_id=user.id, text=f'''
                {url} 
                Перейдите по ссылке для дальнейших инструкций. Если вы хотите оставить отзыв, используйте команду /feedback''', protect_content=True)
        else:
            context.bot.sendMessage(
                chat_id=user.id, text=f'Невозможно создать VPN, попробуйте позднее. Если вы хотите оставить отзыв, используйте команду /feedback', protect_content=True)

    def start_feedback(self, update: Update, context: CallbackContext):
        try:
            member = context.bot.getChatMember(
                chat_id=self.chat_id, user_id=update.effective_user.id)
        except Exception as e:
            self.logger.error(f'Error getting chat info: {e}')
            context.bot.sendMessage(
                chat_id=update.effective_user.id.id, text='Не удалось получить доступ к каналу; попробуйте через несколько секунд')
            return

        if not self._is_member(member):
            self.logger.info('User does not belong to the group')
            context.bot.sendMessage(chat_id=update.effective_chat.id,
                                    text='You do not belong to the group. Ask You Know Who to join.')
            return

        update.message.reply_text(
            'Пожалуйста оставьте ваш отзыв или используйте /cancel для отмены',
        )
        return 0

    def feedback(self, update: Update, context: CallbackContext):
        user = self._create_name(update.effective_user)
        context.bot.sendMessage(
            chat_id=self.dev_chat_id, text=f'User {user} left feedback {update.message.text}')

        if self._clean_text(update.message.text):
            update.message.reply_text('Спасибо за ваш отзыв!')
        else:
            update.message.reply_text('Usage: /feedback')

        return ConversationHandler.END

    def cancel(self, update: Update, context: CallbackContext) -> int:
        """Cancels and ends the conversation."""
        user = update.message.from_user
        name = self._create_name(user=user)
        self.logger.debug(f"User {name} canceled the conversation.")
        update.message.reply_text(
            'Thank you for the feedback', reply_markup=ReplyKeyboardRemove()
        )

        return ConversationHandler.END

    def stats(self, update: Update, context: CallbackContext):
        try:
            member = context.bot.getChatMember(
                chat_id=self.chat_id, user_id=update.effective_user.id)
        except Exception as e:
            self.logger.error(f'Error getting chat info: {e}')
            context.bot.sendMessage(
                chat_id=user.id, text='Не удалось получить доступ к каналу; попробуйте через несколько секунд')
            return

        if not self._is_member(member):
            self.logger.info('User does not belong to the group')
            context.bot.sendMessage(chat_id=update.effective_chat.id,
                                    text='You do not belong to the group. Ask You Know Who to join.')
            return

        user = update.effective_user
        vpn_name = self._create_name(user=user)
        self.logger.info(f'User {vpn_name} requested statistics')
        vpn = self.provider.get_client(vpn_name)
        if vpn is None:
            self.logger.error(
                f'VPN {vpn_name} not found, server url {vpn}')
            update.message.reply_text(
                text='У вас нет активных VPN; Для создания нового используйте /start')
            return

        all_keys = vpn.get_keys()
        user_vpns = [vpn for vpn in all_keys if vpn.name == vpn_name]
        if len(user_vpns) == 1:
            user_vpn: OutlineVPN = user_vpns[0]
            if user_vpn.used_bytes:
                used = bytes_to_MB(user_vpn.used_bytes)
                used_percent = round(used / GB_to_MB(self.limit) * 100, 2)
            else:
                used_percent = 0.0

            used = [vpn.used_bytes for vpn in all_keys if vpn.used_bytes]
            update.message.reply_text(
                f'Вы использовали {used_percent}% трафика от {self.limit} GB.' +
                f' Медианна/Среднестатистическое использование всех пользователей ' +
                f'{bytes_to_MB(np.median(used))}/{bytes_to_MB(np.mean(used))} MB.')
        else:
            update.message.reply_text(
                text='У вас нет активных VPN; Для создания нового используйте /start')

    def error_handler(self, update: object, context: CallbackContext) -> None:
        """Log the error and send a telegram message to notify the developer."""
        # Log the error before we do anything else, so we can see it even if something breaks.
        self.logger.error(msg="Exception while handling an update:",
                          exc_info=context.error)

        # traceback.format_exception returns the usual python message about an exception, but as a
        # list of strings rather than a single string, so we have to join them together.
        tb_list = traceback.format_exception(
            None, context.error, context.error.__traceback__)
        tb_string = ''.join(tb_list)

        # Build the message with some markup and additional information about what happened.
        # You might need to add some logic to deal with messages longer than the 4096 character limit.
        update_str = update.to_dict() if isinstance(update, Update) else str(update)
        message = (
            f'An exception was raised while handling an update\n'
            f'update = {json.dumps(update_str, indent=2, ensure_ascii=False)}'
            '\n\n'
            f'context.chat_data = {context.chat_data}\n\n'
            f'context.user_data = {context.user_data}\n\n'
            f'{tb_string}'
        )

        # Finally, send the message
        self.logger.error(message)
        context.bot.send_message(
            chat_id=update.message.from_user.id, text="Произошла ошибка; попробуйте еще раз")

    def _clean_text(self, text):
        return text.replace('\n', ' ').replace('\r', '').replace('\t', ' ').strip()

    def _create_name(self, user: User):
        return f'{user.first_name}_{user.last_name}_{user.id}'

    def _is_member(self, user: ChatMember) -> bool:
        return user.status != 'left' and user.status != 'banned'
