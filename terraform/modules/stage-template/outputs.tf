output "template_id" {
  description = "Identifier of the created stage template"
  value       = harness_platform_template.stage_template.id
}

output "template_identifier" {
  description = "Template identifier"
  value       = harness_platform_template.stage_template.identifier
}

output "template_version" {
  description = "Template version"
  value       = harness_platform_template.stage_template.version
}

output "template_name" {
  description = "Template name"
  value       = harness_platform_template.stage_template.name
}
