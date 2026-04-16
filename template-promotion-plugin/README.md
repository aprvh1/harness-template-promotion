# Harness Template Promotion Plugin

A Harness CI Plugin for extracting and promoting Harness templates across different tiers.

## Overview

This plugin automates the process of:
- **Extracting** templates from successful pipeline executions
- **Promoting** templates through a 5-tier promotion pipeline (tier-1 through tier-5)
- **Validating** templates against execution YAML
- **Sanitizing** secrets and connectors to runtime inputs

## Features

- ✅ Extract single templates or full dependency trees
- ✅ Tier-based promotion system (5 tiers: beta → canary → staging → production → stable)
- ✅ Automatic template reference qualification
- ✅ Pydantic-based configuration validation
- ✅ Real-time logging to Harness UI
- ✅ Export variables to downstream steps
- ✅ Optimized Docker image (<100MB)

## Installation

### Build Docker Image

```bash
cd template-promotion-plugin
docker build -t harness/template-promotion:1.0.0 .
```

### Push to Registry

```bash
docker tag harness/template-promotion:1.0.0 your-registry/template-promotion:1.0.0
docker push your-registry/template-promotion:1.0.0
```

## Usage

### In Harness Pipeline

Add the plugin as a step in your CI pipeline:

```yaml
- step:
    type: Plugin
    name: Extract Template
    identifier: extract_template
    spec:
      connectorRef: account.dockerhub
      image: harness/template-promotion:1.0.0
      settings:
        api_key: <+secrets.getValue("harness_api_key")>
        account_id: <+account.identifier>
        template_id: Stage_Template
        execution_url: <+pipeline.variables.execution_url>
        project_id: Twilio
        mode: single
```

## Configuration

All configuration is passed via `PLUGIN_*` environment variables (mapped from `settings` in pipeline YAML).

### Required Settings

| Setting | Environment Variable | Description |
|---------|---------------------|-------------|
| `api_key` | `PLUGIN_API_KEY` | Harness API key or PAT token |
| `account_id` | `PLUGIN_ACCOUNT_ID` | Harness account identifier |
| `template_id` | `PLUGIN_TEMPLATE_ID` | Template identifier to extract/promote |

### Extraction Mode Settings

| Setting | Environment Variable | Description | Default |
|---------|---------------------|-------------|---------|
| `execution_url` | `PLUGIN_EXECUTION_URL` | Full Harness execution URL | - |
| `project_id` | `PLUGIN_PROJECT_ID` | Project ID for extraction | - |
| `mode` | `PLUGIN_MODE` | `single` or `tree` | `single` |
| `changelog` | `PLUGIN_CHANGELOG` | Change description | - |
| `source_version` | `PLUGIN_SOURCE_VERSION` | Semantic version (e.g., v1.0) | `v1` |
| `sanitize` | `PLUGIN_SANITIZE` | Convert secrets to runtime inputs | `false` |

### Promotion Mode Settings

| Setting | Environment Variable | Description | Default |
|---------|---------------------|-------------|---------|
| `to_tier` | `PLUGIN_TO_TIER` | Target tier (1-5) | - |
| `tier_skip` | `PLUGIN_TIER_SKIP` | Allow skipping intermediate tiers | `false` |

### Output Settings

| Setting | Environment Variable | Description | Default |
|---------|---------------------|-------------|---------|
| `output_format` | `PLUGIN_OUTPUT_FORMAT` | `json` or `text` | `json` |
| `endpoint` | `PLUGIN_ENDPOINT` | Harness API endpoint | `https://app.harness.io/gateway` |

## Examples

### Example 1: Extract Single Template

```yaml
- step:
    type: Plugin
    name: Extract Template
    identifier: extract_template
    spec:
      connectorRef: dockerhub
      image: harness/template-promotion:1.0.0
      settings:
        api_key: <+secrets.getValue("harness_api_key")>
        account_id: <+account.identifier>
        template_id: <+pipeline.variables.template_id>
        execution_url: <+pipeline.variables.execution_url>
        project_id: <+pipeline.variables.project_id>
        mode: single
```

### Example 2: Extract Template Tree with Sanitization

```yaml
- step:
    type: Plugin
    name: Extract Template Tree
    identifier: extract_tree
    spec:
      connectorRef: dockerhub
      image: harness/template-promotion:1.0.0
      settings:
        api_key: <+secrets.getValue("harness_api_key")>
        account_id: <+account.identifier>
        template_id: Stage_Template
        execution_url: <+pipeline.variables.execution_url>
        project_id: Twilio
        mode: tree
        sanitize: true
```

### Example 3: Promote Template (tier-1 → tier-2)

```yaml
- step:
    type: Plugin
    name: Promote to Tier 2
    identifier: promote_tier2
    spec:
      connectorRef: dockerhub
      image: harness/template-promotion:1.0.0
      settings:
        api_key: <+secrets.getValue("harness_api_key")>
        account_id: <+account.identifier>
        template_id: Stage_Template
        to_tier: 2
```

### Example 4: Tier Skip Promotion (tier-1 → tier-4)

```yaml
- step:
    type: Plugin
    name: Skip to Tier 4
    identifier: skip_to_tier4
    spec:
      connectorRef: dockerhub
      image: harness/template-promotion:1.0.0
      settings:
        api_key: <+secrets.getValue("harness_api_key")>
        account_id: <+account.identifier>
        template_id: Stage_Template
        to_tier: 4
        tier_skip: true
```

## Output Variables

The plugin exports variables that can be used in downstream steps:

### Extraction Mode Outputs

```
template_id         - Template identifier
template_version    - Template version
template_type       - Template type (step, step_group, stage, pipeline)
execution_id        - Execution identifier
execution_status    - Execution status
mode                - Extraction mode (single/tree)
templates_extracted - Number of templates extracted (tree mode)
```

