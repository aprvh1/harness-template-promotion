# Template Promotion System - AI Assistant Context

This file provides comprehensive context for AI assistants working on this project.

---

## Project Overview

**Purpose**: Automate the lifecycle management of Harness templates through a multi-tier promotion system with validation, version control, and Infrastructure as Code (IaCM) deployment.

**Core Problem Solved**: Managing template evolution from development (v1) → production tiers (tier-1 through tier-5) → stable, with dependency tracking, validation, and automated deployment to Harness.

**Technology Stack**:
- Python 3.13+ plugin (extraction, validation, promotion logic)
- Harness CI/CD (orchestration, Docker plugin execution)
- Git (version control for template files)
- Terraform/IaCM (template deployment to Harness)
- GitHub (PR creation, code review)

---

## System Architecture

### Component Flow

```
┌──────────────────────────────────────────────────────────────┐
│                    CI/CD Pipeline (Harness)                  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Extract Template(s)                                      │
│     Plugin: Extracts from execution (single or tree mode)    │
│     Output: templates/{type}/{id}/v1.yaml                   │
│                                                              │
│  2. Promote Through Tiers                                   │
│     Plugin: Promotes tier-1 → tier-2 → ... → tier-5        │
│     Output: templates/{type}/{id}/tier-N.yaml               │
│                                                              │
│  3. Mark Stable                                             │
│     Plugin: Creates stable.yaml from chosen tier            │
│     Output: templates/{type}/{id}/stable.yaml               │
│                                                              │
│  4. Commit & PR                                             │
│     Git: Commits templates/ + versions.yaml                 │
│                                                              │
│  5. Review & Merge                                          │
│     Human: Reviews changes in PR                            │
│                                                              │
│  6. Deploy via IaCM                                         │
│     Terraform: Deploys all versions to Harness              │
│     Marks stable.yaml with is_stable=true                   │
└──────────────────────────────────────────────────────────────┘
```

### Repository Structure

```
template-promotion/
├── template-promotion-plugin/        # Python plugin (core logic)
│   ├── src/
│   │   ├── main.py                  # Entry point
│   │   ├── config.py                # Configuration (Pydantic)
│   │   ├── logic.py                 # Business logic (1500+ lines)
│   │   ├── utils.py                 # Utilities
│   │   └── harness_api/             # API client wrapper
│   ├── Dockerfile                   # Plugin container image
│   └── requirements.txt
│
├── templates/                        # Template files (Git-tracked)
│   ├── step/{id}/{version}.yaml
│   ├── stepgroup/{id}/{version}.yaml
│   ├── stage/{id}/{version}.yaml
│   └── pipeline/{id}/{version}.yaml
│
├── terraform/                        # IaCM configuration
│   ├── control-workspace/           # Creates IaCM workspaces
│   └── template-workspace/          # Deploys templates (this runs in each workspace)
│       └── main.tf                  # Key: line 37 - is_stable detection
│
├── testing/                          # Local testing environment
│   ├── test_ideal_flow.py          # Main end-to-end test
│   ├── test_tree_validation.py     # Tree extraction tests
│   ├── test_invalid_promotions.py  # Validation tests
│   ├── test_edge_cases.py          # Boundary condition tests
│   └── scripts/                     # Component tests
│
├── versions.yaml                     # Version tracking (Git-tracked)
├── SETUP.md                          # Setup guide
├── CLAUDE.md                         # This file
└── README.md                         # User documentation
```

---

## Key Technical Decisions

### 1. Terraform Controls Stable Marking (NOT Python Plugin)

**Decision**: Plugin creates `stable.yaml` file, Terraform marks it as stable in Harness.

**Why**:
- User wants full control over which tier becomes stable
- Any tier (tier-1, tier-3, tier-5) can be marked stable
- Terraform provides declarative control: `is_stable = trimsuffix(filename, ".yaml") == "stable"`
- Avoids API calls from plugin for state changes

