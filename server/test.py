import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

import datetime

from django.utils import timezone
from backend.models import Reservation

import pytz

import psutil

for proc in psutil.process_iter():
    if 'Accounting' in proc.cwd():
        if 'bot.py' in proc.cmdline():
            proc.kill()