# Dockerfile for ELA SDK v2
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY .claude/ ./.claude/

# Create runtime directories (benchmarks are not required at runtime)
RUN mkdir -p outputs data

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

# Change to src directory for uvicorn
WORKDIR /app/src

# Run the FastAPI app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
