# Outputs for control workspace

output "workspaces_created" {
  description = "Map of IaCM workspaces created"
  value = {
    for key, ws in harness_platform_workspace.template_workspaces :
    key => {
      id         = ws.id
      identifier = ws.identifier
      name       = ws.name
    }
  }
}

output "workspace_count" {
  description = "Total number of workspaces created"
  value       = length(harness_platform_workspace.template_workspaces)
}

output "summary" {
  description = "Summary of workspaces by template type"
  value = {
    for tmpl_type in distinct([for tmpl in local.all_templates : tmpl.type]) :
    tmpl_type => {
      count = length([
        for tmpl in local.all_templates :
        tmpl if tmpl.type == tmpl_type
      ])
      templates = [
        for tmpl in local.all_templates :
        tmpl.identifier if tmpl.type == tmpl_type
      ]
    }
  }
}
