# Harness Pipeline Integration Guide

This guide shows how to use the `harness_pipeline_runner.sh` script in Harness CI/CD pipelines for template extraction and promotion.

## Overview

The `harness_pipeline_runner.sh` script provides an environment-variable-based interface to `validate_and_extract.py`, making it easy to integrate with Harness pipelines where parameters are typically passed as environment variables.

## Quick Start

In your Harness pipeline RUN step:

```yaml
- step:
    type: Run
    spec:
      shell: Bash
      envVariables:
        HARNESS_API_KEY: <+secrets.getValue("harness_api_key")>
        HARNESS_ACCOUNT_ID: <+account.identifier>
        TEMPLATE_ID: "Stage_Template"
        EXECUTION_URL: <+pipeline.variables.execution_url>
        PROJECT_ID: <+pipeline.variables.project_id>
        CHANGELOG: "Updated template"
        MODE: "single"
      command: |
        bash scripts/harness_pipeline_runner.sh
```

## Environment Variables Reference

### Required Variables (All Modes)

| Variable | Description | Example |
|----------|-------------|---------|
| `HARNESS_API_KEY` | Harness API key | `pat.xxx...` |
| `HARNESS_ACCOUNT_ID` | Harness account identifier | `Pt_YA3aYQT6g6ZW7MZOMJw` |
| `TEMPLATE_ID` | Template identifier | `Stage_Template` |

### Extraction Mode Variables

Required when `EXECUTION_URL` is set:

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `EXECUTION_URL` | Yes | Full Harness execution URL | `https://app.harness.io/ng/...` |
| `PROJECT_ID` | Yes | Project where template tested | `Twilio` |
| `CHANGELOG` | No | Description of changes | `"Fixed retry logic"` |
| `MODE` | No | `single` or `tree` | `tree` |
| `SOURCE_VERSION` | No | Semantic version label | `v1.3` |
| `SANITIZE` | No | Convert secrets to runtime inputs | `true` |
| `TO_TIER` | No | Create tier during extraction | `1` |

### Promotion Mode Variables

Required when `EXECUTION_URL` is NOT set:

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `TO_TIER` | Yes | Target tier (1-5) | `2` |
| `TIER_SKIP` | No | Allow skipping intermediate tiers | `true` |
| `NO_PR` | No | Skip PR creation | `true` |

### Boolean Values

Boolean variables accept: `true`, `false`, `1`, `0`, `yes`, `no` (case-insensitive)

## Complete Pipeline Examples

### Example 1: Template Extraction Pipeline

This pipeline extracts a template from a successful execution and creates tier-1.

```yaml
pipeline:
  identifier: template_extraction
  name: Template Extraction
  projectIdentifier: Twilio
  orgIdentifier: default
  
  variables:
    - name: template_id
      type: String
      description: Template identifier to extract
      value: ""
    - name: execution_url
      type: String
      description: URL of successful test execution
      value: ""
    - name: project_id
      type: String
      description: Project ID where template tested
      value: "Twilio"
    - name: changelog
      type: String
      description: Description of changes
      value: "Updated template"
    - name: mode
      type: String
      description: single or tree
      value: "single"
      allowedValues:
        - single
        - tree
    - name: sanitize
      type: String
      description: Sanitize secrets
      value: "false"
      allowedValues:
        - "true"
        - "false"
  
  stages:
    - stage:
        identifier: extract_and_create_tier1
        name: Extract and Create Tier-1
        type: CI
        spec:
          cloneCodebase: true
          execution:
            steps:
              - step:
                  identifier: extract_template
                  name: Extract Template
                  type: Run
                  spec:
                    shell: Bash
                    envVariables:
                      HARNESS_API_KEY: <+secrets.getValue("harness_platform_api_key")>
                      HARNESS_ACCOUNT_ID: <+account.identifier>
                      TEMPLATE_ID: <+pipeline.variables.template_id>
                      EXECUTION_URL: <+pipeline.variables.execution_url>
                      PROJECT_ID: <+pipeline.variables.project_id>
                      CHANGELOG: <+pipeline.variables.changelog>
                      MODE: <+pipeline.variables.mode>
                      SANITIZE: <+pipeline.variables.sanitize>
                      TO_TIER: "1"
                    command: |
                      echo "Starting template extraction..."
                      bash scripts/harness_pipeline_runner.sh
                    
                    onFailure:
                      action:
                        type: Abort
```

