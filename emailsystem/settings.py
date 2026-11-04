import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-test-key-for-email-processing-queue-system")

DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")

ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "silk",
    "emailqueue.apps.EmailQueueConfig",
    "orders.apps.OrdersConfig",
]

MIDDLEWARE = [
    "silk.middleware.SilkyMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "emailsystem.urls"

TEMPLATES = []

WSGI_APPLICATION = "emailsystem.wsgi.application"
ASGI_APPLICATION = "emailsystem.asgi.application"

# Database Configuration:
# - SQLite for Section 01 Relational Diagnostic Models & Silk Profiler
# - MongoDB for Section 02 Asynchronous Email Queue (Single persistent source of truth)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Silk Profiler Settings
SILKY_PYTHON_PROFILER = True
SILKY_AUTHENTICATION = False
SILKY_AUTHORISATION = False

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Allow both trailing slash and non-trailing slash requests without redirect errors
APPEND_SLASH = False

# MongoDB Configuration (Using 127.0.0.1 avoids Windows IPv6 localhost resolution delay)
MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "email_queue_db")
MONGO_EMAILS_COLLECTION = os.getenv("MONGO_EMAILS_COLLECTION", "emails")

# Redis Configuration (Using 127.0.0.1 avoids Windows IPv6 localhost resolution delay)
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

# Celery Configuration
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
# We store all state in MongoDB as the source of truth, so disable Redis result backend to prevent result-store reconnection hangs
CELERY_RESULT_BACKEND = None
CELERY_TASK_IGNORE_RESULT = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_EAGER_PROPAGATES = False
