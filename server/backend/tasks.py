import os

import pytz
from telebot import types
from django.utils import timezone
from django_q.tasks import schedule, Schedule

from client.call_types import CallTypes
from client.utils import make_inline_button

from .utils import send_message, edit_message_text
from .models import Reservation
from .templates import Messages, Keys


def get_reservation_info(reservation):
    tz = pytz.timezone(reservation.region.timezone)
    datetime = reservation.datetime.astimezone(tz)
    return Messages.RESERVATION_INFO.format(
        id=reservation.id,
        datetime=datetime,
        region=reservation.region.name,
        status=reservation.get_status_display(),
    )


def confirmation_request(reservation_id):
    reservation = Reservation.reservations.get(id=reservation_id)

    keyboard = types.InlineKeyboardMarkup()
    accept_button = make_inline_button(
        text=Keys.REQUEST_CONFIRMATION_ACCEPT,
        CallType=CallTypes.RequestConfirmationAccept,
        reservation_id=reservation_id,
    )
    refuse_button = make_inline_button(
        text=Keys.REQUEST_CONFIRMATION_REFUSE,
        CallType=CallTypes.RequestConfirmationRefuse,
        reservation_id=reservation_id,
    )
    keyboard.add(accept_button)
    keyboard.add(refuse_button)
    check_time = int(os.getenv('CONFIRMATION_REQUEST_CHECK_TIME'))
    text = Messages.REQUEST_CONFIRMATION.format(
        check_time=check_time,
    )
    send_message(reservation.user.chat_id, text,
                 reply_markup=keyboard)
    message_id = send_message(reservation.user.chat_id,
                              get_reservation_info(reservation))

    name = f'confirmation-request-refuse-{reservation_id}'
    func_name = 'backend.tasks.confirmation_request_refuse'
    next_run = timezone.now() + timezone.timedelta(minutes=check_time)
    schedule(func_name, reservation_id, message_id,
             name=name,
             next_run=next_run,
             schedule_type=Schedule.ONCE)


def confirmation_request_refuse(reservation_id, message_id):
    reservation = Reservation.reservations.get(id=reservation_id)
    reservation.status = Reservation.Status.REFUSED
    reservation.save()

    edit_message_text(reservation.user.chat_id,
                      get_reservation_info(reservation),
                      message_id)


def request_after_visiting(reservation_id):
    reservation = Reservation.reservations.get(id=reservation_id)
    keyboard = types.InlineKeyboardMarkup()
    ok_button = make_inline_button(
        text=Keys.REQUEST_AFTER_VISITING_OK,
        CallType=CallTypes.RequestAfterVisiting,
        status=Reservation.Status.OK,
        reservation_id=reservation_id,
    )
    receiving_button = make_inline_button(
        text=Keys.REQUEST_AFTER_VISITING_RECEIVING,
        CallType=CallTypes.RequestAfterVisiting,
        status=Reservation.Status.RECEIVING,
        reservation_id=reservation_id,
    )
    in_queue_button = make_inline_button(
        text=Keys.REQUEST_AFTER_VISITING_IN_QUEUE,
        CallType=CallTypes.RequestAfterVisiting,
        status=Reservation.Status.IN_QUEUE,
        reservation_id=reservation_id,
    )
    keyboard.add(ok_button)
    keyboard.add(receiving_button)
    keyboard.add(in_queue_button)
    send_message(reservation.user.chat_id, Messages.REQUEST_AFTER_VISITING,
                 reply_markup=keyboard)
