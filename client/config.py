import os
import sys

import dotenv
import django

dotenv.load_dotenv('../.config')

TOKEN = os.getenv('BOT_TOKEN')

PARENT_PACKAGE = '..'
APP_PACKAGE = 'server'
PARENT_DIR = os.path.dirname(os.path.dirname(__file__))
APP_DIR = os.path.join(PARENT_DIR, APP_PACKAGE)

sys.path.append(APP_DIR)
sys.path.append(PARENT_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()
