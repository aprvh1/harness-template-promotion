"""Utility functions for template validation and operations.

This module contains all validation, parsing, and utility functions
ported from the original scripts/common.py.
"""

import re
import logging
import hashlib
from dataclasses import dataclass
from typing import Optional, List, Any, Dict, Tuple
import yaml


logger = logging.getLogger(__name__)


# ============================================================================
# Data Classes
# ============================================================================


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


# ============================================================================
# YAML Template Reference Extraction
# ============================================================================


def extract_template_refs(yaml_dict: Dict, path: str = "root") -> List[TemplateRef]:
    """Extract all template references from YAML dictionary.

    Args:
        yaml_dict: Parsed YAML dictionary
        path: Current path in YAML tree (for debugging)

    Returns:
        List of TemplateRef objects found in YAML
    """
    refs = []

    if isinstance(yaml_dict, dict):
        # Check if this node has a templateRef
        if "templateRef" in yaml_dict:
            template_id = yaml_dict["templateRef"]
            version_label = yaml_dict.get("versionLabel")
            refs.append(TemplateRef(
                identifier=template_id,
                version_label=version_label,
                path=path
            ))

        # Recurse into nested dictionaries
        for key, value in yaml_dict.items():
            if isinstance(value, (dict, list)):
                refs.extend(extract_template_refs(value, f"{path}.{key}"))

    elif isinstance(yaml_dict, list):
        # Recurse into list items
        for i, item in enumerate(yaml_dict):
            if isinstance(item, (dict, list)):
                refs.extend(extract_template_refs(item, f"{path}[{i}]"))

    return refs


# ============================================================================
# YAML Validation Functions
# ============================================================================


def validate_template_in_pipeline_yaml(
    template_id: str,
    pipeline_yaml: str,
    expected_version: Optional[str] = None,
    verbose: bool = False
) -> Dict[str, Any]:
    """Validate template is referenced in pipeline YAML with correct version.

    Args:
        template_id: Template identifier to check
        pipeline_yaml: Pipeline YAML string
        expected_version: Expected version label (optional)
        verbose: Enable detailed logging (default: False)

    Returns:
        Dict with validation results:
        - found: bool
        - reference_count: int
        - locations: List[str]
        - versions: List[str] - versions found for each reference
        - version_match: bool - True if expected_version matches (if provided)
    """
    try:
        # Parse pipeline YAML
        pipeline_dict = yaml.safe_load(pipeline_yaml)

        # Extract all template refs
        all_refs = extract_template_refs(pipeline_dict)

        # Filter for target template
        matching_refs = [ref for ref in all_refs if ref.identifier == template_id]

        # Extract versions
        versions = [ref.version_label for ref in matching_refs]

        # Check version match if expected version provided
        version_match = True
        if expected_version:
            version_match = all(v == expected_version for v in versions if v is not None)

        # Verbose logging
        if verbose:
            logger.info(f"Level 1: Template Reference Validation")
            if matching_refs:
                logger.info(f"  ✓ Found {len(matching_refs)} reference(s) to {template_id} in pipeline YAML")
                for i, ref in enumerate(matching_refs, 1):
                    version_str = ref.version_label if ref.version_label else "no version"
                    logger.info(f"  → Location {i}: {ref.path} (version: {version_str})")
                if expected_version:
                    if version_match:
                        logger.info(f"  ✓ All references use expected version: {expected_version}")
                    else:
                        logger.warning(f"  ✗ Version mismatch! Expected: {expected_version}, Found: {versions}")
            else:
                logger.warning(f"  ✗ Template {template_id} not found in pipeline YAML")

        return {
            "found": len(matching_refs) > 0,
            "reference_count": len(matching_refs),
            "locations": [ref.path for ref in matching_refs],
            "versions": versions,
            "version_match": version_match
        }

    except Exception as e:
        logger.error(f"Error validating template in pipeline YAML: {e}")
        return {
            "found": False,
            "reference_count": 0,
            "locations": [],
            "versions": [],
            "version_match": False,
            "error": str(e)
        }


# Keys to ignore during comparison (contain runtime values)
IGNORE_KEYS = {
    'uuid', 'when', 'startTs', 'endTs', 'status', 'executionUrl',
    'createdAt', 'lastUpdatedAt', 'nodeExecutionId', 'planExecutionId'
}


