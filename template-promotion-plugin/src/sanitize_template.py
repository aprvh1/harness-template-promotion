#!/usr/bin/env python3
"""Sanitize template YAML by converting secrets, connectors, and variables to runtime inputs.

This ensures that extracted templates don't contain environment-specific values
and are portable across environments.
"""

import yaml
import re
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


# Patterns to detect fields that should be runtime inputs
SENSITIVE_PATTERNS = {
    'secrets': [
        r'spec\.connectorRef',
        r'spec\.secretRef',
        r'spec\.auth\.spec\..*Ref',
        r'spec\.configuration\..*Ref',
    ],
    'variables': [
        r'spec\..*\.value',
        r'variables\.\d+\.value',
    ],
    'expressions': [
        r'<\+secrets\.getValue\(',
        r'<\+pipeline\.',
        r'<\+project\.',
        r'<\+org\.',
    ]
}

# Fields that should ALWAYS be runtime inputs in templates
RUNTIME_INPUT_FIELDS = [
    'connectorRef',
    'secretRef',
    'passwordRef',
    'tokenRef',
    'sshKeyRef',
    'certificateRef',
    'privateKeyRef',
    'dockerConfigJsonRef',
]

# Fields that should NEVER be sanitized (script content, commands)
SCRIPT_CONTENT_FIELDS = [
    'script',      # Inline script content
    'command',     # Shell command content
    'commands',    # List of commands
    'scriptString', # Alternative script field
]

# Expression patterns that reference environment-specific values
ENV_SPECIFIC_EXPRESSIONS = [
    r'<\+secrets\.getValue\(["\']([^"\']+)["\']\)>',  # Secrets
    r'<\+pipeline\.variables\.([a-zA-Z0-9_]+)>',       # Pipeline vars
    r'<\+project\.([a-zA-Z0-9_]+)>',                   # Project vars
    r'<\+org\.([a-zA-Z0-9_]+)>',                       # Org vars
    r'<\+account\.([a-zA-Z0-9_]+)>',                   # Account vars
    r'<\+env\.variables\.([a-zA-Z0-9_]+)>',            # Env vars
    r'<\+serviceVariables\.([a-zA-Z0-9_]+)>',          # Service vars
]


def should_convert_to_runtime_input(key: str, value: Any, parent_keys: List[str] = None) -> bool:
    """Determine if a field should be converted to runtime input.

    Args:
        key: Field name
        value: Field value
        parent_keys: List of parent keys for nested fields

    Returns:
        bool: True if should be converted to <+input>
    """
    if parent_keys is None:
        parent_keys = []

    # Check if key matches runtime input fields
    if key in RUNTIME_INPUT_FIELDS:
        return True

    # Check if value is a string containing environment-specific expressions
    if isinstance(value, str):
        for pattern in ENV_SPECIFIC_EXPRESSIONS:
            if re.search(pattern, value):
                logger.debug(f"Found env-specific expression in {key}: {value}")
                return True

    # Check if field path matches sensitive patterns
    full_path = '.'.join(parent_keys + [key])
    for category, patterns in SENSITIVE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, full_path):
                logger.debug(f"Field path {full_path} matches {category} pattern: {pattern}")
                return True

    return False


def sanitize_value(key: str, value: Any, parent_keys: List[str] = None) -> Any:
    """Recursively sanitize a value by converting sensitive fields to runtime inputs.

    Args:
        key: Field name
        value: Field value to sanitize
        parent_keys: List of parent keys for nested fields

    Returns:
        Sanitized value
    """
    if parent_keys is None:
        parent_keys = []

    # IMPORTANT: Skip script content fields - never sanitize actual scripts/commands
    if key in SCRIPT_CONTENT_FIELDS:
        logger.debug(f"Skipping script content field: {key}")
        return value

    # Handle None values
    if value is None:
        return value

    # Handle dictionaries recursively
    if isinstance(value, dict):
        sanitized = {}
        for k, v in value.items():
            sanitized[k] = sanitize_value(k, v, parent_keys + [key])
        return sanitized

    # Handle lists recursively
    if isinstance(value, list):
        return [sanitize_value(key, item, parent_keys) for item in value]

    # Handle strings - check if should be runtime input
    if isinstance(value, str):
        # Skip if already a runtime input or expression
        if value == '<+input>' or value.startswith('<+input.'):
            return value

        # Check if this field should be converted
        if should_convert_to_runtime_input(key, value, parent_keys):
            return '<+input>'

        # Check if value contains specific connector/secret IDs that should be parameterized
        if re.match(r'^[a-zA-Z0-9_]+$', value) and len(value) > 3:
            # If parent context suggests this is a reference, convert it
            if any(ref in key.lower() for ref in ['ref', 'connector', 'secret']):
                return '<+input>'

    return value


def sanitize_template(template_yaml: str) -> str:
    """Sanitize template YAML by converting sensitive fields to runtime inputs.

    Args:
        template_yaml: Template YAML string

    Returns:
        Sanitized template YAML string
    """
    try:
        # Parse YAML
        template_dict = yaml.safe_load(template_yaml)

        if not template_dict:
            return template_yaml

        # Sanitize the template
        sanitized_dict = sanitize_value('root', template_dict)

        # Convert back to YAML
        sanitized_yaml = yaml.dump(sanitized_dict, default_flow_style=False, sort_keys=False)

        return sanitized_yaml

    except Exception as e:
        logger.error(f"Failed to sanitize template: {e}")
        return template_yaml


def get_sanitization_report(original_yaml: str, sanitized_yaml: str) -> Dict[str, Any]:
    """Generate a report of changes made during sanitization.

    Args:
        original_yaml: Original template YAML
        sanitized_yaml: Sanitized template YAML

    Returns:
        Dictionary with sanitization statistics
    """
    original = yaml.safe_load(original_yaml)
    sanitized = yaml.safe_load(sanitized_yaml)

    def count_runtime_inputs(obj: Any) -> int:
        """Count occurrences of <+input> in object."""
        count = 0
        if isinstance(obj, dict):
            for v in obj.values():
                count += count_runtime_inputs(v)
        elif isinstance(obj, list):
            for item in obj:
                count += count_runtime_inputs(item)
        elif obj == '<+input>':
            count += 1
        return count

    original_count = count_runtime_inputs(original)
    sanitized_count = count_runtime_inputs(sanitized)

    return {
        'runtime_inputs_before': original_count,
        'runtime_inputs_after': sanitized_count,
        'fields_converted': sanitized_count - original_count,
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python sanitize_template.py <template_file.yaml>")
        sys.exit(1)

    file_path = sys.argv[1]

    # Read template
    with open(file_path, 'r') as f:
        original = f.read()

    # Sanitize
    print(f"Sanitizing {file_path}...")
    sanitized = sanitize_template(original)

    # Show report
    report = get_sanitization_report(original, sanitized)
    print(f"\nSanitization Report:")
    print(f"  Runtime inputs (before): {report['runtime_inputs_before']}")
    print(f"  Runtime inputs (after): {report['runtime_inputs_after']}")
    print(f"  Fields converted: {report['fields_converted']}")

    # Write sanitized version
    output_path = file_path.replace('.yaml', '-sanitized.yaml')
    with open(output_path, 'w') as f:
        f.write(sanitized)

    print(f"\n✓ Sanitized template saved to: {output_path}")
