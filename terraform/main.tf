locals {
  # Load template content from files
  stage_template_yaml    = file("${path.module}/../templates/stage-templates/${var.stage_template_version}/deploy-stage.yaml")
  pipeline_template_yaml = file("${path.module}/../templates/pipeline-templates/${var.pipeline_template_version}/ci-pipeline.yaml")

  # Determine which pipelines to deploy based on promotion tier
  pipelines_to_deploy = (
    var.promotion_tier == "canary" ? var.canary_pipelines :
    var.promotion_tier == "early_adopters" ? var.early_adopter_pipelines :
    var.promotion_tier == "stable" ? var.stable_pipelines :
    concat(var.canary_pipelines, var.early_adopter_pipelines, var.stable_pipelines)
  )

  # Common tags for all resources
  common_tags = merge(
    {
      Environment        = var.environment
      ManagedBy          = "Terraform"
      TemplateVersion    = var.stage_template_version
      Workspace          = terraform.workspace
    },
    var.tags
  )
}

# Deploy Stage Template
module "stage_template" {
  source = "./modules/stage-template"

  org_id      = var.harness_org_id
  project_id  = var.harness_project_id
  identifier  = "deploy_stage"
  name        = "Deploy Stage Template"
  description = "Reusable deployment stage template with approval and verification"
  version     = var.stage_template_version
  yaml_content = local.stage_template_yaml
  tags        = local.common_tags
}

# Deploy Pipeline Template
module "pipeline_template" {
  source = "./modules/pipeline-template"

  org_id      = var.harness_org_id
  project_id  = var.harness_project_id
  identifier  = "ci_pipeline"
  name        = "CI Pipeline Template"
  description = "CI/CD pipeline template with build, test, and deployment stages"
  version     = var.pipeline_template_version
  yaml_content = local.pipeline_template_yaml
  tags        = local.common_tags

  depends_on = [module.stage_template]
}

# Deploy Pipeline Instances
# This creates pipeline instances for the specified promotion tier
# Uncomment and configure when you have specific pipelines to create
#
# module "canary_pipeline" {
#   source   = "./modules/pipeline"
#   count    = contains(local.pipelines_to_deploy, "test-pipeline-1") ? 1 : 0
#
#   org_id             = var.harness_org_id
#   project_id         = var.harness_project_id
#   identifier         = "test_pipeline_1"
#   name               = "Test Pipeline 1"
#   description        = "Canary test pipeline"
#   pipeline_template_ref = module.pipeline_template.template_id
#   template_version   = var.pipeline_template_version
#   tags               = merge(local.common_tags, { Tier = "canary" })
#
#   depends_on = [module.pipeline_template]
# }
