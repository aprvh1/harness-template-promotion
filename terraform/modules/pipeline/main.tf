terraform {
  required_providers {
    harness = {
      source = "harness/harness"
    }
  }
}

resource "harness_platform_pipeline" "pipeline" {
  identifier = var.identifier
  name       = var.name
  org_id     = var.org_id
  project_id = var.project_id
  description = var.description

  yaml = templatefile("${path.module}/pipeline.yaml.tpl", {
    identifier             = var.identifier
    name                   = var.name
    description            = var.description
    pipeline_template_ref  = var.pipeline_template_ref
    template_version       = var.template_version
    org_id                 = var.org_id
    project_id             = var.project_id
    template_inputs        = var.template_inputs
  })

  tags = var.tags
}
