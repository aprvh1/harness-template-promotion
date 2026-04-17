"""Core business logic for template extraction and promotion.

This module provides TemplateExtractor and TemplatePromoter classes with full
feature parity to the original scripts, including 4-level validation, sanitization,
and dependency tree discovery.
"""

import re
import os
import logging
import yaml
from typing import Dict, Any, Optional, List, Set, Tuple
from dataclasses import dataclass
from pathlib import Path

from harness_api import HarnessClient, Scope, TemplatesApi
from utils import (
    TemplateMetadata,
    validate_template_in_pipeline_yaml,
    validate_template_structure_in_execution_yaml,
    validate_content_hash,
    validate_scripts,
    qualify_template_refs,
    remove_scope_identifiers,
    add_template_tags,
    extract_template_refs,
    update_template_version_label,
    update_child_template_versions,
    remove_child_template_version_labels,
)
from sanitize_template import sanitize_template
from versions_manager import VersionsManager


logger = logging.getLogger(__name__)

# Constants
TEMPLATE_TYPES = ["stage", "stepgroup", "step", "pipeline"]


# ============================================================
# Helper Functions
# ============================================================

def _create_scope(account_id: str, org: str = None, project: str = None) -> Scope:
    """Create Scope object from parameters."""
    return Scope(account_id=account_id, org=org, project=project)


def _parse_scope_from_url(execution_url: str) -> Scope:
    """Parse scope from execution URL."""
    url_parts = parse_execution_url(execution_url)
    return _create_scope(
        account_id=url_parts['account_id'],
        org=url_parts['org'],
        project=url_parts['project']
    )


def _parse_scope_from_config(config) -> Scope:
    """Parse scope from plugin configuration."""
    if config.execution_url:
        return _parse_scope_from_url(config.execution_url)
    elif config.project_id:
        return _create_scope(
            account_id=config.account_id,
            org=config.org_id or 'default',
            project=config.project_id
        )
    else:
        return _create_scope(account_id=config.account_id)


def _get_template_file_path(
    output_dir: str,
    template_type: str,
    identifier: str,
    version: str
) -> Path:
    """Build template file path."""
    return Path(output_dir) / template_type / identifier / f"{version}.yaml"


def _save_template_file(
    template_yaml: Dict,
    template_type: str,
    identifier: str,
    version: str,
    output_dir: str = "templates"
) -> Path:
    """Save template YAML to file system.

    Creates directory structure: {output_dir}/{type}/{identifier}/{version}.yaml

    Args:
        template_yaml: Template YAML dictionary
        template_type: Template type (stage, step_group, etc.)
        identifier: Template identifier
        version: Version label (v1, tier-1, etc.)
        output_dir: Base output directory

    Returns:
        Path to saved file
    """
    # Use absolute path to avoid relative path issues
    output_path = Path(output_dir).resolve()
    template_dir = output_path / template_type / identifier

    # Create directory with full permissions
    # Note: /harness is provided by Harness and is already writable
    # We only create subdirectories under it (e.g., /harness/templates/stage/Stage_Template/)
    try:
        template_dir.mkdir(parents=True, exist_ok=True, mode=0o777)

        # Only set permissions on the directory we just created, not parent paths
        # This avoids trying to chmod /harness or /harness/templates which Harness manages
        if template_dir.exists():
            try:
                os.chmod(template_dir, 0o777)
            except (PermissionError, OSError) as e:
                # If we can't change permissions, log but continue
                # This is normal if running in read-only filesystem
                logger.debug(f"Could not set permissions on {template_dir}: {e}")
    except PermissionError as e:
        logger.error(f"Cannot create directory {template_dir}: {e}")
        logger.error(f"Current user: {os.getuid() if hasattr(os, 'getuid') else 'unknown'}")
        logger.error(f"Directory exists: {template_dir.exists()}, Parent exists: {template_dir.parent.exists()}")
        raise

    file_path = template_dir / f"{version}.yaml"

    # If file exists, check if we can write to it
    if file_path.exists():
        file_stat = os.stat(file_path)
        current_uid = os.getuid() if hasattr(os, 'getuid') else None

        # Check if file is owned by someone else
        if current_uid is not None and file_stat.st_uid != current_uid:
            logger.warning(f"File {file_path} is owned by UID {file_stat.st_uid}, current user is UID {current_uid}")
            logger.error(f"Cannot overwrite file owned by different user. Please clean /harness/templates directory or use a different output directory.")
            logger.error(f"Suggestion: Set PLUGIN_OUTPUT_DIR=/harness/templates-{current_uid} or clean up between runs")
            raise PermissionError(f"Cannot overwrite {file_path} owned by UID {file_stat.st_uid} (current user: {current_uid})")

        # File is owned by us, make it writable
        try:
            os.chmod(file_path, 0o666)
            logger.debug(f"Made existing file writable: {file_path}")
        except (PermissionError, OSError) as e:
            logger.warning(f"Cannot modify existing file {file_path}: {e}")

    # Try to write the file
    try:
        # Create file descriptor with proper permissions before opening
        fd = os.open(file_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o666)
        with os.fdopen(fd, 'w') as f:
            yaml.dump(template_yaml, f, sort_keys=False, default_flow_style=False)

        # Explicitly set file permissions after writing (in case umask interfered)
        try:
            os.chmod(file_path, 0o666)
        except (PermissionError, OSError):
            pass  # Best effort

    except PermissionError as e:
        logger.error(f"Cannot write to {file_path}: {e}")
        logger.error(f"Directory permissions: {oct(os.stat(template_dir).st_mode)[-3:]}")
        logger.error(f"Directory owner: {os.stat(template_dir).st_uid if hasattr(os.stat(template_dir), 'st_uid') else 'unknown'}")
        if file_path.exists():
            logger.error(f"File exists: True")
            logger.error(f"File permissions: {oct(os.stat(file_path).st_mode)[-3:]}")
            logger.error(f"File owner: {os.stat(file_path).st_uid if hasattr(os.stat(file_path), 'st_uid') else 'unknown'}")
        logger.error(f"Container user: {os.getuid() if hasattr(os, 'getuid') else 'unknown'}")
        raise

    logger.info(f"  ✓ Saved to {file_path}")
    return file_path


@dataclass
class PluginResult:
    """Result of plugin execution."""
    success: bool
    message: str
    outputs: Dict[str, Any]
    error: Optional[str] = None


def parse_execution_url(url: str) -> Dict[str, str]:
    """Parse Harness execution URL to extract identifiers.

    Args:
        url: Full Harness execution URL

    Returns:
        Dict with account_id, org, project, pipeline_id, execution_id

    Raises:
        ValueError: If URL format is invalid
    """
    # Pattern matches both /executions/ and /deployments/
    pattern = r'/account/([^/]+)/(?:cd/|all/)?orgs/([^/]+)/projects/([^/]+)/pipelines/[^/]+/(?:executions|deployments)/([^/?]+)'

    match = re.search(pattern, url)
    if not match:
        raise ValueError(
            f"Invalid execution URL format: {url}\n"
            "Expected format: .../account/ID/orgs/ORG/projects/PROJ/pipelines/PIPE/executions/EXEC_ID"
        )

    return {
        "account_id": match.group(1),
        "org": match.group(2),
        "project": match.group(3),
        "execution_id": match.group(4),
    }


