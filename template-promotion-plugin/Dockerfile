# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime - Based on image with harness-python-api-sdk pre-installed
FROM harnesssolutionfactory/harness-python-api-sdk:latest

WORKDIR /plugin

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Copy plugin source code
COPY src/ ./src/

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PATH=/root/.local/bin:$PATH

# Entrypoint
ENTRYPOINT ["python", "/plugin/src/main.py"]