**Implementation**:
- Plugin: Creates `stable.yaml` from chosen source tier
- Plugin: Removes version labels from child template references
- Terraform: Detects `stable.yaml` and sets `is_stable = true`

**Code Location**: 
- Plugin: `logic.py:1326-1332` (removed API call)
- Terraform: `terraform/template-workspace/main.tf:37-38`

---

### 2. Flexible Stable Selection

**Decision**: User chooses which tier to mark stable, not hardcoded to tier-5.

**Why**:
- Different templates have different validation needs
- Fast-track: tier-1 → stable (for urgent fixes)
- Standard: tier-5 → stable (full validation)
- Custom: tier-3 → stable (mid-point)

**Implementation**:
```yaml
# Fast-track
SOURCE_VERSION: tier-1
TO_TIER: stable

# Standard
SOURCE_VERSION: tier-5
TO_TIER: stable

# Auto-detect highest tier
SOURCE_VERSION: ""  # Leave empty
TO_TIER: stable
```

**Terraform Change**: Changed from `== "tier-5"` to `== "stable"` to support any tier.

---

### 3. Tree Extraction vs Single Extraction

**Decision**: Support both modes with different use cases.

**Single Mode** (`mode=single`):
- Extract one template
- Promote one template
- Fast, targeted operations

**Tree Mode** (`mode=tree`):
- Extract template + all dependencies recursively
- Discover nested references (Stage → StepGroup → Step)
- Promote entire dependency tree together
- Maintain version consistency across related templates

**Why Both**:
- Single mode: Quick iterations, individual fixes
- Tree mode: Bulk operations, consistent versioning, dependency validation

**Code Location**: `logic.py:_extract_tree_templates()`, `logic.py:_promote_tree_templates()`

---

### 4. 4-Level Validation System

**Decision**: Run 4 independent validation levels for template correctness.

**Levels**:
1. **Pipeline Reference**: Template found in execution pipeline YAML
2. **Structure Match**: Template spec matches execution structure
3. **Content Hash**: Item-by-item deep comparison
4. **Script Content**: Fuzzy matching for script blocks (90% similarity)

**Why**:
- Level 1: Confirms template was actually used
- Level 2: Validates high-level structure
- Level 3: Ensures exact content match
- Level 4: Handles script formatting differences (whitespace, comments)

**Code Location**: `logic.py:_validate_template_match()`

---

### 5. Strict Promotion Validation Rules

**Decision**: Enforce strict rules with explicit bypass flags.

**Rules Enforced**:
1. **Semantic versions must go to tier-1 first** (v1/v2 → tier-1 only)
2. **Block backwards promotion** (tier-2 → tier-1 NOT allowed)
3. **Tier skip requires flag** (tier-1 → tier-5 requires `TIER_SKIP=true`)
4. **Same-tier allowed as idempotent** (tier-1 → tier-1 with warning)

**Why**:
- Prevents accidental promotion mistakes
- Enforces intended workflow (sequential tier progression)
- Allows controlled tier skipping when needed
- Rollback from stable always allowed (stable → tier-N)

**Code Location**: `logic.py:931-1003` (`_validate_promotion_rules()`)

**Fixed Bug**: Originally only checked adjacent tiers, now checks ANY gap > 1.

---

### 6. Template Type Determination

**Decision**: Automatically determine template type (step/stepgroup/stage/pipeline).

**Why**:
- Previous bug: Hardcoded `template_type = "stage"`, causing all templates to save to `templates/stage/`
- Fix: Created `_determine_template_type()` helper
- Checks: versions.yaml → local directories → Harness API

**Importance**: Critical for tree extraction where different types must be saved to correct directories.

**Code Location**: `logic.py:_determine_template_type()`

---

### 7. Child Template Version Removal for Stable

**Decision**: When promoting to stable, remove `versionLabel` from child template references.

