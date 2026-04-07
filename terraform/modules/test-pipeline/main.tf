terraform {
  required_providers {
    harness = {
      source = "harness/harness"
    }
  }
}

# Standalone test pipeline for stage template testing
resource "harness_platform_pipeline" "test_pipeline" {
  identifier = var.identifier
  name       = var.name
  org_id     = var.org_id
  project_id = var.project_id
  description = var.description

  yaml = templatefile("${path.module}/test-pipeline.yaml.tpl", {
    identifier         = var.identifier
    name               = var.name
    description        = var.description
    org_id             = var.org_id
    project_id         = var.project_id
    stage_template_ref = var.stage_template_ref
    stage_version      = var.stage_version
    test_service       = var.test_service
  })

  tags = merge(
    {
      Purpose = "Testing"
      Type    = "StandaloneStageTest"
    },
    var.tags
  )
}
