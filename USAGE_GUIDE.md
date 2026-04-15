# Template Management Usage Guide

The `validate_and_extract.py` script now supports two workflows:

## 1. EXTRACTION MODE (New Template)

Extract a template from a successful execution and optionally create tier-1.

### Basic Extraction (Single Template)
```bash
python3 scripts/validate_and_extract.py \
  --execution-url "https://app.harness.io/ng/account/ABC/module/cd/orgs/ORG/projects/PROJ/pipelines/test-pipeline/executions/exec-123" \
  --template-id health_check \
  --project-id test \
  --changelog "Added database health checks" \
  --mode single
```

**What it does:**
- Validates the execution
- Extracts the template YAML
- Saves to `templates/{type}/{identifier}-{version}.yaml`
- Updates `versions.yaml` with version metadata
- Auto-detects template type (step, stage, pipeline, step_group)

### Extract with Dependencies (Tree Mode)
```bash
python3 scripts/validate_and_extract.py \
  --execution-url "https://app.harness.io/ng/.../exec-123" \
  --template-id ci_pipeline \
  --project-id test \
  --changelog "Updated CI pipeline" \
  --mode tree
```

**What it does:**
- Recursively discovers all template dependencies
- Extracts all templates in the dependency tree
- Validates each template against execution YAML
- Preserves parent-child relationships

### Extract and Create Tier-1
```bash
python3 scripts/validate_and_extract.py \
  --execution-url "https://app.harness.io/ng/.../exec-123" \
  --template-id health_check \
  --project-id test \
  --changelog "Initial version" \
  --mode single \
  --to-tier 1 \
  --source-version v1.0
```

**What it does:**
- Extracts template (as above)
- Creates `templates/{type}/{identifier}-tier-1.yaml` (copy of extracted version)
- Updates `versions.yaml` with `tier_snapshots.tier-1 = v1.0`
- Opens PR with both files

**Note:** Semantic versions (`--source-version`) can ONLY go to tier-1.

---

## 2. PROMOTION MODE (Tier-to-Tier)

Promote an existing template from one tier to another.

### Sequential Promotion (tier-1 → tier-2)
```bash
python3 scripts/validate_and_extract.py \
  --template-id health_check \
  --to-tier 2
```

**What it does:**
- Auto-detects template type from `versions.yaml`
- Reads tier-1 content from Harness API
- Creates `templates/{type}/{identifier}-tier-2.yaml` (copy of tier-1)
- Updates `versions.yaml` with `tier_snapshots.tier-2 = {source_version}`
- Opens PR with changes

**Requirements:**
- Template must exist in `versions.yaml`
- tier-1 must exist (for tier-2 promotion)
- tier-N-1 must exist (for tier-N promotion, without --tier-skip)

### Tier Skip (tier-1 → tier-4)
```bash
python3 scripts/validate_and_extract.py \
  --template-id health_check \
  --to-tier 4 \
  --tier-skip
```

**What it does:**
- Finds highest existing tier below tier-4 (e.g., tier-1)
- Copies content from that tier to tier-4
- Skips creating tier-2 and tier-3
- Opens PR with tier-4 file

**Use case:** Fast-track a template to production tiers.

**Restrictions:**
- `--tier-skip` does NOT work with `--source-version`
- Can only skip when copying tier-to-tier
- Must have at least one lower tier to copy from

### Dry Run (No PR)
```bash
python3 scripts/validate_and_extract.py \
  --template-id health_check \
  --to-tier 2 \
  --no-pr
```

**What it does:**
- Performs all promotion steps
- Creates local files
- Does NOT create Git branch or PR
- Use for testing or manual PR creation

---

## Validation Rules

### Tier Progression (Without --tier-skip)
```
✅ tier-1 → tier-2  (tier-1 exists)
❌ tier-1 → tier-3  (tier-2 missing, use --tier-skip)
✅ tier-2 → tier-3  (tier-2 exists)
```

### Tier Skip (With --tier-skip)
```
✅ tier-1 → tier-4  (copies from tier-1)
✅ tier-2 → tier-5  (copies from tier-2)
❌ nothing → tier-3 (no lower tier exists)
```

### Semantic Version Rules
```
✅ v1.0 → tier-1  (semantic versions ONLY to tier-1)
❌ v1.0 → tier-2  (blocked, must go to tier-1 first)
❌ v1.0 → tier-3 --tier-skip  (tier-skip does not work with semantic versions)
```

### Idempotency
```bash
# Run promotion twice
python3 scripts/validate_and_extract.py --template-id health_check --to-tier 2

# First run: Creates tier-2
✓ Created tier-2 YAML
✓ Updated versions.yaml
✓ Created PR

# Second run: Skips (content already matches)
✓ tier-2 already matches tier-1, skipping
✅ No changes needed - target tier already up to date
```

---

## Workflow Examples

### Example 1: New Template v1.0
```bash
# Step 1: Test template in Harness, get execution URL
# Step 2: Extract and create tier-1
python3 scripts/validate_and_extract.py \
  --execution-url "https://app.harness.io/.../exec-123" \
  --template-id health_check \
  --project-id test \
  --changelog "Initial health check template" \
  --mode single \
  --to-tier 1 \
  --source-version v1.0

# Result: PR with health_check-v1.0.yaml and health_check-tier-1.yaml
# After merge: Terraform deploys tier-1 to Harness
```

