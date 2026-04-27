"""
Django settings for ai_service project.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-secret")
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",") if h]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "ai",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "ai_service.urls"

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
    }
]

WSGI_APPLICATION = "ai_service.wsgi.application"

if os.environ.get("DATABASE_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": os.environ["DATABASE_HOST"],
            "PORT": int(os.environ.get("DATABASE_PORT", "5432")),
            "NAME": os.environ.get("DATABASE_NAME", "ai_db"),
            "USER": os.environ.get("DATABASE_USER", "postgres"),
            "PASSWORD": os.environ.get("DATABASE_PASSWORD", "postgres"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

CORS_ALLOW_ALL_ORIGINS = os.environ.get("CORS_ALLOW_ALL_ORIGINS", "0") == "1"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# External service endpoints
INTERACTION_SERVICE_URL = os.environ.get("INTERACTION_SERVICE_URL", "http://interaction-service:8000")
PRODUCT_SERVICE_URL = os.environ.get("PRODUCT_SERVICE_URL", "http://product-service:8000")

# Neo4j (optional; features degrade gracefully if missing)
NEO4J_URI = os.environ.get("NEO4J_URI", "")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "neo4j-password")

# OpenAI (optional; chat falls back if missing)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_CHAT_MODEL = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o-mini")
OPENAI_EMBED_MODEL = os.environ.get("OPENAI_EMBED_MODEL", "text-embedding-3-small")

# Gemini (optional; used when OpenAI is not configured or provider selects it)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_CHAT_MODEL = os.environ.get("GEMINI_CHAT_MODEL", "gemini-2.5-flash")
GEMINI_EMBED_MODEL = os.environ.get("GEMINI_EMBED_MODEL", "gemini-embedding-001")

# Providers:
# - EMBEDDING_PROVIDER: "openai" | "gemini" | "local"
# - CHAT_PROVIDER: "openai" | "gemini"
EMBEDDING_PROVIDER = os.environ.get("EMBEDDING_PROVIDER", "openai")
CHAT_PROVIDER = os.environ.get("CHAT_PROVIDER", "openai")

# Recommender: when both graph + behavior embeddings exist, prefer co-occurrence graph if true;
# if graph only has same-category signal, blend with embeddings when user has at least this many product edges.
GRAPH_MIN_PRODUCT_EDGES_FOR_BLEND = int(os.environ.get("GRAPH_MIN_PRODUCT_EDGES_FOR_BLEND", "1"))

# Optional: sequence model (LSTM) for next-action prediction
SEQ_MODEL_PATH = os.environ.get("SEQ_MODEL_PATH", "")

# Phase-4: GraphRAG + GNN knobs (keep defaults small for report reproducibility)
GRAPHRAG_EVIDENCE_LIMIT = int(os.environ.get("GRAPHRAG_EVIDENCE_LIMIT", "20"))
LIGHTGCN_DIM = int(os.environ.get("LIGHTGCN_DIM", "64"))
LIGHTGCN_LAYERS = int(os.environ.get("LIGHTGCN_LAYERS", "2"))
LIGHTGCN_EPOCHS = int(os.environ.get("LIGHTGCN_EPOCHS", "5"))


