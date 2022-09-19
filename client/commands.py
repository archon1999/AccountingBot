from telebot import TeleBot, types

from backend.templates import Messages, Keys
from backend.models import BotUser, Region

import utils
from call_types import CallTypes


def update_info(user: BotUser, message):
    user.first_name = message.from_user.first_name
    user.last_name = message.from_user.last_name
    user.username = message.from_user.username
    user.save()


def start_command_handler(bot: TeleBot, message):
    chat_id = message.chat.id
    user, _ = BotUser.objects.get_or_create(chat_id=chat_id)
    update_info(user, message)
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(Keys.MENU)
    bot.send_message(chat_id, Messages.START_COMMAND,
                     reply_markup=keyboard)
    menu_command_handler(bot, message)


def menu_command_handler(bot: TeleBot, message):
    chat_id = message.chat.id
    user = BotUser.objects.get(chat_id=chat_id)
    if user.region:
        obj = message
        obj.message = message
        region_callback_query_handler(bot, obj)
    else:
        keyboard = types.InlineKeyboardMarkup()
        for region in Region.regions.all():
            region_button = utils.make_inline_button(
                text=region.name,
                CallType=CallTypes.Region,
                region_id=region.id,
            )
            keyboard.add(region_button)

        bot.send_message(chat_id, Messages.SELECT_REGION,
                         reply_markup=keyboard)


def menu_callback_query_handler(bot: TeleBot, call):
    chat_id = call.message.chat.id
    user = BotUser.objects.get(chat_id=chat_id)
    if user.region:
        region_callback_query_handler(bot, call)
    else:
        keyboard = types.InlineKeyboardMarkup()
        for region in Region.regions.all():
            region_button = utils.make_inline_button(
                text=region.name,
                CallType=CallTypes.Region,
                region_id=region.id,
            )
            keyboard.add(region_button)

        bot.edit_message_text(
            chat_id=chat_id,
            text=Messages.SELECT_REGION,
            message_id=call.message.id,
            reply_markup=keyboard,
        )


def region_callback_query_handler(bot: TeleBot, call):
    chat_id = call.message.chat.id
    user = BotUser.objects.get(chat_id=chat_id)
    if hasattr(call, 'data'):
        call_type = CallTypes.parse_data(call.data)
        if hasattr(call_type, 'region_id'):
            region_id = call_type.region_id
            region = Region.regions.get(id=region_id)
            user.region = region
            user.save()

    reservation_button = utils.make_inline_button(
        text=Keys.RESERVATION,
        CallType=CallTypes.Reservation,
    )
    select_region_button = utils.make_inline_button(
        text=Keys.SELECT_REGION,
        CallType=CallTypes.SelectRegion,
    )
    my_reservations_button = utils.make_inline_button(
        text=Keys.MY_RESERVATIONS,
        CallType=CallTypes.MyReservations,
        page=1,
    )
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(reservation_button)
    keyboard.add(my_reservations_button)
    keyboard.add(select_region_button)
    if call.message.from_user.is_bot:
        bot.edit_message_text(
            text=utils.text_to_fat(Keys.MENU),
            chat_id=chat_id,
            message_id=call.message.id,
            reply_markup=keyboard,
        )
    else:
        bot.send_message(chat_id, utils.text_to_fat(Keys.MENU),
                         reply_markup=keyboard)


def select_region_callback_query_handler(bot: TeleBot, call):
    chat_id = call.message.chat.id
    user = BotUser.objects.get(chat_id=chat_id)
    user.region = None
    user.save()
    menu_callback_query_handler(bot, call)


def cancel_message_handler(bot: TeleBot, message):
    chat_id = message.chat.id
    user = BotUser.objects.get(chat_id=chat_id)
    user.bot_state = BotUser.State.NOTHING
    user.save()
    menu_command_handler(bot, message)
