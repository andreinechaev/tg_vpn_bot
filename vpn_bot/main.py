import logging
import requests
import argparse
import os

from bot.vpn_bot import VPNBot
from telegram.ext import Updater, CommandHandler, MessageHandler, ConversationHandler, Filters


requests.packages.urllib3.disable_warnings()

TOKEN = os.getenv('TELEGRAM_TOKEN')
OUTLINE_VPN_ADDRESS = os.getenv('OUTLINE_VPN_ADDRESS')
VPN_LIMIT_GB = 8

logging.basicConfig(filename='tg_bot.log',
                    filemode='a',
                    format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
                    datefmt='%H:%M:%S',
                    level=logging.INFO)
logger = logging.getLogger(__name__)


def launch():
    argparse.ArgumentParser(description='Outline VPN Telegram Bot')
    parser = argparse.ArgumentParser()
    parser.add_argument('--chat_id', type=int, help='Chat ID', required=True)
    parser.add_argument('--dev_chat_id', type=int,
                        help='Dev Chat ID', required=True)
    parser.add_argument('--limit', type=int,
                        help='Dev Chat ID', default=VPN_LIMIT_GB, required=False)
    args = parser.parse_args()
    bot = VPNBot(chat_id=args.chat_id, dev_chat_id=args.dev_chat_id,
                 vpn_url=OUTLINE_VPN_ADDRESS, limit=args.limit)

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
    dispatcher.add_handler(conv_handler)
    dispatcher.add_error_handler(bot.error_handler)

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    launch()