**Why**:
- Stable templates should reference other stable templates
- Removes explicit version: `templateRef: account.SG_Template` (no versionLabel)
- Child templates automatically use their stable version
- Simplifies template YAML

**Example**:
```yaml
# tier-5.yaml (HAS version label)
template:
  templateRef: account.SG_Template
  versionLabel: tier-5

# stable.yaml (NO version label)
template:
  templateRef: account.SG_Template
  # versionLabel removed - uses stable automatically
```

**Code Location**: `logic.py:remove_child_template_version_labels()`

---

## File Responsibilities

### template-promotion-plugin/src/logic.py (1500+ lines)

**Primary business logic file. Key functions:**

| Function | Lines | Purpose |
|----------|-------|---------|
| `execute_plugin()` | 130-167 | Main entry point, routes to extraction/promotion |
| `_extract_single_template()` | 190-292 | Extract one template from execution |
| `_extract_tree_templates()` | 294-477 | Extract template + dependencies recursively |
| `_discover_template_dependencies()` | 479-630 | Find child template references |
| `_validate_template_match()` | 632-773 | 4-level validation logic |
| `_promote_single_template()` | 775-930 | Promote one template between tiers |
| `_validate_promotion_rules()` | 931-1003 | **CRITICAL**: Promotion validation (recently fixed) |
| `_promote_tree_templates()` | 1005-1156 | Bulk promote entire dependency tree |
| `_promote_to_stable()` | 1158-1349 | Mark template as stable (Terraform-controlled) |
| `_determine_template_type()` | 1351-1420 | **CRITICAL**: Determine correct template type (recently added) |
| `remove_child_template_version_labels()` | 1422-1482 | Remove version labels for stable promotion |

### terraform/template-workspace/main.tf

**Deploys all versions of a single template to Harness.**

**Key Logic**:
- Line 28: Discover all `*.yaml` files in template directory
- Line 37: **CRITICAL**: `is_stable = trimsuffix(filename, ".yaml") == "stable"`
  - Detects `stable.yaml` file
  - Sets `is_stable = true` for that version
  - Changed from hardcoded `== "tier-5"` to flexible `== "stable"`
- Line 74-78: Tags templates with source version, managed_by, template_type

### versions.yaml

**Central tracking file for all template versions.**

**Structure**:
```yaml
labels:
  canary: {}    # Future use
  stable: {}    # Tracks stable templates

templates:
  step:
    Step_Name:
      versions:
        - version: v1
          scope: account
          org: default
          project: Twilio
          timestamp: "2026-04-20T10:30:00Z"
      tier_snapshots:
        tier-1: v1
        tier-2: tier-1
        stable: tier-5
  stepgroup: {}
  stage: {}
  pipeline: {}
```

**Purpose**:
- Track all versions for each template
- Store tier_snapshots (which version was promoted to create each tier)
- Record scope/org/project for deployment
- Used by Terraform to read template metadata

---

## Promotion System Deep Dive

### Promotion Flow Example

```
v1.yaml (extracted from execution)
  ↓
  ↓ Promote to tier-1 (semantic version must go to tier-1 first)
  ↓
tier-1.yaml
  ↓
  ↓ Promote to tier-2 (sequential, no skip)
  ↓
tier-2.yaml
  ↓
  ↓ Promote to tier-5 (TIER_SKIP=true required, skips tier-3, tier-4)
  ↓
tier-5.yaml
  ↓
  ↓ Promote to stable (any tier can be source)
  ↓
stable.yaml → Terraform marks is_stable=true in Harness
```

### Validation Rules Table

