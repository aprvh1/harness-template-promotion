# Use SDK base image that has harness-python-api-sdk pre-installed
FROM harnesssolutionfactory/harness-python-api-sdk:latest

WORKDIR /plugin

# Copy requirements, plugin code, and entrypoint script
COPY requirements.txt .
COPY src/ ./src/
COPY entrypoint.sh /entrypoint.sh

# Install plugin dependencies directly in runtime image
RUN pip install --no-cache-dir -r requirements.txt

# Create /harness directory with proper permissions (standard Harness writable location)
# Users can set PLUGIN_OUTPUT_DIR to /harness/templates, /harness/output, etc.
RUN mkdir -p /harness && \
    chmod -R 777 /harness && \
    chmod +x /entrypoint.sh

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Use entrypoint script to fix permissions before running
ENTRYPOINT ["/entrypoint.sh"]
