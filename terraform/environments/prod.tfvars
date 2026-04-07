# Production Environment Configuration

environment = "prod"

# Harness Configuration
# Update these with your actual Harness org and project IDs
harness_org_id     = "your_org_id"
harness_project_id = "your_project_id"

# Template Versions
stage_template_version    = "v1.0.0"
pipeline_template_version = "v1.0.0"

# Promotion Tier - start with canary, then promote gradually
promotion_tier = "canary"

# Pipeline Tier Assignments
canary_pipelines = [
  "test-pipeline-prod",
  "canary-service-prod"
]

early_adopter_pipelines = [
  "service-a-prod",
  "service-b-prod",
  "api-gateway-prod"
]

stable_pipelines = [
  "critical-service-prod",
  "payment-pipeline-prod",
  "auth-service-prod",
  "core-api-prod"
]

# Tags
tags = {
  Environment = "prod"
  Team        = "platform"
  CostCenter  = "engineering"
  Criticality = "high"
}
