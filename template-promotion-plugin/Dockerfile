# Use SDK base image that has harness-python-api-sdk pre-installed
FROM harnesssolutionfactory/harness-python-api-sdk:latest

WORKDIR /plugin

# Run as root to ensure we can install packages and write to /harness
USER root

# Copy requirements and plugin code
COPY requirements.txt .
COPY src/ ./src/

# Install plugin dependencies directly in runtime image
RUN pip install --no-cache-dir -r requirements.txt

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run plugin directly with Python
ENTRYPOINT ["python", "/plugin/src/main.py"]
