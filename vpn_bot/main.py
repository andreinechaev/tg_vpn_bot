import logging
import requests
import argparse
import os

from bot.vpn_bot import VPNBot
from telegram.ext import Updater, CommandHandler, MessageHandler, ConversationHandler, Filters, ChatMemberHandler


requests.packages.urllib3.disable_warnings()

TOKEN = os.getenv('TELEGRAM_TOKEN')
VPN_LIMIT_GB = 10


def launch():
    argparse.ArgumentParser(description='Outline VPN Telegram Bot')
    parser = argparse.ArgumentParser()
    parser.add_argument('--chat_id', type=int, help='Chat ID', required=True)
    parser.add_argument('--dev_chat_id', type=int,
                        help='Dev Chat ID', required=True)
    parser.add_argument('--servers', type=str,
                        help='absolute path to JSON File with the servers list', required=True)
    parser.add_argument('--log_file', type=str, default='/var/log/tg_bot.log',
                        help='absolute path to JSON File with the servers list', required=False)
    parser.add_argument('--log_level', type=int, default=logging.INFO,
                        help='absolute path to JSON File with the servers list', required=False)
    args = parser.parse_args()

    logging.basicConfig(filename=args.log_file,
                        filemode='a',
                        format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
                        datefmt='%H:%M:%S',
                        level=args.log_level)

    bot = VPNBot(chat_id=args.chat_id,
                 dev_chat_id=args.dev_chat_id, config=args.servers)

    updater = Updater(token=TOKEN, use_context=True, request_kwargs={
        'read_timeout': 7, 'connect_timeout': 9})
    dispatcher = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('feedback', bot.start_feedback)],
        states={
            0: [MessageHandler(Filters.text & ~Filters.command, bot.feedback)],
        },
        fallbacks=[CommandHandler('cancel', bot.cancel)],
    )

    dispatcher.add_handler(CommandHandler('start', bot.start))
    dispatcher.add_handler(CommandHandler('stats', bot.stats))
    dispatcher.add_handler(ChatMemberHandler(
        bot.chat_member_update, ChatMemberHandler.MY_CHAT_MEMBER))
    dispatcher.add_handler(conv_handler)
    dispatcher.add_error_handler(bot.error_handler)

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    launch()
