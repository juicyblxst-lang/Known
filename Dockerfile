FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY frontend /app/frontend

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --app-dir /app/backend --host 0.0.0.0 --port ${PORT}"]
