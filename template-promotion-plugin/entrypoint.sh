#!/bin/bash
# Entrypoint script for template promotion plugin
# Ensures /harness directory has proper permissions before running

set -e

# Fix permissions on /harness if it exists and we have permission to change it
if [ -d "/harness" ]; then
    echo "Fixing permissions on /harness directory..."
    chmod -R 777 /harness 2>/dev/null || echo "Warning: Could not set permissions on /harness (continuing anyway)"
fi

# Run the plugin
exec python /plugin/src/main.py "$@"