### Example 2: Promote to tier-2
```bash
# Week later, ready for tier-2
python3 scripts/validate_and_extract.py \
  --template-id health_check \
  --to-tier 2

# Result: PR with health_check-tier-2.yaml
# After merge: Terraform deploys tier-2 to Harness
```

### Example 3: Update tier-1 with v1.1
```bash
# New version tested in Harness
python3 scripts/validate_and_extract.py \
  --execution-url "https://app.harness.io/.../exec-456" \
  --template-id health_check \
  --project-id test \
  --changelog "Enhanced health checks" \
  --mode single \
  --to-tier 1 \
  --source-version v1.1

# Result: PR with health_check-v1.1.yaml and UPDATED health_check-tier-1.yaml
# Note: tier-2 still has v1.0 content (unchanged)
```

### Example 4: Fast-track to tier-4
```bash
# Skip tier-2 and tier-3
python3 scripts/validate_and_extract.py \
  --template-id health_check \
  --to-tier 4 \
  --tier-skip

# Result: PR with health_check-tier-4.yaml (copy of tier-1)
# Note: tier-2 and tier-3 remain empty (not created)
```

### Example 5: Extract with Dependencies
```bash
# Extract pipeline with all stage/step templates
python3 scripts/validate_and_extract.py \
  --execution-url "https://app.harness.io/.../exec-789" \
  --template-id ci_pipeline \
  --project-id test \
  --changelog "CI pipeline with stages" \
  --mode tree

# Result: Extracts ci_pipeline, build_stage, test_stage, deploy_stage, etc.
# All templates saved with their semantic versions
```

---

## Key Features Preserved

### ✅ Recursive Dependency Extraction
The `--mode tree` functionality is fully preserved:
- Discovers all child templates recursively
- Validates each template in execution YAML
- Saves entire dependency tree locally

### ✅ Auto-Detection of Template Type
No need to specify `--template-type`:
- Reads template YAML from Harness
- Extracts `template.type` field
- Determines type automatically (step/stage/pipeline/step_group)

### ✅ Two-Phase Validation
Both validation phases still work:
1. **Pipeline YAML validation**: Checks template referenced
2. **Execution YAML validation**: Checks template structure appears in compiled output

---

## Error Messages

### Missing Source Tier
```
❌ Cannot promote to tier-3: tier-2 does not exist.

Options:
1. Sequential: First promote to tier-2
2. Skip tiers: Use --tier-skip to copy from lower tier
```

### Semantic Version to tier > 1
```
❌ Cannot create tier-3 directly from semantic version v1.5.
   Semantic versions can ONLY be deployed to tier-1.

   To get v1.5 to tier-3:
   1. Deploy to tier-1: --source-version v1.5 --to-tier 1
   2. Promote: --to-tier 3 (with --tier-skip if needed)
```

### Template Not Found
```
❌ Template 'health_check' not found in versions.yaml. 
   You may need to extract it first using --execution-url.
```

### No Lower Tier for Skip
```
❌ Cannot promote to tier-4: No lower tier exists to copy from. 
   Must create tier-1 first.
```

---

## File Structure After Operations

### After Extraction (v1.0)
```
templates/step/
  health_check-v1.0.yaml    # Extracted semantic version

versions.yaml:
  templates:
    step:
      health_check:
        versions:
          - version: v1.0
            created: '2026-04-13'
            changelog: 'Initial version'
```

### After Tier-1 Creation
```
templates/step/
  health_check-v1.0.yaml    # Original
  health_check-tier-1.yaml  # Tier version (v1.0 content)

versions.yaml:
  templates:
    step:
      health_check:
        tier_snapshots:
          tier-1: v1.0      # Tier-1 has v1.0 content
        versions:
          - version: v1.0
```

### After Promotion to Tier-2
```
templates/step/
  health_check-v1.0.yaml
  health_check-tier-1.yaml  # Unchanged
  health_check-tier-2.yaml  # NEW (v1.0 content)

versions.yaml:
  tier_snapshots:
    tier-1: v1.0
    tier-2: v1.0            # NEW
```

### After Updating Tier-1 to v1.1
```
templates/step/
  health_check-v1.0.yaml    # Original
  health_check-v1.1.yaml    # NEW semantic version
  health_check-tier-1.yaml  # UPDATED to v1.1 content
  health_check-tier-2.yaml  # Unchanged (still v1.0)

versions.yaml:
  tier_snapshots:
    tier-1: v1.1            # Changed
    tier-2: v1.0            # Unchanged
```

---

## Next Steps After PR Merge

1. **Review PR**: Check YAML content and versions.yaml changes
2. **Approve and Merge**: Merge to main branch
3. **Terraform Plan**: CI pipeline runs `terraform plan`
4. **Terraform Apply**: Deploys template versions to Harness
5. **Verify in Harness**: Check templates exist with correct versionLabel
6. **Test in Target Tier**: Use template in tier-appropriate project

---

## Tips

- **Always test in Harness first**: Get a successful execution before extraction
- **Use semantic versions for tier-1 only**: All other tiers get content via promotion
- **Sequential promotion is safer**: Default behavior, validates each tier exists
- **Use tier-skip for emergencies**: Fast-track critical fixes to production
- **Check idempotency**: Re-running same promotion is safe, will skip if unchanged
- **Review PR diffs carefully**: Ensure tier content matches expectations
