"""Shared utilities for template promotion scripts.

This module provides common data structures and helper functions used across
all template promotion scripts, following Python best practices.
"""

import os
import sys
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Any, Dict, Set
import yaml

# Add src to path for local harness_api imports
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root / "src"))

# Import Scope from SDK with compatibility wrapper
from harness_python_sdk import Scope as _SDKScope

# Compatibility wrapper for Scope (PyPI SDK uses 'account' not 'account_id')
class Scope:
    """Wrapper for Scope to handle different SDK versions."""
    def __init__(self, account_id=None, org=None, project=None):
        # PyPI SDK uses 'account' parameter, not 'account_id'
        self._scope = _SDKScope(account=account_id, org=org, project=project)
        self.account_id = account_id
        self.org = org
        self.project = project

# Use local HarnessAPIClient (more feature-complete than SDK)
from harness_api.client import HarnessAPIClient as HarnessClient

# Define ApiError
class ApiError(Exception):
    """Harness API error."""
    pass

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class TemplateRef:
    """Reference to a template found in YAML.

    Attributes:
        identifier: Template identifier
        version_label: Optional version label (None means stable reference)
        path: Path in YAML where reference was found
    """
    identifier: str
    version_label: Optional[str]
    path: str


@dataclass
class TemplateMetadata:
    """Metadata for a template version.

    Attributes:
        identifier: Template identifier
        version: Version string (e.g., v1.5)
        type: Template type (pipeline, stage, step_group, step)
        label: Promotion label (None=beta, canary, stable)
        is_stable: Whether this is the stable version in Harness
        scope: Deployment scope (account, org, project)
        org: Optional org ID for org/project scope
        project: Optional project ID for project scope
        depth: Depth in dependency tree (0=root)
    """
    identifier: str
    version: str
    type: str
    label: Optional[str]
    is_stable: bool
    scope: str
    org: Optional[str]
    project: Optional[str]
    depth: int = 0


def get_harness_client() -> HarnessClient:
    """Create and return configured Harness client.

    Returns:
        HarnessClient: Configured client instance.

    Raises:
        ValueError: If required environment variables are not set.
    """
    api_key = os.getenv("HARNESS_API_KEY")
    account_id = os.getenv("HARNESS_ACCOUNT_ID")

    if not api_key or not account_id:
        raise ValueError(
            "HARNESS_API_KEY and HARNESS_ACCOUNT_ID environment variables must be set"
        )

    return HarnessClient(api_key=api_key, account_id=account_id)


def load_versions_yaml() -> dict:
    """Load versions.yaml file from project root.

    Returns:
        dict: Parsed YAML data with labels and templates sections.
    """
    # Get project root (parent of scripts directory)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    versions_file = project_root / "versions.yaml"

    if not versions_file.exists():
        # Return default structure
        return {
            'labels': {
                'canary': {},
                'stable': {}
            },
            'templates': {}
        }

    with open(versions_file, 'r') as f:
        data = yaml.safe_load(f)

    return data or {'labels': {'canary': {}, 'stable': {}}, 'templates': {}}


