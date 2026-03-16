FROM python:3.11-slim

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# gateway/run.py listens on $PORT (Railway injects this, default 8080)
# Telegram bot runs as a side-effect of the gateway startup
CMD ["python", "gateway/run.py"]
