# Terraform variables for tier-based template management

variable "tier_definitions" {
  description = "Tier definitions for template promotion (informational)"
  type = map(object({
    name          = string
    description   = string
    project_count = number
  }))
  default = {
    "1" = {
      name          = "Tier 1 (Canary)"
      description   = "Initial testing tier"
      project_count = 5
    }
    "2" = {
      name          = "Tier 2 (Early Adopters)"
      description   = "Expanded testing"
      project_count = 15
    }
    "3" = {
      name          = "Tier 3 (Wave 1)"
      description   = "First production wave"
      project_count = 30
    }
    "4" = {
      name          = "Tier 4 (Wave 2)"
      description   = "Second production wave"
      project_count = 30
    }
    "5" = {
      name          = "Tier 5 (Stable)"
      description   = "All projects - stable"
      project_count = 20
    }
  }
}
