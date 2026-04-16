"""Core business logic for template extraction and promotion.

This module provides TemplateExtractor and TemplatePromoter classes with full
feature parity to the original scripts, including 4-level validation, sanitization,
and dependency tree discovery.
"""

import re
import logging
import yaml
from typing import Dict, Any, Optional, List, Set, Tuple
from dataclasses import dataclass
from pathlib import Path

from harness_api import HarnessAPIClient
from harness_api.templates import TemplatesApi
from harness_api.client import Scope
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
)
from versions_manager import VersionsManager


logger = logging.getLogger(__name__)


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
    template_dir = Path(output_dir) / template_type / identifier
    template_dir.mkdir(parents=True, exist_ok=True)

    file_path = template_dir / f"{version}.yaml"
    with open(file_path, 'w') as f:
        yaml.dump(template_yaml, f, sort_keys=False, default_flow_style=False)

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

    def __init__(self, client: HarnessAPIClient, config):
        self.client = client
        self.config = config
        self.client.templates = TemplatesApi(self.client)

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
        execution = self.client.templates.get_execution(execution_id, scope)

        # Get execution status
        exec_summary = execution.get('pipelineExecutionSummary', {})
        if not exec_summary:
            exec_summary = execution

        status = exec_summary.get('status')
        logger.info(f"Execution status: {status}")

        if status not in ['Success', 'succeeded']:
            raise ValueError(f"Execution failed or not completed: {status}")

        # Get pipeline YAML
        pipeline_id = exec_summary.get('pipelineIdentifier')
        if not pipeline_id:
            raise ValueError("No pipeline identifier in execution")

        logger.info(f"Fetching pipeline: {pipeline_id}")
        pipeline = self.client.templates.get_pipeline(pipeline_id, scope)
        pipeline_yaml = pipeline.get('yamlPipeline', '')

        # Get execution YAML
        logger.info("Fetching execution YAML...")
        exec_metadata = self.client.templates.get_execution_metadata(execution_id, scope)
        execution_yaml = exec_metadata.get('executionYaml', '')

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
        logger.info("VALIDATION 1: Checking pipeline reference...")
        results['pipeline_ref'] = validate_template_in_pipeline_yaml(
            template_id,
            pipeline_yaml,
            template_version
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
            logger.info("VALIDATION 2: Checking structure match...")
            results['structure'] = validate_template_structure_in_execution_yaml(
                template_yaml,
                execution_yaml,
                template_id
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
            logger.info("VALIDATION 3: Checking content hash...")
            results['hash'] = validate_content_hash(
                template_yaml,
                execution_yaml,
                template_id
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
            logger.info("VALIDATION 4: Checking script content...")
            results['scripts'] = validate_scripts(
                template_yaml,
                execution_yaml,
                template_id
            )
            count = results['scripts'].get('scripts_validated', 0)
            avg = results['scripts'].get('avg_match_percentage', 0)
            logger.info(f"  ✓ {count} script(s) validated, avg match: {avg:.1f}%")
        else:
            results['scripts'] = {'found': False, 'scripts_validated': 0}

        return results

    def _save_template(
        self,
        template_yaml: Dict,
        template_type: str,
        identifier: str,
        version: str
    ) -> Path:
        """Save template YAML to local file.

        Delegates to module-level _save_template_file() function.
        """
        return _save_template_file(
            template_yaml,
            template_type,
            identifier,
            version,
            self.config.output_dir
        )

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
            scope = Scope(
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
            try:
                template_type = self.client.templates.determine_template_type(
                    self.config.template_id,
                    scope
                )
                logger.info(f"  Detected type: {template_type}")
            except Exception as e:
                logger.warning(f"  Could not auto-detect type: {e}")
                template_type = "unknown"

            # Fetch template
            template_data = self.client.templates.get(
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

            if self.config.verbose:
                logger.info(f"\n📋 FINAL PROCESSED TEMPLATE YAML:")
                final_yaml_str = yaml.dump(template_yaml, default_flow_style=False, sort_keys=False)
                logger.info(final_yaml_str)

            # Save template to file
            logger.info("")
            logger.info("Saving template to file...")
            file_path = self._save_template(
                template_yaml,
                template_type,
                self.config.template_id,
                self.config.source_version or "v1"
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
            scope = Scope(
                account_id=url_parts['account_id'],
                org=url_parts['org'],
                project=url_parts['project']
            )

            # Validate execution (side effect: checks execution succeeded)
            _ = self._validate_execution(url_parts['execution_id'], scope)

            # Discover dependency tree
            logger.info("")
            logger.info("Discovering dependency tree...")
            visited = set()
            all_templates = discover_dependencies_recursive(
                self.client.templates,
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
                template_data = self.client.templates.get(tmpl.identifier, tmpl.version, scope)
                if not template_data:
                    logger.warning(f"  ⚠ Could not fetch {tmpl.identifier}")
                    continue

                template_yaml_str = template_data.get('yaml')
                template_yaml = yaml.safe_load(template_yaml_str)

                if self.config.verbose:
                    logger.info(f"\n  📋 ORIGINAL YAML ({tmpl.identifier}):")
                    logger.info(f"  {template_yaml_str}")

                # Process template
                template_yaml = remove_scope_identifiers(template_yaml)
                template_yaml = qualify_template_refs(template_yaml, 'account')
                template_yaml = add_template_tags(template_yaml, {
                    'source_version': tmpl.version,
                    'managed_by': 'plugin',
                    'template_type': tmpl.type
                })
                logger.info("  ✓ Processed (removed scopes, qualified refs, added tags)")

                if self.config.verbose:
                    logger.info(f"\n  📋 PROCESSED YAML ({tmpl.identifier}):")
                    processed_yaml_str = yaml.dump(template_yaml, default_flow_style=False, sort_keys=False)
                    logger.info(f"  {processed_yaml_str}")

                # Save template to file
                file_path = self._save_template(
                    template_yaml,
                    tmpl.type,
                    tmpl.identifier,
                    tmpl.version
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

    def __init__(self, client: HarnessAPIClient, config):
        self.client = client
        self.config = config
        self.client.templates = TemplatesApi(self.client)
        self.versions_manager = VersionsManager()

    def _save_template(
        self,
        template_yaml: Dict,
        template_type: str,
        identifier: str,
        version: str
    ) -> Path:
        """Save template YAML to file.

        Delegates to module-level _save_template_file() function.
        """
        return _save_template_file(
            template_yaml,
            template_type,
            identifier,
            version,
            self.config.output_dir
        )

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
        tier_skip: bool
    ) -> Tuple[bool, str]:
        """Validate promotion follows tier rules.

        Returns:
            (is_valid, error_message)
        """
        # Rule 1: Semantic versions (v1, v2) can only go to tier-1
        if source_version.startswith('v') and target_tier != 1:
            return False, f"Semantic version {source_version} can only promote to tier-1, not tier-{target_tier}"

        # Rule 2: tier-N can only go to tier-N+1 (unless tier_skip enabled)
        if source_version.startswith('tier-'):
            source_tier = int(source_version.replace('tier-', ''))

            # Check backwards first (this is always invalid)
            if target_tier <= source_tier:
                return False, f"Cannot promote backwards from {source_version} to tier-{target_tier}"

            # Check skip (only if not backwards)
            if not tier_skip and target_tier != source_tier + 1:
                return False, f"{source_version} can only promote to tier-{source_tier + 1} (enable tier_skip to skip)"

        return True, ""

    def promote(self) -> PluginResult:
        """Promote template from source version to target tier.

        Promotion Rules:
        - v1/v2/v3 (semantic) can only promote to tier-1
        - tier-N can only promote to tier-N+1
        - With tier_skip=true: can skip to highest available tier below target

        Returns:
            PluginResult with promotion summary
        """
        try:
            template_id = self.config.template_id
            target_tier = self.config.to_tier
            tier_skip = self.config.tier_skip

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
            valid, error_msg = self._validate_promotion_rules(source_version, target_tier, tier_skip)
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

            # Create account-level scope (templates are promoted at account level)
            scope = Scope(account_id=self.config.account_id)

            template_data = self.client.templates.get(
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
            logger.info(f"  ✓ Fetched template (type: {template_type})")

            # Step 4: Process template (remove scopes, qualify refs, add tags)
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

            # Step 5: Write tier file
            logger.info("")
            logger.info(f"Step 5: Writing tier file...")
            file_path = self._save_template(
                processed_yaml,
                template_type,
                template_id,
                f"tier-{target_tier}"
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


def _execute_combined_mode(client, config) -> PluginResult:
    """Execute combined mode: extract then promote.

    Args:
        client: HarnessAPIClient instance
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
                "template_type": tmpl["template_type"]
            })
    else:
        # Single mode - just one template
        templates_to_promote.append({
            "template_id": config.template_id,
            "template_type": extract_result.outputs.get("template_type", "stage")
        })

    logger.info(f"Promoting {len(templates_to_promote)} template(s) to tier-{config.to_tier}...")

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

        # Run promotion
        temp_promoter = TemplatePromoter(client, temp_config)
        promo_result = temp_promoter.promote()

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


def execute_plugin(config) -> PluginResult:
    """Main plugin execution logic.

    Args:
        config: PluginConfig instance

    Returns:
        PluginResult with success status and outputs
    """
    try:
        logger.info("Initializing Harness client...")

        # Initialize client
        client = HarnessAPIClient(
            account_id=config.account_id,
            api_key=config.api_key,
            endpoint=config.endpoint
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
