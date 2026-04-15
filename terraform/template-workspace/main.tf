# Template Workspace - Manages all versions of a single template
# This code runs in each IaCM workspace

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
  # HARNESS_ACCOUNT_ID
  # HARNESS_API_KEY
  account_id      = var.harness_account_id
  platform_api_key = var.harness_platform_api_key
}

locals {
  # Template directory path
  template_dir = "${path.module}/../../templates/${var.template_path}"

  # Get all YAML files in this template directory
  template_files = fileset(local.template_dir, "*.yaml")

  # Parse each YAML file to extract version information
  template_versions = {
    for filename in local.template_files :
    trimsuffix(filename, ".yaml") => {
      version       = trimsuffix(filename, ".yaml")  # v1, tier-1, tier-2, etc.
      yaml_path     = "${local.template_dir}/${filename}"
      yaml_content  = yamldecode(file("${local.template_dir}/${filename}"))
      is_stable     = trimsuffix(filename, ".yaml") == "tier-5"
    }
  }

  # Load versions.yaml to get scope information
  versions_data = yamldecode(file("${path.module}/../../versions.yaml"))
  template_metadata = try(
    local.versions_data.templates[var.template_type][var.template_identifier],
    {}
  )

  # Get scope from versions.yaml
  scope   = try(local.template_metadata.versions[0].scope, "account")
  org     = try(local.template_metadata.versions[0].org, null)
  project = try(local.template_metadata.versions[0].project, null)

  # Get source version mapping from tier_snapshots
  tier_snapshots = try(local.template_metadata.tier_snapshots, {})
}

# Create Harness template resource for each version file
resource "harness_platform_template" "versions" {
  for_each = local.template_versions

  # Template identification
  name = var.template_identifier
  identifier = var.template_identifier
  version    = each.value.version  # v1, tier-1, tier-2, etc.

  # Mark tier-5 as stable
  is_stable = each.value.is_stable

  # Template YAML content
  template_yaml = file(each.value.yaml_path)

  # Tags for tracking (set of strings in key:value format)
  tags = [
    "source_version:${try(local.tier_snapshots[each.key], each.key)}",
    "managed_by:terraform",
    "template_type:${var.template_type}"
  ]

  # Scope handling for org/project-level templates
  org_id     = local.scope == "org" ? local.org : null
  project_id = local.scope == "project" ? local.project : null

  lifecycle {
    # Create before destroy to avoid downtime
    create_before_destroy = true
  }
}
