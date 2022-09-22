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

from backend.models import BotUser, Reservation, Region
from backend.templates import Messages, Keys, Smiles


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
    if reservation.status != Reservation.Status.CONFIRMED:
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


def admin_callback_query_handler(bot: TeleBot, call):
    call_type = CallTypes.parse_data(call.data)
    region_id = call_type.region_id
    region = Region.regions.get(id=region_id)
    chat_id = call.message.chat.id

    region_reservations_button = utils.make_inline_button(
        text=Keys.REGION_RESERVATIONS,
        CallType=CallTypes.RegionReservations,
        region_id=region.id,
        page=1,
    )
    region_edit_working_time_button = utils.make_inline_button(
        text=Keys.REGION_EDIT_WORKING_TIME,
        CallType=CallTypes.RegionEditWorkingTime,
        region_id=region.id,
    )
    region_edit_day_limit_button = utils.make_inline_button(
        text=Keys.REGION_EDIT_DAY_LIMIT,
        CallType=CallTypes.RegionEditDayLimit,
        region_id=region.id,
    )
    region_edit_period_button = utils.make_inline_button(
        text=Keys.REGION_EDIT_PERIOD,
        CallType=CallTypes.RegionEditPeriod,
        region_id=region.id,
    )
    back_button = utils.make_inline_button(
        text=Keys.BACK,
        CallType=CallTypes.Menu,
    )
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(region_reservations_button)
    keyboard.add(region_edit_working_time_button)
    keyboard.add(region_edit_day_limit_button)
    keyboard.add(region_edit_period_button)
    keyboard.add(back_button)
    text = Messages.REGION_INFO.format(
        name=region.name,
        working_time_from=region.working_time_from.strftime('%H:%M'),
        working_time_to=region.working_time_to.strftime('%H:%M'),
        period=region.period,
        day_limit=region.day_limit,
    )
    bot.edit_message_text(
        text=text,
        chat_id=chat_id,
        reply_markup=keyboard,
        message_id=call.message.id,
    )


def region_edit_working_time_callback_query_handler(bot: TeleBot, call):
    chat_id = call.message.chat.id
    user = BotUser.objects.get(chat_id=chat_id)
    call_type = CallTypes.parse_data(call.data)
    region_id = call_type.region_id
    region = Region.regions.get(id=region_id)
    user.region = region
    user.bot_state = BotUser.State.INPUT_WOKRING_TIME
    user.save()
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(Keys.CANCEL)
    bot.send_message(chat_id, Messages.INPUT_WORKING_TIME,
                     reply_markup=keyboard)


def region_edit_working_time_message_handler(bot: TeleBot, message):
    chat_id = message.chat.id
    user = BotUser.objects.get(chat_id=chat_id)
    region = user.region
    try:
        t1, t2 = message.text.split()
        h1, m1 = map(int, t1.split(':'))
        h2, m2 = map(int, t2.split(':'))
        working_time_from = datetime.time(h1, m1)
        working_time_to = datetime.time(h2, m2)
        if working_time_from > working_time_to:
            raise

        region.working_time_from = working_time_from
        region.working_time_to = working_time_to
        region.save()
        user.bot_state = BotUser.State.NOTHING
        user.save()
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.add(Keys.MENU)
        bot.send_message(chat_id, Messages.SAVED,
                         reply_markup=keyboard)
    except Exception:
        traceback.print_exc()
        bot.send_message(chat_id, Messages.INCORRECT_FORMAT)


def region_edit_day_limit_callback_query_handler(bot: TeleBot, call):
    chat_id = call.message.chat.id
    user = BotUser.objects.get(chat_id=chat_id)
    call_type = CallTypes.parse_data(call.data)
    region_id = call_type.region_id
    region = Region.regions.get(id=region_id)
    user.region = region
    user.bot_state = BotUser.State.INPUT_DAY_LIMIT
    user.save()
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(Keys.CANCEL)
    bot.send_message(chat_id, Messages.INPUT_NUMBER,
                     reply_markup=keyboard)


def region_edit_day_limit_message_handler(bot: TeleBot, message):
    chat_id = message.chat.id
    user = BotUser.objects.get(chat_id=chat_id)
    region = user.region
    try:
        day_limit = int(message.text)
        region.day_limit = day_limit
        region.save()
        user.bot_state = BotUser.State.NOTHING
        user.save()
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.add(Keys.MENU)
        bot.send_message(chat_id, Messages.SAVED,
                         reply_markup=keyboard)
    except Exception:
        bot.send_message(chat_id, Messages.INCORRECT_FORMAT)


def region_edit_period_callback_query_handler(bot: TeleBot, call):
    chat_id = call.message.chat.id
    user = BotUser.objects.get(chat_id=chat_id)
    call_type = CallTypes.parse_data(call.data)
    region_id = call_type.region_id
    region = Region.regions.get(id=region_id)
    user.region = region
    user.bot_state = BotUser.State.INPUT_PERIOD
    user.save()
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(Keys.CANCEL)
    bot.send_message(chat_id, Messages.INPUT_NUMBER,
                     reply_markup=keyboard)


