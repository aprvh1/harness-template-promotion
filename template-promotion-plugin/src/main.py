#!/usr/bin/env python3
"""
Harness CI Plugin for Template Promotion
Entrypoint for Docker container execution.
"""

import os
import sys
import json
import logging
from typing import Dict, Any

# Ensure unbuffered output for real-time logging
os.environ["PYTHONUNBUFFERED"] = "1"

from config import PluginConfig
from logic import execute_plugin

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


def mask_sensitive(config: PluginConfig) -> Dict[str, Any]:
    """Return config dict with sensitive fields masked.

    Args:
        config: PluginConfig instance

    Returns:
        Dict with api_key masked
    """
    data = config.model_dump()
    if data.get("api_key"):
        data["api_key"] = "***MASKED***"
    return data


def write_outputs(outputs: Dict[str, Any], format: str = "json"):
    """Write outputs to DRONE_OUTPUT_FILE for downstream steps.

    Args:
        outputs: Dictionary of output variables
        format: Output format (json or text)
    """
    output_file = os.getenv("DRONE_OUTPUT_FILE")
    if not output_file:
        logger.warning("DRONE_OUTPUT_FILE not set, skipping output export")
        return

    try:
        with open(output_file, "w") as f:
            if format == "json":
                # Write as single JSON output variable
                f.write(f"outputs={json.dumps(outputs)}\n")
            else:
                # Write as individual key=value pairs
                for key, value in outputs.items():
                    f.write(f"{key}={value}\n")
        logger.info(f"Outputs written to {output_file}")
    except Exception as e:
        logger.error(f"Failed to write outputs: {e}")


def main():
    """Plugin entrypoint."""
    logger.info("=" * 60)
    logger.info("Harness Template Promotion Plugin v1.0.0")
    logger.info("=" * 60)

    try:
        # Load configuration from PLUGIN_* env vars
        logger.info("Loading plugin configuration...")
        config = PluginConfig()

        # Log config (masked)
        logger.info(f"Configuration: {json.dumps(mask_sensitive(config), indent=2)}")
        logger.info(f"Operation mode: {config.get_mode()}")

        # Execute plugin logic
        logger.info("Executing plugin logic...")
        result = execute_plugin(config)

        # Write outputs for downstream steps
        if result.outputs:
            write_outputs(result.outputs, config.output_format)

        # Log result
        if result.success:
            logger.info(f"✅ SUCCESS: {result.message}")
            logger.info("=" * 60)
            sys.exit(0)
        else:
            logger.error(f"❌ FAILURE: {result.message}")
            if result.error:
                logger.error(f"Error details: {result.error}")
            logger.info("=" * 60)
            sys.exit(1)

    except Exception as e:
        logger.error(f"❌ FATAL ERROR: {e}", exc_info=True)
        logger.info("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
