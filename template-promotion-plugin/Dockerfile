# Use SDK base image that has harness-python-api-sdk pre-installed
FROM harnesssolutionfactory/harness-python-api-sdk:latest

WORKDIR /plugin

# Copy requirements and plugin code
COPY requirements.txt .
COPY src/ ./src/

# Install plugin dependencies directly in runtime image
RUN pip install --no-cache-dir -r requirements.txt

# Create output directories with proper permissions
RUN mkdir -p /plugin/templates && \
    chmod -R 777 /plugin/templates && \
    mkdir -p /plugin/output && \
    chmod -R 777 /plugin/output

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Entrypoint
ENTRYPOINT ["python", "/plugin/src/main.py"]
