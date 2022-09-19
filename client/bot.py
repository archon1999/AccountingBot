from telebot import TeleBot

import config
import commands
import handlers
from call_types import CallTypes

from backend.models import BotUser
from backend.templates import Keys

message_handlers = {
    '/start': commands.start_command_handler,
    '/menu': commands.menu_command_handler,
}

key_handlers = {
    Keys.MENU: commands.menu_command_handler,
    Keys.SELECT_ANOTHER_DATE: handlers.select_another_date_message_handler,
    Keys.CANCEL: commands.cancel_message_handler,
}

state_handlers = {
    BotUser.State.RESERVATION_TIME: handlers.reservation_time_message_handler,
}

bot = TeleBot(
    token=config.TOKEN,
    num_threads=3,
    parse_mode='HTML',
)


@bot.message_handler()
def message_handler(message):
    if message.chat.type != 'private':
        return

    chat_id = message.chat.id
    if not BotUser.objects.filter(chat_id=chat_id).exists():
        commands.start_command_handler(bot, message)
        return

    user = BotUser.objects.get(chat_id=chat_id)
    if user.bot_state:
        if message.text not in [Keys.CANCEL, Keys.SELECT_ANOTHER_DATE]:        
            state_handlers[user.bot_state](bot, message)
            return

    for text, handler in message_handlers.items():
        if message.text.startswith(text):
            handler(bot, message)
            break

    for key, handler in key_handlers.items():
        if message.text == key:
            handler(bot, message)
            break


callback_query_handlers = {
    CallTypes.Menu: commands.menu_callback_query_handler,
    CallTypes.SelectRegion: commands.select_region_callback_query_handler,
    CallTypes.Region: commands.region_callback_query_handler,
    CallTypes.Reservation: handlers.reservation_callback_query_handler,
    CallTypes.ReservationForAnother:
        handlers.reservation_for_another_time_callback_query_handler,
    CallTypes.ReservationForDay:
        handlers.reservation_for_day_callback_query_handler,
    CallTypes.MyReservations: handlers.my_reservations_callback_query_handler,
    CallTypes.RequestConfirmationAccept:
        handlers.request_confirmation_accept_callback_query_handler,
    CallTypes.RequestConfirmationRefuse:
        handlers.request_confirmation_refuse_callback_query_handler,
    CallTypes.RequestAfterVisiting:
        handlers.request_after_visting_callback_query_handler,
}


@bot.callback_query_handler(func=lambda call: True)
def callback_query_handler(call):
    call_type = CallTypes.parse_data(call.data)
    chat_id = call.message.chat.id
    user = BotUser.objects.get(chat_id=chat_id)
    if user.bot_state != BotUser.State.NOTHING:
        ok = False
        if user.bot_state == BotUser.State.RESERVATION_TIME:
            if call_type.__class__ == CallTypes.ReservationForDay:
                ok = True

        if not ok:
            return

    for CallType, handler in callback_query_handlers.items():
        if CallType == call_type.__class__:
            handler(bot, call)
            break


if __name__ == "__main__":
    import locale
    locale.setlocale(locale.LC_ALL, 'ru_RU')
    print(bot.get_me())
    # bot.polling()
    bot.infinity_polling()
