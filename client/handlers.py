import datetime
import traceback
import os

import pytz
from telebot import TeleBot, types
from django_q.tasks import Schedule, schedule
from django.utils import timezone
from django.core.paginator import Paginator

import commands
import utils
from call_types import CallTypes

from backend.models import BotUser, Reservation
from backend.templates import Messages, Keys


def get_reservation_info(reservation):
    tz = pytz.timezone(reservation.region.timezone)
    datetime = reservation.datetime.astimezone(tz)
    return Messages.RESERVATION_INFO.format(
        id=reservation.id,
        datetime=datetime,
        region=reservation.region.name,
        status=reservation.get_status_display(),
    )


def reservation_callback_query_handler(bot: TeleBot, call):
    chat_id = call.message.chat.id
    user = BotUser.objects.get(chat_id=chat_id)
    if not utils.check_user_reservation_limit(user):
        reservation_limit_period = int(os.getenv('RESERVATION_LIMIT_PERIOD'))
        reservation_limit_count = int(os.getenv('RESERVATION_LIMIT_COUNT'))
        text = Messages.RESERVATION_LIMIT_EXCEEDED.format(
            reservation_limit_period=reservation_limit_period,
            reservation_limit_count=reservation_limit_count,
        )
        bot.send_message(chat_id, text)
        return

    region = user.region
    for_today_button = utils.make_inline_button(
        text=Keys.FOR_TODAY,
        CallType=CallTypes.ReservationForDay,
        days=0,
    )
    for_tomorrow_button = utils.make_inline_button(
        text=Keys.FOR_TOMORROW,
        CallType=CallTypes.ReservationForDay,
        days=1,
    )
    for_another_time_button = utils.make_inline_button(
        text=Keys.FOR_ANOTHER_TIME,
        CallType=CallTypes.ReservationForAnother,
    )
    back_button = utils.make_inline_button(
        text=Keys.BACK,
        CallType=CallTypes.Menu,
    )
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(for_today_button, for_tomorrow_button)
    keyboard.add(for_another_time_button)
    keyboard.add(back_button)
    text = Messages.RESERVATION.format(
        working_time_from=region.working_time_from.strftime('%H:%M'),
        working_time_to=region.working_time_to.strftime('%H:%M'),
    )
    bot.edit_message_text(
        chat_id=chat_id,
        text=text,
        message_id=call.message.id,
        reply_markup=keyboard,
    )


def reservation_for_another_time_callback_query_handler(bot: TeleBot, call):
    chat_id = call.message.chat.id
    user = BotUser.objects.get(chat_id=chat_id)
    region = user.region
    dt = timezone.now()
    buttons = []
    for days in range(9):
        day_button = utils.make_inline_button(
            text=dt.strftime('%d/%m'),
            CallType=CallTypes.ReservationForDay,
            days=days,
        )
        buttons.append(day_button)
        dt += timezone.timedelta(days=1)

    back_button = utils.make_inline_button(
        text=Keys.BACK,
        CallType=CallTypes.Reservation,
    )
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(*buttons)
    keyboard.add(back_button)
    text = Messages.RESERVATION.format(
        working_time_from=region.working_time_from.strftime('%H:%M'),
        working_time_to=region.working_time_to.strftime('%H:%M'),
    )
    bot.edit_message_text(
        chat_id=chat_id,
        text=text,
        message_id=call.message.id,
        reply_markup=keyboard,
    )


