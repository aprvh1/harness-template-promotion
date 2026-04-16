"""Harness API client compatibility wrapper.

Provides HarnessClient interface using harness_open_api SDK.

Usage:
    from harness_api import HarnessClient, Scope

    client = HarnessClient(api_key="...", base_url="...")
    templates = client.templates
    template = templates.get("my_template", "v1", scope)
"""

from harness_open_api import ApiClient, Configuration
from harness_open_api.models.scope import Scope as OpenApiScope
from .templates import TemplatesApi


class Scope(OpenApiScope):
    """
    Compatibility wrapper for Scope that accepts both account_id and account parameters.

    The harness_open_api SDK uses 'account' but our plugin code uses 'account_id'.
    This wrapper accepts both for backwards compatibility.
    """

    def __init__(self, account=None, account_id=None, org=None, project=None):
        """
        Initialize Scope with flexible parameter naming.

        Args:
            account: Account identifier (preferred)
            account_id: Account identifier (alias for backwards compatibility)
            org: Organization identifier
            project: Project identifier
        """
        # Accept either account or account_id
        account_value = account or account_id
        super().__init__(account=account_value, org=org, project=project)


class HarnessClient:
    """
    Compatibility wrapper that provides HarnessClient interface
    using the harness_open_api SDK under the hood.
    """

    def __init__(self, api_key: str, account_id: str = None, base_url: str = "https://app.harness.io/gateway"):
        """
        Initialize Harness client.

        Args:
            api_key: Harness API key
            account_id: Account identifier (optional, for compatibility - stored but not used in SDK config)
            base_url: Base URL for Harness API (default: https://app.harness.io/gateway)
        """
        # Store account_id for backwards compatibility (not used in SDK config)
        self.account_id = account_id

        # Configure API client
        config = Configuration()
        config.host = base_url
        config.api_key['x-api-key'] = api_key

        # Create API client
        self._api_client = ApiClient(config)

        # Initialize API wrappers
        self.templates = TemplatesApi(self._api_client)


__all__ = ["HarnessClient", "Scope", "TemplatesApi"]
