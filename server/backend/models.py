import pytz
from django.db import models
from django.contrib import admin
from ckeditor.fields import RichTextField
from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag


class Region(models.Model):
    regions = models.Manager()
    name = models.CharField(
        max_length=255,
        verbose_name='Название',
    )
    address = RichTextField(verbose_name='Адрес')
    timezone = models.CharField(max_length=255)
    working_time_from = models.TimeField(verbose_name='Время работы, от')
    working_time_to = models.TimeField(verbose_name='Время работы, до')
    day_limit = models.PositiveIntegerField(
        verbose_name='Ограничение на количество людей'
    )
    period = models.PositiveIntegerField(verbose_name='Период(в минутах)')

    class Meta:
        verbose_name = 'Регион'
        verbose_name_plural = 'Регионы'

    def __str__(self):
        return self.name


class BotUser(models.Model):
    class State(models.IntegerChoices):
        NOTHING = 0
        RESERVATION_TIME = 1
        INPUT_WOKRING_TIME = 2
        INPUT_DAY_LIMIT = 3
        INPUT_PERIOD = 4

    region = models.ForeignKey(
        verbose_name='Регион',
        to=Region,
        on_delete=models.CASCADE,
        related_name='users',
        null=True,
        blank=True,
    )
    chat_id = models.CharField(unique=True, max_length=255)
    username = models.CharField(max_length=255,
                                null=True,
                                blank=True)
    first_name = models.CharField(max_length=255,
                                  null=True,
                                  blank=True)
    last_name = models.CharField(max_length=255,
                                 null=True,
                                 blank=True)
    from_user = models.ForeignKey(
        to='self',
        on_delete=models.CASCADE,
        related_name='referals',
        null=True,
        blank=True,
    )
    bot_state = models.IntegerField(default=State.NOTHING)
    temp_date = models.DateField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.chat_id

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'


class RegionAdmin(models.Model):
    region = models.ForeignKey(
        to=Region,
        on_delete=models.CASCADE,
        related_name='admins',
    )
    user = models.ForeignKey(
        to=BotUser,
        on_delete=models.CASCADE,
        related_name='region_admins',
    )


class ActualManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().exclude(status=0)


class Reservation(models.Model):
    class Status(models.IntegerChoices):
        REFUSED = 0, 'Отказано'
        RESERVED = 1, 'Зарезирвировано'
        IN_QUEUE = 2, 'В очереди'
        RECEIVING = 3, 'На приеме'
        DID_NOT_COME = 4, 'Не пришел'
        OK = 5, 'Все ок'
        CONFIRMED = 6, 'Подтвержден'

    reservations = models.Manager()
    actual = ActualManager()
    region = models.ForeignKey(
        verbose_name='Регион',
        to=Region,
        on_delete=models.CASCADE,
        related_name='reservations',
    )
    user = models.ForeignKey(
        verbose_name='Пользователь',
        to=BotUser,
        on_delete=models.CASCADE,
        related_name='reservations',
    )
    datetime = models.DateTimeField(
        verbose_name='Дата и время'
    )
    status = models.IntegerField(
        verbose_name='Статус',
        choices=Status.choices,
        default=Status.RESERVED,
    )

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Заявка'
        verbose_name_plural = 'Заявки'
        ordering = ['datetime']

    @admin.display(description='Дата и время')
    def get_datetime(self):
        tz = pytz.timezone(self.region.timezone)
        return self.datetime.astimezone(tz).strftime('%d/%m/%Y %H:%M:%S')


def filter_tag(tag: Tag, ol_number=None):
    if isinstance(tag, NavigableString):
        text = tag
        text = text.replace('<', '&#60;')
        text = text.replace('>', '&#62;')
        return text

    html = str()
    li_number = 0
    for child_tag in tag:
        if tag.name == 'ol':
            if child_tag.name == 'li':
                li_number += 1
        else:
            li_number = None

        html += filter_tag(child_tag, li_number)

    format_tags = ['strong', 'em', 'pre', 'b', 'u', 'i', 'code']
    if tag.name in format_tags:
        return f'<{tag.name}>{html}</{tag.name}>'

    if tag.name == 'a':
        return f"""<a href="{tag.get("href")}">{tag.text}</a>"""

    if tag.name == 'li':
        if ol_number:
            return f'{ol_number}. {html}'
        return f'•  {html}'

    if tag.name == 'br':
        html += '\n'

    if tag.name == 'span':
        styles = tag.get_attribute_list('style')
        if 'text-decoration: underline;' in styles:
            return f'<u>{html}</u>'

    if tag.name == 'ol' or tag.name == 'ul':
        return '\n'.join(map(lambda row: f'   {row}', html.split('\n')))

    return html


def filter_html(html: str):
    soup = BeautifulSoup(html, 'lxml')
    return filter_tag(soup)


class MessageManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(type=Template.Type.MESSAGE)


class KeyManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(type=Template.Type.KEY)


class SmileManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(type=Template.Type.SMILE)


class Template(models.Model):
    class Type(models.IntegerChoices):
        MESSAGE = 1
        KEY = 2
        SMILE = 3

    templates = models.Manager()
    messages = MessageManager()
    keys = KeyManager()
    smiles = SmileManager()

    type = models.IntegerField(choices=Type.choices)
    title = models.CharField(max_length=255)
    body = RichTextField()

    def gettext(self):
        return filter_html(self.body)

    class Meta:
        verbose_name = 'Шаблон'
        verbose_name_plural = 'Шаблоны'

    def __str__(self):
        return self.title
