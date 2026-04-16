"""Manage versions.yaml for tracking template promotions."""

import yaml
import logging
from pathlib import Path
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


class VersionsManager:
    """Manage versions.yaml file for tier promotion tracking."""

    def __init__(self, versions_file: str = "versions.yaml"):
        """Initialize with path to versions.yaml file."""
        self.versions_file = Path(versions_file)

    def load(self) -> Dict:
        """Load versions.yaml or create default structure.

        Returns:
            Dict with structure:
            {
                'labels': {'canary': {}, 'stable': {}},
                'templates': {
                    'stage': {
                        'Stage_Template': {
                            'current_version': 'v2',
                            'tiers': {
                                'tier-1': 'v2',
                                'tier-2': 'v1'
                            }
                        }
                    }
                }
            }
        """
        if not self.versions_file.exists():
            logger.info(f"Creating new {self.versions_file}")
            default_data = {
                'labels': {'canary': {}, 'stable': {}},
                'templates': {}
            }
            self.save(default_data)
            return default_data

        with open(self.versions_file, 'r') as f:
            data = yaml.safe_load(f) or {}

        # Ensure required keys exist
        if 'labels' not in data:
            data['labels'] = {'canary': {}, 'stable': {}}
        if 'templates' not in data:
            data['templates'] = {}

        return data

    def save(self, data: Dict) -> None:
        """Write versions.yaml with proper formatting."""
        with open(self.versions_file, 'w') as f:
            yaml.dump(data, f, sort_keys=False, default_flow_style=False)
        logger.info(f"  ✓ Saved {self.versions_file}")

    def update_tier(
        self,
        template_type: str,
        identifier: str,
        tier_label: str,
        semantic_version: str
    ) -> None:
        """Update tier mapping for a template.

        Args:
            template_type: Template type (stage, step_group, etc.)
            identifier: Template identifier
            tier_label: Tier label (tier-1, tier-2, etc.)
            semantic_version: Source semantic version (v1, v2, etc.)
        """
        data = self.load()

        # Initialize template structure if needed
        if template_type not in data['templates']:
            data['templates'][template_type] = {}

        if identifier not in data['templates'][template_type]:
            data['templates'][template_type][identifier] = {
                'current_version': semantic_version,
                'tiers': {}
            }

        # Ensure 'tiers' key exists (for backwards compatibility)
        if 'tiers' not in data['templates'][template_type][identifier]:
            data['templates'][template_type][identifier]['tiers'] = {}

        # Update tier mapping
        data['templates'][template_type][identifier]['tiers'][tier_label] = semantic_version

        # Update current_version to latest
        data['templates'][template_type][identifier]['current_version'] = semantic_version

        self.save(data)
        logger.info(f"  ✓ Updated {identifier}: {tier_label} = {semantic_version}")

    def get_version_at_tier(
        self,
        template_type: str,
        identifier: str,
        tier_label: str
    ) -> Optional[str]:
        """Get semantic version at a specific tier.

        Returns:
            Semantic version (v1, v2, etc.) or None if not found
        """
        data = self.load()

        try:
            return data['templates'][template_type][identifier]['tiers'][tier_label]
        except KeyError:
            return None

    def get_highest_tier_below(
        self,
        template_type: str,
        identifier: str,
        target_tier: int
    ) -> Optional[int]:
        """Find highest tier number below target (for tier_skip support).

        Args:
            template_type: Template type
            identifier: Template identifier
            target_tier: Target tier number (e.g., 3)

        Returns:
            Highest tier number below target that exists, or None
        """
        data = self.load()

        try:
            tiers = data['templates'][template_type][identifier]['tiers']
            # Extract tier numbers from tier labels (tier-1 → 1)
            tier_numbers = [
                int(label.replace('tier-', ''))
                for label in tiers.keys()
                if label.startswith('tier-')
            ]
            # Find max tier < target
            valid_tiers = [t for t in tier_numbers if t < target_tier]
            return max(valid_tiers) if valid_tiers else None
        except (KeyError, ValueError):
            return None

    def find_templates_at_tier(self, tier_label: str) -> List[Dict]:
        """Find all templates at a specific tier.

        Returns:
            List of dicts with template_type, identifier, version
        """
        data = self.load()
        result = []

        for template_type, templates in data.get('templates', {}).items():
            for identifier, metadata in templates.items():
                tier_version = metadata.get('tiers', {}).get(tier_label)
                if tier_version:
                    result.append({
                        'template_type': template_type,
                        'identifier': identifier,
                        'version': tier_version
                    })

        return result

    def update_stable_label(
        self,
        template_type: str,
        identifier: str,
        source_version: str
    ) -> None:
        """Update stable label to track which version is marked as stable.

        Args:
            template_type: Template type (stage, step_group, etc.)
            identifier: Template identifier
            source_version: Source version that was promoted to stable (e.g., tier-2, v1)
        """
        data = self.load()

        # Ensure labels.stable exists
        if 'labels' not in data:
            data['labels'] = {'canary': {}, 'stable': {}}
        if 'stable' not in data['labels']:
            data['labels']['stable'] = {}

        # Track which version was promoted to stable
        # Format: {identifier: source_version}
        data['labels']['stable'][identifier] = source_version

        # Also update current_version in templates section
        if template_type in data['templates'] and identifier in data['templates'][template_type]:
            data['templates'][template_type][identifier]['current_version'] = 'stable'

        self.save(data)
        logger.info(f"  ✓ Updated stable label: {identifier} promoted from {source_version}")

    def get_highest_tier(
        self,
        template_type: str,
        identifier: str
    ) -> Optional[int]:
        """Get highest tier number for a template (for stable promotion).

        Args:
            template_type: Template type
            identifier: Template identifier

        Returns:
            Highest tier number (e.g., 5 for tier-5) or None if no tiers
        """
        data = self.load()

        try:
            tiers = data['templates'][template_type][identifier]['tiers']
            # Extract tier numbers from tier labels (tier-1 → 1)
            tier_numbers = [
                int(label.replace('tier-', ''))
                for label in tiers.keys()
                if label.startswith('tier-')
            ]
            return max(tier_numbers) if tier_numbers else None
        except (KeyError, ValueError):
            return None
