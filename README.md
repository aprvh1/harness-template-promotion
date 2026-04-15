# Template Promotion System

Progressive rollout system for Harness templates across 100 organizations using tier-based OPA policy enforcement.

## Quick Start

### 1. Extract Template from Successful Execution

```bash
python3 scripts/validate_and_extract.py \
  --execution-url "https://app.harness.io/.../executions/exec-123" \
  --template-id my_template \
  --project-id test \
  --changelog "Added new features" \
  --mode tree
```

### 2. Deploy to Harness with Tier-Based Versions

Upload template to Harness with 5 versions:
- `tier-1` (5 canary projects)
- `tier-2` (20 projects total)
- `tier-3` (50 projects total)
- `tier-4` (80 projects total)
- `tier-5` (100 projects - stable)

### 3. OPA Policy Enforces Access

Projects tagged with `tier: "tier1"` can only use templates with `versionLabel: tier-1`.

## Harness Pipeline Integration

For CI/CD pipeline integration, use the wrapper script with environment variables:

```yaml
# In your Harness pipeline
- step:
    type: Run
    spec:
      envVariables:
        HARNESS_API_KEY: <+secrets.getValue("harness_api_key")>
        HARNESS_ACCOUNT_ID: <+account.identifier>
        TEMPLATE_ID: "Stage_Template"
        EXECUTION_URL: <+pipeline.variables.execution_url>
        PROJECT_ID: "Twilio"
        MODE: "tree"
        TO_TIER: "1"
      command: |
        bash scripts/harness_pipeline_runner.sh
```

**📖 [docs/HARNESS_PIPELINE_USAGE.md](docs/HARNESS_PIPELINE_USAGE.md)** - Complete pipeline integration guide with examples

## Documentation

**📖 [FINAL_MODEL.md](FINAL_MODEL.md)** - Complete guide for tier-based template promotion

**Legacy docs:**
- [README_STEP1.md](README_STEP1.md) - Python extraction implementation
- [VALIDATION_SUMMARY.md](VALIDATION_SUMMARY.md) - Template validation details
- [TEMPLATE_PROMOTION_README.md](TEMPLATE_PROMOTION_README.md) - Original design

## Key Files

**Policy:**
- `policies/template-tier-control.rego` - OPA policy for tier enforcement

**Python Scripts:**
- `scripts/validate_and_extract.py` - Extract templates from successful executions
- `scripts/harness_pipeline_runner.sh` - Wrapper script for Harness pipelines (env vars interface)
- `scripts/common.py` - Shared utilities


## How It Works

### Project-Based Tier Control

```yaml
# Projects tagged by tier
Project: canary_project
  tags:
    tier: "tier1"    # Tier 1 project

Project: prod_project  
  tags:
    tier: "tier5"    # Tier 5 project
```

### Template Versions

```
Template: deploy_stage
├── tier-1 (tier 1 projects only)
├── tier-2 (tier 1-2 projects)
├── tier-3 (tier 1-3 projects)
├── tier-4 (tier 1-4 projects)
└── tier-5 (all projects - stable)
```

### Pipeline References

```yaml
pipeline:
  projectIdentifier: canary_project  # Has tier: "tier1"
  stages:
    - stage:
        template:
          templateRef: deploy_stage
          versionLabel: tier-1    # Must match project tier
```

### Policy Enforcement

**Rule:** `project_tier == template_tier`

- Tier 1 project can use `tier-1` only
- Tier 2 project can use `tier-2` only
- Tier 5 project can use `tier-5` only

## Setup

### Prerequisites

```bash
# Install dependencies
pip install -r requirements.txt

# Set Harness credentials
export HARNESS_API_KEY="your-api-key"
export HARNESS_ACCOUNT_ID="your-account-id"
```

### Deploy OPA Policy

1. Go to Harness → **Account Settings** → **Policies** → **Governance**
2. Create new policy with contents of `policies/template-tier-control.rego`
3. Create policy set:
   - Entity Type: `Pipeline`
   - Event: `On Save`
   - Action: `Error and Exit`

### Tag Projects

Tag all 100 projects with their tier:

```yaml
# Via Harness UI or API
Project: canary_1
  tags:
    tier: "tier1"

Project: prod_1
  tags:
    tier: "tier5"
```

## Progressive Rollout Example

**Week 1:** Upload template with version `tier-1`
- 5 canary projects can use it

**Week 2:** Create version `tier-2`  
- 20 projects (tier 1-2) can use it
- Existing pipelines with `tier-1` still work!

**Week 3-5:** Create `tier-3`, `tier-4`, `tier-5`
- Progressive rollout to all 100 projects
- No pipeline updates needed

## Benefits

✅ **No Pipeline Updates** - Existing pipelines keep working  
✅ **Progressive Rollout** - Controlled tier-by-tier deployment  
✅ **Project-Level Control** - Tag projects once, not 1000s of pipelines  
✅ **Clear Audit Trail** - Each tier version preserved in Harness  
✅ **Automatic Enforcement** - OPA policy blocks unauthorized access

## Architecture

```
100 Projects (tagged by tier)
    ↓
Pipelines (reference tier versions)
    ↓
OPA Policy (enforces project_tier == template_tier)
    ↓
Templates (5 versions: tier-1 through tier-5)
```

## Support

See [FINAL_MODEL.md](FINAL_MODEL.md) for complete documentation including:
- Full promotion workflow
- Troubleshooting guide
- Testing examples
- FAQ
