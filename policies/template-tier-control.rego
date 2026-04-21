package pipeline_environment

import future.keywords.contains
import future.keywords.if
import future.keywords.in

# This policy enforces tier-based template access control for gradual rollout
#
# PROJECT TIERS:
#   tier: "dev"  - Development projects (can use ANY template, ANY version, ANY scope)
#   tier: "1"    - Tier 1 Canary (can use tier-1+, account-level only)
#   tier: "2"    - Tier 2 Early Adopters (can use tier-2+, account-level only)
#   tier: "3"    - Tier 3 Wave 1 (can use tier-3+, account-level only)
#   tier: "4"    - Tier 4 Wave 2 (can use tier-4+, account-level only)
#   tier: "5"    - Tier 5 Production (can use tier-5 only, account-level only)
#   stable       - Always allowed for everyone
#
# TEMPLATE VERSIONS:
#   v1, v2, v3...     - Development versions (tier:dev only)
#   tier-1            - Canary rollout (tier 1+ can use)
#   tier-2            - Early adopters (tier 2+ can use)
#   tier-3            - Wave 1 (tier 3+ can use)
#   tier-4            - Wave 2 (tier 4+ can use)
#   tier-5            - Production (tier 5 can use)
#   stable (no label) - Everyone can use
#
# TEMPLATE SCOPE:
#   account.*    - Account-level templates (required for tier 1-5)
#   org.*        - Org-level templates (tier:dev only)
#   ProjectName  - Project-level templates (tier:dev only)
#
# PROMOTION WORKFLOW:
#   1. Developer in tier:dev creates template (v1)
#   2. Promote to tier-1 (tier 1+ projects can test)
#   3. Promote to tier-2 (tier 2+ projects can use)
#   4. Promote to tier-3, tier-4, tier-5 (progressive rollout)
#   5. Mark as stable (all projects can use)

# Get project tier from metadata (available in both onsave and onrun events)
project_tier_tag := input.metadata.projectMetadata.tags.tier

# Check if project is a dev project (special privileges)
is_dev_project {
    project_tier_tag == "dev"
}

# Parse tier from project tag (supports "1", "2", "tier1", "tier2")
# Returns numeric tier (1-5) or null for "dev"
parse_project_tier := to_number(project_tier_tag) if {
    to_number(project_tier_tag)
}

parse_project_tier := to_number(trim_prefix(project_tier_tag, "tier")) if {
    startswith(project_tier_tag, "tier")
    to_number(trim_prefix(project_tier_tag, "tier"))
}

# Parse tier from template version label (e.g., "tier-3" -> 3)
parse_template_tier(version_label) := to_number(trim_prefix(version_label, "tier-")) if {
    startswith(version_label, "tier-")
}

# Check if template is account-level
is_account_template(template_ref) {
    startswith(template_ref, "account.")
}

# Extract all template references from pipeline
template_refs := {ref |
    walk(input.pipeline, [path, value])
    value.templateRef
    ref := {
        "identifier": value.templateRef,
        "versionLabel": object.get(value, "versionLabel", null)
    }
}

# Check if project's tier allows using this template version
# Rule 1: Stable templates (no version label) are always allowed
template_allowed(template_ref, template_version) {
    template_version == null
}

# Rule 2: tier:dev projects can use ANY template (any scope, any version)
template_allowed(template_ref, template_version) {
    is_dev_project
}

# Rule 3: Tier 1-5 projects can use account-level templates at their tier or higher
template_allowed(template_ref, template_version) {
    # Must have numeric tier (1-5)
    project_tier := parse_project_tier
    project_tier

    # Must be account-level template
    is_account_template(template_ref)

    # Template tier must be >= project tier
    # Example: tier-5 project can only use tier-5 (5 >= 5) ✓
    #          tier-1 project can use tier-1 through tier-5 (5 >= 1) ✓
    #          tier-3 project cannot use tier-1 (1 >= 3) ✗
    template_tier := parse_template_tier(template_version)
    template_tier >= project_tier
}

# Deny if project has no tier tag
deny[msg] {
    not project_tier_tag
    msg := "❌ Project must have a 'tier' tag (e.g., tier: \"dev\" or tier: \"1\"). This determines which template versions are allowed."
}

# Deny if project has invalid tier tag
deny[msg] {
    project_tier_tag
    not is_dev_project
    not parse_project_tier
    msg := sprintf(
        "❌ Invalid tier tag '%s'. Must be 'dev' or numeric (1-5).",
        [project_tier_tag]
    )
}

# Deny if non-dev project uses semantic versions (v1, v2, etc.)
deny[msg] {
    not is_dev_project
    some ref in template_refs
    ref.versionLabel
    startswith(ref.versionLabel, "v")

    msg := sprintf(
        "❌ Template '%s' version '%s' is a development version. Only tier:dev projects can use semantic versions (v1, v2, etc.). Promote to tier-1 first.",
        [ref.identifier, ref.versionLabel]
    )
}

# Deny if tier 1-5 project uses non-account-level templates
deny[msg] {
    parse_project_tier  # Has numeric tier (1-5)
    not is_dev_project
    some ref in template_refs
    not is_account_template(ref.identifier)

    msg := sprintf(
        "❌ Template '%s' must be account-level (account.*). Tier 1-5 projects can only use account-level templates for governance. Use tier:dev for testing org/project-level templates.",
        [ref.identifier]
    )
}

# Deny if template tier is too low for project tier
deny[msg] {
    parse_project_tier  # Has numeric tier (1-5)
    not is_dev_project
    some ref in template_refs
    ref.versionLabel  # Template has version
    startswith(ref.versionLabel, "tier-")  # Follows tier format
    is_account_template(ref.identifier)  # Is account-level
    not template_allowed(ref.identifier, ref.versionLabel)  # But not allowed

    project_tier := parse_project_tier
    template_tier := parse_template_tier(ref.versionLabel)

    tier_names := {
        1: "Tier 1 (Canary)",
        2: "Tier 2 (Early Adopters)",
        3: "Tier 3 (Wave 1)",
        4: "Tier 4 (Wave 2)",
        5: "Tier 5 (Production)"
    }

    msg := sprintf(
        "❌ Template '%s' version '%s' (%s) is below your project's tier. Your project (tier: %s) is in %s and can only use tier-%d or higher. Wait for the template to be promoted to tier-%d or higher.",
        [ref.identifier, ref.versionLabel, tier_names[template_tier], project_tier_tag, tier_names[project_tier], project_tier, project_tier]
    )
}
