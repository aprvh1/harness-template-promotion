# Terraform outputs for tier-based template management

output "deployed_templates" {
  description = "Summary of deployed template versions by identifier"
  value = {
    for identifier in distinct([for tv in local.tier_versions : tv.identifier]) :
    identifier => {
      type             = [for tv in local.tier_versions : tv.type if tv.identifier == identifier][0]
      tier_versions    = sort([for tv in local.tier_versions : tv.tier_label if tv.identifier == identifier])
      source_versions  = distinct([for tv in local.tier_versions : tv.source_version if tv.identifier == identifier])
      is_stable        = contains([for tv in local.tier_versions : tv.tier_label if tv.identifier == identifier], "tier-5")
    }
  }
}

output "template_count" {
  description = "Total number of template resources created"
  value       = length(harness_platform_template.templates)
}

output "tier_summary" {
  description = "Summary of templates by tier"
  value = {
    for tier_num in range(1, 6) :
    "tier-${tier_num}" => {
      tier_name    = var.tier_definitions[tostring(tier_num)].name
      template_count = length([
        for tv in local.tier_versions :
        tv if tv.tier_label == "tier-${tier_num}"
      ])
      templates = [
        for tv in local.tier_versions :
        {
          identifier     = tv.identifier
          type           = tv.type
          source_version = tv.source_version
        }
        if tv.tier_label == "tier-${tier_num}"
      ]
    }
  }
}

output "templates_by_type" {
  description = "Templates grouped by type"
  value = {
    for tmpl_type in distinct([for tv in local.tier_versions : tv.type]) :
    tmpl_type => {
      count = length([for tv in local.tier_versions : tv if tv.type == tmpl_type])
      templates = distinct([
        for tv in local.tier_versions :
        tv.identifier if tv.type == tmpl_type
      ])
    }
  }
}

output "deployment_summary" {
  description = "Human-readable deployment summary"
  value = <<-EOT

  ╔════════════════════════════════════════════════════════════════╗
  ║         Harness Template Deployment Summary                    ║
  ╚════════════════════════════════════════════════════════════════╝

  Total Templates Deployed: ${length(harness_platform_template.templates)}

  By Tier:
  %{for tier_num in range(1, 6)~}
    ${var.tier_definitions[tostring(tier_num)].name}: ${length([for tv in local.tier_versions : tv if tv.tier_label == "tier-${tier_num}"])} template(s)
  %{endfor~}

  By Type:
  %{for tmpl_type in distinct([for tv in local.tier_versions : tv.type])~}
    ${tmpl_type}: ${length([for tv in local.tier_versions : tv if tv.type == tmpl_type])} version(s)
  %{endfor~}

  Next Steps:
  - Verify templates in Harness UI
  - Test with tier-1 project pipelines
  - Promote to next tier when ready: python3 scripts/manage_template.py <template> --to-tier <N>

  EOT
}
