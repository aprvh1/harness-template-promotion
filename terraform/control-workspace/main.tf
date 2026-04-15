# Control Workspace - Creates IaCM workspaces for each template
# One workspace per template directory

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
  # HARNESS_ACCOUNT_ID - required
  # HARNESS_PLATFORM_API_KEY - required for NextGen resources (like platform_workspace)

  account_id      = var.harness_account_id
  platform_api_key = var.harness_platform_api_key
}

locals {
  # Scan templates directory to find all templates
  templates_base_path = "${path.module}/../../templates"

  # Get all YAML files recursively
  all_yaml_files = fileset(local.templates_base_path, "**/*.yaml")

  # Extract unique template directories
  # From paths like "stage/Stage_Template/v1.yaml", extract "stage/Stage_Template"
  template_directories = distinct([
    for file in local.all_yaml_files :
      join("/", slice(split("/", file), 0, length(split("/", file)) - 1))  # Remove last component (filename)
  ])

  # Create template objects
  all_templates = [
    for dir_path in local.template_directories : {
      key        = replace(dir_path, "/", "_")  # stage/Template -> stage_Template
      type       = split("/", dir_path)[0]      # First part is type
      identifier = split("/", dir_path)[1]      # Second part is identifier
      path       = dir_path
    }
    if fileexists("${local.templates_base_path}/${dir_path}/v1.yaml") ||
       fileexists("${local.templates_base_path}/${dir_path}/tier-1.yaml")
  ]

  templates_map = {
    for tmpl in local.all_templates : tmpl.key => tmpl
  }
}

# Create one IaCM workspace per template
resource "harness_platform_workspace" "template_workspaces" {
  for_each = local.templates_map

  identifier  = "${each.value.type}_${each.value.identifier}"
  name        = "${each.value.type}/${each.value.identifier}"
  description = "Manages all versions of ${each.value.identifier} template"

  # Required attributes
  org_id              = var.org_id
  project_id          = var.project_id
  provisioner_type    = "terraform"
  provisioner_version = var.terraform_version

  # Repository configuration
  repository_connector = var.git_connector_ref
  repository           = var.repository_name
  repository_branch    = var.repository_branch
  repository_path      = "terraform/template-workspace"

  # Cost estimation
  cost_estimation_enabled = false

  # Terraform variables passed to workspace (stored as JSON string)
  terraform_variable {
    key        = "template_type"
    value      = each.value.type
    value_type = "string"
  }

  terraform_variable {
    key        = "template_identifier"
    value      = each.value.identifier
    value_type = "string"
  }

  terraform_variable {
    key        = "harness_account_id"
    value      = var.harness_account_id
    value_type = "string"
  }

  terraform_variable {
    key        = "harness_platform_api_key"
    value      = var.harness_platform_api_key
    value_type = "secret"
  }

  terraform_variable {
    key        = "template_path"
    value      = each.value.path
    value_type = "string"
  }

  # Environment variables
  environment_variable {
    key        = "HARNESS_ACCOUNT_ID"
    value      = var.harness_account_id
    value_type = "string"
  }

  tags = [
    "template_type:${each.value.type}",
    "template_id:${each.value.identifier}",
    "managed_by:terraform-control"
  ]
}
