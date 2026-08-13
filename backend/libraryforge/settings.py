from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured


BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent


env = environ.Env(
    DJANGO_DEBUG=(bool, False),
)

environ.Env.read_env(ROOT_DIR / ".env")


def _clean_list(name: str) -> list[str]:
    raw = env(name, default="")
    return [
        item.strip()
        for item in str(raw).split(",")
        if item.strip()
    ]


DEBUG = env.bool(
    "DJANGO_DEBUG",
    default=False,
)

SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    default="",
).strip()

if not SECRET_KEY:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY is required."
    )

_placeholder_secret_markers = (
    "change-me",
    "changeme",
    "replace-this",
    "replace-with",
)

if (
    not DEBUG
    and (
        len(SECRET_KEY) < 32
        or any(
            marker in SECRET_KEY.casefold()
            for marker in _placeholder_secret_markers
        )
    )
):
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be a non-placeholder "
        "secret of at least 32 characters when DEBUG is false."
    )


FFPROBE_PATH = env(
    "FFPROBE_PATH",
    default="ffprobe",
)

FFMPEG_PATH = env(
    "FFMPEG_PATH",
    default="",
)


CSRF_TRUSTED_ORIGINS = env.list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    default=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
)

ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS",
    default=["localhost", "127.0.0.1"],
)


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "rest_framework",
    "django_filters",

    "accounts",
    "libraries",
    "media",
    "metadata",
    "catalog",
    "outputs",
    "operations",
    "preferences",
    "integrations",
    "jobs",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


ROOT_URLCONF = "libraryforge.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,

        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


WSGI_APPLICATION = "libraryforge.wsgi.application"
ASGI_APPLICATION = "libraryforge.asgi.application"


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env(
            "POSTGRES_HOST",
            default="127.0.0.1",
        ),
        "PORT": env(
            "POSTGRES_PORT",
            default="5432",
        ),
    }
}


AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME":
        "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME":
        "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME":
        "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME":
        "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]


REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],

    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],

    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
    ],

    "DEFAULT_PAGINATION_CLASS": (
        "rest_framework.pagination.PageNumberPagination"
    ),

    "PAGE_SIZE": 100,
}


LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Browser/session hardening.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

# The React client reads the CSRF cookie and sends X-CSRFToken, so this
# intentionally remains readable by JavaScript.
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"

_secure_cookie_default = not DEBUG

SESSION_COOKIE_SECURE = env.bool(
    "DJANGO_SECURE_COOKIES",
    default=_secure_cookie_default,
)

CSRF_COOKIE_SECURE = env.bool(
    "DJANGO_SECURE_COOKIES",
    default=_secure_cookie_default,
)

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

SECURE_SSL_REDIRECT = env.bool(
    "DJANGO_SECURE_SSL_REDIRECT",
    default=False,
)

SECURE_HSTS_SECONDS = env.int(
    "DJANGO_SECURE_HSTS_SECONDS",
    default=0,
)

SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool(
    "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS",
    default=False,
)

SECURE_HSTS_PRELOAD = env.bool(
    "DJANGO_SECURE_HSTS_PRELOAD",
    default=False,
)

if env.bool(
    "DJANGO_TRUST_X_FORWARDED_PROTO",
    default=False,
):
    # Only enable this when the reverse proxy is controlled by the
    # LibraryForge operator and strips client-supplied X-Forwarded-Proto.
    SECURE_PROXY_SSL_HEADER = (
        "HTTP_X_FORWARDED_PROTO",
        "https",
    )


# LibraryForge security controls.
LIBRARYFORGE_LOGIN_MAX_FAILURES = env.int(
    "LIBRARYFORGE_LOGIN_MAX_FAILURES",
    default=8,
)

LIBRARYFORGE_LOGIN_IP_MAX_FAILURES = env.int(
    "LIBRARYFORGE_LOGIN_IP_MAX_FAILURES",
    default=40,
)

LIBRARYFORGE_LOGIN_WINDOW_SECONDS = env.int(
    "LIBRARYFORGE_LOGIN_WINDOW_SECONDS",
    default=300,
)

LIBRARYFORGE_MAX_NFO_BYTES = env.int(
    "LIBRARYFORGE_MAX_NFO_BYTES",
    default=10 * 1024 * 1024,
)

LIBRARYFORGE_ALLOWED_LIBRARY_ROOTS = _clean_list(
    "LIBRARYFORGE_ALLOWED_LIBRARY_ROOTS"
)

LIBRARYFORGE_ALLOWED_OUTPUT_ROOTS = _clean_list(
    "LIBRARYFORGE_ALLOWED_OUTPUT_ROOTS"
)

LIBRARYFORGE_RESTART_ENABLED = env.bool(
    "LIBRARYFORGE_RESTART_ENABLED",
    default=False,
)

LIBRARYFORGE_RESTART_FILE = env(
    "LIBRARYFORGE_RESTART_FILE",
    default="",
)
