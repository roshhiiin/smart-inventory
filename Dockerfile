FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend backend
COPY web web
COPY docs docs
WORKDIR /app/backend
ENV APP_ENV=production DATABASE=/data/inventory.db PORT=8000
VOLUME /data
EXPOSE 8000
# First boot: set ADMIN_EMAIL and ADMIN_PASSWORD once to create an admin; SECRET_KEY is required.
CMD ["sh", "-c", "[ -n \"$ADMIN_PASSWORD\" ] && python create_admin.py; exec gunicorn --workers 2 --bind 0.0.0.0:${PORT} 'app:create_app()'"]
