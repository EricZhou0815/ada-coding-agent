FROM python:3.11-slim

# Install system dependencies (git is required for workers to clone and commit repos)
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire Ada application code
COPY . .

# Expose port for the FastAPI web server
EXPOSE 80

# Default command: Runs the API Server
# Note: For AWS Celery Workers or Local Docker Isolation, this CMD is overridden at runtime.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "80"]