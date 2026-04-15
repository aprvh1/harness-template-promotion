# Final Template Tier Model - Complete Guide

## ✅ Model Summary

**Key Insight:** Projects have tier tags. Pipelines inherit tier from their project. Templates have multiple versions, one per tier.

## How It Works

### 1. Projects Tagged by Tier

Each project has a tier tag in Harness:

```yaml
Project: canary_project
  tags:
    tier: "tier1"    # Tier 1 project

Project: prod_project
  tags:
    tier: "tier5"    # Tier 5 project
```

**100 orgs × projects mapped to tiers:**
- **Tier 1:** 5 projects (canary)
- **Tier 2:** 15 projects (early adopters)
- **Tier 3:** 30 projects (wave 1)
- **Tier 4:** 30 projects (wave 2)
- **Tier 5:** 20 projects (conservative/stable)

### 2. Templates Have Multiple Versions

Each template in Harness has 5 versions:

```
Template: health_check
├─ tier-1    (tier 1 projects only)
├─ tier-2    (tier 1-2 projects)
├─ tier-3    (tier 1-3 projects)
├─ tier-4    (tier 1-4 projects)
└─ tier-5    (all projects - stable)
```

### 3. Pipelines Reference Version

Pipelines always reference a specific version:

```yaml
# Tier 1 project pipeline
pipeline:
  identifier: my_pipeline
  projectIdentifier: canary_project  # Has tier: "tier1" tag
  stages:
    - stage:
        template:
          templateRef: health_check
          versionLabel: tier-1    # Can only use tier-1
```

```yaml
# Tier 3 project pipeline
pipeline:
  identifier: my_pipeline
  projectIdentifier: prod_project  # Has tier: "tier3" tag
  stages:
    - stage:
        template:
          templateRef: health_check
          versionLabel: tier-2    # Can use tier-1, tier-2, or tier-3
```

### 4. Policy Enforcement

**Policy checks:** `project_tier >= template_tier`

**At pipeline save/run:**
- OPA policy reads `input.metadata.projectMetadata.tags.tier`
- Extracts tier from template `versionLabel: "tier-X"`
- Enforces: Project tier must be >= template tier

**Examples:**

| Project Tier | Template Version | Result |
|--------------|------------------|--------|
| tier1        | tier-1           | ✅ Allow (1 >= 1) |
| tier1        | tier-2           | ❌ Deny (1 < 2) |
| tier2        | tier-1           | ✅ Allow (2 >= 1) |
| tier2        | tier-2           | ✅ Allow (2 >= 2) |
| tier2        | tier-3           | ❌ Deny (2 < 3) |
| tier5        | tier-1,2,3,4,5   | ✅ Allow all |

## Template Promotion Workflow

### Week 0: Extract from Successful Execution

```bash
python3 scripts/validate_and_extract.py \
  --execution-url "https://app.harness.io/.../executions/exec-123" \
  --template-id health_check \
  --project-id test-project \
  --changelog "Added advanced health checks" \
  --mode tree
```

**Output:** `templates/step/health_check-v1.0.yaml`

### Week 1: Deploy tier-1 to Harness

Upload template to Harness with version `tier-1`:

```bash
# Via Harness UI:
# 1. Account Settings → Templates
# 2. Create "health_check" 
# 3. Version label: tier-1
# 4. Paste template YAML
# 5. Save

# Or via API:
curl -X POST "https://app.harness.io/template/api/templates" \
  -H "x-api-key: $HARNESS_API_KEY" \
  -d '{
    "identifier": "health_check",
    "versionLabel": "tier-1",
    "templateYaml": "..."
  }'
```

**Who can use:** Only tier 1 projects (5 projects)

**Pipelines created this week in tier 1 projects:**
```yaml
stages:
  - stage:
      template:
        templateRef: health_check
        versionLabel: tier-1    # Created with this reference
```

### Week 2: Create tier-2 Version

**Create NEW version `tier-2` in Harness** (copy from tier-1):

