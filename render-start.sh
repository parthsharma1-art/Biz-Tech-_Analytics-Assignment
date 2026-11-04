#!/usr/bin/env bash
set -e

# 1. Apply Django migrations for Section 1 (Orders & Silk)
python manage.py migrate --noinput

# 2. Start Celery worker in background (using thread pool suited for lightweight containers)
celery -A emailsystem worker --loglevel=info --pool=threads --concurrency=2 &

# 3. Start Streamlit web application bound to Render's assigned $PORT
exec streamlit run app.py --server.port "${PORT:-10000}" --server.address 0.0.0.0 --server.headless true

