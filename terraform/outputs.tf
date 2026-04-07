output "stage_template_id" {
  description = "ID of the deployed stage template"
  value       = try(module.stage_template.template_id, null)
}

output "stage_template_version" {
  description = "Version of the deployed stage template"
  value       = var.stage_template_version
}

output "pipeline_template_id" {
  description = "ID of the deployed pipeline template"
  value       = try(module.pipeline_template.template_id, null)
}

output "pipeline_template_version" {
  description = "Version of the deployed pipeline template"
  value       = var.pipeline_template_version
}

output "deployed_pipelines" {
  description = "Map of deployed pipeline identifiers by tier"
  value = {
    canary         = var.promotion_tier == "canary" || var.promotion_tier == "all" ? var.canary_pipelines : []
    early_adopters = var.promotion_tier == "early_adopters" || var.promotion_tier == "all" ? var.early_adopter_pipelines : []
    stable         = var.promotion_tier == "stable" || var.promotion_tier == "all" ? var.stable_pipelines : []
  }
}

output "environment" {
  description = "Current deployment environment"
  value       = var.environment
}

output "workspace" {
  description = "Current Terraform workspace"
  value       = terraform.workspace
}