def discover_dependencies_recursive(
    templates_api: TemplatesApi,
    template_id: str,
    version: str,
    scope: Scope,
    visited: Set[str],
    depth: int = 0
) -> List[TemplateMetadata]:
    """Recursively discover template dependencies.

    Args:
        templates_api: TemplatesApi instance
        template_id: Template identifier
        version: Version label
        scope: Scope (account/org/project)
        visited: Set of visited template IDs
        depth: Current depth in tree

    Returns:
        List of TemplateMetadata for all templates in tree
    """
    # Create unique key for visited tracking
    visit_key = f"{template_id}@{version}"
    if visit_key in visited:
        return []

    visited.add(visit_key)
    templates = []

    try:
        # Fetch template
        logger.info(f"{'  ' * depth}Fetching: {template_id} ({version})")
        template_data = templates_api.get(template_id, version, scope)

        if not template_data:
            logger.warning(f"{'  ' * depth}Template {template_id} not found")
            return []

        # Parse YAML to get type
        template_yaml = template_data.get('yaml')
        if not template_yaml:
            logger.warning(f"{'  ' * depth}No YAML for {template_id}")
            return []

        template_dict = yaml.safe_load(template_yaml)
        template_type = template_dict.get('template', {}).get('type', '').lower()

        # Determine scope from template
        tmpl_scope = "project" if template_dict.get('template', {}).get('projectIdentifier') else "account"
        tmpl_org = template_dict.get('template', {}).get('orgIdentifier')
        tmpl_project = template_dict.get('template', {}).get('projectIdentifier')

        # Create metadata
        metadata = TemplateMetadata(
            identifier=template_id,
            version=version,
            type=template_type,
            label=None,
            is_stable=False,
            scope=tmpl_scope,
            org=tmpl_org,
            project=tmpl_project,
            depth=depth
        )
        templates.append(metadata)

        # Extract child template references
        child_refs = extract_template_refs(template_dict)
        logger.info(f"{'  ' * depth}Found {len(child_refs)} child template(s)")

        # Recursively fetch children
        for ref in child_refs:
            child_version = ref.version_label or "stable"
            child_templates = discover_dependencies_recursive(
                templates_api,
                ref.identifier,
                child_version,
                scope,
                visited,
                depth + 1
            )
            templates.extend(child_templates)

        return templates

    except Exception as e:
        logger.error(f"{'  ' * depth}Error discovering {template_id}: {e}")
        return templates


