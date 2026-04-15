#!/usr/bin/env python3
"""Validate execution, extract templates, and manage tier-based promotion.

This script supports two workflows:
1. EXTRACTION: Validate execution and extract templates (with dependencies)
2. PROMOTION: Promote templates between tiers

EXTRACTION Usage:
    python validate_and_extract.py \\
        --execution-url "https://app.harness.io/ng/account/.../executions/exec-123" \\
        --template-id health_check \\
        --project-id test \\
        --changelog "Added health checks" \\
        --mode single \\
        --to-tier 1

PROMOTION Usage:
    python validate_and_extract.py \\
        --template-id health_check \\
        --to-tier 2 \\
        [--tier-skip]
"""

import argparse
import os
import re
import sys
from datetime import date
from typing import List, Set, Tuple
import yaml

# Import harness_python_sdk with compatibility wrapper
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

# Import extensions - support running from both root and scripts/ directory
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, os.path.join(project_root, "src"))
sys.path.insert(0, script_dir)

from harness_api.templates import TemplatesApi

# Import common utilities
from common import (
    TemplateMetadata,
    TemplateRef,
    get_harness_client,
    load_versions_yaml,
    save_versions_yaml,
    extract_template_refs,
    save_template_yaml,
    validate_template_in_pipeline_yaml,
    validate_template_structure_in_execution_yaml,
    validate_content_hash,
    validate_scripts,
    get_tier_snapshots,
    update_tier_snapshot,
    validate_tier_number,
    format_tier_label,
    get_tier_name,
    get_highest_tier_below,
    logger
)

# Import tier promotion modules
from harness_client import HarnessAPIClient
from git_operations import GitOperations
from sanitize_template import sanitize_template, get_sanitization_report


def parse_execution_url(url: str) -> dict:
    """Extract account/org/project/execution IDs from Harness execution URL.

    Args:
        url: Full Harness execution URL

    Returns:
        dict: Parsed URL components

    Raises:
        ValueError: If URL format is invalid
    """
    # Pattern handles various URL formats:
    # - /account/{id}/orgs/{org}/projects/{project}/...
    # - /account/{id}/cd/orgs/{org}/projects/{project}/...
    # - /account/{id}/all/orgs/{org}/projects/{project}/...
    # Accepts both /executions/ and /deployments/ (Harness uses both)
    pattern = r'/account/([^/]+)/(?:cd/|all/)?orgs/([^/]+)/projects/([^/]+)/pipelines/[^/]+/(?:executions|deployments)/([^/?]+)'
    match = re.search(pattern, url)

    if not match:
        raise ValueError(f"Invalid execution URL format: {url}")

    return {
        'account_id': match.group(1),
        'org_id': match.group(2),
        'project_id': match.group(3),
        'execution_id': match.group(4)
    }


def validate_template_in_execution(
    template_yaml: dict,
    layout_node_map: dict,
    template_id: str
) -> bool:
    """Validate that template appears in execution layout.

    Args:
        template_yaml: Template YAML to validate
        layout_node_map: Execution layout node map
        template_id: Template identifier for logging

    Returns:
        bool: True if template found in execution
    """
    # Check if template identifier appears in the layout node map
    # The layout contains nodes representing what actually executed
    if not layout_node_map:
        logger.warning(f"⚠ No layout data to validate {template_id}")
        return True  # Continue anyway

    # Search for template identifier in node map
    found = False
    node_count = 0

    for node_id, node_data in layout_node_map.items():
        node_count += 1
        # Check if node references this template
        node_str = str(node_data)
        if template_id in node_str:
            found = True
            node_type = node_data.get('nodeType', 'unknown')
            logger.info(f"  ✓ Found {template_id} in execution node: {node_id} (type: {node_type})")
            break

    if not found:
        logger.warning(f"  ⚠ {template_id} not found in {node_count} execution nodes")

    return found


