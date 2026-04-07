# Template Dependency Management

## Problem: Testing Stage Template Changes Independently

When a **pipeline template** references a **stage template** with a hardcoded version, you cannot test new stage template versions without updating the pipeline template.

**Current Situation:**
```yaml
# ci-pipeline.yaml (line 96)
- stage:
    template:
      templateRef: deploy_stage
      versionLabel: v1.0.0  # ← Hardcoded dependency!
```

**The Challenge:**
- You want to update stage template from v1.0.0 → v1.1.0
- You don't want to change the pipeline template (it's stable)
- You need to test the new stage template version
- Your pipeline template has a hardcoded reference to v1.0.0

## Solution Strategies

### Strategy 1: Runtime Input for Stage Template Version (Recommended)

Make the stage template version a **runtime input** in the pipeline template.

#### Implementation

Create a new pipeline template version (v1.1.0) with flexible stage template versioning:

**File: `templates/pipeline-templates/v1.1.0/ci-pipeline.yaml`**

```yaml
template:
  name: CI Pipeline Template
  identifier: ci_pipeline
  versionLabel: v1.1.0
  type: Pipeline
  spec:
    stages:
      # ... Build and Publish stages ...
      
      - stage:
          name: Deploy to Dev
          identifier: deploy_dev
          template:
            templateRef: deploy_stage
            versionLabel: <+pipeline.variables.stage_template_version>  # ← Runtime input!
            templateInputs:
              type: Deployment
              spec:
                service:
                  serviceRef: <+pipeline.variables.service_name>
                environment:
                  environmentRef: dev
              variables:
                - name: environment
                  type: String
                  value: dev
                - name: service_name
                  type: String
                  value: <+pipeline.variables.service_name>
    variables:
      - name: service_name
        type: String
        description: Name of the service
        required: true
        value: <+input>
      - name: image_repo
        type: String
        description: Docker image repository
        required: true
        value: <+input>
      - name: image_tag
        type: String
        description: Docker image tag
        required: true
        value: <+input>.default("latest")
      
      # NEW: Stage template version as variable
      - name: stage_template_version
        type: String
        description: Version of stage template to use
        required: true
        value: <+input>.default("v1.0.0")  # Default to stable version
    tags:
      templateVersion: v1.1.0
```

#### Benefits
- ✅ Test new stage template versions without changing pipeline template code
- ✅ Gradual rollout: different pipelines can use different stage template versions
- ✅ Easy rollback: just change the input value
- ✅ Backward compatible: defaults to v1.0.0

#### Usage

```hcl
# Deploy pipeline with specific stage template version
module "test_pipeline" {
  source = "./modules/pipeline"
  
  identifier             = "test_pipeline_1"
  name                   = "Test Pipeline 1"
  pipeline_template_ref  = "ci_pipeline"
  template_version       = "v1.1.0"  # Use new pipeline template
  
  template_inputs = {
    stage_template_version = "v1.1.0"  # Test new stage template!
  }
}
```

**Promotion Path:**
1. Create pipeline template v1.1.0 with runtime stage template version
2. Deploy pipeline template v1.1.0 to canary
3. Create stage template v1.1.0
4. Test by setting `stage_template_version = "v1.1.0"` in canary pipelines
5. Monitor and promote stage template independently

---

### Strategy 2: Separate Test Pipeline Templates

Create a dedicated **test pipeline template** for validating new stage template versions.

#### Implementation

**File: `templates/pipeline-templates/v1.0.0-test/ci-pipeline-test.yaml`**

```yaml
template:
  name: CI Pipeline Template (Test)
  identifier: ci_pipeline_test
  versionLabel: v1.0.0-test
  type: Pipeline
  spec:
    stages:
      # ... Same Build/Publish stages ...
      
      - stage:
          name: Deploy to Dev
          identifier: deploy_dev
          template:
            templateRef: deploy_stage
            versionLabel: v1.1.0  # ← Testing new version
            templateInputs:
              # ... same as before ...
```

**Terraform configuration:**

```hcl
# Create test pipeline template
module "pipeline_template_test" {
  source = "./modules/pipeline-template"
  
  identifier   = "ci_pipeline_test"
  name         = "CI Pipeline Template (Test)"
  version      = "v1.0.0-test"
  yaml_content = file("${path.module}/../templates/pipeline-templates/v1.0.0-test/ci-pipeline-test.yaml")
  
  tags = {
    Purpose = "Testing"
    StageTemplateVersion = "v1.1.0"
  }
}

# Create test pipelines using the test template
module "canary_test_pipeline" {
  source = "./modules/pipeline"
  
  identifier            = "test_pipeline_stage_v1_1_0"
  name                  = "Test Pipeline - Stage v1.1.0"
  pipeline_template_ref = "ci_pipeline_test"  # Use test template
  template_version      = "v1.0.0-test"
  
  tags = {
    Tier = "canary"
    Testing = "stage-template-v1.1.0"
  }
}
```

#### Benefits
- ✅ Stable pipeline template unchanged
- ✅ Clear separation between production and test
- ✅ Can test multiple stage template versions in parallel

#### Drawbacks
- ❌ Duplication of pipeline template code
- ❌ Must maintain multiple pipeline templates
- ❌ Extra complexity in version management

---

### Strategy 3: Standalone Stage Template Testing

Test the stage template **directly** without going through the pipeline template.

#### Implementation

