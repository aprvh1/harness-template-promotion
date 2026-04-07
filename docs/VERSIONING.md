# Template Versioning Strategy

This document defines the versioning strategy for Harness templates in this project.

## Table of Contents

- [Overview](#overview)
- [Semantic Versioning](#semantic-versioning)
- [Version Structure](#version-structure)
- [Version Lifecycle](#version-lifecycle)
- [Creating New Versions](#creating-new-versions)
- [Breaking Changes](#breaking-changes)
- [Version Deprecation](#version-deprecation)
- [Best Practices](#best-practices)

## Overview

This project uses **Semantic Versioning** (SemVer) for template versions, combined with a **directory-based** storage strategy that enables side-by-side version coexistence.

### Key Principles

1. **Semantic Versioning**: MAJOR.MINOR.PATCH format
2. **Directory-based Storage**: Each version in separate directory
3. **Side-by-side Coexistence**: Multiple versions can exist simultaneously
4. **Gradual Migration**: Pipelines upgraded incrementally
5. **Backward Compatibility**: Maintain for MINOR and PATCH updates

## Semantic Versioning

We follow [Semantic Versioning 2.0.0](https://semver.org/) specification:

```
MAJOR.MINOR.PATCH
  │     │     │
  │     │     └─── Patch: Bug fixes, no functional changes
  │     └───────── Minor: New features, backward compatible
  └─────────────── Major: Breaking changes, not backward compatible
```

### Version Format

- **Format**: `vMAJOR.MINOR.PATCH`
- **Example**: `v1.2.3`
- **Regex**: `^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$`

### Version Components

#### MAJOR Version (Breaking Changes)

Increment when making incompatible changes that require pipeline modifications.

**Examples**:
- Removing or renaming required runtime inputs
- Changing step execution order
- Removing steps that pipelines depend on
- Changing output variable names
- Modifying template type (e.g., Stage → Pipeline)

**Migration Required**: ✅ Yes  
**Backward Compatible**: ❌ No

**Example**:
```
v1.5.3 → v2.0.0

Changes:
- Renamed input 'env' to 'environment' (BREAKING)
- Removed deprecated 'legacy_mode' flag (BREAKING)
```

#### MINOR Version (New Features)

Increment when adding functionality in a backward-compatible manner.

**Examples**:
- Adding new optional runtime inputs
- Adding new steps (that don't affect existing behavior)
- Adding new output variables
- Improving error messages
- Adding new conditional branches

**Migration Required**: ❌ No  
**Backward Compatible**: ✅ Yes

**Example**:
```
v1.5.3 → v1.6.0

Changes:
- Added optional 'notification_channel' input (BACKWARD COMPATIBLE)
- Added health check verification step (BACKWARD COMPATIBLE)
```

#### PATCH Version (Bug Fixes)

Increment when making backward-compatible bug fixes.

**Examples**:
- Fixing incorrect timeout values
- Correcting script errors
- Improving error handling
- Fixing documentation
- Updating comments

**Migration Required**: ❌ No  
**Backward Compatible**: ✅ Yes

**Example**:
```
v1.5.3 → v1.5.4

Changes:
- Fixed timeout value in deployment step (BUG FIX)
- Corrected error message format (BUG FIX)
```

## Version Structure

### Directory Layout

Each version is stored in its own directory:

```
templates/
├── stage-templates/
│   ├── v1.0.0/
│   │   ├── deploy-stage.yaml
│   │   └── metadata.yaml
│   ├── v1.1.0/
│   │   ├── deploy-stage.yaml
│   │   └── metadata.yaml
│   └── v2.0.0/
│       ├── deploy-stage.yaml
│       └── metadata.yaml
└── pipeline-templates/
    ├── v1.0.0/
    │   ├── ci-pipeline.yaml
    │   └── metadata.yaml
    └── v1.1.0/
        ├── ci-pipeline.yaml
        └── metadata.yaml
```

### Metadata File

Every version must have a `metadata.yaml` file:

```yaml
version: "1.1.0"
created: "2026-04-07"
author: "platform-team"
changelog: |
  - Added health check verification
  - Improved error handling
  - Updated timeout values
status: "stable"  # draft, canary, early-adopter, stable, deprecated
breaking_changes: false
deprecated_date: null  # Set when status changes to deprecated
removal_date: null     # Set 60 days after deprecation

description: |
  Detailed description of template functionality and use cases.

compatibility:
  harness_version: ">=1.0.0"
  depends_on:
    - other-template: ">=v2.0.0"

migration_guide: |
  If upgrading from v1.0.0:
  - No changes required (backward compatible)
```

## Version Lifecycle

### Status States

Templates progress through these states:

```
┌──────┐    ┌────────┐    ┌────────────────┐    ┌────────┐    ┌────────────┐
│ Draft│ -> │ Canary │ -> │ Early Adopter  │ -> │ Stable │ -> │ Deprecated │
└──────┘    └────────┘    └────────────────┘    └────────┘    └────────────┘
  │                                                                    │
  │                                                                    │
  └────────────────────────────[Rollback]──────────────────────────────┘
```

#### 1. Draft

- **Purpose**: Development and initial testing
- **Duration**: Until validation passes
- **Deployment**: Only to dev environment
- **Status**: `draft`

**Criteria to Exit**:
- ✅ All validation checks pass
- ✅ Tested in development environment
- ✅ Metadata complete
- ✅ Approval from template owner

#### 2. Canary

- **Purpose**: Initial production testing
- **Duration**: 24 hours minimum
- **Deployment**: 1-3 canary pipelines
- **Status**: `canary`

**Criteria to Exit**:
- ✅ All canary pipelines successful
- ✅ No errors in logs
- ✅ Performance acceptable
- ✅ Observation period complete

#### 3. Early Adopter

- **Purpose**: Broader validation
- **Duration**: 72 hours minimum
- **Deployment**: 10-20% of pipelines
- **Status**: `early-adopter`

**Criteria to Exit**:
- ✅ Success rate >= 95%
- ✅ No performance degradation
- ✅ No critical issues
- ✅ Positive feedback

#### 4. Stable

- **Purpose**: Production use
- **Duration**: Indefinite (until superseded)
- **Deployment**: All pipelines
- **Status**: `stable`

**This version is**:
- ✅ Recommended for new pipelines
- ✅ Fully supported
- ✅ Documented
- ✅ Monitored

#### 5. Deprecated

- **Purpose**: Phasing out
- **Duration**: 30-60 days
- **Deployment**: Existing pipelines only (no new)
- **Status**: `deprecated`

**Action Required**:
- ⚠️ Upgrade to newer version
- ⚠️ Not recommended for new use
- ⚠️ Will be removed after deprecation period

## Creating New Versions

### Step-by-Step Process

#### 1. Determine Version Number

Ask these questions:

**Q: Does this change break existing pipelines?**
- Yes → MAJOR version (v2.0.0)
- No → Continue

**Q: Does this add new functionality?**
- Yes → MINOR version (v1.1.0)
- No → Continue

**Q: Is this a bug fix?**
- Yes → PATCH version (v1.0.1)

#### 2. Create Version Directory

```bash
# Example: Creating v1.1.0
TEMPLATE_TYPE="stage-templates"  # or pipeline-templates
NEW_VERSION="v1.1.0"
PREV_VERSION="v1.0.0"

# Copy from previous version
cp -r templates/${TEMPLATE_TYPE}/${PREV_VERSION} \
      templates/${TEMPLATE_TYPE}/${NEW_VERSION}
```

#### 3. Update Template Files

Edit the template YAML file with your changes:

```bash
vim templates/${TEMPLATE_TYPE}/${NEW_VERSION}/*.yaml
```

Remember to update version labels in the template:

```yaml
template:
  name: Deploy Stage Template
  identifier: deploy_stage
  versionLabel: v1.1.0  # Update this
  # ...
```

#### 4. Create/Update Metadata

Edit `metadata.yaml`:

```yaml
version: "1.1.0"  # Match directory name (without 'v')
created: "2026-04-07"
author: "your-team"
changelog: |
  - Added health check verification step
  - Improved error handling in rollback
  - Increased default timeout to 15m
status: "draft"
breaking_changes: false

description: |
  Enhanced deployment stage with improved reliability and monitoring.

# If this is a MAJOR version with breaking changes:
breaking_changes: true
migration_guide: |
  Breaking changes in v2.0.0:
  
  1. Input renamed: 'env' → 'environment'
     Old: env: dev
     New: environment: dev
  
  2. Removed: 'legacy_mode' flag
     This flag is no longer supported. Update your pipelines to remove it.
```

#### 5. Update Version in Terraform

Edit `terraform/main.tf` locals:

```hcl
locals {
  # Available versions
  stage_template_versions = {
    "v1.0.0" = "templates/stage-templates/v1.0.0/deploy-stage.yaml"
    "v1.1.0" = "templates/stage-templates/v1.1.0/deploy-stage.yaml"  # Add new version
  }
}
```

#### 6. Validate

```bash
./promotion/scripts/validate.sh v1.1.0
```

#### 7. Git Workflow

```bash
# Create feature branch
git checkout -b template/stage-v1.1.0

# Add new version
git add templates/${TEMPLATE_TYPE}/${NEW_VERSION}/

# Commit
git commit -m "feat: Add stage template v1.1.0

- Added health check verification
- Improved error handling
- Updated timeouts

Closes #123"

# Tag the version
git tag -a stage-template-v1.1.0 -m "Stage Template v1.1.0"

# Push
git push origin template/stage-v1.1.0
git push origin stage-template-v1.1.0
```

## Breaking Changes

### Definition

A breaking change is any modification that:
- Requires pipeline updates to continue functioning
- Changes expected behavior in incompatible ways
- Removes functionality that pipelines depend on

### Handling Breaking Changes

#### 1. Increment MAJOR Version

```
v1.5.3 → v2.0.0
```

#### 2. Document Thoroughly

In `metadata.yaml`:

```yaml
breaking_changes: true
migration_guide: |
  ## Upgrading from v1.x to v2.0
  
  ### Breaking Changes
  
  1. **Renamed Input Variable**
     - Old: `env`
     - New: `environment`
     - Reason: Better clarity and consistency
     
     Migration:
     ```yaml
     # Before (v1.x)
     templateInputs:
       env: prod
     
     # After (v2.0)
     templateInputs:
       environment: prod
     ```
  
  2. **Removed Feature**
     - Removed: `legacy_mode` flag
     - Reason: No longer needed
     
     Migration:
     - Simply remove the flag from your pipeline
  
  ### Automated Migration
  
  Run this script to update pipelines:
  ```bash
  ./scripts/migrate-to-v2.sh
  ```
```

#### 3. Provide Migration Path

**Option A: Automated Migration Script**

```bash
#!/bin/bash
# migrate-to-v2.sh

# Find all pipelines using v1.x
# Update inputs according to breaking changes
# Test updated pipelines
```

**Option B: Parallel Version Support**

Keep both versions available:
- v1.x for existing pipelines
- v2.0 for new pipelines
- Gradual migration over time

#### 4. Communicate Widely

- Send announcement email
- Update documentation
- Add banner in Harness UI (if possible)
- Discuss in team meetings
- Post in Slack channels

### Breaking Change Checklist

Before releasing a breaking change:

- [ ] Version number incremented to next MAJOR
- [ ] All breaking changes documented
- [ ] Migration guide provided
- [ ] Automated migration script created (if possible)
- [ ] Backward compatibility period defined
- [ ] Deprecation timeline announced
- [ ] Stakeholders notified
- [ ] Documentation updated
- [ ] Training materials prepared

## Version Deprecation

### When to Deprecate

Deprecate a version when:
- New MAJOR version released
- Security vulnerability discovered
- No longer maintained
- Superseded by better alternative

### Deprecation Process

#### 1. Mark as Deprecated

Update `metadata.yaml`:

```yaml
status: "deprecated"
deprecated_date: "2026-05-01"
removal_date: "2026-07-01"  # 60 days later

deprecation_reason: |
  This version is deprecated in favor of v2.0.0 which includes:
  - Improved security
  - Better performance
  - Enhanced features
  
  Please migrate to v2.0.0 by 2026-07-01.

migration:
  target_version: "v2.0.0"
  migration_guide_url: "https://docs.example.com/migrate-v2"
  automated_migration: true
  migration_script: "./scripts/migrate-to-v2.sh"
```

#### 2. Update Promotion Config

Edit `promotion/promotion-config.yaml`:

```yaml
template_versions:
  stage_template:
    current: v2.0.0  # Point to new version
    available:
      - version: v1.0.0
        status: deprecated
        deprecation_date: "2026-05-01"
        removal_date: "2026-07-01"
      - version: v2.0.0
        status: stable
```

#### 3. Notify Users

Send notifications:

```
Subject: [ACTION REQUIRED] Stage Template v1.0.0 Deprecated

Dear Team,

Stage Template v1.0.0 has been deprecated and will be removed on 2026-07-01.

Action Required:
- Upgrade pipelines to v2.0.0 by 2026-07-01
- Follow migration guide: [link]
- Run migration script: ./scripts/migrate-to-v2.sh

Questions? Contact platform-team@example.com
```

#### 4. Monitor Usage

Track which pipelines still use deprecated version:

```bash
# Query Harness API or check Terraform state
terraform state list | grep "v1.0.0"
```

#### 5. Remove Version

After removal date:

```bash
# Move to archive
mkdir -p templates/archived/stage-templates/
mv templates/stage-templates/v1.0.0 \
   templates/archived/stage-templates/

# Update git
git add templates/
git commit -m "chore: Archive deprecated template v1.0.0"

# Update Terraform
# Remove from locals in main.tf

# Tag the removal
git tag -a stage-template-v1.0.0-removed \
        -m "Removed deprecated v1.0.0"
```

### Deprecation Timeline

**Recommended Timeline**:

```
Day 0:   Announce deprecation
Day 7:   Send first reminder
Day 14:  Send second reminder
Day 30:  Send final warning
Day 45:  Begin contacting stragglers
Day 60:  Remove version
```

## Best Practices

### Do's ✅

1. **Use Semantic Versioning consistently**
   - Follow MAJOR.MINOR.PATCH rules
   - Document version decisions

2. **Keep detailed changelogs**
   - Document all changes
   - Explain reasoning
   - Include examples

3. **Test thoroughly before promoting**
   - Validate in dev
   - Test all use cases
   - Check backward compatibility

4. **Communicate changes widely**
   - Announce new versions
   - Explain benefits
   - Provide migration support

5. **Maintain multiple versions**
   - Support parallel versions
   - Allow gradual migration
   - Don't force upgrades

6. **Tag versions in Git**
   - Create annotated tags
   - Push tags to remote
   - Use consistent naming

### Don'ts ❌

1. **Don't reuse version numbers**
   - Never overwrite existing versions
   - Create new version instead

2. **Don't make surprise breaking changes**
   - Always increment MAJOR version
   - Provide migration guide
   - Give advance notice

3. **Don't remove versions immediately**
   - Allow deprecation period
   - Support old versions
   - Provide migration path

4. **Don't skip validation**
   - Always run validation script
   - Test in non-prod first
   - Verify backward compatibility

5. **Don't version without changelog**
   - Always document changes
   - Explain what and why
   - Include migration notes

## Examples

### Example 1: Adding a Feature

**Change**: Add optional notification step

**Version**: v1.4.0 → v1.5.0 (MINOR)

**Reasoning**:
- New functionality (notification)
- Backward compatible (optional)
- No breaking changes

**Metadata**:
```yaml
version: "1.5.0"
changelog: |
  - Added optional notification step after deployment
  - Notifications sent to Slack, email, or PagerDuty
  - Configurable via new 'notification_config' input (optional)
breaking_changes: false
```

### Example 2: Fixing a Bug

**Change**: Fix incorrect timeout value

**Version**: v1.4.5 → v1.4.6 (PATCH)

**Reasoning**:
- Bug fix only
- No new functionality
- No breaking changes

**Metadata**:
```yaml
version: "1.4.6"
changelog: |
  - Fixed timeout value in verification step (was 5m, now 10m)
  - Corrected error message formatting
breaking_changes: false
```

### Example 3: Breaking Change

**Change**: Rename required input from 'env' to 'environment'

**Version**: v1.9.3 → v2.0.0 (MAJOR)

**Reasoning**:
- Breaking change (required input renamed)
- Requires pipeline updates
- Not backward compatible

**Metadata**:
```yaml
version: "2.0.0"
changelog: |
  - BREAKING: Renamed input 'env' to 'environment' for clarity
  - BREAKING: Removed deprecated 'legacy_mode' flag
  - Added comprehensive error messages
  - Improved rollback reliability
breaking_changes: true
migration_guide: |
  ## Upgrading to v2.0.0
  
  ### 1. Rename 'env' to 'environment'
  
  Before:
  ```yaml
  templateInputs:
    env: prod
  ```
  
  After:
  ```yaml
  templateInputs:
    environment: prod
  ```
  
  ### 2. Remove 'legacy_mode'
  
  Simply delete this input from your pipeline.
  
  ### Automated Migration
  
  Run: ./scripts/migrate-to-v2.sh <pipeline-id>
```

## FAQ

**Q: Can I skip versions?**  
A: Yes, you can skip MINOR and PATCH versions (e.g., v1.0.0 → v1.5.0), but document the changes clearly.

**Q: What if I discover a bug in an old version?**  
A: Create a new PATCH version for that MAJOR.MINOR line (e.g., v1.4.6) if it's still supported.

**Q: How many versions should I maintain?**  
A: Typically maintain current MAJOR version + previous MAJOR version during transition period.

**Q: When can I delete old versions?**  
A: After deprecation period (60 days) + verification that no pipelines use it.

**Q: Should I version templates independently?**  
A: Yes, each template (stage, pipeline) has its own version lifecycle.

## Additional Resources

- [Semantic Versioning 2.0.0](https://semver.org/)
- [Promotion Guide](PROMOTION_GUIDE.md)
- [Project README](../README.md)
