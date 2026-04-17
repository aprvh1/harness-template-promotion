# Use SDK base image that has harness-python-api-sdk pre-installed
FROM harnesssolutionfactory/harness-python-api-sdk:latest

WORKDIR /plugin

# Copy requirements and plugin code
COPY requirements.txt .
COPY src/ ./src/

# Install plugin dependencies directly in runtime image
RUN pip install --no-cache-dir -r requirements.txt

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run as root to avoid permission issues with /harness directory
# Files in /harness may be owned by root from previous runs
USER root

# Run plugin directly with Python
ENTRYPOINT ["python", "/plugin/src/main.py"]