class TemplateExtractor:
    """Handles template extraction logic with full validation."""

    def __init__(self, client: HarnessClient, config):
        self.client = client
        self.config = config
        self.templates = TemplatesApi(self.client)

    def _validate_execution(self, execution_id: str, scope: Scope) -> Dict[str, Any]:
        """Validate execution and fetch YAML.

        Args:
            execution_id: Execution ID
            scope: Scope

        Returns:
            Dict with execution, pipeline, and execution_yaml

        Raises:
            ValueError: If execution failed or validation failed
        """
        logger.info("Fetching execution metadata...")
        execution = self.templates.get_execution(execution_id, scope)

        # Get execution status - SDK uses snake_case
        exec_summary = execution.get('pipeline_execution_summary', {}) if isinstance(execution, dict) else {}
        if not exec_summary:
            exec_summary = execution if isinstance(execution, dict) else {}

        status = exec_summary.get('status') if isinstance(exec_summary, dict) else None
        logger.info(f"Execution status: {status}")

        if status not in ['Success', 'succeeded']:
            raise ValueError(f"Execution failed or not completed: {status}")

        # Get pipeline YAML - try both snake_case and camelCase
        pipeline_id = exec_summary.get('pipeline_identifier') or exec_summary.get('pipelineIdentifier')
        if not pipeline_id:
            if self.config.verbose:
                logger.info(f"exec_summary keys: {list(exec_summary.keys()) if isinstance(exec_summary, dict) else 'NOT A DICT'}")
            raise ValueError("No pipeline identifier in execution")

        logger.info(f"Fetching pipeline: {pipeline_id}")
        pipeline = self.templates.get_pipeline(pipeline_id, scope)
        pipeline_yaml = pipeline.get('yaml_pipeline', '')  # SDK returns snake_case after to_dict()

        # Get execution YAML
        logger.info("Fetching execution YAML...")
        exec_metadata = self.templates.get_execution_metadata(execution_id, scope)

        # Debug: Check what's actually in the response
        if self.config.verbose:
            logger.info(f"exec_metadata keys: {list(exec_metadata.keys()) if isinstance(exec_metadata, dict) else 'not a dict'}")

        # Try to get execution_yaml (SDK returns snake_case keys after to_dict())
        execution_yaml = exec_metadata.get('execution_yaml', '')
        if not execution_yaml and 'data' in exec_metadata:
            execution_yaml = exec_metadata.get('data', {}).get('execution_yaml', '')
            if self.config.verbose:
                logger.info(f"Found execution_yaml under 'data' key")

        return {
            "execution": execution,
            "pipeline": pipeline,
            "pipeline_id": pipeline_id,
            "pipeline_yaml": pipeline_yaml,
            "execution_yaml": execution_yaml,
            "status": status
        }

    def _run_validations(
        self,
        template_id: str,
        template_yaml: Dict,
        pipeline_yaml: str,
        execution_yaml: str
    ) -> Dict[str, Any]:
        """Run all 4 validation levels.

        Args:
            template_id: Template identifier
            template_yaml: Template YAML dict
            pipeline_yaml: Pipeline YAML string
            execution_yaml: Execution YAML string

        Returns:
            Dict with all validation results
        """
        results = {}

        # Extract template version from template YAML
        template_version = template_yaml.get('template', {}).get('versionLabel')

        # Validation 1: Pipeline reference and version
        if not self.config.verbose:
            logger.info("VALIDATION 1: Checking pipeline reference...")
        results['pipeline_ref'] = validate_template_in_pipeline_yaml(
            template_id,
            pipeline_yaml,
            template_version,
            verbose=self.config.verbose
        )
        if results['pipeline_ref']['found']:
            count = results['pipeline_ref']['reference_count']
            versions = results['pipeline_ref'].get('versions', [])
            version_match = results['pipeline_ref'].get('version_match', True)

            logger.info(f"  ✓ Template referenced {count} time(s)")

            if template_version and versions:
                if version_match:
                    logger.info(f"  ✓ Version match: {versions[0]}")
                else:
                    logger.warning(f"  ⚠ Version mismatch: expected {template_version}, found {versions}")
        else:
            logger.warning(f"  ⚠ Template not directly referenced")

        # Validation 2: Structure match
        if execution_yaml:
            if not self.config.verbose:
                logger.info("VALIDATION 2: Checking structure match...")
            results['structure'] = validate_template_structure_in_execution_yaml(
                template_yaml,
                execution_yaml,
                template_id,
                verbose=self.config.verbose
            )
            match_pct = results['structure'].get('match_percentage', 0)
            matching = results['structure'].get('matching_keys', 0)
            total = results['structure'].get('total_keys', 0)
            logger.info(f"  ✓ Structure match: {match_pct:.1f}% ({matching}/{total} keys)")

            if self.config.verbose and results['structure'].get('match_locations'):
                logger.info(f"     Best match found at:")
                for loc in results['structure']['match_locations']:
                    logger.info(f"       - {loc}")
        else:
            logger.warning("  ⚠ No execution YAML for structure validation")
            results['structure'] = {'found': False, 'match_percentage': 0}

        # Validation 3: Content hash
        if execution_yaml:
            if not self.config.verbose:
                logger.info("VALIDATION 3: Checking content hash...")
            results['hash'] = validate_content_hash(
                template_yaml,
                execution_yaml,
                template_id,
                verbose=self.config.verbose
            )

            items_compared = results['hash'].get('items_compared', 0)
            items_matched = results['hash'].get('items_matched', 0)
            match_pct = results['hash'].get('match_percentage', 0)

            if items_compared > 0:
                # Item-by-item comparison
                if results['hash'].get('hash_match'):
                    logger.info(f"  ✓ Content hash match: {items_matched}/{items_compared} items ({match_pct:.0f}%)")
                else:
                    if match_pct > 0:
                        logger.info(f"  ⚠ Partial hash match: {items_matched}/{items_compared} items ({match_pct:.0f}%)")
                    else:
                        logger.warning(f"  ⚠ No matching items found")
            else:
                # Full block comparison (fallback)
                template_hash = results['hash'].get('template_hash', 'N/A')
                execution_hash = results['hash'].get('execution_hash', 'N/A')
                if results['hash'].get('hash_match'):
                    logger.info(f"  ✓ Hash match: {template_hash}")
                else:
                    logger.warning(f"  ⚠ Hash mismatch (expected for expanded templates)")
                    logger.info(f"     Template hash:  {template_hash}")
                    logger.info(f"     Execution hash: {execution_hash}")
        else:
            results['hash'] = {'found': False, 'hash_match': False}

        # Validation 4: Scripts
        if execution_yaml:
            if not self.config.verbose:
                logger.info("VALIDATION 4: Checking script content...")
            results['scripts'] = validate_scripts(
                template_yaml,
                execution_yaml,
                template_id,
                verbose=self.config.verbose
            )
            count = results['scripts'].get('scripts_validated', 0)
            avg = results['scripts'].get('avg_match_percentage', 0)
            logger.info(f"  ✓ {count} script(s) validated, avg match: {avg:.1f}%")
        else:
            results['scripts'] = {'found': False, 'scripts_validated': 0}

        return results


    def extract_single(self) -> PluginResult:
        """Extract single template with full validation.

        Returns:
            PluginResult with extracted template information
        """
        try:
            logger.info("=" * 60)
            logger.info("STARTING SINGLE TEMPLATE EXTRACTION")
            logger.info("=" * 60)

            # Parse execution URL
            logger.info(f"Parsing execution URL...")
            url_parts = parse_execution_url(self.config.execution_url)
            logger.info(f"  Organization: {url_parts['org']}")
            logger.info(f"  Project: {url_parts['project']}")
            logger.info(f"  Execution: {url_parts['execution_id']}")

            if self.config.verbose:
                logger.info(f"\n📋 PARSED URL DATA:")
                logger.info(f"{yaml.dump(url_parts, default_flow_style=False)}")

            # Create scope
            scope = _create_scope(
                account_id=url_parts['account_id'],
                org=url_parts['org'],
                project=url_parts['project']
            )

            # Validate execution
            exec_data = self._validate_execution(url_parts['execution_id'], scope)

            if self.config.verbose:
                logger.info(f"\n📋 EXECUTION METADATA:")
                exec_summary = {
                    'status': exec_data.get('status'),
                    'pipeline': exec_data.get('pipeline_id'),
                    'execution_id': url_parts['execution_id']
                }
                logger.info(f"{yaml.dump(exec_summary, default_flow_style=False)}")

                logger.info(f"\n📋 PIPELINE YAML (first 50 lines):")
                pipeline_lines = exec_data['pipeline_yaml'].split('\n')[:50]
                logger.info('\n'.join(pipeline_lines))

                logger.info(f"\n📋 EXECUTION YAML (first 50 lines):")
                execution_lines = exec_data['execution_yaml'].split('\n')[:50]
                logger.info('\n'.join(execution_lines))

            # Determine template type
            logger.info(f"Fetching template: {self.config.template_id}")

            # Fetch template
            template_data = self.templates.get(
                self.config.template_id,
                self.config.source_version or "v1",
                scope
            )

            if not template_data:
                return PluginResult(
                    success=False,
                    message=f"Template {self.config.template_id} not found",
                    outputs={},
                    error="Template not found in Harness"
                )

            template_yaml_str = template_data.get('yaml')
            template_yaml = yaml.safe_load(template_yaml_str)

            # Determine template type from YAML
            template_type = template_yaml.get('template', {}).get('type', '').lower()
            if not template_type or template_type == '':
                template_type = "unknown"
            logger.info(f"  Template type: {template_type}")

            if self.config.verbose:
                logger.info(f"\n📋 ORIGINAL TEMPLATE YAML:")
                logger.info(template_yaml_str)

            # Run all 4 validation levels
            logger.info("")
            logger.info("Running 4-level validation...")
            validations = self._run_validations(
                self.config.template_id,
                template_yaml,
                exec_data['pipeline_yaml'],
                exec_data['execution_yaml']
            )

            if self.config.verbose:
                logger.info(f"\n📋 DETAILED VALIDATION RESULTS:")
                logger.info(f"{yaml.dump(validations, default_flow_style=False)}")

            # Process template
            logger.info("")
            logger.info("Processing template...")

            # Remove scope identifiers (projectIdentifier, orgIdentifier)
            template_yaml = remove_scope_identifiers(template_yaml)
            logger.info("  ✓ Removed scope identifiers")

            # Qualify template refs (SG_Template → account.SG_Template)
            template_yaml = qualify_template_refs(template_yaml, 'account')
            logger.info("  ✓ Qualified template references")

            # Add tracking tags
            template_yaml = add_template_tags(template_yaml, {
                'source_version': self.config.source_version or 'v1',
                'managed_by': 'plugin',
                'template_type': template_type
            })
            logger.info("  ✓ Added tracking tags")

            # Sanitize template (convert secrets/connectors to runtime inputs)
            logger.info("  Sanitizing template (connectors, secrets → <+input>)...")
            template_yaml_str = yaml.dump(template_yaml, default_flow_style=False, sort_keys=False)
            sanitized_yaml_str = sanitize_template(template_yaml_str)
            template_yaml = yaml.safe_load(sanitized_yaml_str)
            logger.info("  ✓ Template sanitized (scripts preserved)")

            if self.config.verbose:
                logger.info(f"\n📋 FINAL PROCESSED TEMPLATE YAML:")
                final_yaml_str = yaml.dump(template_yaml, default_flow_style=False, sort_keys=False)
                logger.info(final_yaml_str)

            # Save template to file
            logger.info("")
            logger.info("Saving template to file...")
            file_path = _save_template_file(
                template_yaml,
                template_type,
                self.config.template_id,
                self.config.source_version or "v1",
                self.config.output_dir
            )

            # Output results
            outputs = {
                "template_id": self.config.template_id,
                "template_type": template_type,
                "template_version": self.config.source_version or "v1",
                "execution_id": url_parts['execution_id'],
                "execution_status": exec_data['status'],
                "mode": "single",
                "validation_passed": validations['pipeline_ref']['found'],
                "validation_structure_match_pct": validations['structure'].get('match_percentage', 0),
                "validation_scripts": validations['scripts'].get('scripts_validated', 0),
                "file_path": str(file_path),
                "saved": True,
            }

            logger.info("=" * 60)
            logger.info("✅ EXTRACTION COMPLETED SUCCESSFULLY")
            logger.info("=" * 60)

            return PluginResult(
                success=True,
                message=f"Successfully extracted template {self.config.template_id}",
                outputs=outputs
            )

        except Exception as e:
            logger.error(f"Extraction failed: {e}", exc_info=True)
            return PluginResult(
                success=False,
                message=f"Extraction failed: {str(e)}",
                outputs={},
                error=str(e)
            )

    def extract_tree(self) -> PluginResult:
        """Extract template tree with full dependency discovery.

        Returns:
            PluginResult with all extracted templates
        """
        try:
            logger.info("=" * 60)
            logger.info("STARTING TEMPLATE TREE EXTRACTION")
            logger.info("=" * 60)

            # Parse execution URL
            url_parts = parse_execution_url(self.config.execution_url)

            # Create scope
            scope = _create_scope(
                account_id=url_parts['account_id'],
                org=url_parts['org'],
                project=url_parts['project']
            )

            # Validate execution and get execution data for validations
            exec_data = self._validate_execution(url_parts['execution_id'], scope)

            # Discover dependency tree
            logger.info("")
            logger.info("Discovering dependency tree...")
            visited = set()
            all_templates = discover_dependencies_recursive(
                self.templates,
                self.config.template_id,
                self.config.source_version or "v1",
                scope,
                visited,
                depth=0
            )

            logger.info(f"  ✓ Discovered {len(all_templates)} template(s) in tree")

            # Process each template
            processed = 0
            saved_files = []
            for tmpl in all_templates:
                logger.info("")
                logger.info(f"Processing {tmpl.identifier} (depth {tmpl.depth})...")

                # Fetch template YAML
                template_data = self.templates.get(tmpl.identifier, tmpl.version, scope)
                if not template_data:
                    logger.warning(f"  ⚠ Could not fetch {tmpl.identifier}")
                    continue

                template_yaml_str = template_data.get('yaml')
                template_yaml = yaml.safe_load(template_yaml_str)

                if self.config.verbose:
                    logger.info(f"\n  📋 ORIGINAL YAML ({tmpl.identifier}):")
                    logger.info(f"  {template_yaml_str}")

                # Run 4-level validation
                logger.info("  Running 4-level validation...")
                validations = self._run_validations(
                    tmpl.identifier,
                    template_yaml,
                    exec_data['pipeline_yaml'],
                    exec_data['execution_yaml']
                )
                logger.info(f"  ✓ Validation completed")

                if self.config.verbose:
                    logger.info(f"\n  📋 VALIDATION RESULTS ({tmpl.identifier}):")
                    logger.info(f"  {yaml.dump(validations, default_flow_style=False)}")

                # Process template
                template_yaml = remove_scope_identifiers(template_yaml)
                template_yaml = qualify_template_refs(template_yaml, 'account')
                template_yaml = add_template_tags(template_yaml, {
                    'source_version': tmpl.version,
                    'managed_by': 'plugin',
                    'template_type': tmpl.type
                })
                logger.info("  ✓ Processed (removed scopes, qualified refs, added tags)")

                # Sanitize template (convert secrets/connectors to runtime inputs)
                template_yaml_str_for_sanitize = yaml.dump(template_yaml, default_flow_style=False, sort_keys=False)
                sanitized_yaml_str = sanitize_template(template_yaml_str_for_sanitize)
                template_yaml = yaml.safe_load(sanitized_yaml_str)
                logger.info("  ✓ Sanitized (connectors, secrets → <+input>, scripts preserved)")

                if self.config.verbose:
                    logger.info(f"\n  📋 PROCESSED YAML ({tmpl.identifier}):")
                    processed_yaml_str = yaml.dump(template_yaml, default_flow_style=False, sort_keys=False)
                    logger.info(f"  {processed_yaml_str}")

                # Save template to file
                file_path = _save_template_file(
                    template_yaml,
                    tmpl.type,
                    tmpl.identifier,
                    tmpl.version,
                    self.config.output_dir
                )
                saved_files.append(str(file_path))

                processed += 1

            # Output results
            outputs = {
                "template_id": self.config.template_id,
                "template_version": self.config.source_version or "v1",
                "execution_id": url_parts['execution_id'],
                "mode": "tree",
                "templates_extracted": len(all_templates),
                "templates_processed": processed,
                "dependency_depth": max(t.depth for t in all_templates) if all_templates else 0,
                "saved_files": saved_files,
                "files_saved": len(saved_files),
                "tree": [
                    {
                        "identifier": tmpl.identifier,
                        "version": tmpl.version,
                        "template_type": tmpl.type,
                        "depth": tmpl.depth
                    }
                    for tmpl in all_templates
                ],
            }

            logger.info("=" * 60)
            logger.info(f"✅ TREE EXTRACTION COMPLETED: {len(all_templates)} template(s)")
            logger.info("=" * 60)

            return PluginResult(
                success=True,
                message=f"Successfully extracted template tree for {self.config.template_id}",
                outputs=outputs
            )

        except Exception as e:
            logger.error(f"Tree extraction failed: {e}", exc_info=True)
            return PluginResult(
                success=False,
                message=f"Tree extraction failed: {str(e)}",
                outputs={},
                error=str(e)
            )


