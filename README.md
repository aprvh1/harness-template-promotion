# Harness Template Promotion Framework

A Terraform-based infrastructure-as-code solution for managing Harness templates and pipelines with versioned, phased promotion strategies.

## Overview

This project provides a complete framework for:

- **Managing Harness templates as code** using Terraform
- **Versioning templates** with semantic versioning
- **Promoting templates** through a three-tier strategy (canary → early adopters → stable)
- **Validating changes** before deployment
- **Rolling back** quickly when issues arise

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Template Versions                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │ v1.0.0   │  │ v1.1.0   │  │ v1.2.0   │                  │
│  └──────────┘  └──────────┘  └──────────┘                  │
└─────────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                  Promotion Tiers                             │
│                                                               │
│  ┌──────────────────────────────────────────────┐           │
│  │  Canary (1-3 pipelines)                      │           │
│  │  • First to receive updates                  │           │
│  │  • 24h observation                           │           │
│  └──────────────────────────────────────────────┘           │
│                        │                                      │
│                        ▼                                      │
│  ┌──────────────────────────────────────────────┐           │
│  │  Early Adopters (10-20% of pipelines)       │           │
│  │  • Non-critical production                   │           │
│  │  • 72h observation                           │           │
│  └──────────────────────────────────────────────┘           │
│                        │                                      │
│                        ▼                                      │
│  ┌──────────────────────────────────────────────┐           │
│  │  Stable (70-80% of pipelines)               │           │
│  │  • Critical production                       │           │
│  │  • 1-2 week proven stability                │           │
│  └──────────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────┘
```

## Project Structure

```
template-promotion/
├── terraform/              # Terraform infrastructure code
│   ├── modules/           # Reusable Terraform modules
│   │   ├── stage-template/
│   │   ├── pipeline-template/
│   │   └── pipeline/
│   └── environments/      # Environment-specific configurations
├── templates/             # Harness template definitions
│   ├── stage-templates/   # Stage template versions
│   └── pipeline-templates/ # Pipeline template versions
├── promotion/             # Promotion framework
│   ├── scripts/          # Automation scripts
│   └── validation/       # Test cases and validation rules
└── docs/                 # Documentation
```

## Quick Start

### Prerequisites

- [Terraform](https://www.terraform.io/downloads) >= 1.0
- [Harness account](https://harness.io) with API access
- Harness API key and account ID

### Setup

1. **Clone and navigate to the project:**
   ```bash
   cd template-promotion
   ```

2. **Configure Harness authentication:**
   ```bash
   export HARNESS_ACCOUNT_ID="your-account-id"
   export HARNESS_API_KEY="your-api-key"
   ```

3. **Update environment configuration:**
   Edit `terraform/environments/dev.tfvars` with your org and project IDs:
   ```hcl
   harness_org_id     = "your_org_id"
   harness_project_id = "your_project_id"
   ```

4. **Initialize Terraform:**
   ```bash
   cd terraform
   terraform init
   terraform workspace new dev
   ```

5. **Deploy templates:**
   ```bash
   terraform plan -var-file=environments/dev.tfvars
   terraform apply -var-file=environments/dev.tfvars
   ```

## Usage

### Deploying Templates

Deploy templates to a specific environment:

```bash
cd terraform
terraform workspace select dev
terraform apply -var-file=environments/dev.tfvars
```

### Promoting Templates

Use the promotion script to roll out a new template version:

```bash
# Promote to canary tier
./promotion/scripts/promote.sh \
  --tier canary \
  --version v1.1.0 \
  --env prod

# After validation, promote to early adopters
./promotion/scripts/promote.sh \
  --tier early_adopters \
  --version v1.1.0 \
  --env prod

# Finally, promote to stable
./promotion/scripts/promote.sh \
  --tier stable \
  --version v1.1.0 \
  --env prod
```

### Validating Templates

Before promoting, validate the template:

```bash
./promotion/scripts/validate.sh v1.1.0
```

### Rolling Back

If issues are detected, roll back to a previous version:

```bash
./promotion/scripts/rollback.sh \
  --tier canary \
  --version v1.0.0 \
  --env prod
