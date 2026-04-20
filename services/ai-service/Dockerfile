FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app
RUN chmod +x /app/scripts/scheduler.sh

EXPOSE 8000

CMD ["sh", "-c", "python wait_for_db.py && python manage.py migrate && gunicorn ai_service.wsgi:application --bind 0.0.0.0:8000 --workers 2 --threads 4"]