| From | To | Allowed? | Requires | Notes |
|------|-----|----------|----------|-------|
| v1/v2 | tier-1 | ✅ Yes | - | Semantic versions MUST go to tier-1 first |
| v1 | tier-2+ | ❌ No | - | "Semantic version must promote to tier-1 first" |
| tier-N | tier-N+1 | ✅ Yes | - | Sequential promotion (normal flow) |
| tier-N | tier-N+2+ | ✅ Yes | `TIER_SKIP=true` | "Cannot skip N tier(s) without TIER_SKIP flag" |
| tier-N | tier-N | ⚠️ Warning | - | Allowed as idempotent (re-generates file) |
| tier-N | tier-M (M<N) | ❌ No | - | "Backwards promotion not allowed" |
| Any tier | stable | ✅ Yes | - | Any tier can be marked stable |
| stable | Any tier | ✅ Yes | - | Rollback always allowed |

### Error Messages

**Backwards Promotion**:
```
Backwards promotion not allowed: tier-2 → tier-1.
Use rollback feature if intentional downgrade needed.
```

**Semantic Version Skip**:
```
Semantic version v1 must promote to tier-1 first. Cannot skip directly to tier-2.
```

**Tier Skip Without Flag**:
```
Cannot skip 3 tier(s) without TIER_SKIP flag. Attempting to skip: tier-2, tier-3, tier-4.
Set TIER_SKIP=true to allow tier skipping.
```

---

## Recent Changes (Critical Context)

### Change 1: Validation Fixes (2026-04-20)

**Before**: 4 scenarios incorrectly allowed
**After**: All validation gaps fixed

**Fixes**:
1. ✅ Backwards promotion now blocked
2. ✅ Semantic versions must go to tier-1 first
3. ✅ Tier skip flag required for ANY gap > 1 (was only checking adjacent)
4. ✅ Same-tier changed from error to warning (idempotent)

**Impact**: All 24 tests now pass (was 20/24)

**Files Changed**: `logic.py:931-1003`

---

### Change 2: Removed Stable Marking API Call (2026-04-20)

**Before**: Plugin called `self.templates.mark_stable()` to mark template in Harness
**After**: Plugin only creates `stable.yaml`, Terraform marks stable

**Why**: User wants Terraform control for flexible tier selection

**Files Changed**: 
- `logic.py:1326-1332` (removed API call)
- `terraform/template-workspace/main.tf:37` (changed to `== "stable"`)

**Impact**: Any tier can now be marked stable (not hardcoded to tier-5)

---

### Change 3: Template Type Determination Fix (Previous Session)

**Before**: Hardcoded `template_type = "stage"` → all templates saved to `templates/stage/`
**After**: Created `_determine_template_type()` helper

**Impact**: Templates now save to correct directories (stage/, stepgroup/, step/)

**Files Changed**: `logic.py:1351-1420`

---

## Testing Approach

### Test Suite Structure

```
testing/
├── test_ideal_flow.py           # ✅ 5/5 PASSED - Complete lifecycle
├── test_tree_validation.py      # ✅ 5/5 PASSED - Tree extraction
├── test_invalid_promotions.py   # ✅ 8/8 PASSED - Invalid scenarios
├── test_edge_cases.py           # ✅ 6/6 PASSED - Boundary conditions
└── scripts/                     # Component-level tests
    ├── test_extraction_tree.py
    ├── test_promotion_tier.py
    └── test_combined_mode.py
```

**Total**: 24/24 tests passing

### Ideal Flow Test (Tree Mode)

**5 Phases**:
1. Extract tree (Stage_Template + SG_Template + Step)
2. Combined mode (extract + promote all to tier-1)
3. Promote root to tier-2
4. Skip tiers (tier-2 → tier-5 with skip flag)
5. Promote to stable

**Key Validations**:
- ✅ Tree extraction discovers all 3 templates
- ✅ Templates saved to correct type directories (CRITICAL)
- ✅ 4-level validation runs for each template
- ✅ Child template references updated correctly
- ✅ Tier skip logic works with flag
- ✅ Sequential promotion works
- ✅ Stable promotion removes version labels

### Running Tests Locally

```bash
cd testing
source venv/bin/activate

# Run all tests
python test_ideal_flow.py
python test_tree_validation.py
python test_invalid_promotions.py
python test_edge_cases.py

# Expected: 24/24 PASSED
```

