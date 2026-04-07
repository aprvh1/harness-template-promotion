output "pipeline_id" {
  description = "Identifier of the created pipeline"
  value       = harness_platform_pipeline.pipeline.id
}

output "pipeline_identifier" {
  description = "Pipeline identifier"
  value       = harness_platform_pipeline.pipeline.identifier
}

output "pipeline_name" {
  description = "Pipeline name"
  value       = harness_platform_pipeline.pipeline.name
}

output "template_reference" {
  description = "Referenced template identifier"
  value       = var.pipeline_template_ref
}

output "template_version" {
  description = "Template version in use"
  value       = var.template_version
}