def normalize_value(value: Any) -> Any:
    """Normalize a value for comparison.

    Args:
        value: Value to normalize

    Returns:
        Normalized value
    """
    if isinstance(value, str):
        # Normalize whitespace
        return ' '.join(value.split())
    elif isinstance(value, (int, float, bool)):
        return value
    elif value is None:
        return None
    elif isinstance(value, dict):
        return normalize_yaml_for_comparison(value)
    elif isinstance(value, list):
        return [normalize_value(item) for item in value]
    else:
        return str(value)


def normalize_yaml_for_comparison(yaml_dict: Dict) -> Dict:
    """Normalize YAML dictionary for comparison.

    Removes runtime-specific fields and normalizes values.

    Args:
        yaml_dict: YAML dictionary to normalize

    Returns:
        Normalized dictionary
    """
    if not isinstance(yaml_dict, dict):
        return yaml_dict

    normalized = {}
    for key, value in yaml_dict.items():
        # Skip ignored keys
        if key in IGNORE_KEYS:
            continue

        # Recursively normalize nested structures
        if isinstance(value, dict):
            normalized[key] = normalize_yaml_for_comparison(value)
        elif isinstance(value, list):
            normalized[key] = [
                normalize_yaml_for_comparison(item) if isinstance(item, dict) else normalize_value(item)
                for item in value
            ]
        else:
            normalized[key] = normalize_value(value)

    return normalized


def compare_structures(template_dict: Dict, execution_dict: Dict, path: str = "root") -> Tuple[int, int]:
    """Compare template and execution structures.

    Args:
        template_dict: Normalized template dictionary
        execution_dict: Normalized execution dictionary
        path: Current path in structure

    Returns:
        Tuple of (matching_keys, total_keys)
    """
    if not isinstance(template_dict, dict) or not isinstance(execution_dict, dict):
        return (0, 0)

    matching = 0
    total = len(template_dict)

    for key, template_value in template_dict.items():
        if key in execution_dict:
            execution_value = execution_dict[key]

            if isinstance(template_value, dict) and isinstance(execution_value, dict):
                # Recursively compare nested dicts
                sub_match, sub_total = compare_structures(template_value, execution_value, f"{path}.{key}")
                matching += sub_match
                total += sub_total
            elif template_value == execution_value:
                matching += 1

    return (matching, total)


def extract_template_content(template_yaml: Dict) -> Dict:
    """Extract the actual content from a template (spec part).

    Args:
        template_yaml: Full template YAML

    Returns:
        The template's spec content
    """
    if 'template' in template_yaml:
        # Template wrapper exists, extract spec
        return template_yaml['template'].get('spec', {})
    return template_yaml


def search_and_compare_blocks(template_content: Dict, execution_dict: Dict, path: str = "root") -> Tuple[int, int, List[str]]:
    """Recursively search execution for blocks matching template content.

    Args:
        template_content: Template spec to find
        execution_dict: Execution YAML to search in
        path: Current path in execution

    Returns:
        Tuple of (best_matching_keys, total_template_keys, match_locations)
    """
    if not isinstance(template_content, dict) or not isinstance(execution_dict, dict):
        return (0, 0, [])

    # Normalize both
    norm_template = normalize_yaml_for_comparison(template_content)
    norm_execution = normalize_yaml_for_comparison(execution_dict)

    # Try comparing at current level
    matching, total = compare_structures(norm_template, norm_execution)
    best_match = matching
    best_total = total
    match_locations = []

    if matching > 0:
        match_locations.append(f"{path} ({matching}/{total})")

    # Recursively search in nested dicts
    for key, value in execution_dict.items():
        if isinstance(value, dict):
            sub_match, sub_total, sub_locs = search_and_compare_blocks(template_content, value, f"{path}.{key}")
            if sub_match > best_match:
                best_match = sub_match
                best_total = sub_total
                match_locations = sub_locs
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    sub_match, sub_total, sub_locs = search_and_compare_blocks(template_content, item, f"{path}.{key}[{i}]")
                    if sub_match > best_match:
                        best_match = sub_match
                        best_total = sub_total
                        match_locations = sub_locs

    return (best_match, best_total, match_locations)


