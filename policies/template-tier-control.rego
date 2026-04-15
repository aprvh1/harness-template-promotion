package pipeline_environment

import future.keywords.contains
import future.keywords.if
import future.keywords.in

# This policy enforces tier-based template access control
# Projects have tier tags that determine which template versions can be used
# Template version labels follow format: "tier-1", "tier-2", "tier-3", "tier-4", "tier-5"
# Pipelines can only use templates at their project's tier or lower
#
# Example:
#   - Project with tier: "tier1" can create pipelines using: "tier-1"
#   - Project with tier: "tier2" can create pipelines using: "tier-1", "tier-2"
#   - Project with tier: "tier5" can use any tier (stable)
#
# Promotion workflow:
#   Week 1: Template version = "tier-1" (only tier 1 projects)
#   Week 2: Create version "tier-2" (tier 1 & 2 projects)
#   Week 3: Create version "tier-3" (tier 1, 2, 3 projects)
#   Week 4: Create version "tier-4" (tier 1, 2, 3, 4 projects)
#   Week 5: Create version "tier-5" (all projects - stable)

# Get project tier from metadata (available in both onsave and onrun events)
project_tier_tag := input.metadata.projectMetadata.tags.tier

# Parse tier from project tag (supports "1", "2", "tier1", "tier2")
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
template_allowed(template_version) {
    # No version label = stable (always allowed)
    template_version == null
}

template_allowed(template_version) if {
    # Parse tiers
    project_tier := parse_project_tier
    template_tier := parse_template_tier(template_version)

    # Project can use templates at its tier or lower
    # Example: project tier 3 can use tier-1, tier-2, tier-3 (not tier-4, tier-5)
    project_tier == template_tier
}

# Deny if project has no tier tag
deny[msg] {
    not parse_project_tier
    msg := "❌ Project must have a 'tier' tag (e.g., tier: \"1\"). This determines which template versions are allowed."
}

# Deny if template version doesn't follow tier format
deny[msg] {
    parse_project_tier  # Project has valid tier
    some ref in template_refs
    ref.versionLabel  # Has a version label
    not startswith(ref.versionLabel, "tier-")  # But doesn't follow tier-X format

    msg := sprintf(
        "❌ Template '%s' version '%s' doesn't follow tier format. Expected: 'tier-1', 'tier-2', etc.",
        [ref.identifier, ref.versionLabel]
    )
}

# Deny if project tier is too low for template
deny[msg] {
    parse_project_tier  # Project has valid tier
    some ref in template_refs
    ref.versionLabel  # Template has version
    startswith(ref.versionLabel, "tier-")  # Follows tier format
    not template_allowed(ref.versionLabel)  # But not allowed

    project_tier := parse_project_tier
    template_tier := parse_template_tier(ref.versionLabel)

    tier_names := {
        1: "Tier 1 (Canary)",
        2: "Tier 2 (Early Adopters)",
        3: "Tier 3 (Wave 1)",
        4: "Tier 4 (Wave 2)",
        5: "Tier 5 (Stable)"
    }

    msg := sprintf(
        "❌ Template '%s' version '%s' requires %s or higher. Your project (tier: %s) is in %s. Wait for the template to be promoted to your tier.",
        [ref.identifier, ref.versionLabel, tier_names[template_tier], project_tier_tag, tier_names[project_tier]]
    )
}