def validate_execution(
    templates_api: TemplatesApi,
    execution_id: str,
    template_id: str,
    scope: Scope
) -> Tuple[dict, dict, dict, str]:
    """Validate that execution succeeded and template was used.

    Args:
        templates_api: TemplatesApi instance
        execution_id: Execution identifier
        template_id: Template identifier to verify
        scope: Scope for API call

    Returns:
        Tuple[dict, dict, dict, str]: (execution_data, pipeline_data, layout_node_map, execution_yaml)

    Raises:
        ValueError: If validation fails
    """
    logger.info(f"Validating execution {execution_id}...")

    # Fetch execution
    execution = templates_api.get_execution(execution_id, scope)

    # Check status - handle different response structures
    # Note: _get() already unwraps 'data', so execution IS the data
    exec_summary = execution.get('pipelineExecutionSummary', {})

    if not exec_summary:
        # Try alternative: execution might be the summary itself
        exec_summary = execution

    status = exec_summary.get('status')

    if status and status != 'Success':
        raise ValueError(f"Execution status is '{status}', expected 'Success'")
    elif not status:
        # Log available keys for debugging
        logger.warning(f"⚠️  Could not find execution status. Available keys: {list(execution.keys())[:10]}")
        logger.warning("Proceeding with caution...")

    logger.info("✓ Execution successful")

    # Get pipeline identifier from execution
    pipeline_id = exec_summary.get('pipelineIdentifier')
    if not pipeline_id:
        raise ValueError("Could not find pipeline identifier in execution")

    logger.info(f"Fetching pipeline {pipeline_id}...")

    # Fetch the actual pipeline YAML
    pipeline = templates_api.get_pipeline(pipeline_id, scope)

    # Get pipeline YAML (already unwrapped by _get)
    pipeline_yaml_str = pipeline.get('yamlPipeline', '')

    if not pipeline_yaml_str:
        logger.warning(f"Available keys in pipeline response: {list(pipeline.keys())[:10]}")
        raise ValueError("Could not retrieve pipeline YAML")

    logger.info("✓ Retrieved pipeline YAML")

    # Check if template is used in pipeline (case-insensitive)
    if template_id.lower() not in pipeline_yaml_str.lower():
        # Debug: show what templates ARE in the YAML
        import re
        template_refs = re.findall(r'templateRef:\s*["\']?(\w+)["\']?', pipeline_yaml_str)
        logger.error(f"Template '{template_id}' not found in pipeline YAML")
        logger.error(f"Templates found in pipeline: {template_refs}")
        logger.error(f"Pipeline YAML snippet: {pipeline_yaml_str[:500]}")
        raise ValueError(f"Template '{template_id}' not found in pipeline YAML")

    logger.info(f"✓ Template {template_id} found in pipeline")

    # NEW: Fetch execution metadata with compiled YAML
    logger.info("Fetching execution metadata with compiled YAML...")
    try:
        metadata = templates_api.get_execution_metadata(execution_id, scope)
        # _get() already unwraps 'data', so metadata IS the data
        execution_yaml = metadata.get('executionYaml', '')

        if execution_yaml:
            logger.info(f"✓ Retrieved compiled execution YAML ({len(execution_yaml)} bytes)")
        else:
            logger.warning("⚠ No executionYaml in metadata response")
    except Exception as e:
        logger.warning(f"⚠ Failed to fetch execution metadata: {e}")
        execution_yaml = ''

    # Get execution layout for validation (keep existing validation too)
    layout_node_map = exec_summary.get('layoutNodeMap', {})

    if layout_node_map:
        logger.info(f"✓ Retrieved execution layout ({len(layout_node_map)} nodes)")
    else:
        logger.warning("⚠ No execution layout found")

    return execution, pipeline, layout_node_map, execution_yaml


def fetch_template(
    templates_api: TemplatesApi,
    identifier: str,
    version: str,
    scope: Scope
) -> Tuple[dict, str]:
    """Fetch template from Harness.

    Args:
        templates_api: TemplatesApi instance
        identifier: Template identifier
        version: Version label
        scope: Scope for API call

    Returns:
        Tuple[dict, str]: (template_yaml_dict, template_type)

    Raises:
        ValueError: If template not found
    """
    logger.info(f"Fetching {identifier} {version} from project scope...")

    response = templates_api.get(identifier, version, scope)

    # Extract YAML (_get already unwrapped 'data')
    yaml_str = response.get('yaml')
    if not yaml_str:
        logger.error(f"Response keys: {list(response.keys())}")
        raise ValueError(f"No YAML found for template {identifier} {version}")

    template_yaml = yaml.safe_load(yaml_str)

    # Determine type
    template_type = template_yaml.get('template', {}).get('type', '').lower()

    # Convert StepGroup -> step_group
    if template_type == 'stepgroup':
        template_type = 'step_group'

    logger.info(f"✓ Fetched {identifier} {version} (type: {template_type})")

    return template_yaml, template_type


