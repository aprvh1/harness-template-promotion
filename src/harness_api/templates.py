"""Templates API client for Harness SDK.

Provides operations for retrieving templates and pipeline executions.
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Optional, List

if TYPE_CHECKING:
    import sys
    sys.path.append("/Users/apoorvharsh/Downloads/harness-python-sdk/src")
    from harness_python_sdk.client import HarnessClient
    from harness_python_sdk.scope import Scope


class TemplatesApi:
    """API client for template and execution operations."""

    def __init__(self, client: "HarnessClient") -> None:
        """Initialize TemplatesApi with HarnessClient.

        Args:
            client: HarnessClient instance for making requests.
        """
        self._client = client

    def get(
        self,
        identifier: str,
        version: str,
        scope: Optional["Scope"] = None,
    ) -> dict:
        """Get a template by identifier and version.

        Args:
            identifier: Template identifier.
            version: Template version label.
            scope: Scope containing org/project. If None, uses client default scope.

        Returns:
            dict: Template response with YAML and metadata.

        Raises:
            ScopeNotSetError: If scope cannot be resolved.
            ApiError: For non-2xx responses.
        """
        resolved = self._client._resolve_scope(scope)

        # Build URL based on scope level
        url = f"/template/api/templates/{identifier}"

        # Build query parameters
        params = {"accountIdentifier": resolved.account_id, "versionLabel": version}

        if resolved.project:
            params["projectIdentifier"] = resolved.project
            params["orgIdentifier"] = resolved.org
        elif resolved.org:
            params["orgIdentifier"] = resolved.org

        return self._client._get(url, params=params)

    def list_at_project(
        self,
        scope: Optional["Scope"] = None,
        template_type: Optional[str] = None,
    ) -> list[dict]:
        """List all templates at project scope.

        Args:
            scope: Scope containing org/project. If None, uses client default scope.
            template_type: Filter by template type (Step, StepGroup, Stage, Pipeline).

        Returns:
            list[dict]: List of template metadata.

        Raises:
            ScopeNotSetError: If scope cannot be resolved.
            ApiError: For non-2xx responses.
        """
        resolved = self._client._resolve_scope(scope)

        if not resolved.project or not resolved.org:
            raise ValueError("Project and org must be specified for list_at_project")

        url = "/template/api/templates/list"
        params = {
            "accountIdentifier": resolved.account_id,
            "orgIdentifier": resolved.org,
            "projectIdentifier": resolved.project,
            "pageSize": 100,
            "pageIndex": 0,
        }

        if template_type:
            params["templateEntityType"] = template_type

        response = self._client._post(url, params=params, body={})
        return response.get("data", {}).get("content", [])

    def get_execution(
        self,
        execution_id: str,
        scope: Optional["Scope"] = None,
    ) -> dict:
        """Get pipeline execution details including resolved YAML.

        Args:
            execution_id: Execution identifier.
            scope: Scope containing org/project. If None, uses client default scope.

        Returns:
            dict: Execution response with status and resolved pipeline YAML.

        Raises:
            ScopeNotSetError: If scope cannot be resolved.
            ApiError: For non-2xx responses.
        """
        resolved = self._client._resolve_scope(scope)

        if not resolved.project or not resolved.org:
            raise ValueError("Project and org must be specified for execution retrieval")

        url = f"/pipeline/api/pipelines/execution/v2/{execution_id}"
        params = {
            "accountIdentifier": resolved.account_id,
            "orgIdentifier": resolved.org,
            "projectIdentifier": resolved.project,
        }

        return self._client._get(url, params=params)

    def get_execution_input_set(
        self,
        execution_id: str,
        scope: Optional["Scope"] = None,
    ) -> dict:
        """Get compiled/resolved YAML from execution.

        This returns the actual resolved pipeline that was executed,
        with all templates expanded and inputs resolved.

        Args:
            execution_id: Execution identifier.
            scope: Scope containing org/project. If None, uses client default scope.

        Returns:
            dict: Compiled pipeline YAML that was executed.

        Raises:
            ScopeNotSetError: If scope cannot be resolved.
            ApiError: For non-2xx responses.
        """
        resolved = self._client._resolve_scope(scope)

        if not resolved.project or not resolved.org:
            raise ValueError("Project and org must be specified for execution retrieval")

        url = f"/pipeline/api/inputsets/execution/{execution_id}"
        params = {
            "accountIdentifier": resolved.account_id,
            "orgIdentifier": resolved.org,
            "projectIdentifier": resolved.project,
        }

        return self._client._get(url, params=params)

    def get_pipeline(
        self,
        pipeline_id: str,
        scope: Optional["Scope"] = None,
    ) -> dict:
        """Get pipeline YAML.

        Args:
            pipeline_id: Pipeline identifier.
            scope: Scope containing org/project. If None, uses client default scope.

        Returns:
            dict: Pipeline response with YAML.

        Raises:
            ScopeNotSetError: If scope cannot be resolved.
            ApiError: For non-2xx responses.
        """
        resolved = self._client._resolve_scope(scope)

        if not resolved.project or not resolved.org:
            raise ValueError("Project and org must be specified for pipeline retrieval")

        url = f"/pipeline/api/pipelines/{pipeline_id}"
        params = {
            "accountIdentifier": resolved.account_id,
            "orgIdentifier": resolved.org,
            "projectIdentifier": resolved.project,
        }

        return self._client._get(url, params=params)

    def determine_template_type(
        self,
        identifier: str,
        scope: Optional["Scope"] = None,
    ) -> str:
        """Determine template type by fetching template list.

        Args:
            identifier: Template identifier to look up.
            scope: Scope containing org/project.

        Returns:
            str: Template type (step, step_group, stage, pipeline).

        Raises:
            ValueError: If template not found.
        """
        # Try to list templates and find matching identifier
        templates = self.list_at_project(scope)

        for tmpl in templates:
            if tmpl.get("identifier") == identifier:
                tmpl_type = tmpl.get("templateEntityType", "").lower()
                # Convert to our naming convention
                type_map = {
                    "step": "step",
                    "stepgroup": "step_group",
                    "stage": "stage",
                    "pipeline": "pipeline",
                }
                return type_map.get(tmpl_type, tmpl_type)

        raise ValueError(f"Template {identifier} not found at project scope")

    def get_execution_metadata(
        self,
        execution_id: str,
        scope: Optional["Scope"] = None,
    ) -> dict:
        """Get execution metadata including compiled executionYaml.

        This returns the fully resolved/compiled pipeline YAML that was
        actually executed, with all templates expanded and inputs resolved.

        Args:
            execution_id: Execution identifier.
            scope: Scope containing org/project. If None, uses client default scope.

        Returns:
            dict: Metadata response with executionYaml field containing
                  the compiled pipeline YAML.

        Raises:
            ScopeNotSetError: If scope cannot be resolved.
            ApiError: For non-2xx responses.
        """
        resolved = self._client._resolve_scope(scope)

        # This endpoint requires /gateway prefix
        url = f"/gateway/pipeline/api/pipelines/execution/{execution_id}/metadata"
        params = {
            "routingId": resolved.account_id,
            "accountIdentifier": resolved.account_id,
        }

        if resolved.project and resolved.org:
            params["orgIdentifier"] = resolved.org
            params["projectIdentifier"] = resolved.project

        return self._client._get(url, params=params)
