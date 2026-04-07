# Development Environment Configuration

environment = "dev"

# Harness Configuration
# Update these with your actual Harness org and project IDs
harness_org_id     = "your_org_id"
harness_project_id = "your_project_id"

# Template Versions
stage_template_version    = "v1.0.0"
pipeline_template_version = "v1.0.0"

# Promotion Tier - deploy to all in dev
promotion_tier = "all"

# Pipeline Tier Assignments
canary_pipelines = [
  "test-pipeline-1",
  "dev-pipeline-2"
]

early_adopter_pipelines = []

stable_pipelines = []

# Tags
tags = {
  Environment = "dev"
  Team        = "platform"
  CostCenter  = "engineering"
}