def validate_template_structure_in_execution_yaml(
    template_yaml: Dict,
    execution_yaml: str,
    template_id: str,
    verbose: bool = False
) -> Dict[str, Any]:
    """Validate template structure appears in execution YAML.

    Searches through execution YAML to find where template blocks exist.

    Args:
        template_yaml: Template YAML dictionary
        execution_yaml: Execution YAML string
        template_id: Template identifier
        verbose: Enable detailed logging (default: False)

    Returns:
        Dict with validation results:
        - found: bool
        - match_percentage: float
        - matching_keys: int
        - total_keys: int
        - match_locations: List[str]
    """
    try:
        # Parse execution YAML
        execution_dict = yaml.safe_load(execution_yaml)

        # Extract template content (spec part, not wrapper)
        template_content = extract_template_content(template_yaml)

        # Search execution for best matching block
        matching, total, locations = search_and_compare_blocks(template_content, execution_dict)

        match_percentage = (matching / total * 100) if total > 0 else 0

        # Verbose logging
        if verbose:
            logger.info(f"Level 2: Structure Validation")
            if match_percentage > 30:
                logger.info(f"  ✓ Found matching template structure in execution YAML")
                logger.info(f"  → Match percentage: {match_percentage:.1f}% ({matching}/{total} keys matched)")
                if locations:
                    logger.info(f"  → Locations: {', '.join(locations[:3])}")  # Show first 3 locations
                logger.info(f"  ✓ Structure validation passed (threshold: 30%)")
            else:
                logger.warning(f"  ✗ Structure match too low: {match_percentage:.1f}% < 30%")

        return {
            "found": match_percentage > 30,  # At least 30% match
            "match_percentage": match_percentage,
            "matching_keys": matching,
            "total_keys": total,
            "match_locations": locations
        }

    except Exception as e:
        logger.error(f"Error validating template structure: {e}")
        return {
            "found": False,
            "match_percentage": 0,
            "matching_keys": 0,
            "total_keys": 0,
            "error": str(e)
        }


def find_best_matching_block(template_content: Dict, execution_dict: Dict) -> Optional[Dict]:
    """Find the block in execution that best matches template content.

    Args:
        template_content: Template spec to find
        execution_dict: Execution YAML to search in

    Returns:
        Best matching block or None
    """
    if not isinstance(execution_dict, dict):
        return None

    # Try current level
    norm_template = normalize_yaml_for_comparison(template_content)
    norm_execution = normalize_yaml_for_comparison(execution_dict)
    matching, total = compare_structures(norm_template, norm_execution)

    best_match = matching
    best_block = execution_dict if matching > 0 else None

    # Recursively search
    for key, value in execution_dict.items():
        if isinstance(value, dict):
            sub_block = find_best_matching_block(template_content, value)
            if sub_block:
                norm_sub = normalize_yaml_for_comparison(sub_block)
                sub_matching, _ = compare_structures(norm_template, norm_sub)
                if sub_matching > best_match:
                    best_match = sub_matching
                    best_block = sub_block
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    sub_block = find_best_matching_block(template_content, item)
                    if sub_block:
                        norm_sub = normalize_yaml_for_comparison(sub_block)
                        sub_matching, _ = compare_structures(norm_template, norm_sub)
                        if sub_matching > best_match:
                            best_match = sub_matching
                            best_block = sub_block

    return best_block


def extract_comparable_items(yaml_dict: Dict, path: str = "root") -> List[tuple]:
    """Extract items from YAML that can be directly compared (skip templateRef items).

    Args:
        yaml_dict: YAML dictionary
        path: Current path

    Returns:
        List of (path, normalized_item) tuples for comparable items
    """
    items = []

    if not isinstance(yaml_dict, dict):
        return items

    # If this dict has a templateRef, skip it (will be expanded in execution)
    if 'templateRef' in yaml_dict:
        return items

    # If this is a step, stage, or other comparable unit, add it
    if any(key in yaml_dict for key in ['step', 'stage', 'stepGroup', 'parallel']):
        norm = normalize_yaml_for_comparison(yaml_dict)
        items.append((path, norm))

    # Recurse into nested structures
    for key, value in yaml_dict.items():
        if isinstance(value, dict):
            items.extend(extract_comparable_items(value, f"{path}.{key}"))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    items.extend(extract_comparable_items(item, f"{path}.{key}[{i}]"))

    return items


