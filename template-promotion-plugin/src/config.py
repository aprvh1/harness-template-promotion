"""Plugin configuration using Pydantic BaseSettings.

All configuration loaded from PLUGIN_* environment variables.
"""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from typing import Optional, Literal


class PluginConfig(BaseSettings):
    """Plugin configuration from PLUGIN_* environment variables."""

    # Authentication (required)
    api_key: str = Field(..., description="Harness API key")
    account_id: str = Field(..., description="Harness account ID")
    endpoint: str = Field(
        default="https://app.harness.io/gateway",
        description="Harness API endpoint"
    )

    # Template identification (required)
    template_id: str = Field(..., description="Template identifier")

    # Extraction-specific (optional)
    execution_url: Optional[str] = Field(None, description="Harness execution URL")
    project_id: Optional[str] = Field(None, description="Project ID for extraction")
    mode: Literal["single", "tree"] = Field(
        default="single",
        description="Extraction mode: single template or full tree"
    )
    changelog: Optional[str] = Field(None, description="Change description")
    source_version: Optional[str] = Field(None, description="Semantic version (v1.0)")

    # Promotion-specific (optional)
    to_tier: Optional[int] = Field(
        None,
        ge=1,
        le=5,
        description="Target tier (1-5)"
    )
    tier_skip: bool = Field(
        default=False,
        description="Allow skipping intermediate tiers"
    )

    # Output control
    output_format: Literal["json", "text"] = Field(
        default="json",
        description="Output format for DRONE_OUTPUT_FILE"
    )
    verbose: bool = Field(
        default=False,
        description="Enable verbose output showing data at each step"
    )
    output_dir: str = Field(
        default="templates",
        description="Base directory for template files"
    )

    # Git operations (optional)
    enable_git: bool = Field(
        default=False,
        description="Enable Git operations (branch, commit, PR)"
    )

    # Harness Code repository info (optional - for PR creation)
    org_id: Optional[str] = Field(None, description="Harness organization ID (for PR creation)")
    project_id: Optional[str] = Field(None, description="Harness project ID (for PR creation)")
    repo_id: Optional[str] = Field(None, description="Harness Code repository ID (for PR creation)")
    target_branch: str = Field(
        default="main",
        description="Target branch for PR"
    )

    model_config = {
        "env_prefix": "PLUGIN_",
        "case_sensitive": False,
    }


    @field_validator("to_tier")
    @classmethod
    def validate_promotion_params(cls, v, info):
        """Validate promotion-specific parameters."""
        if not v and not info.data.get("execution_url"):
            raise ValueError("Either execution_url or to_tier must be provided")
        return v

    def get_mode(self) -> Literal["extraction", "promotion"]:
        """Determine operation mode."""
        return "extraction" if self.execution_url else "promotion"
