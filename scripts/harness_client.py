#!/usr/bin/env python3
"""Harness API client for template operations.

This module provides a wrapper around the Harness API for template-related operations
including fetching templates, checking existence, and retrieving template content.
"""

import os
import sys
from typing import Optional, Dict, Any
import hashlib
import json

# Try to import harness_python_sdk
try:
    from harness_python_sdk import ApiClient, Configuration
    from harness_python_sdk.api import TemplatesApi, PipelineApi
    HAS_SDK = True
except ImportError:
    HAS_SDK = False
    print("Warning: harness_python_sdk not installed. Install with: pip install harness-python-sdk", file=sys.stderr)


class HarnessAPIClient:
    """Client for interacting with Harness API for template operations."""

    def __init__(self, account_id: Optional[str] = None, api_key: Optional[str] = None, endpoint: Optional[str] = None):
        """
        Initialize Harness API client.

        Args:
            account_id: Harness account ID (defaults to HARNESS_ACCOUNT_ID env var)
            api_key: Harness API key (defaults to HARNESS_API_KEY env var)
            endpoint: Harness API endpoint (defaults to HARNESS_ENDPOINT or https://app.harness.io/gateway)
        """
        self.account_id = account_id or os.getenv('HARNESS_ACCOUNT_ID')
        self.api_key = api_key or os.getenv('HARNESS_API_KEY')
        self.endpoint = endpoint or os.getenv('HARNESS_ENDPOINT', 'https://app.harness.io/gateway')

        if not self.account_id:
            raise ValueError("HARNESS_ACCOUNT_ID must be provided or set as environment variable")
        if not self.api_key:
            raise ValueError("HARNESS_API_KEY must be provided or set as environment variable")

        if HAS_SDK:
            self.config = Configuration(
                host=self.endpoint,
                api_key={'x-api-key': self.api_key}
            )
            self.api_client = ApiClient(self.config)
            self.templates_api = TemplatesApi(self.api_client)
            self.pipeline_api = PipelineApi(self.api_client)
        else:
            # Fallback to direct HTTP requests if SDK not available
            self.templates_api = None
            self.pipeline_api = None

    def get_template_version(self, identifier: str, version_label: str,
                           org: Optional[str] = None, project: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get a specific template version by identifier and version label.

        Args:
            identifier: Template identifier
            version_label: Version label (e.g., "tier-1", "tier-2", "v1.3")
            org: Organization identifier (for org-level templates)
            project: Project identifier (for project-level templates)

        Returns:
            Template data dictionary with 'yaml' and 'metadata' keys, or None if not found
        """
        try:
            if HAS_SDK and self.templates_api:
                # Use SDK to fetch template
                response = self.templates_api.get_template(
                    account_identifier=self.account_id,
                    template_identifier=identifier,
                    version_label=version_label,
                    org_identifier=org,
                    project_identifier=project
                )

                if response and hasattr(response, 'data'):
                    template_data = response.data
                    return {
                        'yaml': template_data.get('yaml', ''),
                        'metadata': {
                            'identifier': template_data.get('identifier'),
                            'version': template_data.get('versionLabel'),
                            'name': template_data.get('name'),
                            'tags': template_data.get('tags', {}),
                        }
                    }
            else:
                # Fallback to HTTP request
                import requests

                url = f"{self.endpoint}/template-service/api/templates/{identifier}"
                params = {
                    'accountIdentifier': self.account_id,
                    'versionLabel': version_label
                }
                if org:
                    params['orgIdentifier'] = org
                if project:
                    params['projectIdentifier'] = project

                headers = {'x-api-key': self.api_key}
                response = requests.get(url, params=params, headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    template_data = data.get('data', {})
                    return {
                        'yaml': template_data.get('yaml', ''),
                        'metadata': {
                            'identifier': template_data.get('identifier'),
                            'version': template_data.get('versionLabel'),
                            'name': template_data.get('name'),
                            'tags': template_data.get('tags', {}),
                        }
                    }
                elif response.status_code == 404:
                    return None
                else:
                    print(f"Error fetching template: HTTP {response.status_code}", file=sys.stderr)
                    return None

        except Exception as e:
            print(f"Error fetching template {identifier} version {version_label}: {e}", file=sys.stderr)
            return None

    def check_template_exists(self, identifier: str, version_label: str,
                            org: Optional[str] = None, project: Optional[str] = None) -> bool:
        """
        Check if a template version exists.

        Args:
            identifier: Template identifier
            version_label: Version label (e.g., "tier-1", "tier-2")
            org: Organization identifier
            project: Project identifier

        Returns:
            True if template version exists, False otherwise
        """
        result = self.get_template_version(identifier, version_label, org, project)
        return result is not None

    def get_template_from_execution(self, execution_url: str) -> Optional[Dict[str, Any]]:
        """
        Extract template information from a pipeline execution URL.

        This is a placeholder - actual implementation would parse the execution URL,
        fetch the execution details, and extract template information.

        Args:
            execution_url: Full URL to pipeline execution

        Returns:
            Dictionary with template data, or None if not found
        """
        # Parse execution URL to extract identifiers
        # Example URL: https://app.harness.io/ng/account/ABC/orgs/myorg/projects/myproj/pipelines/mypipe/executions/exec-123

        try:
            import re
            from urllib.parse import urlparse

            # Parse URL components
            parsed = urlparse(execution_url)
            path_parts = parsed.path.split('/')

            # Extract account, org, project, pipeline, execution IDs
            identifiers = {}
            for i, part in enumerate(path_parts):
                if part == 'account' and i + 1 < len(path_parts):
                    identifiers['account'] = path_parts[i + 1]
                elif part == 'orgs' and i + 1 < len(path_parts):
                    identifiers['org'] = path_parts[i + 1]
                elif part == 'projects' and i + 1 < len(path_parts):
                    identifiers['project'] = path_parts[i + 1]
                elif part == 'pipelines' and i + 1 < len(path_parts):
                    identifiers['pipeline'] = path_parts[i + 1]
                elif part == 'executions' and i + 1 < len(path_parts):
                    identifiers['execution'] = path_parts[i + 1]

            # Fetch execution details to get template information
            # This would require additional API calls to get execution details
            # and parse the resolved pipeline YAML to extract template references

            print(f"Warning: get_template_from_execution is not fully implemented", file=sys.stderr)
            print(f"Extracted identifiers: {identifiers}", file=sys.stderr)

            return None

        except Exception as e:
            print(f"Error parsing execution URL: {e}", file=sys.stderr)
            return None

    def compute_content_hash(self, template_yaml: str) -> str:
        """
        Compute a hash of template YAML content for comparison.

        Args:
            template_yaml: Template YAML content

        Returns:
            SHA256 hash of the content
        """
        return hashlib.sha256(template_yaml.encode('utf-8')).hexdigest()

    def compare_template_content(self, yaml1: str, yaml2: str) -> bool:
        """
        Compare two template YAML contents.

        Args:
            yaml1: First template YAML
            yaml2: Second template YAML

        Returns:
            True if contents match, False otherwise
        """
        return self.compute_content_hash(yaml1) == self.compute_content_hash(yaml2)


def main():
    """Test the Harness API client."""
    import argparse

    parser = argparse.ArgumentParser(description='Test Harness API client')
    parser.add_argument('--identifier', required=True, help='Template identifier')
    parser.add_argument('--version', required=True, help='Template version label')
    parser.add_argument('--org', help='Organization identifier')
    parser.add_argument('--project', help='Project identifier')

    args = parser.parse_args()

    try:
        client = HarnessAPIClient()

        print(f"Checking if template exists: {args.identifier} version {args.version}")
        exists = client.check_template_exists(args.identifier, args.version, args.org, args.project)
        print(f"Exists: {exists}")

        if exists:
            print(f"\nFetching template content...")
            template = client.get_template_version(args.identifier, args.version, args.org, args.project)
            if template:
                print(f"Template: {template['metadata']}")
                print(f"YAML length: {len(template['yaml'])} bytes")
                print(f"Content hash: {client.compute_content_hash(template['yaml'])}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
