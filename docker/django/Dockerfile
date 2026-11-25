FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

COPY app /app

# Build WhiteNoise's production static tree into the immutable image layer.
RUN DJANGO_SETTINGS_MODULE=config.settings.local \
    SECRET_KEY=collectstatic-build-only \
    python manage.py collectstatic --noinput
