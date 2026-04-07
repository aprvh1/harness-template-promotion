terraform {
  required_providers {
    harness = {
      source = "harness/harness"
    }
  }
}

resource "harness_platform_template" "pipeline_template" {
  identifier  = var.identifier
  name        = var.name
  description = var.description
  org_id      = var.org_id
  project_id  = var.project_id
  version     = var.version
  is_stable   = var.is_stable
  template_yaml = var.yaml_content

  tags = var.tags

  lifecycle {
    create_before_destroy = true
  }
}