### Example 2: Template Promotion Pipeline

This pipeline promotes a template from one tier to the next.

```yaml
pipeline:
  identifier: template_promotion
  name: Template Promotion
  projectIdentifier: Twilio
  orgIdentifier: default
  
  variables:
    - name: template_id
      type: String
      description: Template identifier to promote
      value: ""
    - name: to_tier
      type: String
      description: Target tier
      value: "2"
      allowedValues:
        - "1"
        - "2"
        - "3"
        - "4"
        - "5"
    - name: tier_skip
      type: String
      description: Allow skipping intermediate tiers
      value: "false"
      allowedValues:
        - "true"
        - "false"
  
  stages:
    - stage:
        identifier: promote_template
        name: Promote Template
        type: CI
        spec:
          cloneCodebase: true
          execution:
            steps:
              - step:
                  identifier: promotion
                  name: Run Promotion
                  type: Run
                  spec:
                    shell: Bash
                    envVariables:
                      HARNESS_API_KEY: <+secrets.getValue("harness_platform_api_key")>
                      HARNESS_ACCOUNT_ID: <+account.identifier>
                      TEMPLATE_ID: <+pipeline.variables.template_id>
                      TO_TIER: <+pipeline.variables.to_tier>
                      TIER_SKIP: <+pipeline.variables.tier_skip>
                    command: |
                      echo "Starting template promotion..."
                      bash scripts/harness_pipeline_runner.sh
```

### Example 3: Combined Pipeline with Stages

This pipeline supports both extraction and promotion in different stages.

```yaml
pipeline:
  identifier: template_management
  name: Template Management
  projectIdentifier: Twilio
  orgIdentifier: default
  
  variables:
    - name: operation
      type: String
      description: Operation to perform
      value: "extract"
      allowedValues:
        - extract
        - promote
    - name: template_id
      type: String
      value: ""
    - name: execution_url
      type: String
      value: ""
    - name: project_id
      type: String
      value: "Twilio"
    - name: to_tier
      type: String
      value: "1"
  
  stages:
    - stage:
        identifier: extraction_stage
        name: Extract Template
        when:
          condition: <+pipeline.variables.operation> == "extract"
        type: CI
        spec:
          cloneCodebase: true
          execution:
            steps:
              - step:
                  identifier: extract
                  type: Run
                  spec:
                    shell: Bash
                    envVariables:
                      HARNESS_API_KEY: <+secrets.getValue("harness_platform_api_key")>
                      HARNESS_ACCOUNT_ID: <+account.identifier>
                      TEMPLATE_ID: <+pipeline.variables.template_id>
                      EXECUTION_URL: <+pipeline.variables.execution_url>
                      PROJECT_ID: <+pipeline.variables.project_id>
                      MODE: "single"
                      TO_TIER: "1"
                    command: |
                      bash scripts/harness_pipeline_runner.sh
    
    - stage:
        identifier: promotion_stage
        name: Promote Template
        when:
          condition: <+pipeline.variables.operation> == "promote"
        type: CI
        spec:
          cloneCodebase: true
          execution:
            steps:
              - step:
                  identifier: promote
                  type: Run
                  spec:
                    shell: Bash
                    envVariables:
                      HARNESS_API_KEY: <+secrets.getValue("harness_platform_api_key")>
                      HARNESS_ACCOUNT_ID: <+account.identifier>
                      TEMPLATE_ID: <+pipeline.variables.template_id>
                      TO_TIER: <+pipeline.variables.to_tier>
                    command: |
                      bash scripts/harness_pipeline_runner.sh
```

## Local Testing

For local development and testing, you can use the script directly:

```bash
# Test extraction mode
export HARNESS_API_KEY="pat.xxx..."
export HARNESS_ACCOUNT_ID="your-account-id"
export TEMPLATE_ID="Stage_Template"
export EXECUTION_URL="https://app.harness.io/ng/.../executions/abc123"
export PROJECT_ID="Twilio"
export CHANGELOG="Test extraction"
export MODE="single"
export TO_TIER="1"

bash scripts/harness_pipeline_runner.sh
```

