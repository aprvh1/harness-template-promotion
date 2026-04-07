# Test/Staging Environment Configuration

environment = "test"

# Harness Configuration
# Update these with your actual Harness org and project IDs
harness_org_id     = "your_org_id"
harness_project_id = "your_project_id"

# Template Versions
stage_template_version    = "v1.0.0"
pipeline_template_version = "v1.0.0"

# Promotion Tier - use canary for initial testing
promotion_tier = "canary"

# Pipeline Tier Assignments
canary_pipelines = [
  "test-pipeline-1",
  "staging-pipeline-2"
]

early_adopter_pipelines = [
  "service-a-test",
  "service-b-test"
]

stable_pipelines = []

# Tags
tags = {
  Environment = "test"
  Team        = "platform"
  CostCenter  = "engineering"
}