def validate_content_hash(
    template_yaml: Dict,
    execution_yaml: str,
    template_id: str,
    verbose: bool = False
) -> Dict[str, Any]:
    """Validate template content hash by comparing individual comparable items.

    Extracts items from template that don't have templateRef and compares their
    hashes with corresponding items in execution.

    Args:
        template_yaml: Template YAML dictionary
        execution_yaml: Execution YAML string
        template_id: Template identifier
        verbose: Enable detailed logging (default: False)

    Returns:
        Dict with validation results:
        - found: bool
        - hash_match: bool
        - items_compared: int
        - items_matched: int
        - match_percentage: float
    """
    try:
        # Extract template content (spec part)
        template_content = extract_template_content(template_yaml)

        # Parse execution and find best matching block
        execution_dict = yaml.safe_load(execution_yaml)
        matching_block = find_best_matching_block(template_content, execution_dict)

        if not matching_block:
            matching_block = execution_dict

        # Extract comparable items from template (skip templateRef items)
        template_items = extract_comparable_items(template_content)

        # Extract comparable items from execution
        execution_items = extract_comparable_items(matching_block)

        if not template_items:
            # Fallback to full block comparison if no items found
            norm_template = normalize_yaml_for_comparison(template_content)
            norm_execution = normalize_yaml_for_comparison(matching_block)

            template_str = yaml.dump(norm_template, sort_keys=True)
            execution_str = yaml.dump(norm_execution, sort_keys=True)

            template_hash = hashlib.sha256(template_str.encode()).hexdigest()[:12]
            execution_hash = hashlib.sha256(execution_str.encode()).hexdigest()[:12]

            return {
                "found": True,
                "hash_match": template_hash == execution_hash,
                "template_hash": template_hash,
                "execution_hash": execution_hash,
                "items_compared": 0,
                "items_matched": 0,
                "match_percentage": 0
            }

        # Compare items by hash
        template_hashes = {}
        for path, norm_item in template_items:
            item_str = yaml.dump(norm_item, sort_keys=True)
            item_hash = hashlib.sha256(item_str.encode()).hexdigest()[:12]
            template_hashes[item_hash] = path

        execution_hashes = {}
        for path, norm_item in execution_items:
            item_str = yaml.dump(norm_item, sort_keys=True)
            item_hash = hashlib.sha256(item_str.encode()).hexdigest()[:12]
            execution_hashes[item_hash] = path

        # Count matches
        matched_hashes = set(template_hashes.keys()) & set(execution_hashes.keys())
        items_compared = len(template_items)
        items_matched = len(matched_hashes)
        match_percentage = (items_matched / items_compared * 100) if items_compared > 0 else 0

        # Create summary hash from all template items
        all_template_str = yaml.dump([item for _, item in template_items], sort_keys=True)
        template_hash = hashlib.sha256(all_template_str.encode()).hexdigest()[:12]

        # Verbose logging
        if verbose:
            logger.info(f"Level 3: Content Hash Validation")
            logger.info(f"  ✓ Comparing {items_compared} items without template references")
            if items_matched == items_compared:
                logger.info(f"  → All {items_compared} items matched!")
                logger.info(f"  ✓ Content hash validation: 100% ({items_matched}/{items_compared} items matched)")
            else:
                for i in range(min(3, items_matched)):  # Show first 3 matches
                    logger.info(f"  → Item {i+1}: hash matched")
                if items_matched > 3:
                    logger.info(f"  → ... ({items_matched - 3} more items matched)")
                if items_compared > items_matched:
                    logger.warning(f"  ✗ {items_compared - items_matched} item(s) did not match")
                logger.info(f"  → Content hash validation: {match_percentage:.1f}% ({items_matched}/{items_compared} items matched)")

        return {
            "found": True,
            "hash_match": match_percentage == 100,
            "template_hash": template_hash,
            "items_compared": items_compared,
            "items_matched": items_matched,
            "match_percentage": match_percentage
        }

    except Exception as e:
        logger.error(f"Error validating content hash: {e}")
        return {
            "found": False,
            "hash_match": False,
            "error": str(e)
        }


def extract_scripts_from_yaml(yaml_dict: Dict, path: str = "root") -> List[Dict[str, str]]:
    """Extract all script content from YAML.

    Args:
        yaml_dict: YAML dictionary
        path: Current path

    Returns:
        List of dicts with script content and location
    """
    scripts = []

    if isinstance(yaml_dict, dict):
        # Check for script fields
        if "script" in yaml_dict and isinstance(yaml_dict["script"], str):
            scripts.append({
                "content": yaml_dict["script"],
                "path": f"{path}.script"
            })

        # Recurse
        for key, value in yaml_dict.items():
            if isinstance(value, (dict, list)):
                scripts.extend(extract_scripts_from_yaml(value, f"{path}.{key}"))

    elif isinstance(yaml_dict, list):
        for i, item in enumerate(yaml_dict):
            if isinstance(item, (dict, list)):
                scripts.extend(extract_scripts_from_yaml(item, f"{path}[{i}]"))

    return scripts


