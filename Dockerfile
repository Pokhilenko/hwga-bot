# Stage 1: Build stage
FROM python:3.11.5-slim as builder

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Production stage
FROM python:3.11.5-slim

WORKDIR /app

# Create a non-root user
RUN addgroup --system app && adduser --system --group app

# Copy installed dependencies from builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# Copy application code
COPY . .

# Set ownership
RUN chown -R app:app /app

# Switch to non-root user
USER app

CMD ["python", "app.py"]
