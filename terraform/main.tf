# Terraform configuration for tier-based template management
# Reads tier_snapshots from versions.yaml and creates template resources

terraform {
  required_version = ">= 1.0"

  required_providers {
    harness = {
      source  = "harness/harness"
      version = "~> 0.32"
    }
  }
}

provider "harness" {
  # Authentication via environment variables:
  # HARNESS_ACCOUNT_ID - Your Harness account identifier
  # HARNESS_API_KEY    - Your Harness API key or PAT token
  # HARNESS_ENDPOINT   - (Optional) Custom endpoint, defaults to https://app.harness.io/gateway
}

locals {
  # Load versions.yaml
  versions_data = yamldecode(file("${path.module}/../versions.yaml"))

  # Flatten tier snapshots into list of template versions to deploy
  tier_versions = flatten([
    for tmpl_type, templates in try(local.versions_data.templates, {}) : [
      for identifier, data in templates : [
        # Only process templates that have tier_snapshots
        for tier_label, source_version in try(data.tier_snapshots, {}) : {
          # Unique key for Terraform resource
          key = "${identifier}_${replace(tier_label, "-", "_")}"

          # Template metadata
          identifier     = identifier
          type           = tmpl_type
          tier_label     = tier_label
          source_version = source_version

          # File path to tier-specific YAML
          yaml_path = "../templates/${replace(tmpl_type, "_", "-")}/${identifier}-${tier_label}.yaml"

          # Scope (default to account if not specified)
          scope   = try(data.versions[0].scope, "account")
          org     = try(data.versions[0].org, null)
          project = try(data.versions[0].project, null)

          # Mark tier-5 as stable
          is_stable = tier_label == "tier-5"
        }
      ]
    ]
  ])

  # Convert to map for for_each
  tier_versions_map = {
    for tv in local.tier_versions : tv.key => tv
  }
}

# Create Harness template resources for each tier version
resource "harness_platform_template" "templates" {
  for_each = local.tier_versions_map

  # Template identification
  identifier = each.value.identifier
  version    = each.value.tier_label  # tier-1, tier-2, tier-3, etc.

  # Mark tier-5 as stable
  is_stable = each.value.is_stable

  # Template YAML content from tier-specific file
  template_yaml = file("${path.module}/${each.value.yaml_path}")

  # Tags for tracking
  tags = {
    source_version = each.value.source_version
    managed_by     = "terraform"
    tier           = each.value.tier_label
  }

  # Scope handling for org/project-level templates
  org_id     = each.value.scope == "org" ? each.value.org : null
  project_id = each.value.scope == "project" ? each.value.project : null

  lifecycle {
    # Create before destroy to avoid downtime
    create_before_destroy = true
  }
}