class TemplatePromoter:
    """Handles template promotion logic."""

    def __init__(self, client: HarnessClient, config):
        self.client = client
        self.config = config
        self.templates = TemplatesApi(self.client)
        # Initialize versions manager with path in parent of output directory
        # versions.yaml should be alongside templates/ directory, not inside it
        versions_file = Path(self.config.output_dir).parent / "versions.yaml"
        self.versions_manager = VersionsManager(str(versions_file))


    def _determine_source_version(self, target_tier: int, tier_skip: bool) -> Optional[str]:
        """Determine source version for promotion.

        Returns:
            Source version label or None
        """
        # TODO: Get template type from config or fetch template first
        # Current: Assumes "stage" - works for single-type repos
        # Future: Support template_type in config or refactor to fetch before determine
        template_type = "stage"
        identifier = self.config.template_id

        # If source_version explicitly provided in config, use it
        if self.config.source_version:
            return self.config.source_version

        # For tier-1, must provide explicit source_version (v1, v2, etc.)
        if target_tier == 1:
            return None

        # For tier-2+, look for previous tier
        if tier_skip:
            # Find highest tier below target
            highest_tier = self.versions_manager.get_highest_tier_below(
                template_type,
                identifier,
                target_tier
            )
            if highest_tier:
                return f"tier-{highest_tier}"
        else:
            # Must come from tier-N-1
            previous_tier = target_tier - 1
            return f"tier-{previous_tier}"

        return None

    def _validate_promotion_rules(
        self,
        source_version: str,
        target_tier: int,
        tier_skip: bool,
        template_id: str = None,
        template_type: str = "stage"
    ) -> Tuple[bool, str]:
        """Validate promotion follows tier rules.

        Returns:
            (is_valid, error_message)
        """
        # Check if this is a rollback (re-promotion to existing tier)
        if template_id:
            # Try to find the target file (check all template types)
            for tmpl_type in TEMPLATE_TYPES:
                target_file = _get_template_file_path(
                    self.config.output_dir,
                    tmpl_type,
                    template_id,
                    f"tier-{target_tier}"
                )
                if target_file.exists():
                    logger.info(f"  ℹ️  Rollback detected: tier-{target_tier} already exists, re-promoting with {source_version}")
                    return True, ""

        # Rule 1: Semantic versions (v1, v2) can only go to tier-1
        if source_version.startswith('v') and target_tier != 1:
            return False, f"Semantic version {source_version} can only promote to tier-1, not tier-{target_tier}"

        # Rule 2: tier-N can only go to tier-N+1 (unless tier_skip enabled or rollback)
        if source_version.startswith('tier-'):
            source_tier = int(source_version.replace('tier-', ''))

            # Allow same-tier (rollback scenario)
            if target_tier == source_tier:
                logger.info(f"  ℹ️  Same-tier promotion detected (rollback/re-promotion)")
                return True, ""

            # Check backwards (tier-3 → tier-2 without explicit source_version)
            if target_tier < source_tier:
                return False, f"Cannot promote backwards from {source_version} to tier-{target_tier}. For rollback, specify PLUGIN_SOURCE_VERSION explicitly."

            # Check skip (only if not backwards or same)
            if not tier_skip and target_tier != source_tier + 1:
                return False, f"{source_version} can only promote to tier-{source_tier + 1} (enable tier_skip to skip)"

        return True, ""

    def promote(self, version_mapping: Optional[Dict[str, str]] = None) -> PluginResult:
        """Promote template from source version to target tier or stable.

        Promotion Rules:
        - v1/v2/v3 (semantic) can only promote to tier-1
        - tier-N can only promote to tier-N+1
        - With tier_skip=true: can skip to highest available tier below target
        - Any tier can promote to stable

        Returns:
            PluginResult with promotion summary
        """
        try:
            template_id = self.config.template_id
            target_tier = self.config.to_tier
            tier_skip = self.config.tier_skip

            # Check if promoting to stable
            if target_tier == "stable":
                return self._promote_to_stable(template_id, version_mapping)

            logger.info("=" * 60)
            logger.info(f"STARTING TEMPLATE PROMOTION TO TIER-{target_tier}")
            logger.info("=" * 60)
            logger.info(f"Template: {template_id}")
            logger.info(f"Target tier: tier-{target_tier}")
            logger.info(f"Tier skip: {tier_skip}")

            # Step 1: Determine source version
            logger.info("")
            logger.info("Step 1: Determining source version...")
            source_version = self._determine_source_version(target_tier, tier_skip)
            if not source_version:
                error_msg = f"No valid source version found for tier-{target_tier}"
                if target_tier == 1:
                    error_msg += ". For tier-1 promotion, you must provide PLUGIN_SOURCE_VERSION (e.g., v1, v2)"
                return PluginResult(
                    success=False,
                    message=error_msg,
                    outputs={},
                    error="Source version determination failed"
                )

            logger.info(f"  ✓ Source version: {source_version}")

            # Step 2: Validate promotion rules
            logger.info("")
            logger.info("Step 2: Validating promotion rules...")
            valid, error_msg = self._validate_promotion_rules(
                source_version,
                target_tier,
                tier_skip,
                template_id=template_id
            )
            if not valid:
                return PluginResult(
                    success=False,
                    message=error_msg,
                    outputs={},
                    error=error_msg
                )
            logger.info(f"  ✓ Promotion rules validated")

            # Step 3: Fetch source template from Harness
            logger.info("")
            logger.info(f"Step 3: Fetching template from Harness...")
            logger.info(f"  Fetching {template_id} @ {source_version}")

            # Step 3: Fetch template - try local file first, then Harness
            logger.info("")
            logger.info(f"Step 3: Fetching template from local or Harness...")

            # Try to read from local file first (for locally promoted templates)
            template_type = "stage"  # Will be updated from YAML
            source_file = _get_template_file_path(
                self.config.output_dir,
                template_type,
                template_id,
                source_version
            )

            if source_file.exists():
                logger.info(f"  ✓ Found local file: {source_file}")
                with open(source_file, 'r') as f:
                    template_yaml_str = f.read()
                template_yaml = yaml.safe_load(template_yaml_str)
                # Get type from YAML
                template_type = template_yaml.get('template', {}).get('type', 'Stage').lower()
                logger.info(f"  ✓ Loaded from local file (type: {template_type})")
            else:
                # Determine scope from config
                scope = _parse_scope_from_config(self.config)

                logger.info(f"  → Fetching from Harness ({template_id} @ {source_version})...")
                template_data = self.templates.get(
                    template_id,
                    version=source_version,
                    scope=scope
                )

                if not template_data or 'yaml' not in template_data:
                    return PluginResult(
                        success=False,
                        message=f"Failed to fetch template {template_id} @ {source_version}",
                        outputs={},
                        error="Template fetch failed"
                    )

                # Parse YAML from response
                template_yaml_str = template_data.get('yaml')
                template_yaml = yaml.safe_load(template_yaml_str)

                # Get template type from metadata or parsed YAML
                template_type = template_data.get('templateEntityType', 'Stage').lower()
                logger.info(f"  ✓ Fetched from Harness (type: {template_type})")
            logger.info(f"  ✓ Fetched template (type: {template_type})")

            # Step 4: Process template (remove scopes, qualify refs, add tags, update versions)
            logger.info("")
            logger.info(f"Step 4: Processing template...")
            processed_yaml = remove_scope_identifiers(template_yaml)
            logger.info(f"  ✓ Removed scope identifiers")

            processed_yaml = qualify_template_refs(processed_yaml, 'account')
            logger.info(f"  ✓ Qualified template references")

            processed_yaml = add_template_tags(
                processed_yaml,
                {"promoted_from": source_version, "tier": f"tier-{target_tier}"}
            )
            logger.info(f"  ✓ Added tracking tags")

            # Update template's own versionLabel to tier version
            tier_version = f"tier-{target_tier}"
            processed_yaml = update_template_version_label(processed_yaml, tier_version)
            logger.info(f"  ✓ Updated versionLabel to {tier_version}")

            # Update child template versions if version_mapping provided (combined mode)
            if version_mapping:
                processed_yaml = update_child_template_versions(processed_yaml, version_mapping)
                logger.info(f"  ✓ Updated child template versions")

            # Sanitize template (convert secrets/connectors to runtime inputs)
            processed_yaml_str = yaml.dump(processed_yaml, default_flow_style=False, sort_keys=False)
            sanitized_yaml_str = sanitize_template(processed_yaml_str)
            processed_yaml = yaml.safe_load(sanitized_yaml_str)
            logger.info(f"  ✓ Sanitized (connectors, secrets → <+input>, scripts preserved)")

            # Step 5: Write tier file
            logger.info("")
            logger.info(f"Step 5: Writing tier file...")
            file_path = _save_template_file(
                processed_yaml,
                template_type,
                template_id,
                f"tier-{target_tier}",
                self.config.output_dir
            )

            # Step 6: Update versions.yaml
            logger.info("")
            logger.info(f"Step 6: Updating versions.yaml...")
            self.versions_manager.update_tier(
                template_type=template_type,
                identifier=template_id,
                tier_label=f"tier-{target_tier}",
                semantic_version=source_version
            )

            # Prepare outputs
            outputs = {
                "template_id": template_id,
                "source_version": source_version,
                "target_tier": f"tier-{target_tier}",
                "file_path": str(file_path),
                "promotion_status": "success"
            }

            # Step 7: Git operations (if enabled)
            if self.config.enable_git:
                logger.info("")
                logger.info(f"Step 7: Running Git operations...")
                from git_helper import GitOperations

                git = GitOperations()

                # Create branch
                branch_name = f"promotion/{template_id}-{source_version}-to-tier-{target_tier}"
                git.create_branch(branch_name)

                # Commit files
                files_to_commit = [
                    str(file_path),
                    "versions.yaml"
                ]
                commit_message = f"Promote {template_id} from {source_version} to tier-{target_tier}\n\nCo-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
                git.commit_files(files_to_commit, commit_message)

                # Push branch (with API key for Harness Code auth)
                git.push_branch(branch_name, api_key=self.config.api_key)

                # Create PR using Harness Code API (if repo info provided)
                if self.config.org_id and self.config.project_id and self.config.repo_id:
                    pr_url = git.create_pull_request(
                        title=f"Promote {template_id} to tier-{target_tier}",
                        body=f"Promoting {template_id} from {source_version} to tier-{target_tier}\n\n**Changes:**\n- Created {file_path}\n- Updated versions.yaml",
                        source_branch=branch_name,
                        target_branch=self.config.target_branch,
                        api_key=self.config.api_key,
                        account_id=self.config.account_id,
                        org_id=self.config.org_id,
                        project_id=self.config.project_id,
                        repo_id=self.config.repo_id
                    )

                    if pr_url:
                        outputs["pr_url"] = pr_url
                else:
                    logger.warning("  ⚠️ Skipping PR creation (org_id, project_id, or repo_id not provided)")
                    logger.info("  ℹ️  To enable PR creation, set PLUGIN_ORG_ID, PLUGIN_PROJECT_ID, and PLUGIN_REPO_ID")

            # Done
            logger.info("")
            logger.info("=" * 60)
            logger.info("✅ PROMOTION COMPLETED SUCCESSFULLY")
            logger.info("=" * 60)

            return PluginResult(
                success=True,
                message=f"Promoted {template_id} from {source_version} to tier-{target_tier}",
                outputs=outputs
            )

        except Exception as e:
            logger.error(f"Promotion failed: {e}", exc_info=True)
            return PluginResult(
                success=False,
                message=f"Promotion failed: {str(e)}",
                outputs={},
                error=str(e)
            )

    def _promote_to_stable(self, template_id: str, version_mapping: Optional[Dict[str, str]] = None) -> PluginResult:
        """Promote template to stable version.

        Args:
            template_id: Template identifier
            version_mapping: Optional version mapping for bulk stable promotion

        Returns:
            PluginResult with stable promotion summary
        """
        try:
            logger.info("=" * 60)
            logger.info("STARTING TEMPLATE PROMOTION TO STABLE")
            logger.info("=" * 60)
            logger.info(f"Template: {template_id}")

            # Step 1: Determine source version
            logger.info("")
            logger.info("Step 1: Determining source version...")

            # If explicitly provided, use it
            if self.config.source_version:
                source_version = self.config.source_version
                logger.info(f"  ✓ Using explicitly provided version: {source_version}")
            else:
                # Auto-detect: use highest tier
                template_type = "stage"  # TODO: Get actual type
                highest_tier = self.versions_manager.get_highest_tier(template_type, template_id)
                if highest_tier:
                    source_version = f"tier-{highest_tier}"
                    logger.info(f"  ✓ Auto-detected highest tier: {source_version}")
                else:
                    # Fall back to looking for semantic versions
                    error_msg = "No tiers found. Provide PLUGIN_SOURCE_VERSION explicitly (e.g., v1, tier-2)"
                    return PluginResult(
                        success=False,
                        message=error_msg,
                        outputs={},
                        error="Source version determination failed"
                    )

            # Step 2: Determine scope
            logger.info("")
            logger.info("Step 2: Determining scope...")
            if self.config.execution_url:
                url_parts = parse_execution_url(self.config.execution_url)
                scope = Scope(
                    account_id=url_parts['account_id'],
                    org=url_parts['org'],
                    project=url_parts['project']
                )
            elif self.config.project_id:
                scope = Scope(
                    account_id=self.config.account_id,
                    org=self.config.org_id or 'default',
                    project=self.config.project_id
                )
            else:
                scope = Scope(account_id=self.config.account_id)
            logger.info(f"  ✓ Scope: account={scope.account}, org={scope.org}, project={scope.project}")

            # Step 3: Mark version as stable in Harness using SDK
            logger.info("")
            logger.info(f"Step 3: Marking {source_version} as stable in Harness...")
            try:
                self.templates.mark_stable(template_id, source_version, scope)
                logger.info(f"  ✓ Successfully marked {template_id}@{source_version} as stable")
            except Exception as e:
                logger.warning(f"  ⚠️  Failed to mark as stable in Harness: {e}")
                logger.warning(f"  ⚠️  Continuing with local stable.yaml creation...")

            # Step 4: Fetch the template - try local file first, then Harness
            logger.info("")
            logger.info(f"Step 4: Fetching template from local or Harness...")

            # Try to read from local file first (for locally promoted templates)
            template_type = "stage"  # Will be updated from YAML
            source_file = _get_template_file_path(
                self.config.output_dir,
                template_type,
                template_id,
                source_version
            )

            if source_file.exists():
                logger.info(f"  ✓ Found local file: {source_file}")
                with open(source_file, 'r') as f:
                    template_yaml_str = f.read()
                template_yaml = yaml.safe_load(template_yaml_str)
                # Get type from YAML
                template_type = template_yaml.get('template', {}).get('type', 'Stage').lower()
                logger.info(f"  ✓ Loaded from local file (type: {template_type})")
            else:
                # Fetch from Harness
                try:
                    # Try to fetch stable version first
                    template_data = self.templates.get_stable(template_id, scope)
                    logger.info(f"  ✓ Fetched stable template from Harness")

                    # Parse YAML
                    template_yaml_str = template_data.get('yaml')
                    template_yaml = yaml.safe_load(template_yaml_str)
                    template_type = template_data.get('templateEntityType', 'Stage').lower()
                except Exception as e:
                    # Fall back to source version
                    logger.warning(f"  ⚠️  Failed to fetch stable version: {e}")
                    logger.info(f"  → Fetching source version {source_version} instead...")
                    template_data = self.templates.get(template_id, version=source_version, scope=scope)
                    logger.info(f"  ✓ Fetched template @ {source_version} from Harness")

                    if not template_data or 'yaml' not in template_data:
                        return PluginResult(
                            success=False,
                            message=f"Failed to fetch template {template_id}",
                            outputs={},
                            error="Template fetch failed"
                        )

                    # Parse YAML
                    template_yaml_str = template_data.get('yaml')
                    template_yaml = yaml.safe_load(template_yaml_str)
                    template_type = template_data.get('templateEntityType', 'Stage').lower()

            # Step 5: Process template
            logger.info("")
            logger.info(f"Step 5: Processing template...")
            processed_yaml = remove_scope_identifiers(template_yaml)
            logger.info(f"  ✓ Removed scope identifiers")

            processed_yaml = qualify_template_refs(processed_yaml, 'account')
            logger.info(f"  ✓ Qualified template references")

            processed_yaml = add_template_tags(
                processed_yaml,
                {"promoted_from": source_version, "promotion_type": "stable"}
            )
            logger.info(f"  ✓ Added tracking tags")

            # Set versionLabel to "stable"
            processed_yaml = update_template_version_label(processed_yaml, "stable")
            logger.info(f"  ✓ Updated versionLabel to stable")

            # CRITICAL: Remove versionLabel from all child template references
            processed_yaml = remove_child_template_version_labels(processed_yaml)
            logger.info(f"  ✓ Removed versionLabel from child template references")

            # Update child template versions if version_mapping provided (bulk stable)
            if version_mapping:
                # For stable, we actually want to REMOVE labels, not update them
                # version_mapping in this case tells us which templates are being promoted together
                pass  # Already removed above

            # Sanitize template
            processed_yaml_str = yaml.dump(processed_yaml, default_flow_style=False, sort_keys=False)
            sanitized_yaml_str = sanitize_template(processed_yaml_str)
            processed_yaml = yaml.safe_load(sanitized_yaml_str)
            logger.info(f"  ✓ Sanitized template")

            # Step 6: Write stable.yaml file
            logger.info("")
            logger.info(f"Step 6: Writing stable.yaml file...")
            file_path = _save_template_file(
                processed_yaml,
                template_type,
                template_id,
                "stable",
                self.config.output_dir
            )

            # Step 7: Update versions.yaml with stable label
            logger.info("")
            logger.info(f"Step 7: Updating versions.yaml...")
            self.versions_manager.update_stable_label(
                template_type=template_type,
                identifier=template_id,
                source_version=source_version
            )

            # Prepare outputs
            outputs = {
                "template_id": template_id,
                "source_version": source_version,
                "target_tier": "stable",
                "file_path": str(file_path),
                "promotion_status": "success"
            }

            # Done
            logger.info("")
            logger.info("=" * 60)
            logger.info("✅ STABLE PROMOTION COMPLETED SUCCESSFULLY")
            logger.info("=" * 60)

            return PluginResult(
                success=True,
                message=f"Promoted {template_id} from {source_version} to stable",
                outputs=outputs
            )

        except Exception as e:
            logger.error(f"Stable promotion failed: {e}", exc_info=True)
            return PluginResult(
                success=False,
                message=f"Stable promotion failed: {str(e)}",
                outputs={},
                error=str(e)
            )


