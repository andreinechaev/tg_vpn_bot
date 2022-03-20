import traceback
import json
import logging
import urllib.parse

from outline.outline_vpn import OutlineVPN
from telegram import ChatMember, Update, User, ReplyKeyboardRemove
from telegram.ext import ConversationHandler, CallbackContext

VPN_URL_PREFIX = 'https://s3.amazonaws.com/outline-vpn/invite.html#'

def bytes_to_MB(bytes):
    return round(bytes / 1024 / 1024, 2)


def GB_to_MB(GB):
    return round(GB * 1024, 2)


class VPNBot:

    def __init__(self, chat_id: str, dev_chat_id: str, vpn_url: str, limit: int = 8):
        self.chat_id = chat_id
        self.dev_chat_id = dev_chat_id
        self.vpn_url = vpn_url
        self.limit = limit
        self.client = OutlineVPN(api_url=vpn_url)
        self.logger = logging.getLogger(__name__)

    def start(self, update: Update, context: CallbackContext):
        try:
            chat = context.bot.get_chat(chat_id=self.chat_id)
            member = chat.get_member(user_id=update.message.from_user.id)
        except Exception as e:
            self.logger.error(f'Error getting chat info: {e}')
            context.bot.sendMessage(
                chat_id=user.id, text='Не удалось получить доступ к каналу; попробуйте через несколько секунд')
            return

        if member:
            self.logger.info(f'User belongs to the {chat.title}')
            user = update.effective_user
            vpn_name = self._create_name(user=user)
            vpns = self._get_vpns()
            if vpn_name not in [vpn.name for vpn in vpns]:
                print(f'Creating new VPN for {vpn_name}')
                url = self._generate_vpn_url(vpn_name)
                self.logger.info(url)
                context.bot.sendMessage(
                    chat_id=user.id, text=f'''
                    {url} 
                    Перейдите по ссылке для дальнейших инструкций. Если вы хотите оставить отзыв, используйте команду /feedback''', protect_content=True)
            else:
                vpns = [vpn for vpn in vpns if vpn.name == vpn_name]
                if len(vpns) == 1:
                    self.logger.info(f'User {vpn_name} already has a VPN')
                    url = self._get_vpn_url(vpns[0])
                    self.logger.info(url)
                    context.bot.sendMessage(
                        chat_id=user.id, text=f'''
                    {url}
                    Перейдите по ссылке для дальнейших инструкций. Если вы хотите оставить отзыв, используйте команду /feedback''', protect_content=True)
                else:
                    self.logger.error(f'User {vpn_name} has more than one VPN')
        else:
            self.logger.info('User does not belong to the group')
            context.bot.sendMessage(chat_id=update.effective_chat.id,
                                    text='You do not belong to the group. Ask You Know Who to join.')

    def clean_text(self, text):
        return text.replace('\n', ' ').replace('\r', '').replace('\t', ' ').strip()

    def start_feedback(self, update: Update, context: CallbackContext):
        update.message.reply_text(
            'Пожалуйста оставьте ваш отзыв или используйте /cancel для отмены',
        )
        return 0

    def feedback(self, update: Update, context: CallbackContext):
        user = self._create_name(update.effective_user)
        context.bot.sendMessage(
            chat_id=self.dev_chat_id, text=f'User {user} left feedback {update.message.text}')

        if self.clean_text(update.message.text):
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
        user = update.effective_user
        vpn_name = self._create_namereate_name(user=user)
        self.logger.info(f'User {vpn_name} requested statistics')
        vpns = self._get_vpns()
        user_vpns = [vpn for vpn in vpns if vpn.name == vpn_name]
        if len(user_vpns) == 1:
            user_vpn: OutlineVPN = user_vpns[0]
            used = bytes_to_MB(user_vpn.used_bytes)
            used_percent = round(used / GB_to_MB(self.limit) * 100, 2)
            update.message.reply_text(
                f'Вы использовали {used_percent}% трафика')
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

    def _get_vpns(self):
        return self.client.get_keys()

    def _generate_vpn_url(self, name):
        new_key = self.client.create_key()
        self.client.rename_key(new_key.key_id, name)
        return VPN_URL_PREFIX + urllib.parse.quote(new_key.access_url)

    def _get_vpn_url(self, vpn: OutlineVPN):
        return VPN_URL_PREFIX + urllib.parse.quote(vpn.access_url)

    def _create_name(self, user: User):
        return f'{user.first_name}_{user.last_name}_{user.id}'

    def _is_member(self, user: ChatMember) -> bool:
        return user.status != 'left' and user.status != 'banned'
