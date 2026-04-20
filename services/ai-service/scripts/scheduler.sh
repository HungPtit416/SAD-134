#!/bin/sh
# Periodic graph sync + behavior embedding training (run via Docker Compose profile "scheduler").
set -e
cd /app
python wait_for_db.py
INTERVAL="${AI_CRON_INTERVAL_SECONDS:-3600}"
echo "ai-scheduler: interval=${INTERVAL}s"
while true; do
  python manage.py sync_events_to_graph --skip-catalog-categories || true
  python manage.py train_behavior_embeddings || true
  sleep "$INTERVAL"
done
