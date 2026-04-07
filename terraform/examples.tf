# Example Terraform configurations for testing stage template versions
# Uncomment the relevant sections to use

# ============================================================================
# Example 1: Standalone Test Pipeline for Quick Stage Template Testing
# ============================================================================
# Use this to quickly test a new stage template version without affecting
# the pipeline template or production pipelines

# module "stage_template_test_v1_1_0" {
#   source = "./modules/test-pipeline"
#
#   org_id     = var.harness_org_id
#   project_id = var.harness_project_id
#   identifier = "stage_test_v1_1_0"
#   name       = "Stage Template Test - v1.1.0"
#   description = "Testing stage template v1.1.0 independently"
#
#   stage_template_ref = "deploy_stage"
#   stage_version      = "v1.1.0"  # ← Test new version here
#   test_service       = "test-service"
#
#   tags = {
#     Purpose      = "Testing"
#     Tier         = "canary"
#     TemplateTest = "stage-v1.1.0"
#   }
# }

# ============================================================================
# Example 2: Pipeline Using Flexible Pipeline Template (v1.1.0)
# ============================================================================
# Pipeline template v1.1.0 allows runtime stage template version selection

# module "canary_pipeline_flexible" {
#   source = "./modules/pipeline"
#
#   org_id     = var.harness_org_id
#   project_id = var.harness_project_id
#   identifier = "service_a_pipeline"
#   name       = "Service A Pipeline"
#   description = "Service A CI/CD with flexible stage template version"
#
#   pipeline_template_ref = "ci_pipeline"
#   template_version      = "v1.1.0"  # Use flexible pipeline template
#
#   template_inputs = {
#     service_name           = "service-a"
#     image_repo             = "myregistry/service-a"
#     image_tag              = "latest"
#     stage_template_version = "v1.1.0"  # ← Override stage template version!
#   }
#
#   tags = {
#     Tier                 = "canary"
#     StageTemplateVersion = "v1.1.0"
#   }
# }

# ============================================================================
# Example 3: Testing Multiple Stage Template Versions in Parallel
# ============================================================================
# Create multiple test pipelines to compare stage template versions

# module "stage_test_v1_0_0" {
#   source = "./modules/test-pipeline"
#
#   org_id            = var.harness_org_id
#   project_id        = var.harness_project_id
#   identifier        = "stage_test_v1_0_0"
#   name              = "Stage Template Test - v1.0.0 (Baseline)"
#   stage_version     = "v1.0.0"
#   test_service      = "test-service"
#
#   tags = {
#     Purpose  = "Baseline"
#     Version  = "v1.0.0"
#   }
# }

# module "stage_test_v1_1_0" {
#   source = "./modules/test-pipeline"
#
#   org_id            = var.harness_org_id
#   project_id        = var.harness_project_id
#   identifier        = "stage_test_v1_1_0"
#   name              = "Stage Template Test - v1.1.0 (New)"
#   stage_version     = "v1.1.0"
#   test_service      = "test-service"
#
#   tags = {
#     Purpose  = "Testing"
#     Version  = "v1.1.0"
#   }
# }

# ============================================================================
# Example 4: Gradual Rollout Using Runtime Stage Template Version
# ============================================================================
# Deploy pipeline template v1.1.0 to different tiers with different stage
# template versions for gradual rollout

# # Canary tier - Test new stage template version
# module "canary_pipeline_new_stage" {
#   source = "./modules/pipeline"
#
#   org_id                = var.harness_org_id
#   project_id            = var.harness_project_id
#   identifier            = "test_pipeline_1"
#   name                  = "Test Pipeline 1"
#   pipeline_template_ref = "ci_pipeline"
#   template_version      = "v1.1.0"
#
#   template_inputs = {
#     stage_template_version = "v1.1.0"  # Canary uses new version
#   }
#
#   tags = {
#     Tier                 = "canary"
#     StageTemplateVersion = "v1.1.0"
#   }
# }

# # Early adopters tier - Still using stable stage template
# module "early_adopter_pipeline_stable_stage" {
#   source = "./modules/pipeline"
#
#   org_id                = var.harness_org_id
#   project_id            = var.harness_project_id
#   identifier            = "service_a_prod"
#   name                  = "Service A Production"
#   pipeline_template_ref = "ci_pipeline"
#   template_version      = "v1.1.0"
#
#   template_inputs = {
#     stage_template_version = "v1.0.0"  # Early adopters still on stable
#   }
#
#   tags = {
#     Tier                 = "early_adopters"
#     StageTemplateVersion = "v1.0.0"
#   }
# }

# ============================================================================
# Example 5: Complete Test Scenario
# ============================================================================
# Full example showing how to test and promote a new stage template version

# Step 1: Deploy new stage template v1.1.0 (in main.tf)

# Step 2: Create standalone test pipeline
# module "quick_stage_test" {
#   source = "./modules/test-pipeline"
#
#   org_id       = var.harness_org_id
#   project_id   = var.harness_project_id
#   identifier   = "quick_test_stage_v1_1_0"
#   name         = "Quick Test - Stage v1.1.0"
#   stage_version = "v1.1.0"
# }

# Step 3: After validation, deploy pipeline template v1.1.0 (in main.tf)

# Step 4: Create canary pipeline using new pipeline template with new stage version
# module "canary_full_test" {
#   source = "./modules/pipeline"
#
#   org_id                = var.harness_org_id
#   project_id            = var.harness_project_id
#   identifier            = "canary_test"
#   name                  = "Canary Test Pipeline"
#   pipeline_template_ref = "ci_pipeline"
#   template_version      = "v1.1.0"
#
#   template_inputs = {
#     stage_template_version = "v1.1.0"
#   }
#
#   tags = {
#     Tier = "canary"
#   }
# }

# Step 5: After canary validation, roll out to more pipelines by updating
# their template_inputs.stage_template_version to v1.1.0
