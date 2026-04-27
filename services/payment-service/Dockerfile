FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

EXPOSE 8000

CMD ["sh", "-c", "python wait_for_db.py && python manage.py migrate --noinput && gunicorn payment_service.wsgi:application --bind 0.0.0.0:8000 --workers 2 --threads 4 --timeout 60"]