```bash
# Test promotion mode
export HARNESS_API_KEY="pat.xxx..."
export HARNESS_ACCOUNT_ID="your-account-id"
export TEMPLATE_ID="Stage_Template"
export TO_TIER="2"
export NO_PR="true"

bash scripts/harness_pipeline_runner.sh
```

## Troubleshooting

### Error: Missing required environment variables

**Cause:** Required variables not set in pipeline

**Solution:** Verify all required variables are set:
- Extraction: `HARNESS_API_KEY`, `HARNESS_ACCOUNT_ID`, `TEMPLATE_ID`, `EXECUTION_URL`, `PROJECT_ID`
- Promotion: `HARNESS_API_KEY`, `HARNESS_ACCOUNT_ID`, `TEMPLATE_ID`, `TO_TIER`

### Error: Invalid MODE or TO_TIER

**Cause:** Variable has invalid value

**Solution:** 
- `MODE` must be `single` or `tree`
- `TO_TIER` must be `1`, `2`, `3`, `4`, or `5`

### Error: Python not found

**Cause:** Python not available in pipeline environment

**Solution:** Ensure your pipeline has Python 3.7+ installed. Add installation step:

```yaml
- step:
    name: Install Python
    type: Run
    spec:
      command: |
        apt-get update && apt-get install -y python3 python3-pip
```

### Script output not visible

**Cause:** Script output buffered

**Solution:** The wrapper script passes through all Python output. Check full logs.

## Advanced Usage

### Using Expressions

You can use Harness expressions in environment variables:

```yaml
envVariables:
  TEMPLATE_ID: <+trigger.payload.template_id>
  EXECUTION_URL: <+trigger.payload.execution_url>
  CHANGELOG: "Triggered by <+trigger.type> at <+pipeline.executionUrl>"
  TO_TIER: <+stage.output.previous_tier + 1>
```

### Matrix Execution

Promote multiple templates in parallel:

```yaml
- stage:
    identifier: bulk_promotion
    strategy:
      matrix:
        template_id:
          - Stage_Template
          - SG_Template
          - Step_Template
    spec:
      execution:
        steps:
          - step:
              type: Run
              spec:
                envVariables:
                  TEMPLATE_ID: <+matrix.template_id>
                  TO_TIER: "2"
                command: |
                  bash scripts/harness_pipeline_runner.sh
```

### Conditional Tier Creation

Create tier only if validation passes:

```yaml
- step:
    name: Validate Template
    identifier: validate
    type: Run
    spec:
      command: |
        # Custom validation logic
        if [[ condition ]]; then
          echo "VALIDATION_PASSED=true" >> $HARNESS_ENV
        fi

- step:
    name: Create Tier
    identifier: create_tier
    when:
      condition: <+env.VALIDATION_PASSED> == "true"
    type: Run
    spec:
      command: |
        bash scripts/harness_pipeline_runner.sh
```

## Security Best Practices

1. **Store API Key in Secrets**
   ```yaml
   HARNESS_API_KEY: <+secrets.getValue("harness_platform_api_key")>
   ```

2. **Use Scoped Secrets**
   Create API key with minimal required permissions

3. **Audit Trail**
   Use `CHANGELOG` to document all changes

4. **PR Review**
   The script creates PRs by default - require manual review before merge

5. **Restrict Pipeline Execution**
   Use RBAC to control who can run promotion pipelines

## Script Output

The script provides clear, structured output:

```
================================================================
Harness Pipeline Runner for Template Extraction & Promotion
================================================================

[INFO] Working directory: /repo/root
[INFO] Mode: EXTRACTION (EXECUTION_URL is set)
[INFO] Using Python: python3
[INFO] Python version: 3.9
[INFO] Validating environment variables...
[SUCCESS] ✓ All required variables present and valid
[INFO] Building Python command...
[INFO] Command to execute:
  python3 scripts/validate_and_extract.py --template-id Stage_Template ...
[INFO] Configuration:
  Template ID: Stage_Template
  Project ID: Twilio
  Mode: single
  Changelog: Updated template
================================================================
[INFO] Executing Python script...
================================================================

<Python script output>

================================================================
[SUCCESS] ✓ Script completed successfully!
================================================================
```

Exit codes:
- `0` - Success
- `1` - Validation error or missing variables
- `2` - Python script error

## Support

For issues or questions:
1. Check this documentation
2. Review script output for error messages
3. Test locally with same environment variables
4. Check Python script logs in `validate_and_extract.py`
