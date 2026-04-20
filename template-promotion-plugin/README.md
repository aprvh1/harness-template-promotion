# Harness Template Promotion Plugin

A Harness CI Plugin for extracting and promoting Harness templates through a tiered promotion system with automatic validation.

## Table of Contents
- [Overview](#overview)
- [Features](#features)
- [Quick Start](#quick-start)
- [Plugin Modes](#plugin-modes)
- [Configuration](#configuration)
- [Promotion System](#promotion-system)
- [Validation Logic](#validation-logic)
- [Example Pipelines](#example-pipelines)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)

---

## Overview

This plugin automates template lifecycle management in Harness:

1. **Extract** templates from successful pipeline executions
2. **Validate** templates with 4-level validation against execution YAML
3. **Promote** templates through a 5-tier system (tier-1 → tier-5 → stable)
4. **Deploy** promoted templates to Harness using IaCM/Terraform

### When to Use This Plugin

- ✅ Extract templates from successful test executions
- ✅ Promote templates through environments (dev → staging → prod)
- ✅ Automatically discover and extract template dependencies
- ✅ Validate templates match their execution YAML
- ✅ Sanitize secrets and connectors to runtime inputs
- ✅ Track template versions across tiers

---

## Features

### Extraction Features
- ✅ **Single Mode**: Extract one template
- ✅ **Tree Mode**: Extract template + all dependencies recursively
- ✅ **4-Level Validation**: Pipeline ref, structure, content hash, scripts
- ✅ **Template Type Detection**: Automatically determines step, stepgroup, stage, or pipeline
- ✅ **Sanitization**: Converts secrets/connectors to `<+input>` placeholders
- ✅ **Scope Removal**: Removes org/project scopes for reusability

### Promotion Features
- ✅ **5-Tier System**: tier-1 → tier-2 → tier-3 → tier-4 → tier-5 → stable
- ✅ **Tier Skip**: Jump multiple tiers with flag
- ✅ **Bulk Promotion**: Promote entire dependency tree together
- ✅ **Child Reference Updates**: Parent templates auto-update child version labels
- ✅ **Version Tracking**: Track promotions in `versions.yaml`
- ✅ **Rollback Support**: Promote from stable back to any tier

---

## Quick Start

### 1. Build the Plugin

Use the provided CI pipeline to build and push the Docker image:

```yaml
# Pipeline: template-promotion-core-plugin-ci
- step:
    type: BuildAndPushDockerRegistry
    name: BuildAndPushDockerRegistry
    spec:
      repo: template-promotion-plugin
      tags:
        - <+pipeline.sequenceId>
        - latest
      dockerfile: template-promotion-plugin/Dockerfile
      context: template-promotion-plugin
      registryRef: promotion-plugin
```

### 2. Use in Pipeline

```yaml
- step:
    type: Plugin
    name: Promotion Plugin
    spec:
      registryRef: promotion-plugin
      image: template-promotion-plugin:latest
      settings:
        API_KEY: <+secrets.getValue("harness_api_key")>
        ACCOUNT_ID: <+account.identifier>
        TEMPLATE_ID: <+pipeline.variables.template_id>
        MODE: tree
        TO_TIER: 1
```

---

## Plugin Modes

The plugin operates in different modes based on inputs:

### Mode 1: Extraction Only (Tree)

**When**: `MODE=tree` + `EXECUTION_URL` set + `TO_TIER` empty

**What it does**:
- Extracts root template from execution URL
- Discovers all child template dependencies recursively
- Validates each template with 4-level validation
- Saves templates to `templates/{type}/{id}/{version}.yaml`

**Example**:
```yaml
settings:
  MODE: tree
  TEMPLATE_ID: Stage_Template
  EXECUTION_URL: https://app.harness.io/ng/.../executions/abc123/pipeline
  PROJECT_ID: Twilio
  SOURCE_VERSION: v1
```

**Output Files**:
```
templates/
├── stage/Stage_Template/v1.yaml       # Root template
├── stepgroup/SG_Template/v1.yaml      # Dependency (depth 1)
└── step/Step/v1.yaml                  # Dependency (depth 2)
```

---

### Mode 2: Extraction + Promotion (Combined Mode)

**When**: `MODE=tree` + `EXECUTION_URL` set + `TO_TIER` set

**What it does**:
- Extracts entire template tree (as above)
- Immediately promotes ALL templates to target tier
- Updates child template references in parent templates
- Creates tier files for each template

**Example**:
```yaml
settings:
  MODE: tree
  TEMPLATE_ID: Stage_Template
  EXECUTION_URL: https://app.harness.io/ng/.../executions/abc123/pipeline
  PROJECT_ID: Twilio
  SOURCE_VERSION: v1
  TO_TIER: 1
```

**Output Files**:
```
templates/
├── stage/Stage_Template/v1.yaml       # Extracted
├── stage/Stage_Template/tier-1.yaml   # Promoted
├── stepgroup/SG_Template/v1.yaml
├── stepgroup/SG_Template/tier-1.yaml
├── step/Step/v1.yaml
└── step/Step/tier-1.yaml
```

**Key Feature**: Stage_Template tier-1 references `SG_Template@tier-1` (not v1)

---

### Mode 3: Promotion Only (Single)

**When**: `MODE=single` + `EXECUTION_URL` empty + `TO_TIER` set

**What it does**:
- Promotes one template from source to target tier
- Reads source file from `templates/{type}/{id}/{source}.yaml`
- Creates target file at `templates/{type}/{id}/{target}.yaml`
- Updates `versions.yaml` tracking

**Example**:
```yaml
settings:
  MODE: single
  TEMPLATE_ID: Stage_Template
  SOURCE_VERSION: tier-1
  TO_TIER: 2
  TIER_SKIP: false
```

**Promotion Flow**:
```
templates/stage/Stage_Template/tier-1.yaml  
  → templates/stage/Stage_Template/tier-2.yaml
```

---

### Mode 4: Bulk Promotion (Tree)

**When**: `MODE=tree` + `EXECUTION_URL` empty + `TO_TIER` set

**What it does**:
- Promotes entire template tree from one tier to another
- All templates promoted together to maintain version consistency
- Updates all child references in parent templates

**Example**:
```yaml
settings:
  MODE: tree
  TEMPLATE_ID: Stage_Template
  SOURCE_VERSION: tier-1
  TO_TIER: 2
```

**Promotion Flow**:
```
Stage_Template:  tier-1 → tier-2
SG_Template:     tier-1 → tier-2
Step:            tier-1 → tier-2
```

All templates move together; Stage_Template tier-2 references `SG_Template@tier-2`

---

## Configuration

### Required Settings (All Modes)

| Setting | Env Var | Description | Example |
|---------|---------|-------------|---------|
| `API_KEY` | `PLUGIN_API_KEY` | Harness PAT token | `pat.abc.123` |
| `ACCOUNT_ID` | `PLUGIN_ACCOUNT_ID` | Account identifier | `Pt_YA3aYQT6g6ZW7MZOMJw` |
| `TEMPLATE_ID` | `PLUGIN_TEMPLATE_ID` | Template to extract/promote | `Stage_Template` |

### Extraction Settings

| Setting | Env Var | Required | Description | Default |
|---------|---------|----------|-------------|---------|
| `EXECUTION_URL` | `PLUGIN_EXECUTION_URL` | Yes (extraction) | Full execution URL | - |
| `PROJECT_ID` | `PLUGIN_PROJECT_ID` | Yes (extraction) | Project identifier | - |
| `ORG_ID` | `PLUGIN_ORG_ID` | No | Organization identifier | `default` |
| `SOURCE_VERSION` | `PLUGIN_SOURCE_VERSION` | No | Semantic version label | `v1` |
| `CHANGELOG` | `PLUGIN_CHANGELOG` | No | Description of changes | - |

### Promotion Settings

| Setting | Env Var | Required | Description | Valid Values |
|---------|---------|----------|-------------|--------------|
| `TO_TIER` | `PLUGIN_TO_TIER` | Yes (promotion) | Target tier | `1`, `2`, `3`, `4`, `5`, `stable` |
| `TIER_SKIP` | `PLUGIN_TIER_SKIP` | No | Allow skipping tiers | `true`, `false` (default) |
| `SOURCE_VERSION` | `PLUGIN_SOURCE_VERSION` | No | Auto-detected if empty | `tier-1`, `tier-2`, etc. |

### Mode Setting

| Setting | Env Var | Description | Valid Values | Default |
|---------|---------|-------------|--------------|---------|
| `MODE` | `PLUGIN_MODE` | Extraction mode | `single`, `tree` | `single` |

- `single`: Extract/promote one template only
- `tree`: Extract/promote template + all dependencies

### Optional Settings

| Setting | Env Var | Description | Default |
|---------|---------|-------------|---------|
| `VERBOSE` | `PLUGIN_VERBOSE` | Enable detailed logging | `false` |
| `OUTPUT_FORMAT` | `PLUGIN_OUTPUT_FORMAT` | Output format | `json` |
| `ENDPOINT` | `PLUGIN_ENDPOINT` | Harness API endpoint | `https://app.harness.io/gateway` |
| `ENABLE_GIT` | `PLUGIN_ENABLE_GIT` | Enable git operations | `false` |

---

## Promotion System

### Tier Definitions

| Tier | Label | Purpose | Typical Use |
|------|-------|---------|-------------|
| - | `v1`, `v2`, etc. | Semantic versions | Initial extraction from execution |
| 1 | `tier-1` | Development/Beta | First promotion, initial testing |
| 2 | `tier-2` | Canary | Limited production exposure |
| 3 | `tier-3` | Staging | Pre-production validation |
| 4 | `tier-4` | Production | Full production rollout |
| 5 | `tier-5` | Production+ | Confirmed stable production |
| - | `stable` | Stable | Marked as stable release |

### Promotion Rules

#### ✅ Allowed Promotions

| From | To | Requires | Notes |
|------|------|----------|-------|
| `v1`, `v2`, etc. | `tier-1` | - | Semantic versions must start at tier-1 |
| `tier-N` | `tier-N+1` | - | Sequential promotion (default) |
| `tier-N` | `tier-M` (M > N+1) | `TIER_SKIP=true` | Skip intermediate tiers with flag |
| Any tier | `stable` | - | Any tier can be marked stable |
| `stable` | Any tier | - | Rollback from stable allowed |

#### ✅ All Validation Rules Enforced (Fixed 2026-04-20)

All promotion rules are now strictly validated:

| Rule | Enforcement | Error Message Example |
|------|-------------|----------------------|
| Backwards promotion | ❌ Blocked | "Backwards promotion not allowed: tier-2 → tier-1" |
| Semantic version to tier-1 only | ❌ Blocked if not tier-1 | "Semantic version v1 must promote to tier-1 first" |
| Tier skip requires flag | ❌ Blocked without flag | "Cannot skip 3 tier(s) without TIER_SKIP flag" |
| Same-tier promotion | ⚠️ Allowed (idempotent) | Warning: "This is a no-op operation" |
| Rollback from stable | ✅ Explicitly allowed | "Rollback from stable" |

#### ❌ Blocked Promotions

| From | To | Reason |
|------|------|--------|
| `v1` | `tier-0` | Invalid tier number |
| `tier-1` | `tier-6` | Invalid tier number (max is 5) |
| `tier-1` | `tier-3` | Skip not allowed without `TIER_SKIP=true` |
| `v99` | `tier-1` | Source version doesn't exist |

### Promotion Examples

#### Example 1: Standard Sequential Flow
```bash
# Initial extraction
MODE=tree, EXECUTION_URL=..., TO_TIER=1
  → Creates v1.yaml and tier-1.yaml

# Promote through tiers
TO_TIER=2  → tier-1.yaml → tier-2.yaml
TO_TIER=3  → tier-2.yaml → tier-3.yaml
TO_TIER=4  → tier-3.yaml → tier-4.yaml
TO_TIER=5  → tier-4.yaml → tier-5.yaml
TO_TIER=stable → tier-5.yaml → stable.yaml
```

#### Example 2: Fast-Track with Tier Skip
```bash
# Skip to production
MODE=single, SOURCE_VERSION=tier-1, TO_TIER=4, TIER_SKIP=true
  → tier-1.yaml → tier-4.yaml (skips tier-2, tier-3)

# Mark as stable
TO_TIER=stable
  → tier-4.yaml → stable.yaml
```

#### Example 3: Hotfix Rollback
```bash
# Roll back from stable to tier-3 for hotfix
MODE=single, SOURCE_VERSION=stable, TO_TIER=3
  → stable.yaml → tier-3.yaml
```

---

## Stable Promotion

### How Stable Works

When promoting to `stable`, the plugin:

1. ✅ **Creates local `stable.yaml` file**
   - Copies content from source tier (e.g., tier-5)
   - Sets `versionLabel: stable`
   - **Removes `versionLabel` from all child template references**
   - Child templates will use their stable versions automatically

2. ❌ **Does NOT make Harness API calls**
   - Plugin does not call `update_stable_template` API
   - Stable marking is controlled via **Terraform/IaCM**
   - Set `is_stable = true` in `harness_platform_template` resource

3. ✅ **Updates `versions.yaml` tracking**
   - Records which tier is marked stable locally
   - Used for version tracking and auto-detection

### Terraform Integration

**Marking stable is controlled via Terraform**:

```hcl
resource "harness_platform_template" "stage_template_stable" {
  identifier = "Stage_Template"
  org_id     = "default"
  project_id = "Twilio"
  
  # Read from stable.yaml created by plugin
  yaml = file("${path.module}/stable.yaml")
  
  # Mark as stable in Harness (controlled by you)
  is_stable = true
  
  version = "stable"
}
```

### Flexible Tier Selection

**Any tier can be marked stable** - you control which one:

```yaml
# Option 1: Mark tier-1 as stable (fast-track)
SOURCE_VERSION: tier-1
TO_TIER: stable

# Option 2: Mark tier-5 as stable (normal)
SOURCE_VERSION: tier-5
TO_TIER: stable

# Option 3: Auto-detect highest tier
TO_TIER: stable
# Omit SOURCE_VERSION - uses highest tier from versions.yaml
```

### Child Template Behavior

**Key Feature**: When a template is marked stable, child template references have their `versionLabel` removed:

```yaml
# Before stable promotion (tier-5.yaml)
template:
  versionLabel: tier-5
  spec:
    steps:
      - stepGroup:
          template:
            templateRef: account.SG_Template
            versionLabel: tier-1  # ← Pinned version

# After stable promotion (stable.yaml)
template:
  versionLabel: stable
  spec:
    steps:
      - stepGroup:
          template:
            templateRef: account.SG_Template
            # NO versionLabel ← Uses stable automatically
```

**Result**: Parent stable template always references child stable templates, keeping the entire hierarchy in sync.

See [TERRAFORM_INTEGRATION.md](../TERRAFORM_INTEGRATION.md) for complete Terraform/IaCM workflow documentation.

---

## Validation Logic

The plugin performs **4-level validation** for each extracted template:

### Level 1: Pipeline Reference Validation
- **Purpose**: Verify template is used in the pipeline
- **Checks**: 
  - Template reference found in pipeline YAML
  - Version label matches expected version
- **Expected Result**: Root template found, child templates may not be (they're expanded)

### Level 2: Structure Validation
- **Purpose**: Verify template structure matches execution YAML
- **Checks**: 
  - Match percentage of YAML keys between template and execution
  - Threshold: 30% match required
- **Notes**: Child templates validated against expanded YAML in execution

### Level 3: Content Hash Validation
- **Purpose**: Verify template content matches execution (item-by-item)
- **Checks**:
  - Hash comparison of steps, stages, etc. (excluding template refs)
  - Items compared: steps, stages, etc.
- **Notes**: Partial matches allowed (e.g., 2/3 items matched = 66%)

### Level 4: Script Validation
- **Purpose**: Verify script content matches (fuzzy match)
- **Checks**:
  - Extract all inline scripts from template
  - Match scripts in execution YAML (fuzzy string matching)
  - Threshold: 80% similarity required
- **Result**: Reports average match percentage across all scripts

### Validation Outcomes

All 4 levels run independently and results are logged:

```
✓ Level 1: Template referenced 1 time(s), version matches
⚠ Level 2: Structure match 25% (below 30% threshold)
✓ Level 3: Content hash 66% (2/3 items matched)
✓ Level 4: Scripts validated, avg match 100%
```

**Note**: Validation warnings don't block extraction. They provide visibility into how well the template matches the execution.

---

## Example Pipelines

### Pipeline 1: Build and Push Plugin

Build the Docker image and push to registry:

```yaml
pipeline:
  name: template-promotion-core-plugin-ci
  identifier: templatepromotioncorepluginci
  projectIdentifier: Twilio
  orgIdentifier: default
  properties:
    ci:
      codebase:
        connectorRef: account.Github_IDP
        repoName: template-promotion
        build: <+input>
  stages:
    - stage:
        name: Promotion
        identifier: Promotion
        type: CI
        spec:
          cloneCodebase: true
          caching:
            enabled: true
          buildIntelligence:
            enabled: true
          platform:
            os: Linux
            arch: Amd64
          runtime:
            type: Cloud
            spec: {}
          execution:
            steps:
              - step:
                  type: BuildAndPushDockerRegistry
                  name: BuildAndPushDockerRegistry
                  identifier: BuildAndPushDockerRegistry
                  spec:
                    repo: template-promotion-plugin
                    tags:
                      - <+pipeline.sequenceId>
                      - latest
                    caching: true
                    dockerfile: template-promotion-plugin/Dockerfile
                    context: template-promotion-plugin
                    registryRef: promotion-plugin
```

---

### Pipeline 2: Use Plugin (Extract + Promote + Create PR)

Extract templates, promote to tier, and create a PR:

```yaml
pipeline:
  name: temp-promotion-plugin
  identifier: temppromotionplugin
  projectIdentifier: Twilio
  orgIdentifier: default
  properties:
    ci:
      codebase:
        connectorRef: account.Github_IDP
        repoName: template-promotion
        build: <+input>
  stages:
    - stage:
        name: Promotion
        identifier: Promotion
        type: CI
        spec:
          cloneCodebase: true
          platform:
            os: Linux
            arch: Amd64
          runtime:
            type: Cloud
            spec: {}
          execution:
            steps:
              # Step 1: Run promotion plugin
              - step:
                  type: Plugin
                  name: Promotion Plugin
                  identifier: Promotion_Plugin
                  spec:
                    registryRef: promotion-plugin
                    image: template-promotion-plugin:latest
                    settings:
                      API_KEY: <+secrets.getValue("harness_api_key")>
                      ACCOUNT_ID: <+account.identifier>
                      TEMPLATE_ID: <+pipeline.variables.template_id>
                      EXECUTION_URL: <+pipeline.variables.execution_url>
                      PROJECT_ID: <+pipeline.variables.project_id>
                      ENABLE_GIT: "false"
                      TO_TIER: <+pipeline.variables.to_tier>
                      TIER_SKIP: "false"
                      SOURCE_VERSION: <+pipeline.variables.source_version>
                      MODE: <+pipeline.variables.mode>
                      VERBOSE: "true"
              
              # Step 2: Create PR with changes
              - step:
                  type: Run
                  name: Create PR
                  identifier: Create_PR
                  spec:
                    shell: Bash
                    command: |-
                      #!/bin/bash
                      set -e
                      
                      # Setup git authentication
                      cat <<EOF > ~/.netrc
                      machine ${DRONE_NETRC_MACHINE:-github.com}
                      login ${DRONE_NETRC_USERNAME}
                      password ${DRONE_NETRC_PASSWORD}
                      EOF
                      
                      export GH_TOKEN="${DRONE_NETRC_PASSWORD}"
                      git config user.name "${GITHUB_ACTOR:-github-actions}"
                      git config user.email "${GITHUB_ACTOR}@users.noreply.github.com"
                      
                      # Branch config
                      BRANCH_NAME="template-update-$(date +%Y%m%d-%H%M%S)"
                      BASE_BRANCH="${PR_BASE_BRANCH:-main}"
                      TEMPLATE_ID="${TEMPLATE_ID:-template}"
                      
                      # Check for changes
                      git add --force templates/ versions.yaml 2>/dev/null || true
                      STAGED_FILES=$(git diff --cached --name-only)
                      
                      if [ -z "$STAGED_FILES" ]; then
                        echo "No changes detected. Skipping PR creation."
                        exit 0
                      fi
                      
                      echo "Files staged: $STAGED_FILES"
                      
                      # Create branch and commit
                      git checkout -b "$BRANCH_NAME"
                      git commit -m "feat: Update $TEMPLATE_ID template"
                      git push origin "$BRANCH_NAME"
                      
                      # Create PR
                      gh pr create \
                        --title "feat: Update $TEMPLATE_ID template" \
                        --body "Automated template update for $TEMPLATE_ID" \
                        --base "$BASE_BRANCH" \
                        --head "$BRANCH_NAME"
  
  variables:
    - name: template_id
      type: String
      required: true
      value: <+input>
    - name: execution_url
      type: String
      required: false
      value: <+input>
    - name: project_id
      type: String
      required: true
      value: <+input>
    - name: mode
      type: String
      required: true
      value: <+input>.default(single).selectOneFrom(tree,single)
    - name: to_tier
      type: String
      required: false
      value: <+input>.selectOneFrom(1,2,3,4,5,stable)
    - name: source_version
      type: String
      required: false
      value: <+input>
```

**Pipeline Inputs**:
- `template_id`: Template to extract/promote (e.g., `Stage_Template`)
- `execution_url`: Execution URL (for extraction mode)
- `project_id`: Project identifier (e.g., `Twilio`)
- `mode`: `single` or `tree`
- `to_tier`: Target tier (`1`, `2`, `3`, `4`, `5`, or leave empty for extraction-only)
- `source_version`: Source version (auto-detected if empty)

---

### Pipeline 3: Deploy Templates with IaCM

Deploy promoted templates to Harness using IaCM/Terraform:

```yaml
pipeline:
  name: template-promotion-iacm
  identifier: templatepromotioniacm
  projectIdentifier: Twilio
  orgIdentifier: default
  stages:
    # Stage 1: Deploy template controller (Terraform workspace)
    - stage:
        name: template deploy
        identifier: template_deploy
        type: IACM
        spec:
          workspace: templatecontrollerwsgit
          execution:
            steps:
              # Parse webhook payload to find modified templates
              - step:
                  type: Run
                  name: Payload Debug
                  identifier: Payload_Debug
                  spec:
                    shell: Bash
                    command: |-
                      # Extract modified template files from webhook
                      PAYLOAD='<+trigger.payload>'
                      MODIFIED=$(echo "$PAYLOAD" | jq -r '[(.commits[]?.modified // []), (.commits[]?.added // [])] | flatten | .[]' | grep '^templates/' || true)
                      
                      # Initialize workspace lists
                      step_list=""
                      sg_list=""
                      stage_list=""
                      pipeline_list=""
                      
                      # Parse template files and categorize by type
                      while IFS= read -r file; do
                        if [[ $file =~ ^templates/(step|stepgroup|stage|pipeline)/([^/]+)/ ]]; then
                          type="${BASH_REMATCH[1]}"
                          id="${BASH_REMATCH[2]}"
                          ws="${type}_${id}"
                          
                          case "$type" in
                            step) step_list="$step_list $ws" ;;
                            stepgroup) sg_list="$sg_list $ws" ;;
                            stage) stage_list="$stage_list $ws" ;;
                            pipeline) pipeline_list="$pipeline_list $ws" ;;
                          esac
                        fi
                      done <<< "$MODIFIED"
                      
                      # Deduplicate and export
                      export STEP_LIST=$(echo $step_list | tr ' ' '\n' | sort -u | tr '\n' ' ')
                      export SG_LIST=$(echo $sg_list | tr ' ' '\n' | sort -u | tr '\n' ' ')
                      export STAGE_LIST=$(echo $stage_list | tr ' ' '\n' | sort -u | tr '\n' ' ')
                      export PIPELINE_LIST=$(echo $pipeline_list | tr ' ' '\n' | sort -u | tr '\n' ' ')
                    outputVariables:
                      - name: STEP_LIST
                      - name: SG_LIST
                      - name: STAGE_LIST
                      - name: PIPELINE_LIST
              
              - step:
                  type: IACMOpenTofuPlugin
                  name: init
                  spec:
                    command: init
              - step:
                  type: IACMOpenTofuPlugin
                  name: plan
                  spec:
                    command: plan
              - step:
                  type: IACMOpenTofuPlugin
                  name: apply
                  spec:
                    command: apply
    
    # Stage 2: Deploy step templates
    - stage:
        name: step templates
        identifier: step_templates
        type: IACM
        spec:
          workspace: <+repeat.item>
          execution:
            steps:
              - step:
                  type: IACMOpenTofuPlugin
                  name: init
                  spec:
                    command: init
              - step:
                  type: IACMOpenTofuPlugin
                  name: plan
                  spec:
                    command: plan
              - step:
                  type: IACMOpenTofuPlugin
                  name: apply
                  spec:
                    command: apply
        strategy:
          repeat:
            items: <+pipeline.stages.template_deploy.spec.execution.steps.Payload_Debug.output.outputVariables.STEP_LIST>.split(" ")
        when:
          condition: <+pipeline.stages.template_deploy.spec.execution.steps.Payload_Debug.output.outputVariables.STEP_LIST> != ""
    
    # Stage 3: Deploy stepgroup templates
    - stage:
        name: step-group templates
        identifier: step_group_templates
        type: IACM
        spec:
          workspace: <+repeat.item>
          execution:
            steps:
              - step:
                  type: IACMOpenTofuPlugin
                  name: init
                  spec:
                    command: init
              - step:
                  type: IACMOpenTofuPlugin
                  name: plan
                  spec:
                    command: plan
              - step:
                  type: IACMOpenTofuPlugin
                  name: apply
                  spec:
                    command: apply
        strategy:
          repeat:
            items: <+pipeline.stages.template_deploy.spec.execution.steps.Payload_Debug.output.outputVariables.SG_LIST>.split(" ")
        when:
          condition: <+pipeline.stages.template_deploy.spec.execution.steps.Payload_Debug.output.outputVariables.SG_LIST> != ""
    
    # Stage 4: Deploy stage templates
    - stage:
        name: stage templates
        identifier: stage_templates
        type: IACM
        spec:
          workspace: <+repeat.item>
          execution:
            steps:
              - step:
                  type: IACMOpenTofuPlugin
                  name: init
                  spec:
                    command: init
              - step:
                  type: IACMOpenTofuPlugin
                  name: plan
                  spec:
                    command: plan
              - step:
                  type: IACMOpenTofuPlugin
                  name: apply
                  spec:
                    command: apply
        strategy:
          repeat:
            items: <+pipeline.stages.template_deploy.spec.execution.steps.Payload_Debug.output.outputVariables.STAGE_LIST>.split(" ")
        when:
          condition: <+pipeline.stages.template_deploy.spec.execution.steps.Payload_Debug.output.outputVariables.STAGE_LIST> != ""
    
    # Stage 5: Deploy pipeline templates
    - stage:
        name: pipeline templates
        identifier: pipeline_templates
        type: IACM
        spec:
          workspace: <+repeat.item>
          execution:
            steps:
              - step:
                  type: IACMOpenTofuPlugin
                  name: init
                  spec:
                    command: init
              - step:
                  type: IACMOpenTofuPlugin
                  name: plan
                  spec:
                    command: plan
              - step:
                  type: IACMOpenTofuPlugin
                  name: apply
                  spec:
                    command: apply
        strategy:
          repeat:
            items: <+pipeline.stages.template_deploy.spec.execution.steps.Payload_Debug.output.outputVariables.PIPELINE_LIST>.split(" ")
        when:
          condition: <+pipeline.stages.template_deploy.spec.execution.steps.Payload_Debug.output.outputVariables.PIPELINE_LIST> != ""
```

**Pipeline Behavior**:
1. Triggered by webhook when templates/ directory changes
2. Parses modified files and categorizes by template type
3. Deploys templates in dependency order:
   - Step templates first (no dependencies)
   - StepGroup templates second (depend on steps)
   - Stage templates third (depend on stepgroups)
   - Pipeline templates last (depend on stages)
4. Each template deployed via separate IaCM workspace

---

## Testing

The plugin includes comprehensive test suites. See [`testing/` directory](../testing/README.md) for details.

### Test Suites

| Test Suite | Purpose | Status |
|------------|---------|--------|
| `test_ideal_flow.py` | Complete lifecycle (extract → promote → stable) | ✅ 5/5 PASSED |
| `test_tree_validation.py` | Tree extraction and validation | ✅ 5/5 PASSED |
| `test_invalid_promotions.py` | Invalid promotion rejection | ⚠️ 5/8 PASSED |
| `test_edge_cases.py` | Boundary conditions | ⚠️ 5/6 PASSED |

### Run Tests Locally

```bash
cd testing
bash setup.sh
source venv/bin/activate

# Run all tests
python test_ideal_flow.py
python test_tree_validation.py
python test_invalid_promotions.py
python test_edge_cases.py

# Run individual component tests
python scripts/test_extraction_tree.py
python scripts/test_promotion_tier.py
python scripts/test_combined_mode.py
```

### What's Tested

✅ **Working Correctly**:
- Tree extraction discovers all dependencies
- Template type determination (stage, stepgroup, step)
- 4-level validation for each template
- Child template reference updates
- Sequential tier progression (1→2→3→4→5→stable)
- Tier skip with flag enabled
- Combined mode (extract + promote)
- Stable promotion from any tier
- Missing source file rejection

✅ **All Validation Rules Enforced** (Fixed 2026-04-20):
- Backwards promotion blocked (tier-2 → tier-1) ✅
- Same-tier promotion allowed as idempotent with warning (tier-1 → tier-1) ✅
- Semantic version must go to tier-1 first (v1 can only → tier-1) ✅
- Large tier skip requires flag (tier-1 → tier-5 needs TIER_SKIP=true) ✅

---

## Troubleshooting

### Common Errors

#### 1. Configuration Validation Error
```
ValueError: project_id required when execution_url is set
```
**Solution**: Provide both `EXECUTION_URL` and `PROJECT_ID` for extraction mode.

#### 2. API Authentication Error
```
401 Unauthorized
```
**Solution**: 
- Verify `API_KEY` is a valid PAT token
- Ensure token has permissions: `core_template_view`, `core_template_edit`

#### 3. Template Not Found
```
Template Stage_Template not found
```
**Solution**:
- Verify template exists in Harness
- Check `TEMPLATE_ID` matches exactly (case-sensitive)
- Ensure template is in the correct org/project

#### 4. Execution Failed
```
Execution failed or not completed: Failed
```
**Solution**: Plugin only extracts from **successful** executions. Re-run the pipeline and use the new execution URL.

#### 5. No Templates Extracted (Tree Mode)
```
Extracted 0 templates
```
**Solution**:
- Verify execution URL points to a successful execution
- Check that the execution actually used the template
- Ensure template has proper `templateRef` in execution YAML

#### 6. Template Type Determination Failed
```
All templates saved to templates/stage/ (wrong!)
```
**Solution**: This was a bug fixed in recent versions. Update to latest plugin version.

#### 7. Child Template References Not Updated
```
Parent template still references child@v1 instead of child@tier-1
```
**Solution**: Use **tree mode** (`MODE=tree`) for bulk promotions. Single mode only promotes one template.

---

## Output Variables

Plugin exports variables for use in downstream steps:

### Extraction Mode Outputs

```bash
template_id           # Template identifier
template_version      # Template version (e.g., v1)
template_type         # Template type (step, stepgroup, stage, pipeline)
execution_id          # Execution identifier
execution_status      # Execution status
mode                  # Extraction mode (single/tree)
templates_extracted   # Number of templates extracted (tree mode)
tree                  # JSON array of extracted templates with metadata
```

### Promotion Mode Outputs

```bash
template_id           # Template identifier
source_version        # Source version (e.g., tier-1)
target_version        # Target version (e.g., tier-2)
tier_file             # Path to created tier file
templates_promoted    # Number of templates promoted (tree mode)
promoted_templates    # JSON array of promoted template IDs
```

### Using Outputs

```yaml
- step:
    type: Run
    name: Display Results
    spec:
      shell: Bash
      command: |
        echo "Template: <+execution.steps.Promotion_Plugin.output.outputVariables.template_id>"
        echo "Promoted: <+execution.steps.Promotion_Plugin.output.outputVariables.templates_promoted>"
```

---

## File Structure

Plugin generates this directory structure:

```
templates/
├── step/
│   └── Step_Template/
│       ├── v1.yaml
│       ├── tier-1.yaml
│       ├── tier-2.yaml
│       └── stable.yaml
├── stepgroup/
│   └── SG_Template/
│       ├── v1.yaml
│       └── tier-1.yaml
├── stage/
│   └── Stage_Template/
│       ├── v1.yaml
│       ├── tier-1.yaml
│       ├── tier-2.yaml
│       ├── tier-5.yaml
│       └── stable.yaml
└── pipeline/
    └── Pipeline_Template/
        ├── v1.yaml
        └── tier-1.yaml

versions.yaml     # Tracks all template versions and tier mappings
```

### versions.yaml Format

```yaml
labels:
  canary: {}
  stable: {}
templates:
  stage:
    Stage_Template:
      current_version: v1
      tiers:
        tier-1: v1
        tier-2: v1
        tier-5: v1
  stepgroup:
    SG_Template:
      current_version: v1
      tiers:
        tier-1: v1
  step:
    Step:
      current_version: v1
      tiers:
        tier-1: v1
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Harness CI Pipeline                                         │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Plugin Step                                         │   │
│  │                                                     │   │
│  │  Environment Variables:                            │   │
│  │  - PLUGIN_API_KEY                                  │   │
│  │  - PLUGIN_ACCOUNT_ID                               │   │
│  │  - PLUGIN_TEMPLATE_ID                              │   │
│  │  - PLUGIN_MODE                                     │   │
│  │  - PLUGIN_TO_TIER                                  │   │
│  └─────────────────────────────────────────────────────┘   │
│                          │                                   │
│                          ▼                                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Docker Container (plugin image)                     │   │
│  │                                                     │   │
│  │  ┌──────────────────────────────────────────────┐  │   │
│  │  │ main.py                                      │  │   │
│  │  │ - Load config (Pydantic validation)         │  │   │
│  │  │ - Initialize logging                        │  │   │
│  │  │ - Call execute_plugin()                     │  │   │
│  │  │ - Write DRONE_OUTPUT_FILE                   │  │   │
│  │  │ - Exit with status code                     │  │   │
│  │  └──────────────────────────────────────────────┘  │   │
│  │                          │                           │   │
│  │                          ▼                           │   │
│  │  ┌──────────────────────────────────────────────┐  │   │
│  │  │ logic.py                                     │  │   │
│  │  │                                              │  │   │
│  │  │ TemplateExtractor:                          │  │   │
│  │  │ - extract_single()                          │  │   │
│  │  │ - extract_tree()                            │  │   │
│  │  │ - _validate_template() [4 levels]          │  │   │
│  │  │                                              │  │   │
│  │  │ TemplatePromoter:                           │  │   │
│  │  │ - promote()                                 │  │   │
│  │  │ - _determine_source_version()              │  │   │
│  │  │ - _update_child_references()               │  │   │
│  │  └──────────────────────────────────────────────┘  │   │
│  │                          │                           │   │
│  │                          ▼                           │   │
│  │  ┌──────────────────────────────────────────────┐  │   │
│  │  │ harness_api/                                 │  │   │
│  │  │ - HarnessAPIClient                          │  │   │
│  │  │ - TemplatesApi                              │  │   │
│  │  │ - ExecutionsApi                             │  │   │
│  │  │ - PipelinesApi                              │  │   │
│  │  └──────────────────────────────────────────────┘  │   │
│  │                          │                           │   │
│  └──────────────────────────┼───────────────────────────┘   │
│                             │                               │
│                             ▼                               │
│                  Harness API (app.harness.io)               │
└─────────────────────────────────────────────────────────────┘
```

---

## Development

### Local Development Setup

```bash
# Clone repo
git clone https://github.com/your-org/template-promotion.git
cd template-promotion/template-promotion-plugin

# Install dependencies
pip install -r requirements.txt

# Run locally (no Docker)
cd ../testing
bash setup.sh
source venv/bin/activate
python test_ideal_flow.py
```

### Project Structure

```
template-promotion-plugin/
├── src/
│   ├── __init__.py
│   ├── main.py                  # Plugin entrypoint
│   ├── config.py                # Pydantic configuration
│   ├── logic.py                 # Business logic
│   ├── versions_manager.py      # versions.yaml management
│   └── harness_api/
│       ├── __init__.py
│       ├── client.py            # API client
│       ├── templates.py         # Templates API
│       ├── executions.py        # Executions API
│       └── pipelines.py         # Pipelines API
├── Dockerfile                   # Multi-stage Docker build
├── requirements.txt             # Python dependencies
├── .dockerignore
└── README.md                    # This file
```

### Build and Test

```bash
# Build Docker image
docker build -t template-promotion-plugin:dev .

# Test extraction
docker run --rm \
  -e PLUGIN_API_KEY="pat.xxx" \
  -e PLUGIN_ACCOUNT_ID="xyz" \
  -e PLUGIN_TEMPLATE_ID="Stage_Template" \
  -e PLUGIN_EXECUTION_URL="https://app.harness.io/..." \
  -e PLUGIN_PROJECT_ID="Twilio" \
  -e PLUGIN_MODE="tree" \
  template-promotion-plugin:dev

# Test promotion
docker run --rm \
  -e PLUGIN_API_KEY="pat.xxx" \
  -e PLUGIN_ACCOUNT_ID="xyz" \
  -e PLUGIN_TEMPLATE_ID="Stage_Template" \
  -e PLUGIN_TO_TIER="2" \
  template-promotion-plugin:dev
```

---

## License

MIT License

## Support

For issues and feature requests:
- GitHub Issues: https://github.com/your-org/template-promotion/issues
- Documentation: See `testing/` directory for comprehensive test examples
- Test Results: See `testing/TEST_RESULTS.md` for validation findings