def _execute_combined_mode(client, config) -> PluginResult:
    """Execute combined mode: extract then promote.

    Args:
        client: HarnessClient instance
        config: PluginConfig instance

    Returns:
        PluginResult with combined outputs
    """
    logger.info("")
    logger.info("=" * 60)
    logger.info("COMBINED MODE: EXTRACT + PROMOTE")
    logger.info("=" * 60)

    # Step 1: Extract templates
    logger.info("")
    logger.info("Phase 1: EXTRACTION")
    logger.info("-" * 60)
    extractor = TemplateExtractor(client, config)

    if config.mode == "single":
        extract_result = extractor.extract_single()
    else:
        extract_result = extractor.extract_tree()

    if not extract_result.success:
        return extract_result

    # Step 2: Promote all extracted templates
    logger.info("")
    logger.info("Phase 2: PROMOTION")
    logger.info("-" * 60)

    # Get list of templates to promote
    templates_to_promote = []
    if config.mode == "tree":
        # In tree mode, we need to promote all extracted templates
        # Parse from extraction outputs
        tree_data = extract_result.outputs.get("tree", [])
        for tmpl in tree_data:
            templates_to_promote.append({
                "template_id": tmpl["identifier"],
                "template_type": tmpl["template_type"],
                "source_version": tmpl["version"]  # Track source version from extraction
            })
    else:
        # Single mode - just one template
        templates_to_promote.append({
            "template_id": config.template_id,
            "template_type": extract_result.outputs.get("template_type", "stage"),
            "source_version": extract_result.outputs.get("template_version", "v1")  # Track source version
        })

    logger.info(f"Promoting {len(templates_to_promote)} template(s) to tier-{config.to_tier}...")

    # Build version mapping for all templates being promoted
    # This allows child templates to reference the correct tier versions
    tier_version = f"tier-{config.to_tier}"
    version_mapping = {
        tmpl["template_id"]: tier_version
        for tmpl in templates_to_promote
    }
    logger.info(f"Version mapping: {version_mapping}")

    # Promote each template
    promoter = TemplatePromoter(client, config)
    promoted_templates = []
    failed_promotions = []

    for tmpl in templates_to_promote:
        template_id = tmpl["template_id"]
        logger.info("")
        logger.info(f"Promoting {template_id}...")

        # Create temp config for this template
        temp_config = config.model_copy()
        temp_config.template_id = template_id
        # Set source_version from extraction result
        temp_config.source_version = tmpl.get("source_version")

        # Run promotion with version_mapping
        temp_promoter = TemplatePromoter(client, temp_config)
        promo_result = temp_promoter.promote(version_mapping=version_mapping)

        if promo_result.success:
            promoted_templates.append(template_id)
            logger.info(f"  ✓ {template_id} promoted successfully")
        else:
            failed_promotions.append({
                "template_id": template_id,
                "error": promo_result.message
            })
            logger.warning(f"  ✗ {template_id} promotion failed: {promo_result.message}")

    # Compile results
    logger.info("")
    logger.info("=" * 60)
    logger.info(f"✅ COMBINED MODE COMPLETED")
    logger.info(f"   Extracted: {len(templates_to_promote)} template(s)")
    logger.info(f"   Promoted: {len(promoted_templates)} template(s)")
    if failed_promotions:
        logger.info(f"   Failed: {len(failed_promotions)} promotion(s)")
    logger.info("=" * 60)

    # Build combined outputs
    combined_outputs = {
        "mode": "combined",
        "extraction": extract_result.outputs,
        "promotion": {
            "target_tier": f"tier-{config.to_tier}",
            "promoted_templates": promoted_templates,
            "failed_promotions": failed_promotions,
            "success_count": len(promoted_templates),
            "failure_count": len(failed_promotions)
        }
    }

    success = len(failed_promotions) == 0
    if success:
        message = f"Successfully extracted and promoted {len(promoted_templates)} template(s) to tier-{config.to_tier}"
    else:
        message = f"Extracted {len(templates_to_promote)} template(s), promoted {len(promoted_templates)}, failed {len(failed_promotions)}"

    return PluginResult(
        success=success,
        message=message,
        outputs=combined_outputs,
        error=None if success else f"{len(failed_promotions)} promotion(s) failed"
    )


