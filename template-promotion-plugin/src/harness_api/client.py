#!/usr/bin/env python3
"""Harness API client wrapper.

Provides a thin wrapper around harness-python-sdk with helper methods
for HTTP requests used by TemplatesApi.
"""

from typing import Optional, Dict
from dataclasses import dataclass

# Import harness_python_sdk (always available in Docker container)
from harness_python_sdk import ApiClient, Configuration
from harness_python_sdk.api import TemplatesApi, PipelineApi


@dataclass
class Scope:
    """Scope for Harness API operations (account/org/project)."""
    account_id: str
    org: Optional[str] = None
    project: Optional[str] = None


class HarnessAPIClient:
    """Client for interacting with Harness API for template operations."""

    def __init__(self, account_id: str, api_key: str, endpoint: str = 'https://app.harness.io/gateway'):
        """
        Initialize Harness API client.

        Args:
            account_id: Harness account ID (required)
            api_key: Harness API key (required)
            endpoint: Harness API endpoint (default: https://app.harness.io/gateway)
        """
        if not account_id:
            raise ValueError("account_id is required")
        if not api_key:
            raise ValueError("api_key is required")

        self.account_id = account_id
        self.api_key = api_key
        self.endpoint = endpoint

        # Initialize SDK client
        self.config = Configuration()
        self.config.host = self.endpoint
        self.config.api_key = {'x-api-key': self.api_key}
        self.api_client = ApiClient(self.config)
        self.templates_api = TemplatesApi(self.api_client)
        self.pipeline_api = PipelineApi(self.api_client)

        # Set default scope
        self.default_scope = None

    def _resolve_scope(self, scope):
        """Resolve scope (use provided or default)."""
        return scope if scope else self.default_scope

    def _get(self, url: str, params: Optional[Dict] = None):
        """Make HTTP GET request."""
        import requests
        full_url = f"{self.endpoint}{url}"
        headers = {'x-api-key': self.api_key}
        response = requests.get(full_url, params=params, headers=headers)
        response.raise_for_status()
        return response.json().get('data', {})

    def _post(self, url: str, params: Optional[Dict] = None, body: Optional[Dict] = None):
        """Make HTTP POST request."""
        import requests
        full_url = f"{self.endpoint}{url}"
        headers = {
            'x-api-key': self.api_key,
            'Content-Type': 'application/json'
        }
        response = requests.post(full_url, params=params, json=body, headers=headers)
        response.raise_for_status()
        return response.json()