def save_versions_yaml(data: dict) -> None:
    """Save data to versions.yaml file in project root.

    Args:
        data: Dictionary to save as YAML.
    """
    # Get project root (parent of scripts directory)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    versions_file = project_root / "versions.yaml"

    with open(versions_file, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    logger.info("✓ Saved versions.yaml")


def find_version(
    versions: dict,
    tmpl_type: str,
    identifier: str,
    version: str
) -> dict:
    """Find version info in versions.yaml structure.

    Args:
        versions: Parsed versions.yaml data
        tmpl_type: Template type (pipeline, stage, step_group, step)
        identifier: Template identifier
        version: Version string

    Returns:
        dict: Version info dictionary.

    Raises:
        ValueError: If version not found.
    """
    templates = versions.get('templates', {}).get(tmpl_type, {}).get(identifier, {})
    versions_list = templates.get('versions', [])
    version_info = next((v for v in versions_list if v['version'] == version), None)

    if not version_info:
        raise ValueError(f"Version {version} not found for {tmpl_type}/{identifier}")

    return version_info


def extract_template_refs(template_yaml: dict) -> List[TemplateRef]:
    """Recursively extract all templateRef entries from YAML.

    Uses recursion to walk the entire YAML tree structure.

    Args:
        template_yaml: Parsed template YAML dictionary.

    Returns:
        List[TemplateRef]: All template references found.
    """
    refs = []

    def walk(obj, path=""):
        """Recursive function to walk YAML structure."""
        if isinstance(obj, dict):
            # Check if this dict contains a templateRef
            if 'templateRef' in obj:
                refs.append(TemplateRef(
                    identifier=obj['templateRef'],
                    version_label=obj.get('versionLabel'),
                    path=path
                ))
            # Recurse into all dict values
            for key, value in obj.items():
                walk(value, f"{path}.{key}" if path else key)
        elif isinstance(obj, list):
            # Recurse into all list items
            for i, item in enumerate(obj):
                walk(item, f"{path}[{i}]")

    walk(template_yaml)
    return refs


def save_template_yaml(
    template_yaml: dict,
    template_type: str,
    identifier: str,
    version: str
) -> Path:
    """Save template YAML to local file.

    Args:
        template_yaml: Template YAML dictionary
        template_type: Template type (pipeline, stage, step_group, step)
        identifier: Template identifier
        version: Version string

    Returns:
        Path: Path to saved file.
    """
    # Convert step_group -> step-group for directory name
    dir_type = template_type.replace('_', '-')
    # Use project root directory with template-specific subdirectory
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    template_dir = project_root / "templates" / dir_type / identifier
    template_dir.mkdir(parents=True, exist_ok=True)

    file_path = template_dir / f"{version}.yaml"

    # Remove scope identifiers to make template reusable at account level
    if 'template' in template_yaml:
        if 'projectIdentifier' in template_yaml['template']:
            del template_yaml['template']['projectIdentifier']
        if 'orgIdentifier' in template_yaml['template']:
            del template_yaml['template']['orgIdentifier']

        # Add tags for tracking
        if 'tags' not in template_yaml['template']:
            template_yaml['template']['tags'] = {}
        template_yaml['template']['tags'].update({
            'source_version': version,
            'managed_by': 'terraform',
            'template_type': dir_type
        })

    # Qualify templateRef with account. prefix
    def add_account_prefix(obj):
        if isinstance(obj, dict):
            if 'templateRef' in obj and isinstance(obj['templateRef'], str):
                ref = obj['templateRef']
                if not ref.startswith(('account.', 'org.')):
                    obj['templateRef'] = f"account.{ref}"
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    add_account_prefix(v)
        elif isinstance(obj, list):
            for item in obj:
                add_account_prefix(item)

    add_account_prefix(template_yaml)

    with open(file_path, 'w') as f:
        yaml.dump(template_yaml, f, default_flow_style=False, sort_keys=False)

    logger.info(f"✓ Saved {file_path}")
    return file_path


# ============================================================================
# YAML Validation Functions for Strong Template Validation
# ============================================================================

# Keys to ignore during comparison (contain runtime values)
IGNORE_KEYS = {
    'secretRef', 'connectorRef', 'value', 'default',
    'uuid', 'executionInputTemplate', 'timeout'
}

# Pattern to match Harness expressions
EXPRESSION_PATTERN = re.compile(r'<\+[^>]+>|\$\{[^}]+\}')


def normalize_value(value: Any) -> Any:
    """Normalize a single value for comparison.

    Replaces Harness expressions with placeholders so only
    structure is compared, not runtime values.

    Args:
        value: Value to normalize

    Returns:
        Normalized value or placeholder
    """
    if isinstance(value, str):
        # Replace Harness expressions with placeholder
        if EXPRESSION_PATTERN.search(value):
            return '<EXPRESSION>'
    return value


def normalize_yaml_for_comparison(yaml_obj: Any, parent_key: str = '') -> Any:
    """Recursively normalize YAML for structural comparison.

    Replaces runtime values (secrets, connectors, expressions) with
    placeholders so only structure is compared.

    Args:
        yaml_obj: YAML object (dict, list, or scalar)
        parent_key: Parent key name for context

    Returns:
        Normalized YAML object
    """
    if isinstance(yaml_obj, dict):
        normalized = {}
        for key, value in yaml_obj.items():
            # Ignore certain keys that contain runtime values
            if key in IGNORE_KEYS:
                normalized[key] = '<IGNORED>'
            else:
                normalized[key] = normalize_yaml_for_comparison(value, key)
        return normalized

    elif isinstance(yaml_obj, list):
        return [normalize_yaml_for_comparison(item, parent_key) for item in yaml_obj]

    else:
        # Scalar value - check if it's an expression
        return normalize_value(yaml_obj)


def find_template_expansion(
    template_structure: dict,
    execution_yaml: dict,
    path: str = 'root'
) -> Optional[str]:
    """Find where template was expanded in execution YAML.

    Recursively searches execution YAML for a structure matching
    the template.

    Args:
        template_structure: Normalized template structure
        execution_yaml: Normalized execution YAML
        path: Current path in execution YAML

    Returns:
        str: Path where template was found, or None
    """
    # Get template identifier
    template_id = template_structure.get('template', {}).get('identifier')

    if not template_id:
        return None

    # Recursive search
    def search(obj, current_path):
        if isinstance(obj, dict):
            # Check if this dict has the template identifier
            if obj.get('identifier') == template_id:
                return current_path

            # Recurse into children
            for key, value in obj.items():
                result = search(value, f"{current_path}.{key}")
                if result:
                    return result

        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                result = search(item, f"{current_path}[{i}]")
                if result:
                    return result

        return None

    return search(execution_yaml, path)


def compare_structures(
    template_structure: dict,
    execution_structure: dict
) -> Dict[str, Any]:
    """Compare two normalized YAML structures.

    Args:
        template_structure: Normalized template YAML
        execution_structure: Normalized execution YAML section

    Returns:
        dict: Comparison results with match percentage and differences
    """
    def get_all_keys(obj, prefix=''):
        """Get all keys recursively from nested structure."""
        keys = set()
        if isinstance(obj, dict):
            for key, value in obj.items():
                current = f"{prefix}.{key}" if prefix else key
                keys.add(current)
                keys.update(get_all_keys(value, current))
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                keys.update(get_all_keys(item, f"{prefix}[{i}]"))
        return keys

    template_keys = get_all_keys(template_structure)
    execution_keys = get_all_keys(execution_structure)

    common_keys = template_keys & execution_keys
    missing_keys = template_keys - execution_keys
    extra_keys = execution_keys - template_keys

    # Calculate match percentage
    if len(template_keys) == 0:
        match_percentage = 0.0
    else:
        match_percentage = (len(common_keys) / len(template_keys)) * 100

    return {
        'found': len(common_keys) > 0,
        'match_percentage': match_percentage,
        'missing_keys': list(missing_keys)[:10],  # First 10 for brevity
        'extra_keys': list(extra_keys)[:10],
        'total_template_keys': len(template_keys),
        'total_execution_keys': len(execution_keys),
        'common_keys': len(common_keys)
    }


def validate_template_in_pipeline_yaml(
    template_id: str,
    pipeline_yaml_str: str
) -> Dict[str, Any]:
    """Validate that template is referenced in pipeline YAML.

    Args:
        template_id: Template identifier to search for
        pipeline_yaml_str: Pipeline YAML string

    Returns:
        dict: Validation results with reference details
    """
    try:
        pipeline_yaml = yaml.safe_load(pipeline_yaml_str)
    except Exception as e:
        logger.error(f"Failed to parse pipeline YAML: {e}")
        return {'found': False, 'error': 'Failed to parse pipeline YAML'}

    # Search for templateRef references
    refs = extract_template_refs(pipeline_yaml)
    matching_refs = [ref for ref in refs if ref.identifier == template_id]

    if matching_refs:
        return {
            'found': True,
            'reference_count': len(matching_refs),
            'references': [{'path': ref.path, 'version': ref.version_label} for ref in matching_refs]
        }
    else:
        return {
            'found': False,
            'error': f'Template {template_id} not referenced in pipeline YAML'
        }


def validate_template_structure_in_execution_yaml(
    template_yaml: dict,
    execution_yaml_str: str,
    template_id: str
) -> Dict[str, Any]:
    """Validate template structure appears in compiled execution YAML.

    This compares the template's structural keys against the execution YAML
    to verify the template was actually expanded/compiled into the execution.

    Args:
        template_yaml: Template YAML dictionary
        execution_yaml_str: Execution YAML string (from metadata endpoint)
        template_id: Template identifier for logging

    Returns:
        dict: Validation results with match details
    """
    # Parse execution YAML
    try:
        execution_yaml = yaml.safe_load(execution_yaml_str)
    except Exception as e:
        logger.error(f"Failed to parse execution YAML: {e}")
        return {'found': False, 'error': 'Failed to parse execution YAML'}

    # Normalize both YAMLs
    logger.info(f"Comparing {template_id} structure against compiled execution YAML...")
    normalized_template = normalize_yaml_for_comparison(template_yaml)
    normalized_execution = normalize_yaml_for_comparison(execution_yaml)

    # Get template spec (the actual content that gets expanded)
    template_spec = normalized_template.get('template', {}).get('spec', {})

    if not template_spec:
        logger.warning(f"No spec found in template {template_id}")
        return {
            'found': False,
            'error': 'No spec found in template'
        }

    # Compare template spec structure with execution YAML
    # Don't look for template identifier (it's been replaced)
    # Instead, check if template's structural keys appear in execution
    comparison = compare_structures(template_spec, normalized_execution)

    # Ensure 'found' key is set based on match percentage
    if 'found' not in comparison or not comparison['found']:
        # If match percentage > 0, consider it found (even if partial)
        if comparison.get('match_percentage', 0) > 0:
            comparison['found'] = True
        else:
            comparison['found'] = False
            if 'error' not in comparison:
                comparison['error'] = 'No structural match found between template and execution'

    return comparison


def compute_content_hash(yaml_obj: dict, ignore_secrets: bool = True) -> str:
    """Compute hash of template/execution content for comparison.

    Hash includes structure and critical values, but excludes runtime-specific values.

    Args:
        yaml_obj: YAML dictionary to hash
        ignore_secrets: If True, ignore secret/connector refs and expressions

    Returns:
        SHA256 hash of normalized content
    """
    import hashlib
    import json

    def normalize_for_hash(obj: Any) -> Any:
        """Normalize object for consistent hashing."""
        if isinstance(obj, dict):
            normalized = {}
            for key, value in sorted(obj.items()):
                # Skip runtime-specific keys if ignore_secrets=True
                if ignore_secrets and key in IGNORE_KEYS:
                    continue
                normalized[key] = normalize_for_hash(value)
            return normalized
        elif isinstance(obj, list):
            return [normalize_for_hash(item) for item in obj]
        elif isinstance(obj, str):
            # Replace expressions with placeholder if ignore_secrets=True
            if ignore_secrets and EXPRESSION_PATTERN.search(obj):
                return '<EXPRESSION>'
            return obj
        else:
            return obj

    # Normalize and convert to JSON for consistent ordering
    normalized = normalize_for_hash(yaml_obj)
    content_str = json.dumps(normalized, sort_keys=True, default=str)

    # Compute SHA256 hash
    return hashlib.sha256(content_str.encode('utf-8')).hexdigest()


def validate_content_hash(
    template_yaml: dict,
    execution_yaml: dict,
    template_id: str
) -> Dict[str, Any]:
    """Validate template and execution content using hash comparison.

    Computes hash of root-level elements (type, spec structure) and compares.
    Ignores secrets/connectors/expressions but catches real content differences.

    Args:
        template_yaml: Template YAML dictionary
        execution_yaml: Execution YAML dictionary (or subset)
        template_id: Template identifier for logging

    Returns:
        dict: Validation results with hash comparison
    """
    try:
        # Extract template spec
        template_spec = template_yaml.get('template', {}).get('spec', {})

        if not template_spec:
            return {
                'hash_match': False,
                'error': 'No template spec found'
            }

        # For execution, we need to find the relevant section
        # This is tricky because templates are expanded into the execution
        # We'll hash the template spec and try to find matching sections in execution

        # Normalize both
        normalized_template = normalize_yaml_for_comparison(template_spec)
        normalized_execution = normalize_yaml_for_comparison(execution_yaml)

        # Compute hashes
        template_hash = compute_content_hash(normalized_template)

        # Try to find matching hash in execution by checking various sections
        execution_sections = []

        def extract_sections(obj, sections, depth=0, max_depth=5):
            """Extract all dict sections from execution for hash comparison."""
            if depth > max_depth:
                return
            if isinstance(obj, dict):
                if len(obj) > 2:  # Only consider substantial sections
                    sections.append(obj)
                for value in obj.values():
                    extract_sections(value, sections, depth + 1, max_depth)
            elif isinstance(obj, list):
                for item in obj:
                    extract_sections(item, sections, depth + 1, max_depth)

        extract_sections(normalized_execution, execution_sections)

        # Check if any execution section matches template hash
        matching_section = False
        closest_similarity = 0

        for section in execution_sections:
            section_hash = compute_content_hash(section)
            if section_hash == template_hash:
                matching_section = True
                closest_similarity = 100
                break
            else:
                # Calculate similarity (approximate)
                template_keys = set(str(k) for k in get_all_keys_flat(normalized_template))
                section_keys = set(str(k) for k in get_all_keys_flat(section))
                if template_keys:
                    similarity = len(template_keys & section_keys) / len(template_keys) * 100
                    closest_similarity = max(closest_similarity, similarity)

        return {
            'hash_match': matching_section,
            'template_hash': template_hash[:12],
            'closest_similarity': closest_similarity,
            'confidence': 'high' if matching_section else ('medium' if closest_similarity > 70 else 'low')
        }

    except Exception as e:
        logger.warning(f"Hash validation error: {e}")
        return {
            'hash_match': False,
            'error': str(e)
        }


def get_all_keys_flat(obj: Any) -> set:
    """Get all keys from nested structure as flat set."""
    keys = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            keys.add(key)
            keys.update(get_all_keys_flat(value))
    elif isinstance(obj, list):
        for item in obj:
            keys.update(get_all_keys_flat(item))
    return keys


def extract_scripts_from_yaml(yaml_obj: dict) -> List[str]:
    """Extract all script content from YAML recursively.

    Args:
        yaml_obj: YAML dictionary

    Returns:
        List of script strings found
    """
    scripts = []

    def find_scripts(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in ('script', 'command', 'commands'):
                    if isinstance(value, str):
                        scripts.append(value)
                    elif isinstance(value, list):
                        scripts.extend([str(v) for v in value if v])
                else:
                    find_scripts(value)
        elif isinstance(obj, list):
            for item in obj:
                find_scripts(item)

    find_scripts(yaml_obj)
    return scripts


def fuzzy_match_scripts(
    template_scripts: List[str],
    execution_scripts: List[str],
    threshold: float = 0.5
) -> Dict[str, Any]:
    """Fuzzy match scripts between template and execution.

    Extracts command keywords and compares similarity, ignoring variables and expressions.

    Args:
        template_scripts: Scripts from template
        execution_scripts: Scripts from execution
        threshold: Similarity threshold (0.0-1.0)

    Returns:
        dict: Match results with similarity scores
    """
    import re

    if not template_scripts or not execution_scripts:
        return {
            'matched': False,
            'reason': 'No scripts found in template or execution'
        }

    matches = []

    for tmpl_script in template_scripts:
        # Extract keywords (commands, not variables/expressions)
        # Remove Harness expressions first
        tmpl_clean = re.sub(r'<\+[^>]+>', '', tmpl_script)
        tmpl_clean = re.sub(r'\$\{[^}]+\}', '', tmpl_clean)

        # Extract command keywords (ignore variable assignments)
        tmpl_keywords = set(re.findall(r'\b[a-zA-Z_][\w-]*\b', tmpl_clean))
        # Filter out common shell keywords and short words
        tmpl_keywords = {k for k in tmpl_keywords if len(k) > 2 and k not in {
            'if', 'then', 'else', 'fi', 'for', 'do', 'done', 'while', 'case', 'esac',
            'echo', 'set', 'export', 'env', 'var', 'let', 'read'
        }}

        if not tmpl_keywords:
            continue

        best_match = None
        best_similarity = 0

        for exec_script in execution_scripts:
            # Clean execution script
            exec_clean = re.sub(r'<\+[^>]+>', '', exec_script)
            exec_clean = re.sub(r'\$\{[^}]+\}', '', exec_clean)

            # Extract keywords
            exec_keywords = set(re.findall(r'\b[a-zA-Z_][\w-]*\b', exec_clean))
            exec_keywords = {k for k in exec_keywords if len(k) > 2 and k not in {
                'if', 'then', 'else', 'fi', 'for', 'do', 'done', 'while', 'case', 'esac',
                'echo', 'set', 'export', 'env', 'var', 'let', 'read'
            }}

            if not exec_keywords:
                continue

            # Calculate similarity
            common = tmpl_keywords & exec_keywords
            total = tmpl_keywords | exec_keywords
            similarity = len(common) / len(total) if total else 0

            if similarity > best_similarity:
                best_similarity = similarity
                best_match = {
                    'template_script': tmpl_script[:80],
                    'execution_script': exec_script[:80],
                    'similarity': similarity,
                    'common_keywords': list(common)[:5],
                    'template_keywords': list(tmpl_keywords)[:5],
                    'execution_keywords': list(exec_keywords)[:5]
                }

        if best_match:
            matches.append(best_match)

    if not matches:
        return {
            'matched': False,
            'reason': 'No script matches found'
        }

    # Calculate average similarity
    avg_similarity = sum(m['similarity'] for m in matches) / len(matches)

    # Find lowest similarity match (most concerning)
    worst_match = min(matches, key=lambda m: m['similarity'])

    return {
        'matched': avg_similarity >= threshold,
        'average_similarity': avg_similarity,
        'worst_match': worst_match,
        'total_matches': len(matches),
        'threshold': threshold
    }


def validate_scripts(
    template_yaml: dict,
    execution_yaml: dict,
    template_id: str,
    threshold: float = 0.5
) -> Dict[str, Any]:
    """Validate scripts/commands match between template and execution.

    Args:
        template_yaml: Template YAML dictionary
        execution_yaml: Execution YAML dictionary
        template_id: Template identifier for logging
        threshold: Similarity threshold (0.0-1.0)

    Returns:
        dict: Script validation results
    """
    # Extract template spec
    template_spec = template_yaml.get('template', {}).get('spec', {})

    # Extract scripts
    template_scripts = extract_scripts_from_yaml(template_spec)
    execution_scripts = extract_scripts_from_yaml(execution_yaml)

    if not template_scripts:
        return {
            'validated': True,
            'reason': 'No scripts in template to validate'
        }

    # Fuzzy match
    match_result = fuzzy_match_scripts(template_scripts, execution_scripts, threshold)

    result = {
        'validated': match_result.get('matched', False),
        'average_similarity': match_result.get('average_similarity', 0),
        'script_count': len(template_scripts)
    }

    # Add warning details if similarity is low
    if not match_result.get('matched', False):
        result['warning'] = match_result.get('reason', 'Scripts do not match')
        if 'worst_match' in match_result:
            worst = match_result['worst_match']
            result['worst_match_similarity'] = worst['similarity']
            result['template_script_sample'] = worst['template_script']
            result['execution_script_sample'] = worst['execution_script']

    return result


# ============================================================================
# Tier Snapshot Management Functions
# ============================================================================

def get_tier_snapshots(
    versions: dict,
    tmpl_type: str,
    identifier: str
) -> Dict[str, str]:
    """Get tier snapshots for a template.

    Args:
        versions: Parsed versions.yaml data
        tmpl_type: Template type (pipeline, stage, step_group, step)
        identifier: Template identifier

    Returns:
        dict: Tier snapshots mapping (e.g., {"tier-1": "v1.4", "tier-2": "v1.3"})
    """
    templates = versions.get('templates', {}).get(tmpl_type, {}).get(identifier, {})
    return templates.get('tier_snapshots', {})


def update_tier_snapshot(
    versions: dict,
    tmpl_type: str,
    identifier: str,
    tier_label: str,
    semantic_version: str
) -> None:
    """Update tier snapshot for a template.

    Args:
        versions: Parsed versions.yaml data (modified in place)
        tmpl_type: Template type (pipeline, stage, step_group, step)
        identifier: Template identifier
        tier_label: Tier label (e.g., "tier-1", "tier-2")
        semantic_version: Semantic version (e.g., "v1.4")
    """
    # Ensure template structure exists
    if 'templates' not in versions:
        versions['templates'] = {}
    if tmpl_type not in versions['templates']:
        versions['templates'][tmpl_type] = {}
    if identifier not in versions['templates'][tmpl_type]:
        versions['templates'][tmpl_type][identifier] = {'versions': []}

    template = versions['templates'][tmpl_type][identifier]

    # Ensure tier_snapshots dict exists
    if 'tier_snapshots' not in template:
        template['tier_snapshots'] = {}

    # Update tier snapshot
    template['tier_snapshots'][tier_label] = semantic_version

    logger.info(f"✓ Updated {identifier} {tier_label} → {semantic_version}")


def remove_tier_snapshot(
    versions: dict,
    tmpl_type: str,
    identifier: str,
    tier_label: str
) -> bool:
    """Remove tier snapshot for a template.

    Args:
        versions: Parsed versions.yaml data (modified in place)
        tmpl_type: Template type
        identifier: Template identifier
        tier_label: Tier label to remove

    Returns:
        bool: True if removed, False if not found
    """
    try:
        template = versions['templates'][tmpl_type][identifier]
        if tier_label in template.get('tier_snapshots', {}):
            del template['tier_snapshots'][tier_label]
            logger.info(f"✓ Removed {identifier} {tier_label}")
            return True
    except KeyError:
        pass

    return False


def validate_tier_number(tier: int) -> None:
    """Validate tier number is in valid range (1-5).

    Args:
        tier: Tier number

    Raises:
        ValueError: If tier is invalid
    """
    if not isinstance(tier, int):
        raise ValueError(f"Tier must be an integer, got {type(tier)}")

    if tier < 1 or tier > 5:
        raise ValueError(
            f"Tier must be between 1 and 5, got {tier}. "
            f"Tier 5 is the maximum (stable)."
        )


def parse_tier_label(tier_label: str) -> int:
    """Parse tier label to extract tier number.

    Supports formats: "tier-1", "tier1", "1"

    Args:
        tier_label: Tier label string

    Returns:
        int: Tier number (1-5)

    Raises:
        ValueError: If tier label format is invalid
    """
    # Handle numeric string
    if tier_label.isdigit():
        tier = int(tier_label)
        validate_tier_number(tier)
        return tier

    # Handle tier-N format
    if tier_label.startswith('tier-'):
        tier_str = tier_label[5:]  # Remove "tier-" prefix
        if tier_str.isdigit():
            tier = int(tier_str)
            validate_tier_number(tier)
            return tier

    # Handle tierN format
    if tier_label.startswith('tier') and len(tier_label) > 4:
        tier_str = tier_label[4:]  # Remove "tier" prefix
        if tier_str.isdigit():
            tier = int(tier_str)
            validate_tier_number(tier)
            return tier

    raise ValueError(
        f"Invalid tier label format: '{tier_label}'. "
        f"Expected 'tier-1', 'tier1', or '1'"
    )


def format_tier_label(tier: int) -> str:
    """Format tier number as standard label.

    Args:
        tier: Tier number (1-5)

    Returns:
        str: Formatted tier label (e.g., "tier-1")
    """
    validate_tier_number(tier)
    return f"tier-{tier}"


def get_tier_name(tier: int) -> str:
    """Get human-readable tier name.

    Args:
        tier: Tier number (1-5)

    Returns:
        str: Tier name
    """
    tier_names = {
        1: "Tier 1 (Canary)",
        2: "Tier 2 (Early Adopters)",
        3: "Tier 3 (Wave 1)",
        4: "Tier 4 (Wave 2)",
        5: "Tier 5 (Stable)"
    }
    return tier_names.get(tier, f"Tier {tier}")


def find_templates_at_tier(
    versions: dict,
    tier: int
) -> List[Dict[str, str]]:
    """Find all templates at a specific tier.

    Args:
        versions: Parsed versions.yaml data
        tier: Tier number to search for

    Returns:
        list: List of dicts with 'type', 'identifier', 'semantic_version' keys
    """
    tier_label = format_tier_label(tier)
    templates_at_tier = []

    for tmpl_type, templates in versions.get('templates', {}).items():
        for identifier, data in templates.items():
            tier_snapshots = data.get('tier_snapshots', {})
            if tier_label in tier_snapshots:
                templates_at_tier.append({
                    'type': tmpl_type,
                    'identifier': identifier,
                    'semantic_version': tier_snapshots[tier_label],
                    'tier_label': tier_label
                })

    return templates_at_tier


def get_template_tier_range(
    versions: dict,
    tmpl_type: str,
    identifier: str
) -> tuple:
    """Get the tier range for a template (min, max).

    Args:
        versions: Parsed versions.yaml data
        tmpl_type: Template type
        identifier: Template identifier

    Returns:
        tuple: (min_tier, max_tier) or (None, None) if no tiers exist
    """
    tier_snapshots = get_tier_snapshots(versions, tmpl_type, identifier)

    if not tier_snapshots:
        return (None, None)

    # Extract tier numbers from tier labels
    tier_numbers = []
    for tier_label in tier_snapshots.keys():
        try:
            tier_numbers.append(parse_tier_label(tier_label))
        except ValueError:
            continue

    if not tier_numbers:
        return (None, None)

    return (min(tier_numbers), max(tier_numbers))


def get_highest_tier_below(
    versions: dict,
    tmpl_type: str,
    identifier: str,
    target_tier: int
) -> Optional[int]:
    """Find the highest tier below target tier that exists for a template.

    Used for tier-skip functionality.

    Args:
        versions: Parsed versions.yaml data
        tmpl_type: Template type
        identifier: Template identifier
        target_tier: Target tier number

    Returns:
        int: Highest tier below target, or None if none exist
    """
    tier_snapshots = get_tier_snapshots(versions, tmpl_type, identifier)

    if not tier_snapshots:
        return None

    # Get all tiers below target
    tiers_below = []
    for tier_label in tier_snapshots.keys():
        try:
            tier = parse_tier_label(tier_label)
            if tier < target_tier:
                tiers_below.append(tier)
        except ValueError:
            continue

    if not tiers_below:
        return None

    return max(tiers_below)