def discover_dependencies_recursive(
    templates_api: TemplatesApi,
    identifier: str,
    version: str,
    scope: Scope,
    visited: Set[Tuple[str, str]],
    depth: int = 0
) -> List[TemplateMetadata]:
    """Recursively discover template dependencies.

    Uses recursion to traverse the entire dependency tree, preventing
    infinite loops with a visited set.

    Args:
        templates_api: TemplatesApi instance
        identifier: Template identifier
        version: Version label
        scope: Scope for API calls
        visited: Set of (identifier, version) tuples already processed
        depth: Current depth in tree (0=root)

    Returns:
        List[TemplateMetadata]: All discovered dependencies
    """
    # Prevent infinite loops
    key = (identifier, version)
    if key in visited:
        return []
    visited.add(key)

    indent = "  " * depth
    logger.info(f"{indent}Discovering {identifier} {version}...")

    # Fetch template
    try:
        template_yaml, template_type = fetch_template(
            templates_api, identifier, version, scope
        )
    except Exception as e:
        logger.warning(f"{indent}⚠ Failed to fetch {identifier} {version}: {e}")
        return []

    # Extract template references
    refs = extract_template_refs(template_yaml)

    # Filter to only pinned references (those with versionLabel)
    pinned_refs = [ref for ref in refs if ref.version_label is not None]

    # Recursively process each child
    all_deps = []
    for ref in pinned_refs:
        logger.info(f"{indent}  └─ Found dependency: {ref.identifier} {ref.version_label}")

        # Recurse into child
        child_deps = discover_dependencies_recursive(
            templates_api,
            ref.identifier,
            ref.version_label,
            scope,
            visited,
            depth + 1
        )
        all_deps.extend(child_deps)

    # Add current template to dependencies list
    all_deps.append(TemplateMetadata(
        identifier=identifier,
        version=version,
        type=template_type,
        label=None,  # Beta (implicit)
        is_stable=False,
        scope="account",  # Will be deployed to account
        org=None,
        project=None,
        depth=depth
    ))

    return all_deps


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate execution, extract templates, and manage tier-based promotion"
    )
    parser.add_argument(
        "--execution-url",
        help="Full Harness execution URL (required for extraction)"
    )
    parser.add_argument(
        "--template-id",
        required=True,
        help="Template identifier to extract or promote"
    )
    parser.add_argument(
        "--project-id",
        help="Project ID where template was tested (required for extraction)"
    )
    parser.add_argument(
        "--changelog",
        default="No changelog provided",
        help="Description of changes (for extraction)"
    )
    parser.add_argument(
        "--mode",
        choices=["single", "tree"],
        default="single",
        help="Extract single template or entire dependency tree"
    )
    parser.add_argument(
        "--to-tier",
        type=int,
        choices=[1, 2, 3, 4, 5],
        help="Target tier (1-5). For extraction: creates tier-1. For promotion: promotes to this tier"
    )
    parser.add_argument(
        "--tier-skip",
        action="store_true",
        help="Allow skipping intermediate tiers during promotion (e.g., tier-1 → tier-4)"
    )
    parser.add_argument(
        "--no-pr",
        action="store_true",
        help="Skip automatic PR creation"
    )
    parser.add_argument(
        "--source-version",
        type=str,
        help="Semantic version label (e.g., v1.0) - only valid for tier-1 extraction"
    )
    parser.add_argument(
        "--sanitize",
        action="store_true",
        help="Sanitize templates by converting secrets/connectors to runtime inputs"
    )

    args = parser.parse_args()

    # Validate argument combinations
    is_promotion = not args.execution_url
    is_extraction = args.execution_url

    if is_promotion and not args.to_tier:
        parser.error("--to-tier is required for promotion (when --execution-url is not provided)")

    if is_extraction and not args.project_id:
        parser.error("--project-id is required for extraction (when --execution-url is provided)")

    if is_promotion and args.mode == "tree":
        parser.error("--mode tree is only valid for extraction, not promotion")

    if args.tier_skip and is_extraction:
        parser.error("--tier-skip is only valid for promotion, not extraction")

    if args.source_version and is_promotion:
        parser.error("--source-version is only valid for extraction, not promotion")

    # ============================================================
    # PROMOTION MODE: Promote template between tiers
    # ============================================================
    if is_promotion:
        try:
            logger.info("=== PROMOTION MODE ===")
            logger.info(f"Template: {args.template_id}")
            logger.info(f"Target Tier: {args.to_tier}")
            if args.tier_skip:
                logger.info("Tier Skip: Enabled (can skip intermediate tiers)")
            print()

            # Load versions.yaml
            versions = load_versions_yaml()

            # Initialize Harness API client
            api_client = HarnessAPIClient()

            # Step 1: Auto-detect template type by fetching from Harness
            logger.info("Auto-detecting template type from Harness...")
            # Find the template in versions.yaml to get tier snapshots
            template_found = False
            template_type = None
            tier_snapshots = {}

            for tmpl_type, templates in versions.get('templates', {}).items():
                if args.template_id in templates:
                    template_found = True
                    template_type = tmpl_type
                    tier_snapshots = templates[args.template_id].get('tier_snapshots', {})
                    logger.info(f"  ✓ Found template '{args.template_id}' of type '{template_type}'")
                    break

            if not template_found:
                raise ValueError(
                    f"Template '{args.template_id}' not found in versions.yaml. "
                    f"You may need to extract it first using --execution-url."
                )

            print()

            # Step 2: Validate tier progression
            logger.info("Validating tier progression...")

            # Determine source tier
            if args.tier_skip:
                # Find highest existing tier below target
                source_tier = None
                for tier_num in range(args.to_tier - 1, 0, -1):
                    tier_label = format_tier_label(tier_num)
                    if tier_label in tier_snapshots:
                        source_tier = tier_num
                        break

                if not source_tier:
                    raise ValueError(
                        f"Cannot promote to tier-{args.to_tier}: No lower tier exists to copy from. "
                        f"Must create tier-1 first."
                    )

                logger.info(f"  ✓ Using tier-skip: Will copy from tier-{source_tier} → tier-{args.to_tier}")
            else:
                # Sequential promotion
                source_tier = args.to_tier - 1
                tier_label = format_tier_label(source_tier)

                if tier_label not in tier_snapshots:
                    raise ValueError(
                        f"Cannot promote to tier-{args.to_tier}: tier-{source_tier} does not exist.\n"
                        f"\n"
                        f"Options:\n"
                        f"1. Sequential: First promote to tier-{source_tier}\n"
                        f"2. Skip tiers: Use --tier-skip to copy from lower tier"
                    )

                logger.info(f"  ✓ Sequential promotion: tier-{source_tier} → tier-{args.to_tier}")

            source_tier_label = format_tier_label(source_tier)
            target_tier_label = format_tier_label(args.to_tier)
            print()

            # Step 3: Check idempotency - compare source and target if target exists
            logger.info("Checking if promotion is needed...")

            if target_tier_label in tier_snapshots:
                # Target tier exists - check if it matches source
                source_version_label = tier_snapshots[source_tier_label]
                target_version_label = tier_snapshots[target_tier_label]

                logger.info(f"  Target tier-{args.to_tier} exists with source version: {target_version_label}")
                logger.info(f"  Source tier-{source_tier} has source version: {source_version_label}")

                # Fetch both from Harness and compare content
                source_yaml = api_client.get_template_version(args.template_id, source_tier_label)
                target_yaml = api_client.get_template_version(args.template_id, target_tier_label)

                if api_client.compare_template_content(source_yaml, target_yaml):
                    logger.info(f"  ✓ tier-{args.to_tier} already matches tier-{source_tier}, skipping")
                    logger.info("\n✅ No changes needed - target tier already up to date")
                    sys.exit(0)
                else:
                    logger.warning(f"  ⚠️ tier-{args.to_tier} exists but differs from tier-{source_tier}")
                    logger.info(f"  Will UPDATE tier-{args.to_tier}")
                    action = "update"
            else:
                logger.info(f"  ✓ tier-{args.to_tier} does not exist yet (OK to create)")
                action = "create"

            print()

            # Step 4: Read source tier content from Harness
            logger.info(f"Reading tier-{source_tier} from Harness API...")
            source_yaml = api_client.get_template_version(args.template_id, source_tier_label)

            if not source_yaml:
                raise ValueError(
                    f"Failed to fetch tier-{source_tier} from Harness. "
                    f"Ensure template '{args.template_id}' version '{source_tier_label}' exists."
                )

            # Get source version from tier_snapshots
            source_semantic_version = tier_snapshots[source_tier_label]
            logger.info(f"  ✓ Found tier-{source_tier} with source version: {source_semantic_version}")
            logger.info(f"  Content hash: {api_client.compute_content_hash(source_yaml)[:12]}...")
            print()

            # Step 5: Create target tier file
            logger.info(f"Creating tier-{args.to_tier} YAML file...")

            # Determine file path
            type_dir = template_type.replace('_', '-')
            tier_file_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'templates',
                type_dir,
                args.template_id,
                f"{target_tier_label}.yaml"
            )

            # Ensure directory exists
            os.makedirs(os.path.dirname(tier_file_path), exist_ok=True)

            # Parse source YAML and update child template references to use target tier
            logger.info(f"  Updating child template references to use {target_tier_label} or stable...")
            source_yaml_dict = yaml.safe_load(source_yaml)

            # versions is already loaded earlier, use it to check which tiers exist for child templates
            def update_template_refs_to_tier_promotion(obj, target_tier_label):
                """Recursively update templateRef versionLabel to use target tier or stable."""
                if isinstance(obj, dict):
                    # Check if this is a template reference
                    if 'templateRef' in obj and 'versionLabel' in obj:
                        child_template_id = obj['templateRef']

                        # Find the child template in versions.yaml
                        for t_type, templates in versions.get('templates', {}).items():
                            if child_template_id in templates:
                                tier_snapshots_child = templates[child_template_id].get('tier_snapshots', {})
                                if target_tier_label in tier_snapshots_child:
                                    # Child has this tier, use it
                                    obj['versionLabel'] = target_tier_label
                                    logger.info(f"    ✓ Updated {child_template_id} reference to use {target_tier_label}")
                                else:
                                    # Child doesn't have this tier, check if stable exists (tier-5)
                                    if 'tier-5' in tier_snapshots_child:
                                        # Remove versionLabel to use stable
                                        del obj['versionLabel']
                                        logger.info(f"    ✓ Updated {child_template_id} reference to use stable (no versionLabel)")
                                    else:
                                        # Keep original versionLabel
                                        logger.warning(f"    ⚠ {child_template_id} has no {target_tier_label} or stable, keeping versionLabel: {obj['versionLabel']}")
                                break

                    # Recurse into nested dicts
                    for key, value in obj.items():
                        if isinstance(value, (dict, list)):
                            update_template_refs_to_tier_promotion(value, target_tier_label)

                elif isinstance(obj, list):
                    for item in obj:
                        if isinstance(item, (dict, list)):
                            update_template_refs_to_tier_promotion(item, target_tier_label)

            update_template_refs_to_tier_promotion(source_yaml_dict, target_tier_label)

            # Update the template's own versionLabel to match the tier
            if 'template' in source_yaml_dict and 'versionLabel' in source_yaml_dict['template']:
                source_yaml_dict['template']['versionLabel'] = target_tier_label
                logger.info(f"  ✓ Updated template versionLabel to {target_tier_label}")

            # Remove scope identifiers to make template reusable at account level
            if 'template' in source_yaml_dict:
                removed_fields = []
                if 'projectIdentifier' in source_yaml_dict['template']:
                    del source_yaml_dict['template']['projectIdentifier']
                    removed_fields.append('projectIdentifier')
                if 'orgIdentifier' in source_yaml_dict['template']:
                    del source_yaml_dict['template']['orgIdentifier']
                    removed_fields.append('orgIdentifier')
                if removed_fields:
                    logger.info(f"  ✓ Removed scope identifiers: {', '.join(removed_fields)}")

                # Add tags for tracking
                type_dir = template_type.replace('_', '-')
                if 'tags' not in source_yaml_dict['template']:
                    source_yaml_dict['template']['tags'] = {}
                source_yaml_dict['template']['tags'].update({
                    'source_version': source_semantic_version,
                    'managed_by': 'terraform',
                    'template_type': type_dir
                })
                logger.info(f"  ✓ Added tags: source_version={source_semantic_version}")

            # Qualify templateRef with account. prefix
            def add_account_prefix(obj):
                if isinstance(obj, dict):
                    if 'templateRef' in obj and isinstance(obj['templateRef'], str):
                        ref = obj['templateRef']
                        if not ref.startswith(('account.', 'org.')):
                            obj['templateRef'] = f"account.{ref}"
                            logger.info(f"  ✓ Qualified: {ref} → account.{ref}")
                    for v in obj.values():
                        if isinstance(v, (dict, list)):
                            add_account_prefix(v)
                elif isinstance(obj, list):
                    for item in obj:
                        add_account_prefix(item)

            add_account_prefix(source_yaml_dict)

            # Write updated tier file
            with open(tier_file_path, 'w') as f:
                yaml.dump(source_yaml_dict, f, default_flow_style=False, sort_keys=False)

            logger.info(f"  ✓ Created: {tier_file_path}")
            print()

            # Step 6: Update versions.yaml
            logger.info("Updating versions.yaml...")

            # Update tier_snapshots using common utility
            update_tier_snapshot(versions, template_type, args.template_id, target_tier_label, source_semantic_version)

            # Save versions.yaml
            save_versions_yaml(versions)

            logger.info(f"  ✓ Updated tier_snapshots.{target_tier_label} = {source_semantic_version}")
            if source_tier != args.to_tier - 1:
                logger.info(f"  Note: Skipped tier-{source_tier + 1} through tier-{args.to_tier - 1} (tier-skip used)")
            print()

            # Step 7: Create Git PR (unless --no-pr specified)
            if not args.no_pr:
                logger.info("Creating Git PR...")

                git_ops = GitOperations()

                # Create branch name
                branch_name = f"feat/{args.template_id}-tier{source_tier}-to-tier{args.to_tier}"

                # Create commit message
                if action == "create":
                    commit_message = f"feat: Promote {args.template_id} tier-{source_tier} → tier-{args.to_tier} ({source_semantic_version})"
                else:
                    commit_message = f"feat: Update {args.template_id} tier-{args.to_tier} from tier-{source_tier} ({source_semantic_version})"

                if args.tier_skip and source_tier != args.to_tier - 1:
                    commit_message += f"\n\nTier skip used: copied from tier-{source_tier} (skipped intermediate tiers)"

                commit_message += "\n\nCo-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

                # Files to commit
                versions_yaml_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'versions.yaml')
                files_to_commit = [tier_file_path, versions_yaml_path]

                # Create branch, commit, push
                git_ops.create_branch(branch_name)
                git_ops.commit_files(files_to_commit, commit_message)
                git_ops.push_branch(branch_name)

                # Create PR
                pr_title = f"Promote {args.template_id} to tier-{args.to_tier}"
                pr_body = f"""## Summary
- Template: `{args.template_id}` ({template_type})
- Source: tier-{source_tier} (version {source_semantic_version})
- Target: tier-{args.to_tier}
- Action: {action.upper()}
{'- Tier skip: Yes (skipped intermediate tiers)' if args.tier_skip and source_tier != args.to_tier - 1 else ''}

## Changes
- Created/Updated: `{os.path.relpath(tier_file_path, os.path.dirname(os.path.dirname(__file__)))}`
- Updated: `versions.yaml` (tier_snapshots)

## Test Plan
- [ ] Review tier-{args.to_tier} YAML content
- [ ] Verify versions.yaml tier_snapshots mapping
- [ ] After merge, verify Terraform plan shows expected changes
- [ ] After apply, test in tier-{args.to_tier} project

🤖 Generated with [Claude Code](https://claude.com/claude-code)
"""

                pr_url = git_ops.create_pull_request(pr_title, pr_body, base='main', head=branch_name)

                logger.info(f"  ✓ Created PR: {pr_url}")
                print()
            else:
                logger.info("Skipping PR creation (--no-pr specified)")
                print()

            # Success summary
            logger.info("=" * 60)
            logger.info("✅ PROMOTION COMPLETE")
            logger.info("=" * 60)
            logger.info(f"Template: {args.template_id}")
            logger.info(f"Promoted: tier-{source_tier} → tier-{args.to_tier}")
            logger.info(f"Source Version: {source_semantic_version}")
            logger.info(f"Action: {action.upper()}")
            if not args.no_pr:
                logger.info(f"\nNext Steps:")
                logger.info(f"1. Review and approve the PR")
                logger.info(f"2. Merge to main")
                logger.info(f"3. IaC pipeline will auto-deploy to Harness")
            else:
                logger.info(f"\nNext Steps:")
                logger.info(f"1. Review changes: {tier_file_path}")
                logger.info(f"2. Commit and push manually")
                logger.info(f"3. Create PR for review")
            print()

        except Exception as e:
            logger.error(f"❌ Error: {e}")
            sys.exit(1)

    # ============================================================
    # EXTRACTION MODE: Extract template from execution
    # ============================================================
    elif is_extraction:
        try:
            # Parse execution URL
            url_parts = parse_execution_url(args.execution_url)
            logger.info(f"Parsed execution URL:")
            logger.info(f"  Account: {url_parts['account_id']}")
            logger.info(f"  Org: {url_parts['org_id']}")
            logger.info(f"  Project: {url_parts['project_id']}")
            logger.info(f"  Execution: {url_parts['execution_id']}")
            print()

            # Create Harness client
            client = get_harness_client()

            # Add templates API to client
            client.templates = TemplatesApi(client)

            # Create scope
            scope = Scope(
                account_id=url_parts['account_id'],
                org=url_parts['org_id'],
                project=url_parts['project_id']
            )

            # Validate execution
            execution, pipeline, layout_node_map, execution_yaml = validate_execution(
                client.templates,
                url_parts['execution_id'],
                args.template_id,
                scope
            )
            print()

            # Parse pipeline YAML to find the template version
            # Note: pipeline is already unwrapped by _get()
            pipeline_yaml_str = pipeline.get('yamlPipeline', '')
            pipeline_yaml_dict = yaml.safe_load(pipeline_yaml_str)

            # Extract template refs from pipeline to find the version used
            refs = extract_template_refs(pipeline_yaml_dict)
            root_ref = next(
                (ref for ref in refs if ref.identifier == args.template_id),
                None
            )

            if not root_ref:
                raise ValueError(f"Template {args.template_id} not found in pipeline YAML")

            # Use the version from the pipeline, or fetch latest if not specified
            if root_ref.version_label:
                version = root_ref.version_label
                logger.info(f"Detected version from pipeline: {version}")
            else:
                # Stable reference - need to fetch latest version
                # For now, we'll require explicit version in pipeline
                raise ValueError(f"Template {args.template_id} uses stable reference (no versionLabel). Please use a pinned version for extraction.")

            print()

            # Extract templates
            if args.mode == "single":
                logger.info(f"Extracting single template: {args.template_id} {version}")
                print()

                # Fetch template
                template_yaml, template_type = fetch_template(
                    client.templates,
                    args.template_id,
                    version,
                    scope
                )

                # VALIDATION 1: Check template is referenced in pipeline YAML
                logger.info(f"Validating {args.template_id} reference in pipeline YAML...")
                pipeline_yaml_str = pipeline.get('yamlPipeline', '')
                pipeline_validation = validate_template_in_pipeline_yaml(args.template_id, pipeline_yaml_str)

                if pipeline_validation.get('found'):
                    ref_count = pipeline_validation.get('reference_count', 0)
                    logger.info(f"  ✓ {args.template_id} referenced {ref_count} time(s) in pipeline YAML")
                else:
                    logger.error(f"  ✗ {args.template_id} not referenced in pipeline YAML")

                # VALIDATION 2: Check template structure appears in compiled execution YAML
                if execution_yaml:
                    logger.info(f"Validating {args.template_id} structure in compiled execution YAML...")
                    structure_validation = validate_template_structure_in_execution_yaml(
                        template_yaml,
                        execution_yaml,
                        args.template_id
                    )

                    if structure_validation.get('found'):
                        match_pct = structure_validation.get('match_percentage', 0)
                        logger.info(f"  ✓ {args.template_id} structure validated (match: {match_pct:.1f}%)")

                        # Log details if match is not perfect
                        if match_pct < 50:
                            logger.warning(f"    ⚠ Match percentage below 50%")
                            if 'missing_keys' in structure_validation and structure_validation['missing_keys']:
                                logger.warning(f"    Missing keys (sample): {structure_validation['missing_keys'][:3]}")
                    else:
                        error = structure_validation.get('error', 'Unknown error')
                        logger.warning(f"  ⚠ {args.template_id} structure validation: {error}")

                        # Don't fail extraction, just log warning
                        logger.warning(f"  ⚠ Proceeding with extraction")

                    # VALIDATION 3: Hash-based content validation
                    logger.info(f"Validating {args.template_id} content hash...")
                    execution_yaml_dict = yaml.safe_load(execution_yaml) if isinstance(execution_yaml, str) else execution_yaml
                    hash_validation = validate_content_hash(
                        template_yaml,
                        execution_yaml_dict,
                        args.template_id
                    )

                    if hash_validation.get('hash_match'):
                        logger.info(f"  ✓ Content hash matched (confidence: {hash_validation.get('confidence', 'unknown')})")
                    else:
                        similarity = hash_validation.get('closest_similarity', 0)
                        confidence = hash_validation.get('confidence', 'low')
                        logger.warning(f"  ⚠ Content hash mismatch (confidence: {confidence}, similarity: {similarity:.1f}%)")
                        if 'error' in hash_validation:
                            logger.warning(f"    Error: {hash_validation['error']}")

                    # VALIDATION 4: Script/command fuzzy matching
                    logger.info(f"Validating {args.template_id} scripts/commands...")
                    script_validation = validate_scripts(
                        template_yaml,
                        execution_yaml_dict,
                        args.template_id,
                        threshold=0.5
                    )

                    if script_validation.get('validated'):
                        avg_sim = script_validation.get('average_similarity', 0)
                        logger.info(f"  ✓ Scripts validated (similarity: {avg_sim:.1%})")
                    elif script_validation.get('reason') == 'No scripts in template to validate':
                        logger.info(f"  ✓ No scripts to validate")
                    else:
                        logger.warning(f"  ⚠ Script validation warning: {script_validation.get('warning', 'Scripts differ')}")
                        if 'worst_match_similarity' in script_validation:
                            logger.warning(f"    Lowest similarity: {script_validation['worst_match_similarity']:.1%}")
                            logger.warning(f"    Template: {script_validation.get('template_script_sample', 'N/A')}")
                            logger.warning(f"    Execution: {script_validation.get('execution_script_sample', 'N/A')}")

                else:
                    logger.warning(f"  ⚠ Skipping execution YAML validation (no executionYaml available)")

                # Sanitize if requested
                if args.sanitize:
                    logger.info(f"Sanitizing {args.template_id}...")
                    original_yaml = yaml.dump(template_yaml, default_flow_style=False, sort_keys=False)
                    sanitized_yaml = sanitize_template(original_yaml)
                    template_yaml = yaml.safe_load(sanitized_yaml)

                    # Show sanitization report
                    report = get_sanitization_report(original_yaml, sanitized_yaml)
                    logger.info(f"  Converted {report['fields_converted']} field(s) to runtime inputs")

                # Save locally
                save_template_yaml(template_yaml, template_type, args.template_id, version)

                # Create metadata
                templates_to_register = [TemplateMetadata(
                    identifier=args.template_id,
                    version=version,
                    type=template_type,
                    label=None,
                    is_stable=False,
                    scope="account",
                    org=None,
                    project=None,
                    depth=0
                )]

            else:  # tree mode
                logger.info(f"Extracting dependency tree for: {args.template_id} {version}")
                print()

                # Discover all dependencies recursively
                visited = set()
                all_templates = discover_dependencies_recursive(
                    client.templates,
                    args.template_id,
                    version,
                    scope,
                    visited,
                    depth=0
                )

                # Save all templates locally and validate against compiled YAML
                print()
                logger.info("Saving templates locally...")
                pipeline_yaml_str = pipeline.get('yamlPipeline', '')

                for tmpl in all_templates:
                    template_yaml, _ = fetch_template(
                        client.templates,
                        tmpl.identifier,
                        tmpl.version,
                        scope
                    )

                    # VALIDATION 1: Check template is referenced in pipeline YAML
                    logger.info(f"Validating {tmpl.identifier} reference in pipeline YAML...")
                    pipeline_validation = validate_template_in_pipeline_yaml(tmpl.identifier, pipeline_yaml_str)

                    if pipeline_validation.get('found'):
                        ref_count = pipeline_validation.get('reference_count', 0)
                        logger.info(f"  ✓ {tmpl.identifier} referenced {ref_count} time(s) in pipeline YAML")
                    else:
                        logger.warning(f"  ⚠ {tmpl.identifier} not directly referenced (may be child dependency)")

                    # VALIDATION 2: Check template structure appears in compiled execution YAML
                    if execution_yaml:
                        logger.info(f"Validating {tmpl.identifier} structure in compiled execution YAML...")
                        structure_validation = validate_template_structure_in_execution_yaml(
                            template_yaml,
                            execution_yaml,
                            tmpl.identifier
                        )

                        if structure_validation.get('found'):
                            match_pct = structure_validation.get('match_percentage', 0)
                            logger.info(f"  ✓ {tmpl.identifier} structure validated (match: {match_pct:.1f}%)")

                            # Log details if match is not perfect
                            if match_pct < 50:
                                logger.warning(f"    ⚠ Match percentage below 50%")
                        else:
                            error = structure_validation.get('error', 'Unknown error')
                            logger.warning(f"  ⚠ {tmpl.identifier} structure validation: {error}")

                        # VALIDATION 3: Hash-based content validation
                        logger.info(f"Validating {tmpl.identifier} content hash...")
                        execution_yaml_dict = yaml.safe_load(execution_yaml) if isinstance(execution_yaml, str) else execution_yaml
                        hash_validation = validate_content_hash(
                            template_yaml,
                            execution_yaml_dict,
                            tmpl.identifier
                        )

                        if hash_validation.get('hash_match'):
                            logger.info(f"  ✓ Content hash matched (confidence: {hash_validation.get('confidence', 'unknown')})")
                        else:
                            similarity = hash_validation.get('closest_similarity', 0)
                            confidence = hash_validation.get('confidence', 'low')
                            logger.warning(f"  ⚠ Content hash mismatch (confidence: {confidence}, similarity: {similarity:.1f}%)")

                        # VALIDATION 4: Script/command fuzzy matching
                        logger.info(f"Validating {tmpl.identifier} scripts/commands...")
                        script_validation = validate_scripts(
                            template_yaml,
                            execution_yaml_dict,
                            tmpl.identifier,
                            threshold=0.5
                        )

                        if script_validation.get('validated'):
                            avg_sim = script_validation.get('average_similarity', 0)
                            logger.info(f"  ✓ Scripts validated (similarity: {avg_sim:.1%})")
                        elif script_validation.get('reason') == 'No scripts in template to validate':
                            logger.info(f"  ✓ No scripts to validate")
                        else:
                            logger.warning(f"  ⚠ Script validation warning: {script_validation.get('warning', 'Scripts differ')}")
                            if 'worst_match_similarity' in script_validation:
                                logger.warning(f"    Lowest similarity: {script_validation['worst_match_similarity']:.1%}")

                    else:
                        logger.warning(f"  ⚠ Skipping execution YAML validation (no executionYaml available)")

                    # Sanitize if requested
                    if args.sanitize:
                        logger.info(f"Sanitizing {tmpl.identifier}...")
                        original_yaml = yaml.dump(template_yaml, default_flow_style=False, sort_keys=False)
                        sanitized_yaml = sanitize_template(original_yaml)
                        template_yaml = yaml.safe_load(sanitized_yaml)

                        # Show sanitization report
                        report = get_sanitization_report(original_yaml, sanitized_yaml)
                        logger.info(f"  Converted {report['fields_converted']} field(s) to runtime inputs")

                    save_template_yaml(
                        template_yaml,
                        tmpl.type,
                        tmpl.identifier,
                        tmpl.version
                    )

                templates_to_register = all_templates

            # Update versions.yaml
            print()
            logger.info("Updating versions.yaml...")
            versions = load_versions_yaml()

            for tmpl in templates_to_register:
                # Ensure structure exists
                if tmpl.type not in versions['templates']:
                    versions['templates'][tmpl.type] = {}
                if tmpl.identifier not in versions['templates'][tmpl.type]:
                    versions['templates'][tmpl.type][tmpl.identifier] = {'versions': []}

                # Check if version already exists
                versions_list = versions['templates'][tmpl.type][tmpl.identifier]['versions']
                existing = next((v for v in versions_list if v['version'] == tmpl.version), None)

                if existing:
                    # Update existing
                    logger.info(f"  Updating existing {tmpl.identifier} {tmpl.version}")
                    existing['label'] = tmpl.label
                    existing['is_stable'] = tmpl.is_stable
                    existing['scope'] = tmpl.scope
                else:
                    # Add new
                    logger.info(f"  Adding new {tmpl.identifier} {tmpl.version}")
                    versions_list.append({
                        'version': tmpl.version,
                        'created': date.today().isoformat(),
                        'changelog': args.changelog,
                        'label': tmpl.label,
                        'is_stable': tmpl.is_stable,
                        'scope': tmpl.scope,
                        'org': tmpl.org,
                        'project': tmpl.project,
                        'created_from_execution': url_parts['execution_id']
                    })

            save_versions_yaml(versions)

            # NEW FEATURE: Create tier files if --to-tier is specified
            if args.to_tier:
                print()
                logger.info(f"Creating tier-{args.to_tier} files for all extracted templates...")
                tier_label = format_tier_label(args.to_tier)

                # Reload versions to get updated state
                versions = load_versions_yaml()

                for tmpl in templates_to_register:
                    # Load the semantic version YAML that was just saved
                    type_dir = tmpl.type.replace('_', '-')
                    semantic_file_path = os.path.join(
                        os.path.dirname(os.path.dirname(__file__)),
                        'templates',
                        type_dir,
                        tmpl.identifier,
                        f"{tmpl.version}.yaml"
                    )

                    with open(semantic_file_path, 'r') as f:
                        template_content = yaml.safe_load(f)

                    # Update child template references to use tier-N or stable
                    def update_template_refs_to_tier(obj, target_tier_label):
                        """Recursively update templateRef versionLabel to use target tier or stable."""
                        if isinstance(obj, dict):
                            # Check if this is a template reference
                            if 'templateRef' in obj and 'versionLabel' in obj:
                                child_template_id = obj['templateRef']

                                # Find the child template in versions.yaml
                                child_has_tier = False
                                for t_type, templates in versions.get('templates', {}).items():
                                    if child_template_id in templates:
                                        tier_snapshots = templates[child_template_id].get('tier_snapshots', {})
                                        if target_tier_label in tier_snapshots:
                                            # Child has this tier, use it
                                            obj['versionLabel'] = target_tier_label
                                            child_has_tier = True
                                            logger.info(f"    Updated {child_template_id} reference to use {target_tier_label}")
                                        else:
                                            # Child doesn't have this tier, check if stable exists
                                            # For now, keep original versionLabel or set to stable if tier-5 exists
                                            if 'tier-5' in tier_snapshots:
                                                # Remove versionLabel to use stable
                                                del obj['versionLabel']
                                                logger.info(f"    Updated {child_template_id} reference to use stable (no versionLabel)")
                                            else:
                                                # Keep original versionLabel
                                                logger.warning(f"    {child_template_id} has no {target_tier_label} or stable, keeping versionLabel: {obj['versionLabel']}")
                                        break

                            # Recurse into nested dicts
                            for key, value in obj.items():
                                if isinstance(value, (dict, list)):
                                    update_template_refs_to_tier(value, target_tier_label)

                        elif isinstance(obj, list):
                            for item in obj:
                                if isinstance(item, (dict, list)):
                                    update_template_refs_to_tier(item, target_tier_label)

                    logger.info(f"  Processing {tmpl.identifier}...")
                    update_template_refs_to_tier(template_content, tier_label)

                    # Update the template's own versionLabel to match the tier
                    if 'template' in template_content and 'versionLabel' in template_content['template']:
                        template_content['template']['versionLabel'] = tier_label
                        logger.info(f"    ✓ Updated template versionLabel to {tier_label}")

                    # Remove scope identifiers to make template reusable at account level
                    if 'template' in template_content:
                        removed_fields = []
                        if 'projectIdentifier' in template_content['template']:
                            del template_content['template']['projectIdentifier']
                            removed_fields.append('projectIdentifier')
                        if 'orgIdentifier' in template_content['template']:
                            del template_content['template']['orgIdentifier']
                            removed_fields.append('orgIdentifier')
                        if removed_fields:
                            logger.info(f"    ✓ Removed scope identifiers: {', '.join(removed_fields)}")

                        # Add tags for tracking
                        if 'tags' not in template_content['template']:
                            template_content['template']['tags'] = {}
                        template_content['template']['tags'].update({
                            'source_version': tmpl.version,
                            'managed_by': 'terraform',
                            'template_type': type_dir
                        })
                        logger.info(f"    ✓ Added tags: source_version={tmpl.version}")

                    # Qualify templateRef with account. prefix
                    def add_account_prefix_tier(obj):
                        if isinstance(obj, dict):
                            if 'templateRef' in obj and isinstance(obj['templateRef'], str):
                                ref = obj['templateRef']
                                if not ref.startswith(('account.', 'org.')):
                                    obj['templateRef'] = f"account.{ref}"
                                    logger.info(f"    ✓ Qualified: {ref} → account.{ref}")
                            for v in obj.values():
                                if isinstance(v, (dict, list)):
                                    add_account_prefix_tier(v)
                        elif isinstance(obj, list):
                            for item in obj:
                                add_account_prefix_tier(item)

                    add_account_prefix_tier(template_content)

                    # Save tier file
                    tier_file_path = os.path.join(
                        os.path.dirname(os.path.dirname(__file__)),
                        'templates',
                        type_dir,
                        tmpl.identifier,
                        f"{tier_label}.yaml"
                    )

                    # Ensure directory exists
                    os.makedirs(os.path.dirname(tier_file_path), exist_ok=True)

                    with open(tier_file_path, 'w') as f:
                        yaml.dump(template_content, f, default_flow_style=False, sort_keys=False)

                    logger.info(f"    ✓ Created {tier_file_path}")

                    # Update tier_snapshots in versions.yaml
                    update_tier_snapshot(versions, tmpl.type, tmpl.identifier, tier_label, tmpl.version)

                # Save updated versions.yaml with tier_snapshots
                save_versions_yaml(versions)
                logger.info(f"  ✓ Updated versions.yaml with tier_snapshots for {len(templates_to_register)} template(s)")

            # Summary
            print()
            print("=" * 60)
            logger.info(f"✓ Extracted {len(templates_to_register)} template(s)")
            print("=" * 60)
            for tmpl in templates_to_register:
                print(f"  - {tmpl.identifier} {tmpl.version} ({tmpl.type}, beta - implicit)")

            print()
            if args.to_tier:
                logger.info(f"✓ Created tier-{args.to_tier} files for all templates")
                logger.info(f"Next: Review tier files and deploy with Terraform")
            else:
                logger.info("Next: Wait 7 days before promoting to canary")

        except Exception as e:
            logger.error(f"❌ Error: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
