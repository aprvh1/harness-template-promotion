# Outputs for template workspace

output "template_versions_deployed" {
  description = "All versions deployed for this template"
  value = {
    for version_key, tmpl in harness_platform_template.versions :
    version_key => {
      identifier = tmpl.identifier
      version    = tmpl.version
      is_stable  = tmpl.is_stable
      scope      = local.scope
    }
  }
}

output "version_count" {
  description = "Number of versions managed"
  value       = length(harness_platform_template.versions)
}

output "template_info" {
  description = "Template information"
  value = {
    identifier = var.template_identifier
    type       = var.template_type
    path       = var.template_path
    scope      = local.scope
  }
}

output "deployment_summary" {
  description = "Human-readable deployment summary"
  value = <<-EOT

  ╔════════════════════════════════════════════════════════════════╗
  ║  Template: ${var.template_identifier} (${var.template_type})
  ╚════════════════════════════════════════════════════════════════╝

  Versions Deployed: ${length(harness_platform_template.versions)}

  Versions:
  %{for version_key in sort(keys(harness_platform_template.versions))~}
    - ${version_key}${harness_platform_template.versions[version_key].is_stable ? " (stable)" : ""}
  %{endfor~}

  Scope: ${local.scope}
  ${local.scope == "org" ? "Org: ${local.org}" : ""}
  ${local.scope == "project" ? "Project: ${local.project}" : ""}

  EOT
}
