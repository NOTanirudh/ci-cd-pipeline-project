FROM python:3.10-slim

# create a non-root user
RUN useradd -m appuser || true
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000

# Use gunicorn for production; fallback to flask dev server if GUNICORN_CMD not set
ENV GUNICORN_WORKERS=2
USER appuser
CMD ["sh", "-c", "gunicorn -w $GUNICORN_WORKERS -b 0.0.0.0:5000 app:app"]
