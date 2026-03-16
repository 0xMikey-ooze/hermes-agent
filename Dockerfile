FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (git required for github_work_tool)
RUN apt-get update && apt-get install -y --no-install-recommends     git     ca-certificates     curl     && apt-get clean && rm -rf /var/lib/apt/lists/*

# Configure git identity for agent commits
RUN git config --global user.email "hermes@agent.local" &&     git config --global user.name "Hermes Agent"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# gateway/run.py listens on $PORT (Railway injects this, default 8080)
# Telegram bot runs as a side-effect of the gateway startup
CMD ["python", "gateway/run.py"]
