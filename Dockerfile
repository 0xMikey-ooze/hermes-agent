FROM python:3.11-slim

# Install Node.js for the dashboard
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install and build Next.js dashboard
COPY dashboard/package*.json dashboard/
RUN cd dashboard && npm ci --production=false

COPY dashboard/ dashboard/
RUN cd dashboard && npm run build

# Copy rest of app
COPY . .

# Start both: Python gateway (port 3001 REST API) + Next.js dashboard (port 4000)
# Use a simple shell script to run both processes
CMD ["sh", "-c", "cd dashboard && PORT=4000 npm start & python gateway/run.py"]
