FROM python:3.11-slim-buster

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Set environment variables for Alembic to pick up
ENV DOTA_DB_DSN="postgresql+psycopg2://user:pass@dota_db:5432/dota_stats"

# Run Alembic migrations
RUN alembic -c dota_analytics/db/migrations/alembic.ini upgrade head

CMD ["uvicorn", "dota_analytics.api.main:app", "--host", "0.0.0.0", "--port", "8000"]