```bash
# Via Harness UI:
# 1. Go to health_check template
# 2. Click "New Version"
# 3. Version label: tier-2
# 4. Copy content from tier-1 (or make changes)
# 5. Save
```

**Who can use:** Tier 1 & 2 projects (20 projects total)

**Existing pipelines:** 
- Tier 1 pipelines still reference `versionLabel: tier-1` ✅ Still works
- No updates needed!

**New pipelines in tier 2 projects:**
```yaml
stages:
  - stage:
      template:
        templateRef: health_check
        versionLabel: tier-2    # Tier 2 projects can now use this
```

### Weeks 3-5: Continue Creating Versions

```
Week 3: Create tier-3 (50 projects total)
Week 4: Create tier-4 (80 projects total)
Week 5: Create tier-5 (100 projects - stable)
```

### Final State in Harness

After 5 weeks, template has 5 versions:

```
health_check
├─ tier-1 (old, but still valid for tier 1+ projects)
├─ tier-2 (old, but still valid for tier 2+ projects)
├─ tier-3 (old, but still valid for tier 3+ projects)
├─ tier-4 (old, but still valid for tier 4+ projects)
└─ tier-5 (stable - all projects can use)
```

**Old pipelines keep working** with their original `versionLabel` references!

### Optional: Mark tier-5 as Stable

In Harness, mark `tier-5` as the stable version so new pipelines default to it.

## Benefits of This Model

### ✅ No Pipeline Updates Needed

When you promote a template:
- Create new version `tier-2` in Harness
- Tier 2 projects can NOW create pipelines with `tier-2`
- **Existing pipelines with `tier-1` still work!**

### ✅ Progressive Rollout

- Week 1: 5 tier 1 projects test `tier-1`
- Week 2: 15 tier 2 projects can adopt `tier-2` (or keep using `tier-1`)
- Week 5: Everyone can use `tier-5` (stable)

### ✅ Project-Level Control

- Tag projects by tier once
- All pipelines in that project inherit the tier
- Easy to manage: 100 projects, not 1000s of pipelines

### ✅ Clear Version History

Each tier version is preserved:
- Audit trail of what was deployed when
- Can compare versions side-by-side
- Old pipelines keep working

## Deploy to Harness

### Step 1: Tag All Projects

Go through your 100 projects and tag them:

```bash
# Tier 1 projects (5 canary)
projects=("canary_1" "canary_2" "canary_3" "canary_4" "canary_5")
for project in "${projects[@]}"; do
  # Add tag via Harness UI or API
  # tags: { tier: "tier1" }
done

# Tier 2 projects (15 early adopters)
# tags: { tier: "tier2" }

# ... continue for tier 3, 4, 5
```

### Step 2: Upload OPA Policy

1. **Account Settings** → **Policies** → **Governance** → **+ New Policy**
2. **Name:** `Template Tier Control`
3. **Type:** `Pipeline`
4. Copy contents of [policies/template-tier-control.rego](policies/template-tier-control.rego)
5. **Save**

### Step 3: Create Policy Set

1. **Account Settings** → **Policies** → **Policy Sets** → **+ New Policy Set**
2. **Name:** `Template Tier Enforcement`
3. **Entity Type:** `Pipeline`
4. **Event:** `On Save` (enforces at pipeline creation time)
5. **Action:** `Error and Exit`
6. **Add Policy:** Select "Template Tier Control"
7. **Save**

**No policy data needed!**

### Step 4: Upload Templates with Tier Versions

For each template you want to roll out:

1. Create version `tier-1` (tier 1 projects only)
2. Wait 1 week, monitor
3. Create version `tier-2` (tier 1-2 projects)
4. Continue through `tier-5`

## Testing

### Test Case 1: Tier 1 Project Creating Pipeline ✅

**Project:** `canary_project` with `tier: "tier1"`

**Pipeline:**
```yaml
pipeline:
  projectIdentifier: canary_project
  stages:
    - stage:
        template:
          templateRef: health_check
          versionLabel: tier-1
```

