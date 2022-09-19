import os

from django_q.tasks import schedule, Schedule
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

from backend.models import Template, Reservation
from backend.templates import Messages
from backend.utils import send_message


def get_confirmation_request_time_list(reservation_datetime):
    result = []
    for i in range(1, 10):
        key_name = f'CONFIRMATION_REQUEST_TIME_{i}'
        if (value := os.getenv(key_name, None)) is None:
            break

        dt = reservation_datetime - timezone.timedelta(hours=float(value))
        if dt >= timezone.now():
            result.append(dt)

    return result


@receiver(post_save, sender=Reservation)
def reservation_post_save_handler(instance, **kwargs):
    if instance.status == Reservation.Status.RESERVED:
        dt_list = get_confirmation_request_time_list(instance.datetime)
        for index, dt in enumerate(dt_list, 1):
            func_name = 'backend.tasks.confirmation_request'
            name = f'confirmation-request-{instance.id}-{index}'
            schedule(func_name, instance.id,
                     name=name,
                     schedule_type=Schedule.ONCE,
                     next_run=dt)

        request_after_visiting_time = os.getenv('REQUEST_AFTER_VISITING_TIME')
        dt = instance.datetime + timezone.timedelta(
            minutes=int(request_after_visiting_time)
        )
        func_name = 'backend.tasks.request_after_visiting'
        name = f'request-after-visiting-{instance.id}'
        schedule(func_name, instance.id,
                 name=name,
                 next_run=dt,
                 schedule_type=Schedule.ONCE)

    if instance.status == Reservation.Status.REFUSED:
        name = f'confirmation-request-{instance.id}'
        Schedule.objects.filter(name__startswith=name).delete()
        name = f'request-after-visiting-{instance.id}'
        Schedule.objects.filter(name=name).delete()
        send_message(instance.user.chat_id, Messages.RESERVATION_REFUSED)


def generate_code():
    code_text = str()
    code_text += 'from backend.models import Template\n'
    code_text += '\n\nclass Messages():\n'
    for message in Template.messages.all():
        code_text += f'    {message.title} = Template.messages.get(id={message.id}).gettext()\n'

    code_text += '\n\nclass Keys():\n'
    for key in Template.keys.all():
        code_text += f'    {key.title} = Template.keys.get(id={key.id}).gettext()\n'

    code_text += '\n\nclass Smiles():\n'
    for smile in Template.smiles.all():
        code_text += f'    {smile.title} = Template.smiles.get(id={smile.id}).gettext()\n'

    return code_text


@receiver(post_save, sender=Template)
def template_post_save_handler(instance, **kwargs):
    template_file = 'backend/templates.py'
    with open(template_file, 'w') as file:
        file.write(generate_code())


@receiver(post_delete, sender=Template)
def template_post_delete_handler(instance, **kwargs):
    template_file = 'backend/templates.py'
    with open(template_file, 'w') as file:
        file.write(generate_code())
