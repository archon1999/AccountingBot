import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

import datetime

from django.utils import timezone
from backend.models import Reservation

import pytz

tz = pytz.timezone('Etc/GMT-3')

dt = datetime.datetime.now()
dt = dt.replace(tzinfo=tz)
print(dt)

for tz in pytz.all_timezones:
    print(tz)