def reservation_for_day_callback_query_handler(bot: TeleBot, call):
    chat_id = call.message.chat.id
    user = BotUser.objects.get(chat_id=chat_id)
    if not utils.check_user_reservation_limit(user):
        reservation_limit_period = int(os.getenv('RESERVATION_LIMIT_PERIOD'))
        reservation_limit_count = int(os.getenv('RESERVATION_LIMIT_COUNT'))
        text = Messages.RESERVATION_LIMIT_EXCEEDED.format(
            reservation_limit_period=reservation_limit_period,
            reservation_limit_count=reservation_limit_count,
        )
        bot.send_message(chat_id, text)
        return

    call_type = CallTypes.parse_data(call.data)
    days = call_type.days
    region = user.region
    datetime = (timezone.now() + timezone.timedelta(days=days))
    if days == 0:
        working_time = region.working_time_to.strftime('%H:%M')
        if datetime.strftime('%H:%M') >= working_time:
            bot.answer_callback_query(
                callback_query_id=call.id,
                text=Messages.CANT_TODAY,
                show_alert=True,
            )
            return

    if region.reservations.filter(
        datetime__range=utils.get_datetime_range_for_day(
            datetime.replace(tzinfo=pytz.timezone(region.timezone))
        )
    ).count() > region.day_limit:
        bot.answer_callback_query(
            callback_query_id=call.id,
            text=Messages.DAY_LIMIT_EXCEEDED,
            show_alert=True,
        )
        return

    date = datetime.date()
    user.temp_date = date
    user.bot_state = BotUser.State.RESERVATION_TIME
    user.save()
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True,
                                         one_time_keyboard=True)
    keyboard.add(Keys.SELECT_ANOTHER_DATE)
    keyboard.add(Keys.CANCEL)
    bot.send_message(chat_id, Messages.RESERVATION_TIME,
                     reply_markup=keyboard)


def reservation_time_message_handler(bot: TeleBot, message):
    chat_id = message.chat.id
    user = BotUser.objects.get(chat_id=chat_id)
    region = user.region
    text = message.text
    date = user.temp_date
    try:
        hour, minute = map(int, text.split(':'))
        time = datetime.time(hour, minute)
        tz = pytz.timezone(region.timezone)
        dt = timezone.datetime(date.year, date.month, date.day,
                               hour, minute).replace(tzinfo=tz)
    except Exception:
        traceback.print_exc()
        bot.send_message(chat_id, Messages.INCORRECT_TIME)
        return

    if time < region.working_time_from or time >= region.working_time_to:
        text = Messages.WORKING_TIME_ERROR.format(
            working_time_from=region.working_time_from.strftime('%H:%M'),
            working_time_to=region.working_time_to.strftime('%H:%M'),
        )
        bot.send_message(chat_id, text)
        return

    min_time = int(os.getenv('RESERVATION_MIN_TIME'))
    if (dt - timezone.now()).total_seconds() // 60 <= min_time:
        text = Messages.RESERVATION_TIME_PAST.format(
            min_time=min_time
        )
        bot.send_message(chat_id, text)
        return

    if not utils.check_user_reservation_limit(user):
        reservation_limit_period = int(os.getenv('RESERVATION_LIMIT_PERIOD'))
        reservation_limit_count = int(os.getenv('RESERVATION_LIMIT_COUNT'))
        text = Messages.RESERVATION_LIMIT_EXCEEDED.format(
            reservation_limit_period=reservation_limit_period,
            reservation_limit_count=reservation_limit_count,
        )
        bot.send_message(chat_id, text)
        return

    if utils.check_reservation_time(region, dt):
        region.reservations.create(
            datetime=dt,
            user=user,
        )
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.add(Keys.MENU)
        bot.send_message(chat_id, Messages.RESERVATION_FINISH,
                         reply_markup=keyboard)
        commands.menu_command_handler(bot, message)
        user.bot_state = BotUser.State.NOTHING
        user.save()
    else:
        bot.send_message(chat_id, Messages.RESERVATION_TIME_OCCUPIED)
        next_unoccupied_time = utils.get_next_unoccupied_time(region, dt)
        text = Messages.NEXT_UNOCCUPIED_TIME.format(
            next_unoccupied_time=next_unoccupied_time.strftime('%d/%m %H:%M'),
        )
        bot.send_message(chat_id, text)