def _execute_bulk_promotion(client, config) -> PluginResult:
    """Execute bulk promotion: promote all templates at source tier to target tier or stable.

    Args:
        client: HarnessClient instance
        config: PluginConfig instance

    Returns:
        PluginResult with bulk promotion outputs
    """
    logger.info("")
    logger.info("=" * 60)
    if config.to_tier == "stable":
        logger.info("BULK STABLE PROMOTION MODE: PROMOTE ALL TO STABLE")
    else:
        logger.info("BULK PROMOTION MODE: PROMOTE ALL AT TIER")
    logger.info("=" * 60)

    target_tier = config.to_tier

    # Determine source tier
    # versions.yaml should be alongside templates/ directory, not inside it
    versions_file = Path(config.output_dir).parent / "versions.yaml"
    versions_manager = VersionsManager(str(versions_file))

    # Handle stable promotion
    if target_tier == "stable":
        # For stable, we need to find all templates at their highest tier
        if config.source_version:
            source_version = config.source_version
            logger.info(f"Source version (from config): {source_version}")
        else:
            # For bulk stable, we'll find each template's highest tier individually
            source_version = None
            logger.info("Auto-detect mode: Will find highest tier for each template")

    # If source_version provided for tier promotion, use it
    elif config.source_version:
        source_version = config.source_version
        logger.info(f"Source version (from config): {source_version}")
    else:
        # Auto-detect: source is tier-(target-1)
        if target_tier == 1:
            logger.error("Cannot bulk promote to tier-1. Use extraction mode or specify source_version.")
            return PluginResult(
                success=False,
                message="Bulk promotion to tier-1 requires extraction from execution",
                outputs={},
                error="Invalid tier for bulk promotion"
            )

        source_tier = target_tier - 1
        source_version = f"tier-{source_tier}"
        logger.info(f"Auto-detected source: {source_version} (tier-{source_tier} → tier-{target_tier})")

    # Find all templates at source tier
    logger.info("")
    if target_tier == "stable":
        logger.info(f"Finding all templates for stable promotion...")
    else:
        logger.info(f"Finding templates at {source_version}...")

    # Read versions.yaml and find templates
    all_templates_at_tier = []
    data = versions_manager.load()

    if target_tier == "stable" and not source_version:
        # For bulk stable without explicit source: find highest tier for each template
        for template_type, templates in data.get('templates', {}).items():
            for identifier, metadata in templates.items():
                tiers = metadata.get('tiers', {})
                if tiers:
                    # Find highest tier for this template
                    tier_numbers = [
                        int(label.replace('tier-', ''))
                        for label in tiers.keys()
                        if label.startswith('tier-')
                    ]
                    if tier_numbers:
                        highest = max(tier_numbers)
                        all_templates_at_tier.append({
                            "template_id": identifier,
                            "template_type": template_type,
                            "current_tier": f"tier-{highest}"
                        })
    else:
        # For specific source version: find all templates at that tier
        for template_type, templates in data.get('templates', {}).items():
            for identifier, metadata in templates.items():
                # Check if this template has the source version in any tier
                tiers = metadata.get('tiers', {})
                for tier_label, tier_version in tiers.items():
                    if tier_label == source_version:
                        all_templates_at_tier.append({
                            "template_id": identifier,
                            "template_type": template_type,
                            "current_tier": source_version
                        })
                        break  # Found it, move to next template

    if not all_templates_at_tier:
        msg = "No templates found for bulk stable promotion" if target_tier == "stable" else f"No templates found at {source_version}"
        logger.warning(msg)
        return PluginResult(
            success=False,
            message=f"{msg} in versions.yaml",
            outputs={"templates_found": 0},
            error="No templates to promote"
        )

    logger.info(f"Found {len(all_templates_at_tier)} template(s):")
    for tmpl in all_templates_at_tier:
        logger.info(f"  - {tmpl['template_type']}/{tmpl['template_id']} @ {tmpl['current_tier']}")

    # Build version mapping for all templates being promoted
    if target_tier == "stable":
        # For stable, no version labels on child refs
        version_mapping = None  # Will be handled by stable promotion logic
    else:
        tier_version = f"tier-{target_tier}"
        version_mapping = {
            tmpl["template_id"]: tier_version
            for tmpl in all_templates_at_tier
        }
        logger.info(f"Version mapping: {version_mapping}")

    # Promote each template
    logger.info("")
    if target_tier == "stable":
        logger.info(f"Promoting {len(all_templates_at_tier)} template(s) to stable...")
    else:
        logger.info(f"Promoting {len(all_templates_at_tier)} template(s) to tier-{target_tier}...")

    promoted_templates = []
    failed_promotions = []

    for tmpl in all_templates_at_tier:
        template_id = tmpl["template_id"]
        current_tier = tmpl["current_tier"]
        logger.info("")
        logger.info(f"Promoting {template_id} from {current_tier}...")

        # Create temp config for this template
        temp_config = config.model_copy()
        temp_config.template_id = template_id

        # For bulk stable with auto-detect, set source_version to this template's highest tier
        if target_tier == "stable" and not config.source_version:
            temp_config.source_version = current_tier

        # Run promotion with version_mapping
        temp_promoter = TemplatePromoter(client, temp_config)
        promo_result = temp_promoter.promote(version_mapping=version_mapping)

        if promo_result.success:
            promoted_templates.append(template_id)
            logger.info(f"  ✓ {template_id} promoted successfully")
        else:
            failed_promotions.append({
                "template_id": template_id,
                "error": promo_result.message
            })
            logger.warning(f"  ✗ {template_id} promotion failed: {promo_result.message}")

    # Compile results
    logger.info("")
    logger.info("=" * 60)
    if target_tier == "stable":
        logger.info(f"✅ BULK STABLE PROMOTION COMPLETED")
        logger.info(f"   Target: stable")
    else:
        logger.info(f"✅ BULK PROMOTION COMPLETED")
        logger.info(f"   Source: {source_version}")
        logger.info(f"   Target: tier-{target_tier}")
    logger.info(f"   Promoted: {len(promoted_templates)} template(s)")
    if failed_promotions:
        logger.info(f"   Failed: {len(failed_promotions)} promotion(s)")
    logger.info("=" * 60)

    # Build outputs
    target_display = "stable" if target_tier == "stable" else f"tier-{target_tier}"
    outputs = {
        "mode": "bulk_promotion",
        "source_version": source_version if source_version else "auto-detected",
        "target_tier": target_display,
        "promoted_templates": promoted_templates,
        "failed_promotions": failed_promotions,
        "success_count": len(promoted_templates),
        "failure_count": len(failed_promotions),
        "templates_found": len(all_templates_at_tier)
    }

    success = len(failed_promotions) == 0
    if success:
        if target_tier == "stable":
            message = f"Successfully promoted {len(promoted_templates)} template(s) to stable"
        else:
            message = f"Successfully promoted {len(promoted_templates)} template(s) from {source_version} to tier-{target_tier}"
    else:
        message = f"Promoted {len(promoted_templates)} template(s), failed {len(failed_promotions)}"

    return PluginResult(
        success=success,
        message=message,
        outputs=outputs,
        error=None if success else f"{len(failed_promotions)} promotion(s) failed"
    )


