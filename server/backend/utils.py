import os

from telebot import TeleBot


def send_message(chat_id, text, reply_markup=None):
    bot = TeleBot(token=os.getenv('BOT_TOKEN'), parse_mode='HTML')
    return bot.send_message(chat_id, text,
                            reply_markup=reply_markup).id


def edit_message_text(chat_id, text, message_id, reply_markup=None):
    bot = TeleBot(token=os.getenv('BOT_TOKEN'), parse_mode='HTML')
    bot.edit_message_text(
        text=text,
        chat_id=chat_id,
        message_id=message_id,
        reply_markup=reply_markup,
    )
