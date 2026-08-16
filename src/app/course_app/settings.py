"""Settings for the minimal, repository-based Django application."""

from __future__ import annotations

import os
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = APP_DIR.parent
REPOSITORY_ROOT = SRC_DIR.parent

DATA_DIR = SRC_DIR / "data"
ASSET_DIR = DATA_DIR / "assets"
STYLE_DIR = SRC_DIR / "styles"
ANSWER_DIR = REPOSITORY_ROOT / "student_answer"
SOLUTION_DIR = REPOSITORY_ROOT / "correct_solution"
STUDENT_CONFIG = REPOSITORY_ROOT / "student.yaml"

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY", "local-course-app-key-not-for-shared-deployment"
)
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() in {"1", "true", "yes"}
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "[::1]"]

INSTALLED_APPS = [
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "assessments",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "course_app.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
                "assessments.context.course_context",
            ],
        },
    }
]

WSGI_APPLICATION = "course_app.wsgi.application"
ASGI_APPLICATION = "course_app.asgi.application"

# The app stores answers in JSON files, so it needs no database.
DATABASES = {}

# Cookie-backed messages preserve POST/redirect/GET without requiring sessions
# or a database.
MESSAGE_STORAGE = "django.contrib.messages.storage.cookie.CookieStorage"

# Local Git integration. The template remote is rejected so students do not
# accidentally try to submit to the instructor's template repository.
GIT_BRANCH = os.environ.get("BRANCHWORK_GIT_BRANCH", "main")
GIT_TEMPLATE_REMOTE = os.environ.get(
    "BRANCHWORK_TEMPLATE_REMOTE",
    "https://github.com/JCatwood/Branchwork_student.git",
)
GIT_TIMEOUT_SECONDS = int(os.environ.get("BRANCHWORK_GIT_TIMEOUT", "45"))

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Chicago"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [STYLE_DIR, ("assessment_assets", ASSET_DIR)]
STATIC_ROOT = APP_DIR / "staticfiles"
