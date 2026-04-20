# Template Promotion System - Setup Guide

Complete guide to setting up and using the Harness Template Promotion system.

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [System Architecture](#system-architecture)
4. [Initial Setup](#initial-setup)
5. [Repository Structure](#repository-structure)
6. [Workflows](#workflows)
7. [Testing](#testing)
8. [Troubleshooting](#troubleshooting)

---

## Overview

The Template Promotion system automates the lifecycle of Harness templates through multiple tiers (development → production → stable) with validation, version control, and IaCM deployment.

### Key Components

1. **Plugin (Python)**: Extracts templates from executions, validates them, and promotes through tiers
2. **Git Repository**: Version controls all template files
3. **Terraform/IaCM**: Deploys templates to Harness and marks stable versions
4. **CI Pipelines**: Automates extraction, promotion, and PR creation

---

## Prerequisites

### Required Tools

- **Python 3.13+** (for local testing)
- **Harness Account** with API access
- **Git** for version control
- **Terraform 1.0+** (managed via Harness IaCM)
- **GitHub CLI (`gh`)** (for PR creation)

### Required Harness Setup

1. **PAT Token** with permissions:
   - `core_template_view`
   - `core_template_edit`
   - `core_pipeline_view`

2. **Docker Registry** connected to Harness:
   - For storing plugin image
   - Example: `promotion-plugin` connector

3. **IaCM Setup**:
   - IaCM workspace: `templatecontrollerwsgit`
   - Connected to this Git repository
   - Webhook configured for `templates/` directory changes

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CI/CD Pipeline                              │
│                                                                     │
│  1. Extract from Execution                                          │
│     └─> Plugin: Extracts template + dependencies (tree mode)       │
│         Output: templates/{type}/{id}/v1.yaml                      │
│                                                                     │
│  2. Promote Through Tiers                                          │
│     └─> Plugin: Promotes tier-1 → tier-2 → ... → tier-5           │
│         Output: templates/{type}/{id}/tier-N.yaml                  │
│                                                                     │
│  3. Mark Stable                                                    │
│     └─> Plugin: Creates stable.yaml from chosen tier              │
│         Output: templates/{type}/{id}/stable.yaml                 │
│                                                                     │
│  4. Create PR                                                      │
│     └─> Git: Commits templates/ and versions.yaml                 │
│                                                                     │
│  5. Review & Merge                                                 │
│     └─> Human: Reviews changes in PR                              │
│                                                                     │
│  6. Deploy via IaCM                                                │
│     └─> Terraform: Deploys all versions to Harness                │
│         └─> Marks stable.yaml as is_stable=true                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Initial Setup

### Step 1: Clone Repository

```bash
git clone https://github.com/your-org/template-promotion.git
cd template-promotion
```

### Step 2: Build Plugin Docker Image

```bash
cd template-promotion-plugin
docker build -t template-promotion-plugin:latest .
docker tag template-promotion-plugin:latest your-registry/template-promotion-plugin:latest
docker push your-registry/template-promotion-plugin:latest
```

Or use the provided CI pipeline:
```yaml
# Pipeline: template-promotion-core-plugin-ci
# Automatically builds and pushes on commit to main
```

### Step 3: Configure Harness Secrets

Create these secrets in Harness:

| Secret Name | Description | Example |
|-------------|-------------|---------|
| `harness_api_key` | PAT token for API access | `pat.abc.123...` |
| `github_token` | GitHub PAT for PR creation | `ghp_...` |

### Step 4: Create IaCM Workspaces

#### Control Workspace

```hcl
# terraform/control-workspace/
# Manages workspace creation for each template
```

**Purpose**: Creates/destroys IaCM workspaces for templates

#### Template Workspaces

```hcl
# terraform/template-workspace/
# Deployed to each workspace (e.g., stage_Stage_Template)
```

**Purpose**: Deploys all versions of a single template

### Step 5: Set Up IaCM Pipeline

Deploy the IaCM pipeline:

```yaml
# Pipeline: template-promotion-iacm
# Triggered by webhook on templates/ changes
# Applies Terraform for modified templates
```

**Webhook Configuration**:
- Repository: This repo
- Trigger on: Push to `main`
- Paths: `templates/**/*.yaml`, `versions.yaml`

### Step 6: Initialize versions.yaml

Create initial `versions.yaml`:

```yaml
labels:
  canary: {}
  stable: {}
templates:
  step: {}
  stepgroup: {}
  stage: {}
  pipeline: {}
```

Commit to repository:
```bash
git add versions.yaml
git commit -m "chore: Initialize versions.yaml"
git push origin main
```

---

## Repository Structure

```
template-promotion/
├── template-promotion-plugin/      # Python plugin source
│   ├── src/
│   │   ├── main.py                # Entry point
│   │   ├── config.py              # Configuration
│   │   ├── logic.py               # Business logic
│   │   ├── utils.py               # Utilities
│   │   └── harness_api/           # API client
│   ├── Dockerfile
│   └── requirements.txt
│
├── templates/                      # Template files (managed by plugin)
│   ├── step/
│   │   └── Step_Template/
│   │       ├── v1.yaml
│   │       ├── tier-1.yaml
│   │       └── stable.yaml
│   ├── stepgroup/
│   │   └── SG_Template/
│   │       ├── v1.yaml
│   │       └── tier-1.yaml
│   └── stage/
│       └── Stage_Template/
│           ├── v1.yaml
│           ├── tier-1.yaml
│           ├── tier-5.yaml
│           └── stable.yaml
│
├── terraform/                      # Terraform/IaCM configuration
│   ├── control-workspace/         # Workspace management
│   │   ├── main.tf
│   │   └── variables.tf
│   └── template-workspace/        # Template deployment
│       ├── main.tf                # ← Deploys templates
│       └── variables.tf
│
├── testing/                        # Local testing environment
│   ├── config/                    # Test configurations
│   ├── scripts/                   # Test scripts
│   ├── test_ideal_flow.py        # Main test
│   └── README.md
│
├── versions.yaml                   # Version tracking file
├── SETUP.md                        # This file
├── CLAUDE.md                       # Project context for AI
├── README.md                       # User documentation
└── TERRAFORM_INTEGRATION.md        # Terraform guide
```

---

## Workflows

### Workflow 1: Extract New Template from Execution

**Use Case**: You ran a pipeline with a new template and want to extract it.

#### Step 1: Run Extraction Pipeline

```yaml
# Pipeline: temp-promotion-plugin
# Input variables:
variables:
  template_id: "My_New_Template"
  execution_url: "https://app.harness.io/ng/.../executions/abc123/pipeline"
  project_id: "Twilio"
  mode: "tree"           # Extract tree (template + dependencies)
  to_tier: "1"          # Optional: also promote to tier-1
  source_version: "v1"
```

#### Step 2: Review PR

Plugin creates PR with:
- `templates/stage/My_New_Template/v1.yaml`
- `templates/stage/My_New_Template/tier-1.yaml` (if to_tier set)
- `versions.yaml` updated

#### Step 3: Merge PR

After review, merge to main.

#### Step 4: IaCM Deploys

Webhook triggers IaCM pipeline:
- Detects new template files
- Runs Terraform apply
- Deploys templates to Harness

**Result**: Template available in Harness at `v1` and `tier-1`.

---

### Workflow 2: Promote Template Through Tiers

**Use Case**: Template tested in tier-1, ready for tier-2.

#### Step 1: Run Promotion Pipeline

```yaml
# Pipeline: temp-promotion-plugin
variables:
  template_id: "My_Template"
  mode: "single"
  source_version: "tier-1"
  to_tier: "2"
```

#### Step 2: Review and Merge PR

Plugin creates:
- `templates/stage/My_Template/tier-2.yaml`
- `versions.yaml` updated

#### Step 3: IaCM Deploys

Terraform deploys `tier-2.yaml` to Harness.

**Result**: Template available at `tier-2`.

---

### Workflow 3: Mark Template as Stable

**Use Case**: Template has been validated through all tiers, ready for production stable.

#### Step 1: Choose Which Tier to Mark Stable

You control this! Options:

**Option A: Mark tier-5 as stable (normal flow)**
```yaml
variables:
  template_id: "My_Template"
  source_version: "tier-5"
  to_tier: "stable"
```

**Option B: Mark tier-1 as stable (fast-track)**
```yaml
variables:
  source_version: "tier-1"
  to_tier: "stable"
```

**Option C: Auto-detect highest tier**
```yaml
variables:
  # Omit source_version
  to_tier: "stable"
  # Plugin uses highest tier from versions.yaml
```

#### Step 2: Review PR

Plugin creates:
- `templates/stage/My_Template/stable.yaml`
- Child templates have **no version labels** (they use stable automatically)

#### Step 3: Merge PR

#### Step 4: IaCM Deploys and Marks Stable

Terraform:
```hcl
resource "harness_platform_template" "stable" {
  version = "stable"
  is_stable = true  # ← Marks as stable in Harness
  template_yaml = file("stable.yaml")
}
```

**Result**: Template marked as stable. References without version use this version.

---

### Workflow 4: Bulk Promote Entire Tree

**Use Case**: Promote template + all dependencies together.

#### Step 1: Run Tree Promotion

```yaml
variables:
  template_id: "Stage_Template"  # Root template
  mode: "tree"                   # Promote entire tree
  source_version: "tier-1"
  to_tier: "2"
```

#### Step 2: Review PR

Plugin creates tier-2 files for ALL templates:
- `Stage_Template/tier-2.yaml` → references `SG_Template@tier-2`
- `SG_Template/tier-2.yaml` → references `Step@tier-2`
- `Step/tier-2.yaml`

#### Step 3: Merge and Deploy

IaCM deploys all three templates.

**Result**: Entire tree at tier-2 with consistent versions.

---

## Testing

### Local Testing Setup

```bash
cd testing

# One-time setup
bash setup.sh
source venv/bin/activate

# Configure
nano config/test.env          # Add API key
nano config/extraction.env    # Add execution URL
```

### Run Tests

```bash
# Complete lifecycle test
python test_ideal_flow.py

# Tree validation
python test_tree_validation.py

# Invalid promotions (validation rules)
python test_invalid_promotions.py

# Edge cases
python test_edge_cases.py
```

### Expected Results

All tests should pass:
```
✅ test_ideal_flow.py          5/5 PASSED
✅ test_tree_validation.py     5/5 PASSED
✅ test_invalid_promotions.py  8/8 PASSED
✅ test_edge_cases.py          6/6 PASSED

Total: 24/24 PASSED
```

See [`testing/README.md`](testing/README.md) for details.

---

## Configuration Reference

### Plugin Environment Variables

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `PLUGIN_API_KEY` | Yes | Harness PAT token | `pat.abc.123` |
| `PLUGIN_ACCOUNT_ID` | Yes | Harness account ID | `Pt_YA3aYQT6g6ZW7MZOMJw` |
| `PLUGIN_TEMPLATE_ID` | Yes | Template identifier | `Stage_Template` |
| `PLUGIN_EXECUTION_URL` | For extraction | Full execution URL | `https://app.harness.io/...` |
| `PLUGIN_PROJECT_ID` | For extraction | Project identifier | `Twilio` |
| `PLUGIN_MODE` | No | `single` or `tree` | `tree` |
| `PLUGIN_TO_TIER` | For promotion | Target tier `1-5` or `stable` | `2` |
| `PLUGIN_SOURCE_VERSION` | No | Source version (auto-detect if empty) | `tier-1` |
| `PLUGIN_TIER_SKIP` | No | Allow tier skip | `true` / `false` |

### Promotion Rules

| From | To | Requires | Notes |
|------|------|----------|-------|
| `v1`, `v2` | `tier-1` | - | Semantic versions must go to tier-1 first |
| `tier-N` | `tier-N+1` | - | Sequential promotion (default) |
| `tier-N` | `tier-M` (M > N+1) | `TIER_SKIP=true` | Skip intermediate tiers |
| Any tier | `stable` | - | Any tier can be marked stable |
| `stable` | Any tier | - | Rollback allowed |

### Blocked Promotions

| Scenario | Error |
|----------|-------|
| Backwards (tier-2 → tier-1) | "Backwards promotion not allowed" |
| v1 → tier-2 | "Semantic version must promote to tier-1 first" |
| tier-1 → tier-5 without flag | "Cannot skip 3 tiers without TIER_SKIP flag" |
| tier-0, tier-6+ | "Invalid tier number" |

---

## Troubleshooting

### Issue 1: Plugin Fails with 401 Unauthorized

**Symptom**:
```
Error: 401 Unauthorized
```

**Solution**:
- Verify `PLUGIN_API_KEY` is correct
- Check token has `core_template_view`, `core_template_edit` permissions
- Token not expired

---

### Issue 2: Template Not Found in Harness

**Symptom**:
```
Template Stage_Template not found
```

**Solution**:
- Check template exists in specified org/project
- Verify `PLUGIN_TEMPLATE_ID` matches exactly (case-sensitive)
- For extraction: verify execution URL is correct

---

### Issue 3: IaCM Pipeline Doesn't Trigger

**Symptom**: PR merged but Terraform doesn't apply

**Solution**:
- Check webhook configuration in Git repo
- Verify webhook points to Harness IaCM pipeline
- Check IaCM pipeline trigger paths include `templates/**`
- Review IaCM pipeline execution logs

---

### Issue 4: Stable Not Marked in Harness

**Symptom**: `stable.yaml` deployed but template not marked stable

**Solution**:
- Check Terraform configuration has `is_stable = true`
- Verify `terraform/template-workspace/main.tf` line 37:
  ```hcl
  is_stable = trimsuffix(filename, ".yaml") == "stable"
  ```
- Run `terraform plan` to see what will be applied

---

### Issue 5: Templates in Wrong Directory

**Symptom**: StepGroup template saved to `templates/stage/` instead of `templates/stepgroup/`

**Solution**:
- This was a bug, now fixed
- Update to latest plugin version
- Check `logic.py` has `_determine_template_type()` function
- Re-run extraction to regenerate files

---

### Issue 6: Child Templates Have Version Labels in stable.yaml

**Symptom**:
```yaml
# In stable.yaml:
template:
  templateRef: account.SG_Template
  versionLabel: tier-1  # ← Should NOT be here
```

**Solution**:
- This should be removed automatically
- Check plugin has `remove_child_template_version_labels()` in stable promotion
- Re-run stable promotion to regenerate file

---

## Support and Documentation

### Documentation Files

- **[README.md](README.md)** - User guide and plugin documentation
- **[SETUP.md](SETUP.md)** - This file (setup guide)
- **[CLAUDE.md](CLAUDE.md)** - Project context for AI assistance
- **[TERRAFORM_INTEGRATION.md](TERRAFORM_INTEGRATION.md)** - Terraform workflow details
- **[TERRAFORM_CHANGES.md](TERRAFORM_CHANGES.md)** - Required Terraform updates
- **[STABLE_MARKING_CHANGES.md](STABLE_MARKING_CHANGES.md)** - Stable marking changes
- **[VALIDATION_FIXES.md](VALIDATION_FIXES.md)** - Validation rule fixes
- **[testing/README.md](testing/README.md)** - Testing guide
- **[testing/TEST_RESULTS.md](testing/TEST_RESULTS.md)** - Test results

### Getting Help

1. Check documentation files above
2. Review test examples in `testing/`
3. Check GitHub issues
4. Contact: Platform team

---

## Quick Reference

### Extract Template
```yaml
TEMPLATE_ID: "My_Template"
EXECUTION_URL: "https://app.harness.io/.../executions/abc/pipeline"
PROJECT_ID: "Twilio"
MODE: "tree"
TO_TIER: "1"
```

### Promote to Next Tier
```yaml
TEMPLATE_ID: "My_Template"
SOURCE_VERSION: "tier-1"
TO_TIER: "2"
MODE: "single"
```

### Mark as Stable
```yaml
TEMPLATE_ID: "My_Template"
SOURCE_VERSION: "tier-5"  # Or any tier
TO_TIER: "stable"
```

### Bulk Promotion
```yaml
TEMPLATE_ID: "Root_Template"
SOURCE_VERSION: "tier-1"
TO_TIER: "2"
MODE: "tree"
```

---

## Next Steps

1. ✅ Complete [Initial Setup](#initial-setup)
2. ✅ Run [Local Tests](#testing) to verify setup
3. ✅ Extract your first template ([Workflow 1](#workflow-1-extract-new-template-from-execution))
4. ✅ Promote through tiers ([Workflow 2](#workflow-2-promote-template-through-tiers))
5. ✅ Mark stable ([Workflow 3](#workflow-3-mark-template-as-stable))

For questions or issues, refer to [Troubleshooting](#troubleshooting) or check the documentation files.

Happy promoting! 🚀