**Requirements**:
- Python 3.13+
- Valid Harness API key in `config/test.env`
- Valid execution URL in `config/extraction.env`
- Local harness-python-api-sdk installed

---

## Common Patterns and Conventions

### Configuration Management

**Uses Pydantic Settings**:
```python
from pydantic_settings import BaseSettings

class PluginConfig(BaseSettings):
    api_key: str = Field(..., alias="PLUGIN_API_KEY")
    account_id: str = Field(..., alias="PLUGIN_ACCOUNT_ID")
    # All config from environment variables with PLUGIN_ prefix
```

**Why**: Type safety, validation, clear defaults

### Error Handling

**Pattern**: Return tuples with success status and message
```python
def _validate_promotion_rules(...) -> tuple[bool, str]:
    if error_condition:
        return False, "Error message with context"
    return True, ""
```

**Why**: Allows caller to decide how to handle errors (log, raise, continue)

### Template Type Detection

**Priority Order**:
1. Check versions.yaml (existing templates)
2. Check local template directories
3. Fetch from Harness API
4. Default to "stage" (fallback)

**Why**: Performance (cached data first) + accuracy (API as fallback)

### Child Template Reference Format

**Standard Format**:
```yaml
template:
  templateRef: account.Template_Name  # Account-level
  templateRef: org.Template_Name      # Org-level
  templateRef: Template_Name          # Project-level
  versionLabel: tier-1                # Optional (removed for stable)
```

**Detection Pattern**: `(account|org)\.[\w_]+` or standalone identifier

---

## Known Limitations and Edge Cases

### 1. Same-Tier Promotion
**Behavior**: Allowed as idempotent operation with warning
**Why**: Re-generating same tier may be needed for template updates
**Log**: "Same-tier promotion detected: no-op operation"

### 2. Rollback from Stable
**Behavior**: Always allowed (stable → tier-N)
**Why**: Emergency rollback may be needed
**Bypass**: Skips validation rules for stable source

### 3. Tier-0 and Tier-6+
**Behavior**: Blocked with validation error
**Why**: Only tiers 1-5 are valid
**Error**: "Invalid tier number: 0. Must be 1-5."

### 4. Missing Source File
**Behavior**: Fails with clear error
**Why**: Cannot promote if source doesn't exist
**Error**: "Source template file not found: templates/stage/Name/tier-1.yaml"

### 5. Template Not Found in Execution
**Behavior**: Level 1 validation fails
**Why**: Template may not have been used in execution
**Log**: "⚠️  Level 1: Template not found in execution pipeline (expected for child templates)"

### 6. Dependency Discovery Depth
**Behavior**: Recursively discovers all depths
**Implementation**: Uses visited set to avoid circular references
**Example**: Stage (depth 0) → StepGroup (depth 1) → Step (depth 2)

---

## Integration Points

### Harness API
**Used For**:
- Fetching pipeline execution YAML
- Fetching template definitions
- (NOT USED) Marking templates as stable (controlled by Terraform)

**Authentication**: PAT token with `core_template_view`, `core_template_edit`, `core_pipeline_view`

**Endpoint**: `https://app.harness.io/gateway`

### GitHub
**Used For**:
- Version control for template files
- Pull request creation (via `gh` CLI)
- Code review workflow

**Authentication**: GitHub PAT token

**Branch Strategy**: Feature branches → PR → main branch

### Terraform/IaCM
**Used For**:
- Creating IaCM workspaces (control-workspace)
- Deploying all template versions to Harness (template-workspace)
- Marking stable versions with `is_stable = true`

**Webhook**: Triggers on `templates/**/*.yaml` changes in main branch

---

## Quick Reference

### Environment Variables

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

### Common Commands

**Extract Template Tree**:
```yaml
TEMPLATE_ID: Stage_Template
EXECUTION_URL: https://app.harness.io/.../executions/abc/pipeline
PROJECT_ID: Twilio
MODE: tree
SOURCE_VERSION: v1
```