def region_edit_period_message_handler(bot: TeleBot, message):
    chat_id = message.chat.id
    user = BotUser.objects.get(chat_id=chat_id)
    region = user.region
    try:
        period = int(message.text)
        region.period = period
        region.save()
        user.bot_state = BotUser.State.NOTHING
        user.save()
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.add(Keys.MENU)
        bot.send_message(chat_id, Messages.SAVED,
                         reply_markup=keyboard)
    except Exception:
        bot.send_message(chat_id, Messages.INCORRECT_FORMAT)


def region_reservations_callback_query_handler(bot: TeleBot, call):
    chat_id = call.message.chat.id
    call_type = CallTypes.parse_data(call.data)
    region_id = call_type.region_id
    region = Region.regions.get(id=region_id)
    page_number = call_type.page
    text = utils.text_to_fat(Keys.REGION_RESERVATIONS)
    text += '\n\n'
    dt_range = utils.get_datetime_range_for_day(timezone.now())
    reservations = region.reservations(manager='actual').filter(
        datetime__range=dt_range
    )
    paginator = Paginator(reservations, 5)
    page = paginator.get_page(page_number)
    keyboard = utils.make_page_keyboard(page, CallTypes.RegionReservations)
    for index, reservation in enumerate(page, 1):
        reservation_info = Messages.REGION_RESERVATION_INFO.format(
            id=reservation.id,
            datetime=reservation.get_datetime(),
            status=reservation.get_status_display(),
        )
        keyboard.add(utils.make_inline_button(str(index), CallTypes.Nothing))
        come_key = Keys.COME
        if reservation.status == Reservation.Status.CONFIRMED:
            come_key = f'{Smiles.YES} ' + come_key

        not_come_key = Keys.NOT_COME
        if reservation.status == Reservation.Status.DID_NOT_COME:
            not_come_key = f'{Smiles.NO} ' + not_come_key

        keyboard.add(utils.make_inline_button(
            text=come_key,
            CallType=CallTypes.ReservationStatusChange,
            reservation_id=reservation.id,
            status=Reservation.Status.CONFIRMED
        ), utils.make_inline_button(
            text=not_come_key,
            CallType=CallTypes.ReservationStatusChange,
            reservation_id=reservation.id,
            status=Reservation.Status.DID_NOT_COME
        ))
        text += reservation_info + '\n\n'

    back_button = utils.make_inline_button(
        text=Keys.BACK,
        CallType=CallTypes.Menu,
    )
    keyboard.add(back_button)
    bot.edit_message_text(
        chat_id=chat_id,
        text=text,
        message_id=call.message.id,
        reply_markup=keyboard,
    )


def reservation_status_change_callback_query_handler(bot: TeleBot, call):
    call_type = CallTypes.parse_data(call.data)
    reservation_id = call_type.reservation_id
    reservation = Reservation.reservations.get(id=reservation_id)
    status = call_type.status
    reservation.status = status
    reservation.save()
    call_type = CallTypes.RegionReservations(region_id=reservation.region.id,
                                             page=1)
    call.data = CallTypes.make_data(call_type)
    region_reservations_callback_query_handler(bot, call)


def referal_program_callback_query_handler(bot: TeleBot, call):
    chat_id = call.message.chat.id
    referals_button = utils.make_inline_button(
        text=Keys.REFERALS,
        CallType=CallTypes.Referals,
    )
    back_button = utils.make_inline_button(
        text=Keys.BACK,
        CallType=CallTypes.Menu,
    )
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(referals_button)
    keyboard.add(back_button)
    referal_link = f'https://t.me/{bot.get_me().username}?start={chat_id}'
    referal_link = utils.text_to_code(referal_link)
    bot.edit_message_text(
        chat_id=chat_id,
        text=Messages.REFERAL_PROGRAM.format(referal_link=referal_link),
        message_id=call.message.id,
        reply_markup=keyboard,
    )


def referals_callback_query_handler(bot: TeleBot, call):
    chat_id = call.message.chat.id
    user = BotUser.objects.get(chat_id=chat_id)
    text = utils.text_to_fat(Keys.REFERALS)
    text += '\n\n'
    for index, referal in enumerate(user.referals.all(), 1):
        text += f'<b>{index}.</b> <code>{referal.chat_id}</code>\n'

    back_button = utils.make_inline_button(
        text=Keys.BACK,
        CallType=CallTypes.ReferalProgram,
    )
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(back_button)
    bot.edit_message_text(
        chat_id=chat_id,
        text=text,
        message_id=call.message.id,
        reply_markup=keyboard,
    )