def fuzzy_match_scripts(template_script: str, execution_script: str) -> float:
    """Fuzzy match two scripts.

    Args:
        template_script: Template script content
        execution_script: Execution script content

    Returns:
        Match percentage (0-100)
    """
    # Normalize whitespace
    template_lines = [line.strip() for line in template_script.split('\n') if line.strip()]
    execution_lines = [line.strip() for line in execution_script.split('\n') if line.strip()]

    if not template_lines or not execution_lines:
        return 0.0

    # Count matching lines
    matching = 0
    for template_line in template_lines:
        if template_line in execution_lines:
            matching += 1

    return (matching / len(template_lines)) * 100


def validate_scripts(
    template_yaml: Dict,
    execution_yaml: str,
    template_id: str,
    threshold: float = 80.0,
    verbose: bool = False
) -> Dict[str, Any]:
    """Validate scripts in template match execution.

    Args:
        template_yaml: Template YAML dictionary
        execution_yaml: Execution YAML string
        template_id: Template identifier
        threshold: Minimum match percentage (default 80%)
        verbose: Enable detailed logging (default: False)

    Returns:
        Dict with validation results:
        - found: bool
        - scripts_validated: int
        - avg_match_percentage: float
        - all_above_threshold: bool
    """
    try:
        # Extract scripts from both
        template_scripts = extract_scripts_from_yaml(template_yaml)
        execution_dict = yaml.safe_load(execution_yaml)
        execution_scripts = extract_scripts_from_yaml(execution_dict)

        if not template_scripts:
            return {
                "found": True,
                "scripts_validated": 0,
                "avg_match_percentage": 100.0,
                "all_above_threshold": True,
                "message": "No scripts to validate"
            }

        # Match scripts
        match_percentages = []
        for tmpl_script in template_scripts:
            best_match = 0.0
            for exec_script in execution_scripts:
                match_pct = fuzzy_match_scripts(
                    tmpl_script["content"],
                    exec_script["content"]
                )
                best_match = max(best_match, match_pct)
            match_percentages.append(best_match)

        avg_match = sum(match_percentages) / len(match_percentages) if match_percentages else 0.0
        all_above = all(m >= threshold for m in match_percentages)

        # Verbose logging
        if verbose:
            logger.info(f"Level 4: Script Validation")
            logger.info(f"  ✓ Found {len(template_scripts)} script(s) in template")
            for i, (script, match_pct) in enumerate(zip(template_scripts, match_percentages), 1):
                # Truncate script content for display
                script_preview = script["content"][:50].replace('\n', ' ')
                if len(script["content"]) > 50:
                    script_preview += "..."
                logger.info(f"  → Script {i}: {match_pct:.1f}% match ({script_preview})")
            if all_above:
                logger.info(f"  ✓ All scripts above threshold ({threshold}%)")
            else:
                below_count = sum(1 for m in match_percentages if m < threshold)
                logger.warning(f"  ✗ {below_count} script(s) below threshold")

        return {
            "found": True,
            "scripts_validated": len(template_scripts),
            "avg_match_percentage": avg_match,
            "all_above_threshold": all_above,
            "threshold": threshold
        }

    except Exception as e:
        logger.error(f"Error validating scripts: {e}")
        return {
            "found": False,
            "scripts_validated": 0,
            "avg_match_percentage": 0.0,
            "all_above_threshold": False,
            "error": str(e)
        }


# ============================================================================
# Tier Management Functions
# ============================================================================


# ============================================================================
# Template Reference Qualification
# ============================================================================


def qualify_template_refs(yaml_dict: Dict, prefix: str = "account") -> Dict:
    """Add scope prefix to all template references.

    Args:
        yaml_dict: YAML dictionary to modify
        prefix: Scope prefix (account, org, project)

    Returns:
        Modified YAML dictionary
    """
    if isinstance(yaml_dict, dict):
        # Qualify templateRef if present
        if "templateRef" in yaml_dict and isinstance(yaml_dict["templateRef"], str):
            ref = yaml_dict["templateRef"]
            if not ref.startswith(('account.', 'org.', 'project.')):
                yaml_dict["templateRef"] = f"{prefix}.{ref}"

        # Recurse
        for key, value in yaml_dict.items():
            if isinstance(value, (dict, list)):
                yaml_dict[key] = qualify_template_refs(value, prefix)

    elif isinstance(yaml_dict, list):
        yaml_dict = [qualify_template_refs(item, prefix) if isinstance(item, (dict, list)) else item for item in yaml_dict]

    return yaml_dict