### Promotion Mode Outputs

```
template_id         - Template identifier
source_tier         - Source tier label (e.g., tier-1)
target_tier         - Target tier label (e.g., tier-2)
promotion_status    - Promotion status (success/failure)
tier_skip           - Whether tier skip was used
```

### Using Outputs in Next Step

```yaml
- step:
    type: Run
    name: Display Results
    identifier: display_results
    spec:
      shell: Bash
      command: |
        echo "Template: <+execution.steps.extract_template.output.outputVariables.template_id>"
        echo "Version: <+execution.steps.extract_template.output.outputVariables.template_version>"
        echo "Type: <+execution.steps.extract_template.output.outputVariables.template_type>"
```

## Local Testing

### Test Extraction

```bash
docker run --rm \
  -e PLUGIN_API_KEY="pat.xxx" \
  -e PLUGIN_ACCOUNT_ID="Pt_YA3aYQT6g6ZW7MZOMJw" \
  -e PLUGIN_TEMPLATE_ID="Stage_Template" \
  -e PLUGIN_EXECUTION_URL="https://app.harness.io/ng/.../executions/abc123" \
  -e PLUGIN_PROJECT_ID="Twilio" \
  -e PLUGIN_MODE="single" \
  harness/template-promotion:1.0.0
```

### Test Promotion

```bash
docker run --rm \
  -e PLUGIN_API_KEY="pat.xxx" \
  -e PLUGIN_ACCOUNT_ID="Pt_YA3aYQT6g6ZW7MZOMJw" \
  -e PLUGIN_TEMPLATE_ID="Stage_Template" \
  -e PLUGIN_TO_TIER=2 \
  harness/template-promotion:1.0.0
```

### Test with Output File

```bash
docker run --rm \
  -e PLUGIN_API_KEY="pat.xxx" \
  -e PLUGIN_ACCOUNT_ID="Pt_YA3aYQT6g6ZW7MZOMJw" \
  -e PLUGIN_TEMPLATE_ID="Stage_Template" \
  -e PLUGIN_TO_TIER=2 \
  -e DRONE_OUTPUT_FILE="/tmp/outputs.txt" \
  -v /tmp:/tmp \
  harness/template-promotion:1.0.0

# Check outputs
cat /tmp/outputs.txt
```

## Tier Promotion System

The plugin supports a 5-tier promotion system:

| Tier | Label | Purpose | Stability |
|------|-------|---------|-----------|
| 1 | `tier-1` | Beta/Development | Low |
| 2 | `tier-2` | Canary/Testing | Medium-Low |
| 3 | `tier-3` | Staging | Medium |
| 4 | `tier-4` | Production | Medium-High |
| 5 | `tier-5` | Stable | High (marked stable) |

### Sequential Promotion

Templates must be promoted sequentially through tiers:

```
tier-1 → tier-2 → tier-3 → tier-4 → tier-5 (stable)
```

### Tier Skip

Use `tier_skip: true` to jump tiers (e.g., tier-1 → tier-4):

```yaml
settings:
  to_tier: 4
  tier_skip: true
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Failure (configuration error, API error, etc.) |

## Architecture

```
┌─────────────────────────────────────────────────┐
│ Plugin Container                                │
│                                                 │
│  ┌──────────────────────────────────────────┐  │
│  │ main.py (Entrypoint)                     │  │
│  │ - Load config (Pydantic)                 │  │
│  │ - Initialize logging                     │  │
│  │ - Call execute_plugin()                  │  │
│  │ - Write DRONE_OUTPUT_FILE                │  │
│  │ - Exit with status code                  │  │
│  └──────────────────────────────────────────┘  │
│                     ↓                            │
│  ┌──────────────────────────────────────────┐  │
│  │ logic.py (Business Logic)                │  │
│  │ - TemplateExtractor                      │  │
│  │ - TemplatePromoter                       │  │
│  │ - parse_execution_url()                  │  │
│  └──────────────────────────────────────────┘  │
│                     ↓                            │
│  ┌──────────────────────────────────────────┐  │
│  │ harness_api/ (API Client)                │  │
│  │ - HarnessAPIClient                       │  │
│  │ - TemplatesApi                           │  │
│  └──────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

## Troubleshooting

### Configuration Validation Errors

```
ValueError: project_id required when execution_url is set
```

**Solution:** Ensure both `execution_url` and `project_id` are provided for extraction mode.

### API Authentication Errors

```
Error: 401 Unauthorized
```

**Solution:** Verify your `api_key` is valid and has the necessary permissions.

### Template Not Found

```
Error: Template Stage_Template not found
```

**Solution:** Check that the template exists in Harness and the identifier is correct.

### Execution Failed

```
Error: Execution failed or not completed: Failed
```

**Solution:** The plugin only extracts from successful executions. Ensure the execution completed successfully.

## Development

### Project Structure

```
template-promotion-plugin/
├── src/
│   ├── __init__.py
│   ├── main.py              # Entrypoint
│   ├── config.py            # Pydantic configuration
│   ├── logic.py             # Business logic
│   └── harness_api/         # API client
│       ├── __init__.py
│       ├── client.py
│       └── templates.py
├── test/                    # Unit tests
├── Dockerfile               # Multi-stage build
├── requirements.txt         # Dependencies
├── .dockerignore           # Docker ignore
└── README.md               # This file
```

### Running Tests

```bash
cd template-promotion-plugin
python -m pytest test/
```

### Building for Development

```bash
docker build -t harness/template-promotion:dev .
```

## License

MIT License

## Support

For issues and feature requests, please create an issue in the repository.
