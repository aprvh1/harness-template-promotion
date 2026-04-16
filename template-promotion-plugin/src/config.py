"""Plugin configuration using Pydantic BaseSettings.

All configuration loaded from PLUGIN_* environment variables.
"""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from typing import Optional, Literal, Union


class PluginConfig(BaseSettings):
    """Plugin configuration from PLUGIN_* environment variables."""

    # Authentication (required)
    api_key: str = Field(..., description="Harness API key")
    account_id: str = Field(..., description="Harness account ID")
    endpoint: str = Field(
        default="https://app.harness.io/gateway",
        description="Harness API endpoint"
    )

    # Template identification (optional for bulk promotion)
    template_id: Optional[str] = Field(None, description="Template identifier (optional for bulk promotion)")

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
    to_tier: Union[int, Literal["stable"], None] = Field(
        None,
        description="Target tier (1-5) or 'stable'"
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

    @field_validator("execution_url", "source_version", "changelog", "template_id", mode="before")
    @classmethod
    def convert_null_strings(cls, v):
        """Convert string 'null' to None (common when passing through pipelines)."""
        if isinstance(v, str) and v.lower() in ('null', 'none', ''):
            return None
        return v

    @field_validator("to_tier", mode="before")
    @classmethod
    def convert_to_tier_value(cls, v):
        """Convert to_tier value - handle string 'stable' and numeric values."""
        if isinstance(v, str):
            if v.lower() == 'stable':
                return 'stable'
            # Try to convert numeric string to int
            try:
                return int(v)
            except ValueError:
                raise ValueError(f"Invalid to_tier value: {v}. Must be 1-5 or 'stable'")
        return v

    @field_validator("to_tier")
    @classmethod
    def validate_promotion_params(cls, v, info):
        """Validate that at least one operation mode is specified.

        Valid combinations:
        - execution_url only: extraction mode (requires template_id)
        - to_tier only: promotion mode (template_id optional for bulk)
        - both: combined mode (extract + promote)
        """
        if not v and not info.data.get("execution_url"):
            raise ValueError("Either execution_url, to_tier, or both must be provided")

        # Validate tier number range (if not stable)
        if isinstance(v, int) and (v < 1 or v > 5):
            raise ValueError("to_tier must be between 1 and 5, or 'stable'")

        # For extraction or combined mode, template_id is required
        if info.data.get("execution_url") and not info.data.get("template_id"):
            raise ValueError("template_id is required when extraction_url is provided")

        return v

    def get_mode(self) -> Literal["extraction", "promotion", "combined"]:
        """Determine operation mode.

        Returns:
            - "combined": Both execution_url and to_tier provided (extract then promote)
            - "extraction": Only execution_url provided
            - "promotion": Only to_tier provided
        """
        if self.execution_url and self.to_tier:
            return "combined"
        elif self.execution_url:
            return "extraction"
        else:
            return "promotion"
