# Template Promotion Guide

This guide provides detailed instructions for promoting Harness template versions through the three-tier promotion strategy.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Promotion Workflow](#promotion-workflow)
- [Tier Descriptions](#tier-descriptions)
- [Step-by-Step Process](#step-by-step-process)
- [Monitoring and Validation](#monitoring-and-validation)
- [Rollback Procedures](#rollback-procedures)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

## Overview

The promotion strategy ensures safe, controlled rollout of template changes through three tiers:

```
v1.0.0 (stable) → v1.1.0 (new version)

Step 1: Canary       [■□□□□□□□□□] 1-3 pipelines   → 24h observation
Step 2: Early        [■■■□□□□□□□] 10-20% pipelines → 72h observation
Step 3: Stable       [■■■■■■■■■■] 70-80% pipelines → 1-2 week observation
```

## Prerequisites

Before starting a promotion:

### Required Access

- Harness account with appropriate permissions
- Terraform workspace access
- Git repository write access

### Environment Setup

```bash
# Set Harness credentials
export HARNESS_ACCOUNT_ID="your-account-id"
export HARNESS_API_KEY="your-api-key"

# Verify Terraform installation
terraform version  # Should be >= 1.0

# Verify script permissions
ls -la promotion/scripts/
# All .sh files should be executable (rwxr-xr-x)
```

### Pre-Promotion Checklist

- [ ] New template version created in `templates/`
- [ ] Metadata file updated with version and changelog
- [ ] Breaking changes documented (if any)
- [ ] Validation script passes
- [ ] Testing completed in dev environment
- [ ] Approval from template owner obtained
- [ ] Stakeholders notified of upcoming promotion

## Tier Descriptions

### Canary Tier

**Purpose**: Initial testing with minimal blast radius

- **Pipelines**: 1-3 test or development pipelines
- **Observation Period**: 24 hours
- **Success Criteria**: 
  - All pipelines execute successfully
  - No errors in logs
  - Performance within acceptable range
  - No breaking changes detected

**Example Pipelines**:
- test-pipeline-1
- dev-pipeline-2
- canary-service-prod

### Early Adopters Tier

**Purpose**: Broader validation with non-critical services

- **Pipelines**: 10-20% of total pipelines
- **Observation Period**: 72 hours
- **Success Criteria**:
  - Success rate >= 95%
  - No increase in execution time
  - No customer-impacting issues
  - Positive feedback from service owners

**Example Pipelines**:
- service-a-prod
- service-b-prod
- api-gateway-prod
- reporting-pipeline

### Stable Tier

**Purpose**: Final rollout to all critical production services

- **Pipelines**: 70-80% of total pipelines
- **Observation Period**: 1-2 weeks
- **Success Criteria**:
  - Proven stability in early adopters
  - No degradation in metrics
  - No critical incidents
  - Template marked as stable

**Example Pipelines**:
- critical-service-prod
- payment-pipeline-prod
- auth-service-prod
- core-api-prod

## Step-by-Step Process

### Phase 1: Preparation

#### 1.1 Create New Template Version

Create a new version directory:

```bash
# For stage templates
mkdir -p templates/stage-templates/v1.1.0
cp templates/stage-templates/v1.0.0/deploy-stage.yaml \
   templates/stage-templates/v1.1.0/

# Make your changes to v1.1.0/deploy-stage.yaml
```

#### 1.2 Update Metadata

Create/update `metadata.yaml`:

```yaml
version: "1.1.0"
created: "2026-04-07"
author: "your-team"
changelog: |
  - Added new verification step
  - Improved error handling
  - Updated timeout values
status: "draft"
breaking_changes: false

description: |
  Enhanced deployment stage with improved verification and error handling.
```

#### 1.3 Run Validation

```bash
./promotion/scripts/validate.sh v1.1.0
```

Expected output:
```
[INFO] Starting validation for version: v1.1.0
[INFO] [1/5] Checking file existence...
[INFO]   ✓ Found: deploy-stage.yaml
[INFO]   ✓ Found: metadata.yaml
...
[INFO] ✓ All validations passed for version v1.1.0
```

#### 1.4 Test in Development

```bash
cd terraform
terraform workspace select dev
terraform apply -var-file=environments/dev.tfvars \
                -var=stage_template_version=v1.1.0
```

Run test pipelines and verify functionality.

### Phase 2: Canary Deployment

#### 2.1 Update Promotion Config

Edit `promotion/promotion-config.yaml`:

```yaml
template_versions:
  stage_template:
    current: v1.0.0
    available:
      - version: v1.0.0
        status: stable
      - version: v1.1.0
        status: canary
        deployed_tiers:
          - canary
```

#### 2.2 Deploy to Canary

```bash
./promotion/scripts/promote.sh \
  --tier canary \
  --version v1.1.0 \
  --env prod

# Review the Terraform plan
# Type 'yes' to confirm
```

#### 2.3 Monitor Canary (24 hours)

**Immediate Checks** (0-2 hours):

```bash
# Verify templates deployed
terraform output

# Check Harness UI
# - Navigate to Templates
# - Verify v1.1.0 is available
# - Check canary pipelines

# Run test executions
# - Manually trigger canary pipelines
# - Watch execution logs
# - Verify all steps complete
```

**Ongoing Monitoring** (2-24 hours):

- Monitor pipeline execution metrics
- Check error logs and failure rates
- Review execution times
- Watch for alerts or anomalies
- Collect feedback from pipeline owners

**Success Metrics**:
- Pipeline success rate >= 98%
- No increase in execution time
- No error spikes in logs
- No customer-impacting issues

#### 2.4 Decision Point

After 24 hours, evaluate:

**Proceed to Early Adopters if**:
- ✅ All canary pipelines successful
- ✅ No errors or anomalies
- ✅ Performance acceptable
- ✅ Stakeholder approval

**Rollback if**:
- ❌ Pipeline failures
- ❌ Performance degradation
- ❌ Errors in logs
- ❌ Breaking changes discovered

```bash
# If rollback needed:
./promotion/scripts/rollback.sh \
  --tier canary \
  --version v1.0.0 \
  --env prod
```

### Phase 3: Early Adopters Deployment

#### 3.1 Promote to Early Adopters

```bash
./promotion/scripts/promote.sh \
  --tier early_adopters \
  --version v1.1.0 \
  --env prod
```

#### 3.2 Monitor Early Adopters (72 hours)

**Day 1** (0-24 hours):
- Close monitoring of all early adopter pipelines
- Check execution logs frequently
- Respond quickly to any issues
- Document any unexpected behavior

**Day 2-3** (24-72 hours):
- Continue monitoring metrics
- Review aggregated statistics
- Compare with baseline metrics
- Collect feedback from service teams

**Success Metrics**:
- Success rate >= 95%
- Average execution time within +10% of baseline
- No critical incidents
- Positive feedback from service owners

#### 3.3 Decision Point

After 72 hours, evaluate:

**Proceed to Stable if**:
- ✅ Success rate meets threshold
- ✅ No performance degradation
- ✅ No critical issues
- ✅ Positive feedback

**Rollback or Pause if**:
- ❌ Success rate below threshold
- ❌ Performance issues
- ❌ Critical bugs discovered
- ❌ Negative feedback

### Phase 4: Stable Deployment

#### 4.1 Promote to Stable

```bash
./promotion/scripts/promote.sh \
  --tier stable \
  --version v1.1.0 \
  --env prod
```

#### 4.2 Monitor Stable (1-2 weeks)

**Week 1**:
- Daily monitoring of all pipelines
- Track success rates and execution times
- Monitor for any degradation
- Be prepared for quick rollback

**Week 2**:
- Continue monitoring
- Analyze trends
- Document lessons learned
- Update runbooks if needed

#### 4.3 Mark as Stable

After successful observation period:

```bash
# Update metadata.yaml
sed -i 's/status: "canary"/status: "stable"/' \
  templates/stage-templates/v1.1.0/metadata.yaml

# Update promotion config
# Edit promotion/promotion-config.yaml:
template_versions:
  stage_template:
    current: v1.1.0  # Update current version
    available:
      - version: v1.0.0
        status: deprecated  # Mark old version
      - version: v1.1.0
        status: stable  # Mark new version as stable
```

#### 4.4 Deprecate Old Version

```bash
# Update old version metadata
sed -i 's/status: "stable"/status: "deprecated"/' \
  templates/stage-templates/v1.0.0/metadata.yaml

# Set deprecation date (30-60 days from now)
# After this date, v1.0.0 can be removed
```

## Monitoring and Validation

### Key Metrics to Track

1. **Success Rate**
   ```
   Success Rate = (Successful Executions / Total Executions) × 100
   Target: >= 95%
   ```

2. **Execution Time**
   ```
   Compare: Average execution time vs baseline
   Target: Within +20% of baseline
   ```

3. **Error Rate**
   ```
   Error Rate = (Failed Steps / Total Steps) × 100
   Target: <= 2%
   ```

4. **Rollback Frequency**
   ```
   Target: < 5% of deployments require rollback
   ```

### Monitoring Tools

**Harness Dashboard**:
- Navigate to Dashboards → Pipelines
- Filter by template version
- Review execution statistics

**Logs**:
```bash
# View Terraform state
cd terraform
terraform show

# Check recent changes
terraform state list
```

**Custom Queries** (if using Harness API):
```bash
# Get pipeline execution stats
curl -H "x-api-key: $HARNESS_API_KEY" \
  "https://app.harness.io/gateway/pipeline/api/pipelines/execution/summary"
```

### Alerts

Set up alerts for:
- Pipeline failure rate > 5%
- Execution time > 2x baseline
- Error count > threshold
- Template rollback triggered

## Rollback Procedures

### When to Rollback

Immediate rollback triggers:
- Critical production issue
- Success rate < 90%
- Data loss or corruption
- Security vulnerability discovered
- Breaking change not documented

Planned rollback triggers:
- Success rate < 95% after observation period
- Consistent performance degradation
- Multiple stakeholder complaints
- Better alternative discovered

### Rollback Process

#### Emergency Rollback (All Tiers)

```bash
# Rollback all tiers immediately
./promotion/scripts/rollback.sh \
  --tier all \
  --version v1.0.0 \
  --env prod \
  --force
```

#### Tiered Rollback

```bash
# Rollback specific tier
./promotion/scripts/rollback.sh \
  --tier canary \
  --version v1.0.0 \
  --env prod

# Without --force, you'll be prompted to confirm
```

#### Post-Rollback Steps

1. **Verify Rollback**
   ```bash
   # Check Terraform outputs
   terraform output
   
   # Verify in Harness UI
   # Check template versions in use
   ```

2. **Document Incident**
   - What went wrong
   - When it was detected
   - Impact scope
   - Resolution timeline

3. **Root Cause Analysis**
   - Identify root cause
   - Document in version changelog
   - Update validation checks
   - Improve testing

4. **Communicate**
   - Notify stakeholders
   - Update status page
   - Share lessons learned

## Best Practices

### Do's ✅

1. **Always validate** before promoting
   ```bash
   ./promotion/scripts/validate.sh <version>
   ```

2. **Use dry-run** to preview changes
   ```bash
   ./promotion/scripts/promote.sh ... --dry-run
   ```

3. **Monitor actively** during observation periods

4. **Document everything**:
   - Changes in metadata.yaml
   - Issues encountered
   - Decisions made

5. **Communicate proactively**:
   - Notify before promotion
   - Share observation results
   - Report incidents quickly

6. **Test thoroughly** in dev/test first

7. **Follow observation periods**:
   - Don't rush promotions
   - Wait for metrics to stabilize

### Don'ts ❌

1. **Don't skip validation**
   - Always run validation script
   - Never bypass checks

2. **Don't rush promotions**
   - Respect observation periods
   - Wait for metrics

3. **Don't promote during high traffic**
   - Avoid peak hours
   - Schedule during maintenance windows

4. **Don't make multiple changes**
   - One version upgrade at a time
   - Don't mix infrastructure changes

5. **Don't ignore warnings**
   - Investigate all errors
   - Address feedback

6. **Don't promote without approval**
   - Get stakeholder sign-off
   - Document approvals

## Troubleshooting

### Validation Fails

**Problem**: `validate.sh` reports errors

**Solution**:
```bash
# Check YAML syntax
yamllint templates/stage-templates/v1.1.0/*.yaml

# Verify metadata version matches
grep version templates/stage-templates/v1.1.0/metadata.yaml

# Run Terraform validation
cd terraform
terraform validate
```

### Promotion Script Hangs

**Problem**: `promote.sh` doesn't complete

**Solution**:
```bash
# Check Terraform lock
cd terraform
terraform force-unlock <lock-id>

# Verify Harness API connectivity
curl -H "x-api-key: $HARNESS_API_KEY" \
  https://app.harness.io/gateway/ng/api/user/currentUser

# Check workspace
terraform workspace list
terraform workspace select prod
```

### Pipeline Failures After Promotion

**Problem**: Pipelines fail with new template version

**Solution**:
1. Check error logs in Harness UI
2. Compare with previous version execution
3. Verify runtime inputs are compatible
4. Check for breaking changes
5. Rollback if necessary

```bash
./promotion/scripts/rollback.sh \
  --tier <affected-tier> \
  --version <previous-stable-version> \
  --env prod
```

### Template Not Visible in Harness

**Problem**: Template deployed but not showing in UI

**Solution**:
```bash
# Verify Terraform applied successfully
cd terraform
terraform show | grep -A 10 "harness_platform_template"

# Check in Harness API
curl -H "x-api-key: $HARNESS_API_KEY" \
  "https://app.harness.io/gateway/template/api/templates"

# Refresh Harness UI
# Clear browser cache
# Try incognito mode
```

## Emergency Contacts

- **Template Owner**: [contact info]
- **Platform Team**: [contact info]
- **On-Call Engineer**: [contact info]
- **Slack Channel**: #harness-templates

## Additional Resources

- [Versioning Strategy](VERSIONING.md)
- [Harness Documentation](https://docs.harness.io)
- [Terraform Provider Docs](https://registry.terraform.io/providers/harness/harness/latest/docs)
- [Project README](../README.md)
