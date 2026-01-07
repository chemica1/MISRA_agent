FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY .env.example .env

# Create directories for outputs
RUN mkdir -p /app/target_project

# Run agent
CMD ["python", "-m", "src.main"]
