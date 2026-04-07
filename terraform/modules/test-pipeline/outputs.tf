output "pipeline_id" {
  description = "Identifier of the created test pipeline"
  value       = harness_platform_pipeline.test_pipeline.id
}

output "pipeline_identifier" {
  description = "Test pipeline identifier"
  value       = harness_platform_pipeline.test_pipeline.identifier
}

output "stage_version" {
  description = "Stage template version being tested"
  value       = var.stage_version
}