```

## Template Versions

Templates are versioned using semantic versioning:

- **MAJOR**: Breaking changes requiring pipeline updates (v2.0.0)
- **MINOR**: New features, backward compatible (v1.1.0)
- **PATCH**: Bug fixes, no functional changes (v1.0.1)

Each version is stored in its own directory under `templates/`:

```
templates/stage-templates/
├── v1.0.0/
│   ├── deploy-stage.yaml
│   └── metadata.yaml
└── v1.1.0/
    ├── deploy-stage.yaml
    └── metadata.yaml
```

## Promotion Strategy

### Three-Tier Model

1. **Canary Tier** (1-3 pipelines)
   - Test/development pipelines
   - First to receive updates
   - 24-hour observation window
   - Quick rollback if issues detected

2. **Early Adopters Tier** (10-20% of pipelines)
   - Non-critical production pipelines
   - Second wave of deployment
   - 72-hour observation window
   - Broader validation

3. **Stable Tier** (70-80% of pipelines)
   - Critical production pipelines
   - Final deployment stage
   - 1-2 week proven stability
   - Maximum safety

### Promotion Workflow

1. Create new template version in `templates/`
2. Update metadata.yaml with changelog
3. Run validation: `./promotion/scripts/validate.sh v1.1.0`
4. Deploy to canary: `./promotion/scripts/promote.sh --tier canary --version v1.1.0 --env prod`
5. Monitor canary pipelines for 24 hours
6. Promote to early adopters
7. Monitor for 72 hours
8. Promote to stable tier

## Configuration

### Environment Variables

- `HARNESS_ACCOUNT_ID`: Your Harness account identifier
- `HARNESS_API_KEY`: Your Harness API key or PAT token
- `HARNESS_ENDPOINT`: (Optional) Custom Harness endpoint

### Terraform Workspaces

The project uses Terraform workspaces for environment separation:

- `dev`: Development environment
- `test`: Test/staging environment
- `prod`: Production environment

### Pipeline Tier Assignment

Edit `promotion/promotion-config.yaml` to assign pipelines to tiers:

```yaml
promotion_tiers:
  canary:
    pipelines:
      - test-pipeline-1
      - dev-pipeline-2
  early_adopters:
    pipelines:
      - service-a-prod
      - service-b-prod
  stable:
    pipelines:
      - critical-service-prod
      - payment-pipeline-prod
```

## Validation

The framework includes five layers of validation:

1. **Static Validation**: Terraform format and YAML syntax checks
2. **Plan Analysis**: Review changes before applying
3. **Test Execution**: Apply to canary tier and run tests
4. **Integration Testing**: Verify pipeline executions
5. **Monitoring**: Track success rates and execution times

## Documentation

- [Promotion Guide](docs/PROMOTION_GUIDE.md) - Detailed promotion workflow
- [Versioning Strategy](docs/VERSIONING.md) - Template versioning guidelines

## Best Practices

1. **Always validate** templates before promotion
2. **Use dry-run mode** to preview changes
3. **Monitor metrics** during observation periods
4. **Document breaking changes** in metadata
5. **Test in dev/test** environments first
6. **Keep observation periods** for safety
7. **Have a rollback plan** ready

## Troubleshooting

### Terraform Initialization Fails

```bash
# Remove cached provider plugins and reinitialize
rm -rf .terraform
terraform init
```

### Template Validation Errors

```bash
# Check YAML syntax
yamllint templates/

# Validate Terraform config
cd terraform
terraform validate
```

### Promotion Script Fails

```bash
# Run in dry-run mode to see what would happen
./promotion/scripts/promote.sh --tier canary --version v1.1.0 --env prod --dry-run

# Check Terraform logs
export TF_LOG=DEBUG
```

## Contributing

1. Create new template version in `templates/`
2. Update metadata with version and changelog
3. Run validation script
4. Test in dev environment
5. Follow promotion workflow

## License

[Your License Here]

## Support

For issues or questions:
- Check the [Promotion Guide](docs/PROMOTION_GUIDE.md)
- Review [Harness Terraform Provider Docs](https://registry.terraform.io/providers/harness/harness/latest/docs)
- Contact platform team