def remove_scope_identifiers(yaml_dict: Dict) -> Dict:
    """Remove projectIdentifier and orgIdentifier from template.

    Args:
        yaml_dict: Template YAML dictionary

    Returns:
        Modified YAML dictionary
    """
    if isinstance(yaml_dict, dict):
        if 'template' in yaml_dict:
            if 'projectIdentifier' in yaml_dict['template']:
                del yaml_dict['template']['projectIdentifier']
            if 'orgIdentifier' in yaml_dict['template']:
                del yaml_dict['template']['orgIdentifier']

    return yaml_dict


def add_template_tags(yaml_dict: Dict, tags: Dict[str, str]) -> Dict:
    """Add tags to template YAML.

    Args:
        yaml_dict: Template YAML dictionary
        tags: Tags to add

    Returns:
        Modified YAML dictionary
    """
    if isinstance(yaml_dict, dict) and 'template' in yaml_dict:
        if 'tags' not in yaml_dict['template']:
            yaml_dict['template']['tags'] = {}
        yaml_dict['template']['tags'].update(tags)

    return yaml_dict


def update_template_version_label(yaml_dict: Dict, new_version: str) -> Dict:
    """Update the template's own versionLabel.

    Args:
        yaml_dict: Template YAML dictionary
        new_version: New version label (e.g., "tier-1", "tier-2")

    Returns:
        Modified YAML dictionary with updated versionLabel
    """
    if isinstance(yaml_dict, dict) and 'template' in yaml_dict:
        yaml_dict['template']['versionLabel'] = new_version

    return yaml_dict


def update_child_template_versions(yaml_dict: Dict, version_mapping: Dict[str, str]) -> Dict:
    """Update versionLabel in child template references.

    Recursively walks the YAML and updates versionLabel for templates
    that are being promoted together.

    Args:
        yaml_dict: Template YAML dictionary
        version_mapping: Dict mapping template identifier to new version
                        e.g., {"Stage_Template": "tier-1", "SG_Template": "tier-1"}

    Returns:
        Modified YAML dictionary with updated child template versions
    """
    def _update_refs(obj: Any) -> Any:
        """Recursively update template references."""
        if isinstance(obj, dict):
            # Check if this is a template reference
            if 'template' in obj and isinstance(obj['template'], dict):
                template_block = obj['template']

                # Extract templateRef (could be just identifier or account.identifier)
                if 'templateRef' in template_block:
                    ref = template_block['templateRef']

                    # Remove scope prefix to get identifier
                    identifier = ref.split('.')[-1]  # account.Step -> Step

                    # If this template is in our mapping, update its version
                    if identifier in version_mapping:
                        template_block['versionLabel'] = version_mapping[identifier]

            # Recurse into all dict values
            return {k: _update_refs(v) for k, v in obj.items()}

        elif isinstance(obj, list):
            # Recurse into all list items
            return [_update_refs(item) for item in obj]

        else:
            # Leave primitives unchanged
            return obj

    return _update_refs(yaml_dict)


def remove_child_template_version_labels(yaml_dict: Dict) -> Dict:
    """Remove versionLabel from all child template references.

    Used when promoting to stable - child templates should have no versionLabel
    so they default to stable versions.

    Args:
        yaml_dict: Template YAML dictionary

    Returns:
        Updated YAML dictionary with versionLabel removed from all template refs
    """
    def _remove_version_labels(obj, is_root=False):
        """Recursively walk YAML and remove versionLabel from template blocks."""
        if isinstance(obj, dict):
            # Check if this is a CHILD template reference (not the root template definition)
            # Child refs have both 'template' key AND 'templateRef' inside
            if 'template' in obj and isinstance(obj['template'], dict) and not is_root:
                template_block = obj['template']

                # Only remove versionLabel if this is a reference (has templateRef)
                if 'templateRef' in template_block and 'versionLabel' in template_block:
                    del template_block['versionLabel']

            # Recurse into all dict values (skip root on first level)
            if is_root:
                # For root, recurse but mark children as non-root
                return {k: _remove_version_labels(v, is_root=False) if k != 'template' else v
                        for k, v in obj.items()}
            else:
                return {k: _remove_version_labels(v, is_root=False) for k, v in obj.items()}

        elif isinstance(obj, list):
            # Recurse into all list items
            return [_remove_version_labels(item, is_root=False) for item in obj]

        else:
            # Leave primitives unchanged
            return obj

    return _remove_version_labels(yaml_dict, is_root=True)