**Promote to Next Tier**:
```yaml
TEMPLATE_ID: Stage_Template
SOURCE_VERSION: tier-1
TO_TIER: 2
MODE: single
```

**Mark as Stable**:
```yaml
TEMPLATE_ID: Stage_Template
SOURCE_VERSION: tier-5  # Or any tier
TO_TIER: stable
```

**Bulk Promotion (Tree)**:
```yaml
TEMPLATE_ID: Stage_Template
SOURCE_VERSION: tier-1
TO_TIER: 2
MODE: tree
```

---

## Troubleshooting Guide for AI Assistants

### Issue: "Template not found in execution"
**Check**: 
- Is execution URL correct?
- Is template actually used in that execution?
- Is template ID exact match (case-sensitive)?

### Issue: "Backwards promotion not allowed"
**Expected**: This is correct validation behavior
**Solution**: Use rollback feature if intentional

### Issue: "Cannot skip N tier(s) without TIER_SKIP flag"
**Expected**: This is correct validation behavior
**Solution**: Set `PLUGIN_TIER_SKIP=true` or promote sequentially

### Issue: "Templates all saving to stage/ directory"
**Likely Cause**: Using old version before template type determination fix
**Solution**: Verify `_determine_template_type()` exists in logic.py

### Issue: "Stable not marked in Harness"
**Check**:
- Is `stable.yaml` file created?
- Does Terraform have `is_stable = trimsuffix(filename, ".yaml") == "stable"`?
- Did IaCM pipeline run after PR merge?

### Issue: "Child templates have version labels in stable.yaml"
**Expected**: Version labels should be removed for stable
**Check**: `remove_child_template_version_labels()` function in logic.py

---

## Documentation Files

- **SETUP.md**: Complete setup guide (prerequisites, workflows, configuration)
- **README.md**: User documentation and plugin usage
- **CLAUDE.md**: This file (AI assistant context)
- **TERRAFORM_INTEGRATION.md**: Terraform/IaCM workflow details
- **TERRAFORM_CHANGES.md**: Explanation of Terraform changes
- **STABLE_MARKING_CHANGES.md**: Stable marking changes
- **VALIDATION_FIXES.md**: Validation rule fixes
- **FIXES_COMPLETE.md**: Summary of all fixes
- **testing/README.md**: Testing guide
- **testing/TEST_RESULTS.md**: Test results documentation
- **testing/SUMMARY.md**: Testing summary

---

## Contributing Guidelines

When making changes:

1. **Testing First**: Run local tests before committing
2. **Validation Rules**: Don't bypass validation without strong reason
3. **Terraform Changes**: Test IaCM deployment after template file changes
4. **Documentation**: Update SETUP.md and relevant docs
5. **Commit Messages**: Use conventional commits (feat:, fix:, docs:, test:)
6. **PR Description**: Link to changed files, explain "why" not just "what"

---

## Success Metrics

The system is working correctly when:

✅ Templates extracted with correct types (stage/, stepgroup/, step/)  
✅ 4-level validation passes for extracted templates  
✅ Tree extraction discovers all dependencies  
✅ Promotion validation blocks invalid transitions  
✅ Tier skip requires flag for gaps > 1  
✅ Stable.yaml created from chosen tier  
✅ Terraform marks stable versions with is_stable=true  
✅ Child template version labels removed for stable  
✅ versions.yaml tracks all promotions correctly  
✅ All 24 tests passing  

---

## Contact and Support

**Documentation**: See SETUP.md for detailed setup instructions  
**Issues**: Check troubleshooting sections in documentation  
**Testing**: Run local test suite to validate changes  
**Context**: This file (CLAUDE.md) for project understanding

---

*Last Updated*: 2026-04-20  
*Plugin Version*: 1.0 (validation fixes, stable marking changes)  
*Test Status*: 24/24 passing  
*Production Ready*: Yes
