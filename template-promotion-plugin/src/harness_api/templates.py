"""Templates API client for Harness SDK.

Provides operations for retrieving templates and pipeline executions.
Uses the official harness_open_api SDK.
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Any

from harness_open_api.api.templates_api import TemplatesApi as OpenApiTemplatesApi
from harness_open_api.api.pipeline_api import PipelineApi
from harness_open_api.api.pipeline_execution_details_api import PipelineExecutionDetailsApi
from harness_open_api.models.scope import Scope

if TYPE_CHECKING:
    from harness_open_api import ApiClient


def _to_dict(obj: Any) -> dict:
    """Convert SDK model object to dictionary.

    Args:
        obj: SDK model object or dict

    Returns:
        dict: Dictionary representation
    """
    if isinstance(obj, dict):
        return obj

    if hasattr(obj, 'to_dict'):
        return obj.to_dict()

    if hasattr(obj, '__dict__'):
        result = {}
        for key, value in obj.__dict__.items():
            if not key.startswith('_'):
                if hasattr(value, 'to_dict'):
                    result[key] = value.to_dict()
                elif hasattr(value, '__dict__') and not isinstance(value, (str, int, float, bool)):
                    result[key] = _to_dict(value)
                else:
                    result[key] = value
        return result

    return obj


class TemplatesApi:
    """API client for template and execution operations."""

    def __init__(self, client) -> None:
        """Initialize TemplatesApi with ApiClient or HarnessClient.

        Args:
            client: ApiClient or HarnessClient instance for making requests.
        """
        # Handle both ApiClient and HarnessClient
        if hasattr(client, '_api_client'):
            # It's a HarnessClient wrapper, extract the internal ApiClient
            self._api_client = client._api_client
        else:
            # It's a raw ApiClient
            self._api_client = client

        self._templates_api = OpenApiTemplatesApi(self._api_client)
        self._pipeline_api = PipelineApi(self._api_client)
        self._execution_api = PipelineExecutionDetailsApi(self._api_client)

    def get(
        self,
        identifier: str,
        version: str,
        scope: "Scope" = None,
        account_id: str = None,
    ) -> dict:
        """Get a template by identifier and version.

        Args:
            identifier: Template identifier.
            version: Template version label.
            scope: Scope containing org/project (optional).
            account_id: Account identifier (required if scope not provided).

        Returns:
            dict: Template response with YAML and metadata.

        Raises:
            ApiError: For non-2xx responses.
        """
        # Build parameters
        kwargs = {
            "version_label": version,
        }

        if scope:
            kwargs["account_identifier"] = scope.account
            if scope.project:
                kwargs["project_identifier"] = scope.project
                kwargs["org_identifier"] = scope.org
            elif scope.org:
                kwargs["org_identifier"] = scope.org
        elif account_id:
            kwargs["account_identifier"] = account_id
        else:
            raise ValueError("Either scope or account_id must be provided")

        # Call SDK method
        response = self._templates_api.get_template(
            account_identifier=kwargs["account_identifier"],
            template_identifier=identifier,
            version_label=version,
            org_identifier=kwargs.get("org_identifier"),
            project_identifier=kwargs.get("project_identifier"),
        )

        # SDK returns ResponseDTOTemplateResponse object
        if hasattr(response, 'data'):
            return _to_dict(response.data)
        return _to_dict(response)

    def list_at_project(
        self,
        scope: "Scope" = None,
        template_type: str = None,
        account_id: str = None,
    ) -> list:
        """List all templates at project scope.

        Args:
            scope: Scope containing org/project.
            template_type: Filter by template type (Step, StepGroup, Stage, Pipeline).
            account_id: Account identifier (required if scope not provided).

        Returns:
            list: List of template metadata.

        Raises:
            ApiError: For non-2xx responses.
        """
        # Build parameters
        kwargs = {}

        if scope:
            kwargs["account_identifier"] = scope.account
            if not scope.project or not scope.org:
                raise ValueError("Project and org must be specified for list_at_project")
            kwargs["project_identifier"] = scope.project
            kwargs["org_identifier"] = scope.org
        elif account_id:
            kwargs["account_identifier"] = account_id
        else:
            raise ValueError("Either scope or account_id must be provided")

        # Call SDK method
        # Note: SDK doesn't support filtering by template_entity_type in list method
        response = self._templates_api.get_template_metadata_list(
            account_identifier=kwargs["account_identifier"],
            template_list_type="All",
            org_identifier=kwargs.get("org_identifier"),
            project_identifier=kwargs.get("project_identifier"),
            size=100,
            page=0,
        )

        # Extract content from response
        if hasattr(response, 'data') and response.data:
            if hasattr(response.data, 'content'):
                content = response.data.content or []
                # Convert each item to dict
                return [_to_dict(item) for item in content]
        return []

    def get_execution(
        self,
        execution_id: str,
        scope: "Scope" = None,
        account_id: str = None,
    ) -> dict:
        """Get pipeline execution details including resolved YAML.

        Args:
            execution_id: Execution identifier.
            scope: Scope containing org/project.
            account_id: Account identifier (required if scope not provided).

        Returns:
            dict: Execution response with status and resolved pipeline YAML.

        Raises:
            ApiError: For non-2xx responses.
        """
        # Build parameters
        kwargs = {}

        if scope:
            kwargs["account_identifier"] = scope.account
            if not scope.project or not scope.org:
                raise ValueError("Project and org must be specified for execution retrieval")
            kwargs["project_identifier"] = scope.project
            kwargs["org_identifier"] = scope.org
        elif account_id:
            kwargs["account_identifier"] = account_id
        else:
            raise ValueError("Either scope or account_id must be provided")

        # Call SDK method
        response = self._execution_api.get_execution_detail_v2(
            account_identifier=kwargs["account_identifier"],
            org_identifier=kwargs["org_identifier"],
            project_identifier=kwargs["project_identifier"],
            plan_execution_id=execution_id,
        )

        # Convert to dict for compatibility
        if hasattr(response, 'data'):
            return _to_dict(response.data)
        return _to_dict(response)

    def get_execution_input_set(
        self,
        execution_id: str,
        scope: "Scope" = None,
        account_id: str = None,
    ) -> dict:
        """Get compiled/resolved YAML from execution.

        This returns the actual resolved pipeline that was executed,
        with all templates expanded and inputs resolved.

        Args:
            execution_id: Execution identifier.
            scope: Scope containing org/project.
            account_id: Account identifier (required if scope not provided).

        Returns:
            dict: Compiled pipeline YAML that was executed.

        Raises:
            ApiError: For non-2xx responses.
        """
        # Build parameters
        kwargs = {}

        if scope:
            kwargs["account_identifier"] = scope.account
            if not scope.project or not scope.org:
                raise ValueError("Project and org must be specified for execution retrieval")
            kwargs["project_identifier"] = scope.project
            kwargs["org_identifier"] = scope.org
        elif account_id:
            kwargs["account_identifier"] = account_id
        else:
            raise ValueError("Either scope or account_id must be provided")

        # Call SDK method
        response = self._execution_api.get_inputset_yaml_v2(
            account_identifier=kwargs["account_identifier"],
            org_identifier=kwargs["org_identifier"],
            project_identifier=kwargs["project_identifier"],
            plan_execution_id=execution_id,
        )

        if hasattr(response, 'data'):
            return _to_dict(response.data)
        return _to_dict(response)

    def get_pipeline(
        self,
        pipeline_id: str,
        scope: "Scope" = None,
        account_id: str = None,
    ) -> dict:
        """Get pipeline YAML.

        Args:
            pipeline_id: Pipeline identifier.
            scope: Scope containing org/project.
            account_id: Account identifier (required if scope not provided).

        Returns:
            dict: Pipeline response with YAML.

        Raises:
            ApiError: For non-2xx responses.
        """
        # Build parameters
        kwargs = {}

        if scope:
            kwargs["account_identifier"] = scope.account
            if not scope.project or not scope.org:
                raise ValueError("Project and org must be specified for pipeline retrieval")
            kwargs["project_identifier"] = scope.project
            kwargs["org_identifier"] = scope.org
        elif account_id:
            kwargs["account_identifier"] = account_id
        else:
            raise ValueError("Either scope or account_id must be provided")

        # Call SDK method
        response = self._pipeline_api.get_pipeline(
            account_identifier=kwargs["account_identifier"],
            org_identifier=kwargs["org_identifier"],
            project_identifier=kwargs["project_identifier"],
            pipeline_identifier=pipeline_id,
        )

        if hasattr(response, 'data'):
            return _to_dict(response.data)
        return _to_dict(response)

    def determine_template_type(
        self,
        identifier: str,
        scope: "Scope" = None,
        account_id: str = None,
    ) -> str:
        """Determine template type by fetching template list.

        Args:
            identifier: Template identifier to look up.
            scope: Scope containing org/project.
            account_id: Account identifier (required if scope not provided).

        Returns:
            str: Template type (step, stepgroup, stage, pipeline).

        Raises:
            ValueError: If template not found.
        """
        # Try to list templates and find matching identifier
        if scope:
            templates = self.list_at_project(scope=scope)
        else:
            templates = self.list_at_project(account_id=account_id)

        for tmpl in templates:
            # Handle both dict and object responses
            tmpl_id = tmpl.get("identifier") if isinstance(tmpl, dict) else getattr(tmpl, "identifier", None)
            tmpl_type = tmpl.get("templateEntityType", "") if isinstance(tmpl, dict) else getattr(tmpl, "template_entity_type", "")

            if tmpl_id == identifier:
                tmpl_type_lower = str(tmpl_type).lower()
                # Convert to our naming convention
                type_map = {
                    "step": "step",
                    "stepgroup": "stepgroup",
                    "stage": "stage",
                    "pipeline": "pipeline",
                }
                return type_map.get(tmpl_type_lower, tmpl_type_lower)

        raise ValueError(f"Template {identifier} not found at project scope")

    def get_execution_metadata(
        self,
        execution_id: str,
        scope: "Scope" = None,
        account_id: str = None,
    ) -> dict:
        """Get execution metadata including compiled executionYaml.

        This returns the fully resolved/compiled pipeline YAML that was
        actually executed, with all templates expanded and inputs resolved.

        Args:
            execution_id: Execution identifier.
            scope: Scope containing org/project.
            account_id: Account identifier (required if scope not provided).

        Returns:
            dict: Metadata response with executionYaml field containing
                  the compiled pipeline YAML.

        Raises:
            ApiError: For non-2xx responses.
        """
        # Build parameters
        kwargs = {}

        if scope:
            kwargs["account_identifier"] = scope.account
            if scope.project and scope.org:
                kwargs["project_identifier"] = scope.project
                kwargs["org_identifier"] = scope.org
        elif account_id:
            kwargs["account_identifier"] = account_id
        else:
            raise ValueError("Either scope or account_id must be provided")

        # Call SDK method - use get_execution_data which provides metadata
        response = self._execution_api.get_execution_data(
            account_identifier=kwargs["account_identifier"],
            plan_execution_id=execution_id,
        )

        if hasattr(response, 'data'):
            return _to_dict(response.data)
        return _to_dict(response)

    def mark_stable(
        self,
        identifier: str,
        version: str,
        scope: "Scope" = None,
        account_id: str = None,
    ) -> dict:
        """Mark a specific template version as stable.

        This calls the Harness API to designate a version as the stable version.
        When users reference the template without a version, they get the stable version.

        Uses SDK's update_stable_template method.

        Args:
            identifier: Template identifier.
            version: Version label to mark as stable (e.g., "tier-2", "v3").
            scope: Scope containing org/project (optional).
            account_id: Account identifier (required if scope not provided).

        Returns:
            dict: Response from Harness API.

        Raises:
            ApiError: For non-2xx responses.
        """
        # Build parameters
        kwargs = {}

        if scope:
            kwargs["account_identifier"] = scope.account
            if scope.project:
                kwargs["project_identifier"] = scope.project
                kwargs["org_identifier"] = scope.org
            elif scope.org:
                kwargs["org_identifier"] = scope.org
        elif account_id:
            kwargs["account_identifier"] = account_id
        else:
            raise ValueError("Either scope or account_id must be provided")

        # Call SDK method
        response = self._templates_api.update_stable_template(
            account_identifier=kwargs["account_identifier"],
            template_identifier=identifier,
            version_label=version,
            org_identifier=kwargs.get("org_identifier"),
            project_identifier=kwargs.get("project_identifier"),
        )

        if hasattr(response, 'data'):
            return _to_dict(response.data)
        return _to_dict(response)

    def get_stable(
        self,
        identifier: str,
        scope: "Scope" = None,
        account_id: str = None,
    ) -> dict:
        """Get the stable version of a template.

        Retrieves the template version that has been marked as stable.
        This is equivalent to calling get() without specifying a version.

        Args:
            identifier: Template identifier.
            scope: Scope containing org/project (optional).
            account_id: Account identifier (required if scope not provided).

        Returns:
            dict: Template response with YAML and metadata for stable version.

        Raises:
            ApiError: For non-2xx responses.
        """
        # Build parameters
        kwargs = {}

        if scope:
            kwargs["account_identifier"] = scope.account
            if scope.project:
                kwargs["project_identifier"] = scope.project
                kwargs["org_identifier"] = scope.org
            elif scope.org:
                kwargs["org_identifier"] = scope.org
        elif account_id:
            kwargs["account_identifier"] = account_id
        else:
            raise ValueError("Either scope or account_id must be provided")

        # Call SDK method without version_label to get stable
        response = self._templates_api.get_template(
            account_identifier=kwargs["account_identifier"],
            template_identifier=identifier,
            org_identifier=kwargs.get("org_identifier"),
            project_identifier=kwargs.get("project_identifier"),
        )

        if hasattr(response, 'data'):
            return _to_dict(response.data)
        return _to_dict(response)