**Save pipeline** → ✅ Success

### Test Case 2: Tier 1 Project Using tier-2 ❌

**Project:** `canary_project` with `tier: "tier1"`

**Pipeline:**
```yaml
pipeline:
  projectIdentifier: canary_project
  stages:
    - stage:
        template:
          templateRef: health_check
          versionLabel: tier-2    # Too new!
```

**Save pipeline** → ❌ Error:
```
❌ Template 'health_check' version 'tier-2' requires Tier 2 (Early Adopters) or higher. 
Your project (tier: tier1) is in Tier 1 (Canary). 
Wait for the template to be promoted to your tier.
```

### Test Case 3: Tier 3 Project Using tier-2 ✅

**Project:** `prod_project` with `tier: "tier3"`

**Pipeline:**
```yaml
pipeline:
  projectIdentifier: prod_project
  stages:
    - stage:
        template:
          templateRef: health_check
          versionLabel: tier-2    # Older version OK!
```

**Save pipeline** → ✅ Success (3 >= 2)

## Complete Example: Rolling Out New Template

### Scenario

You have a new `deploy_stage` template tested in a successful execution.

### Steps

**1. Extract template (Week 0)**

```bash
python3 scripts/validate_and_extract.py \
  --execution-url "https://app.harness.io/.../exec-abc123" \
  --template-id deploy_stage \
  --project-id test \
  --changelog "New deployment with health checks" \
  --mode tree
```

**2. Upload tier-1 version (Week 1)**

- Upload to Harness with `versionLabel: tier-1`
- Tier 1 projects can now create pipelines using it
- Monitor 5 canary projects for 1 week

**3. Create tier-2 version (Week 2)**

- In Harness: Create new version `tier-2` (copy from `tier-1`)
- Tier 1-2 projects (20 total) can now use it
- **Existing pipelines with `tier-1` keep working!**
- Monitor for 1 week

**4. Continue promotion (Weeks 3-5)**

- Week 3: Create `tier-3` (50 projects)
- Week 4: Create `tier-4` (80 projects)
- Week 5: Create `tier-5` (100 projects - stable)

**5. Final state**

Template has 5 versions in Harness:
- `tier-1`, `tier-2`, `tier-3`, `tier-4`, `tier-5`

Pipelines across 100 projects use different versions based on when they were created:
- Old tier 1 pipelines: `versionLabel: tier-1`
- Newer tier 2 pipelines: `versionLabel: tier-2`
- Latest pipelines: `versionLabel: tier-5`

**All continue working!** No updates needed.

## FAQ

### Q: Do I need to update existing pipelines when I promote?

**A:** No! When you create `tier-2` version:
- Tier 2 projects can NOW create new pipelines with `tier-2`
- Existing pipelines with `tier-1` keep working
- No updates needed

### Q: What if I want everyone to use the latest version?

**A:** Two options:
1. **Recommended:** Gradually update pipelines to reference newer versions
2. **Alternative:** Mark older versions as deprecated in Harness

### Q: Can tier 3 projects use tier-1 templates?

**A:** Yes! Higher tiers can use lower tier versions. Policy allows `project_tier >= template_tier`.

### Q: How many template versions will I have?

**A:** 5 versions per template (one per tier). After promotion to tier-5, you can optionally deprecate older tier versions.

### Q: What about stable references (no version label)?

**A:** Pipelines without `versionLabel` use the stable version in Harness. Mark your `tier-5` version as stable.

## Summary

**Simplified workflow:**
1. ✅ Tag 100 projects by tier (1-5) - **ONE TIME**
2. ✅ Extract template from successful execution
3. ✅ Upload to Harness with version `tier-1`
4. ✅ Each week, create next tier version: `tier-2`, `tier-3`, `tier-4`, `tier-5`
5. ✅ OPA policy enforces project tier >= template tier
6. ✅ Existing pipelines keep working - no updates needed!

**Key benefit:** Progressive rollout with zero pipeline updates. Projects gain access to new versions automatically as templates are promoted through tiers.
