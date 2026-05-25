FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user for security
RUN adduser --disabled-password --gecos "" appuser
USER appuser

# Cloud Run listens on PORT env var (default 8080)
ENV PORT=8080
EXPOSE 8080

# Use Gunicorn with 1 worker and 8 threads for Cloud Run so in-memory state is shared
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "120", "app:app"]