def select_another_date_message_handler(bot: TeleBot, message):
    chat_id = message.chat.id
    user = BotUser.objects.get(chat_id=chat_id)
    user.bot_state = BotUser.State.NOTHING
    user.save()
    region = user.region
    dt = timezone.now()
    buttons = []
    for days in range(9):
        day_button = utils.make_inline_button(
            text=dt.strftime('%d/%m'),
            CallType=CallTypes.ReservationForDay,
            days=days,
        )
        buttons.append(day_button)
        dt += timezone.timedelta(days=1)

    back_button = utils.make_inline_button(
        text=Keys.BACK,
        CallType=CallTypes.Reservation,
    )
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(*buttons)
    keyboard.add(back_button)
    text = Messages.RESERVATION.format(
        working_time_from=region.working_time_from.strftime('%H:%M'),
        working_time_to=region.working_time_to.strftime('%H:%M'),
    )
    bot.send_message(chat_id, text,
                     reply_markup=keyboard)


def my_reservations_callback_query_handler(bot: TeleBot, call):
    chat_id = call.message.chat.id
    user = BotUser.objects.get(chat_id=chat_id)
    if not user.reservations.exists():
        bot.answer_callback_query(
            callback_query_id=call.id,
            text=Messages.MY_RESERVATIONS_EMPTY,
            show_alert=True
        )
        return

    paginator = Paginator(user.reservations.all(), 1)
    call_type = CallTypes.parse_data(call.data)
    page_number = call_type.page
    page = paginator.get_page(page_number)
    back_button = utils.make_inline_button(
        text=Keys.BACK,
        CallType=CallTypes.Menu,
    )
    keyboard = utils.make_page_keyboard(page, CallTypes.MyReservations)
    keyboard.add(back_button)
    text = get_reservation_info(page.object_list[0])
    bot.edit_message_text(
        text=text,
        chat_id=chat_id,
        message_id=call.message.id,
        reply_markup=keyboard,
    )


def request_confirmation_accept_callback_query_handler(bot: TeleBot, call):
    call_type = CallTypes.parse_data(call.data)
    reservation_id = call_type.reservation_id
    reservation = Reservation.reservations.get(id=reservation_id)
    if reservation.status == Reservation.Status.REFUSED:
        return

    chat_id = call.message.chat.id
    bot.delete_message(chat_id, call.message.id)
    bot.send_message(chat_id, Messages.REQUEST_CONFIRMATION_ACCEPT)

    name = f'confirmation-request-refuse-{reservation_id}'
    Schedule.objects.filter(name=name).delete()


def request_confirmation_refuse_callback_query_handler(bot: TeleBot, call):
    chat_id = call.message.chat.id
    call_type = CallTypes.parse_data(call.data)
    reservation_id = call_type.reservation_id
    reservation = Reservation.reservations.get(id=reservation_id)
    if reservation.status == Reservation.Status.REFUSED:
        return

    bot.delete_message(chat_id, call.message.id)
    reservation.status = Reservation.Status.REFUSED
    reservation.save()

    name = f'confirmation-request-refuse-{reservation_id}'
    Schedule.objects.filter(name=name).delete()


def request_after_visting_callback_query_handler(bot: TeleBot, call):
    chat_id = call.message.chat.id
    call_type = CallTypes.parse_data(call.data)
    reservation_id = call_type.reservation_id
    reservation = Reservation.reservations.get(id=reservation_id)
    status = call_type.status
    reservation.status = status
    reservation.save()
    if status != Reservation.Status.OK:
        request_after_visiting_time = os.getenv('REQUEST_AFTER_VISITING_TIME')
        dt = timezone.now() + timezone.timedelta(
            minutes=int(request_after_visiting_time)
        )
        func_name = 'backend.tasks.request_after_visiting'
        name = f'request-after-visiting-{reservation.id}'
        schedule(func_name, reservation.id,
                 name=name,
                 next_run=dt,
                 schedule_type=Schedule.ONCE)

    bot.send_message(chat_id, Messages.REQUEST_CONFIRMATION_ACCEPT)
    bot.delete_message(chat_id, call.message.id)