Create **standalone test pipelines** that use only the stage template:

**File: `templates/test-pipelines/stage-template-test.yaml`**

```yaml
pipeline:
  identifier: stage_template_test_v1_1_0
  name: Stage Template Test - v1.1.0
  orgIdentifier: <org>
  projectIdentifier: <project>
  stages:
    - stage:
        name: Test Deploy Stage v1.1.0
        identifier: test_deploy
        template:
          templateRef: deploy_stage
          versionLabel: v1.1.0  # ← Testing this version
          templateInputs:
            type: Deployment
            spec:
              service:
                serviceRef: test-service
              environment:
                environmentRef: dev
            variables:
              - name: environment
                value: dev
              - name: service_name
                value: test-service
  tags:
    Purpose: Testing
    TemplateVersion: v1.1.0
```

**Terraform module:**

```hcl
# Create standalone test pipeline
resource "harness_platform_pipeline" "stage_template_test" {
  identifier = "stage_template_test_v1_1_0"
  name       = "Stage Template Test - v1.1.0"
  org_id     = var.harness_org_id
  project_id = var.harness_project_id
  
  yaml = file("${path.module}/../templates/test-pipelines/stage-template-test.yaml")
  
  tags = {
    Purpose          = "Testing"
    TemplateVersion  = "v1.1.0"
    Tier             = "canary"
  }
}
```

#### Benefits
- ✅ **Fastest way** to test stage template changes
- ✅ **No dependency** on pipeline template
- ✅ **Focused testing** of stage template only
- ✅ **Quick iteration** cycle

#### Usage Pattern

1. Create new stage template version (v1.1.0)
2. Create standalone test pipeline referencing v1.1.0
3. Run tests extensively
4. Once validated, update pipeline template to use v1.1.0
5. Delete test pipeline

---

### Strategy 4: Semantic Versioning with Auto-Upgrade Rules

Use **semantic versioning** to allow automatic patch/minor upgrades.

#### Implementation

Instead of hardcoding exact versions, use version ranges:

```yaml
# In pipeline template
- stage:
    template:
      templateRef: deploy_stage
      versionLabel: v1.x.x  # ← Allow any v1 minor/patch version
```

**Version upgrade rules:**
- **PATCH** (v1.0.0 → v1.0.1): Auto-upgrade ✅
- **MINOR** (v1.0.0 → v1.1.0): Auto-upgrade ✅
- **MAJOR** (v1.0.0 → v2.0.0): Manual upgrade ❌

#### Terraform Configuration

```hcl
locals {
  # Determine stage template version based on promotion tier
  stage_template_version = {
    canary         = var.stage_template_version  # Use specified version
    early_adopters = var.stage_template_version
    stable         = "v1.0.0"  # Keep stable on v1.0.0
  }[var.promotion_tier]
}
```

#### Benefits
- ✅ Automatic propagation of bug fixes (patches)
- ✅ Gradual adoption of new features (minors)
- ✅ Protection against breaking changes (majors)

#### Drawbacks
- ❌ Less control over exact versions
- ❌ Potential for unexpected behavior
- ❌ May not be supported by Harness (check documentation)

---

## Recommended Approach

For your use case, I recommend a **combination of Strategy 1 and Strategy 3**:

### Phase 1: Quick Testing (Strategy 3)
Use standalone test pipelines to rapidly test new stage template versions:

```bash
# 1. Create stage template v1.1.0
mkdir -p templates/stage-templates/v1.1.0
# ... create template files ...

# 2. Create standalone test pipeline
# (See Strategy 3 example above)

# 3. Deploy and test
cd terraform
terraform apply -var="stage_template_version=v1.1.0"

# 4. Run test pipeline multiple times
# Monitor for issues
```

### Phase 2: Production Rollout (Strategy 1)
After validating in Phase 1, use runtime inputs for production rollout:

```bash
# 1. Create pipeline template v1.1.0 with runtime stage template version
mkdir -p templates/pipeline-templates/v1.1.0
# ... update template with runtime input ...

# 2. Promote pipeline template to canary (using v1.0.0 stage template)
./promotion/scripts/promote.sh \
  --tier canary \
  --version v1.1.0 \
  --env prod

# 3. Override stage template version for canary pipelines
# Update terraform/main.tf:
module "canary_pipeline" {
  template_inputs = {
    stage_template_version = "v1.1.0"  # Override here
  }
}

# 4. Apply and monitor
terraform apply

# 5. Gradually expand to more pipelines
```

---

## Implementation Guide

Let me create the necessary files for you:

### Step 1: Create Flexible Pipeline Template

I'll create a new pipeline template version (v1.1.0) that supports runtime stage template versioning.

### Step 2: Create Standalone Test Infrastructure

I'll create a module for standalone stage template testing.

### Step 3: Update Terraform Configuration

I'll update the main Terraform config to support both approaches.

Would you like me to implement these changes now?

---

## Summary

| Strategy | Best For | Complexity | Flexibility |
|----------|----------|------------|-------------|
| **Runtime Inputs** | Production gradual rollout | Medium | High ✅ |
| **Test Templates** | Parallel testing | High | Medium |
| **Standalone Pipelines** | Quick iteration | Low ✅ | High ✅ |
| **Semantic Versioning** | Automatic updates | Low | Low |

**Recommendation:** Start with **Standalone Pipelines** for quick testing, then use **Runtime Inputs** for production rollout.