def execute_plugin(config) -> PluginResult:
    """Main plugin execution logic.

    Args:
        config: PluginConfig instance

    Returns:
        PluginResult with success status and outputs
    """
    try:
        logger.info("Initializing Harness client...")

        # Initialize client using SDK
        # Strip /gateway suffix if present (SDK expects base URL without it)
        base_url = config.endpoint.replace('/gateway', '').rstrip('/')

        client = HarnessClient(
            api_key=config.api_key,
            account_id=config.account_id,
            base_url=base_url
        )

        logger.info(f"Client initialized for account: {config.account_id}")
        mode = config.get_mode()
        logger.info(f"Operating in {mode} mode")

        # Route to appropriate handler
        if mode == "extraction":
            extractor = TemplateExtractor(client, config)
            if config.mode == "single":
                return extractor.extract_single()
            else:
                return extractor.extract_tree()
        elif mode == "promotion":
            # Check if bulk promotion (mode: tree) or single template
            if config.mode == "tree":
                return _execute_bulk_promotion(client, config)
            else:
                promoter = TemplatePromoter(client, config)
                return promoter.promote()
        else:  # combined mode
            return _execute_combined_mode(client, config)

    except Exception as e:
        logger.error(f"Plugin execution failed: {e}", exc_info=True)
        return PluginResult(
            success=False,
            message=f"Plugin execution failed: {str(e)}",
            outputs={},
            error=str(e)
        )
