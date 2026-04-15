# Enhanced Template Validation

## Overview

The template validation now includes **4 validation levels** to detect real content differences while ignoring environment-specific values.

---

## Validation Levels

### ✅ Level 1: Pipeline YAML Reference Check
**Purpose**: Is template referenced in pipeline?

**What it checks**:
- `templateRef` exists in pipeline YAML
- Correct template identifier
- Version label specified

**Example**:
```
✓ Stage_Template referenced 1 time(s) in pipeline YAML
```

---

### ✅ Level 2: Structure Validation (Keys)
**Purpose**: Does template structure appear in execution?

**What it checks**:
- Key paths from template exist in execution
- Hierarchical structure preserved
- Nested keys present

**Example**:
```
✓ Stage_Template structure validated (match: 90.0%)
```

**Limitation**: Only checks keys exist, not values!

---

### 🆕 Level 3: Hash-Based Content Validation
**Purpose**: Does template CONTENT match execution?

**What it checks**:
- Computes hash of template spec (root elements)
- Compares against execution sections
- Ignores secrets/connectors/expressions
- Catches real content differences

**How it works**:
```python
# Normalize template (ignore runtime values)
normalized_template = normalize(template_spec)

# Compute hash
template_hash = SHA256(normalized_template)

# Compare against all execution sections
for section in execution:
    section_hash = SHA256(section)
    if section_hash == template_hash:
        MATCH!
```

**Example Output**:
```
✓ Content hash matched (confidence: high)
```

**Or if different**:
```
⚠ Content hash mismatch (confidence: low, similarity: 45.2%)
```

**What gets hashed**:
```yaml
# These are included in hash:
type: "Custom"           # ✓ Critical field
steps:                   # ✓ Structure
  - step:
      type: "ShellScript"  # ✓ Critical field
      name: "Deploy"       # ✓ Content

# These are excluded:
connectorRef: "aws_123"  # ✗ Environment-specific
secretRef: "token_456"   # ✗ Environment-specific
value: <+pipeline.vars>  # ✗ Runtime expression
```

**Catches**:
- ✅ Different step types (ShellScript vs Http)
- ✅ Different script commands
- ✅ Different stage types
- ✅ Missing or extra steps

**Ignores**:
- ✅ Connector IDs (environment-specific)
- ✅ Secret names (environment-specific)
- ✅ Expressions (resolved at runtime)
- ✅ Timeout values (may vary)

---

### 🆕 Level 4: Script/Command Fuzzy Matching
**Purpose**: Do scripts/commands match?

**What it checks**:
- Extracts all scripts from template and execution
- Compares command keywords (not variables)
- Fuzzy matching with threshold
- Reports similarity percentage

**How it works**:
```python
# Extract scripts
template_scripts = ["kubectl apply -f deployment.yaml"]
execution_scripts = ["kubectl apply -f production.yaml"]

# Extract keywords (ignore variables/expressions)
template_keywords = {"kubectl", "apply", "deployment"}
execution_keywords = {"kubectl", "apply", "production"}

# Calculate similarity
common = {"kubectl", "apply"}
similarity = len(common) / len(total) = 2/4 = 50%
```

**Example Output**:
```
✓ Scripts validated (similarity: 85%)
```

**Or if different**:
```
⚠ Script validation warning: Scripts differ
  Lowest similarity: 30%
  Template: kubectl apply -f deployment.yaml
  Execution: terraform destroy --auto-approve
```

**What it catches**:
- ✅ Completely different commands (kubectl vs terraform)
- ✅ Different operations (apply vs destroy)
- ✅ Wrong scripts running

**What it ignores**:
- ✅ Variable names (`$REGION` vs `$ENV`)
- ✅ Expressions (`<+pipeline.variables.X>`)
- ✅ File paths if commands match
- ✅ Shell keywords (echo, set, export)

---

## Validation Flow

```
┌─────────────────────────────────────────────────────────┐
│ 1. Pipeline YAML Reference Check                        │
│    ✓ templateRef: "Stage_Template"                     │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│ 2. Structure Validation                                  │
│    ✓ Keys: spec.type, spec.spec.execution.steps        │
│    Match: 90%                                           │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│ 3. Hash-Based Content Validation                        │
│    Template Hash: a3f5c9d2...                           │
│    Execution Hash: a3f5c9d2... ← MATCH!                │
│    ✓ Content verified                                   │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│ 4. Script Fuzzy Matching                                 │
│    Template: "kubectl apply -f deployment.yaml"         │
│    Execution: "kubectl apply -f production.yaml"        │
│    Keywords: {kubectl, apply} similarity: 85%           │
│    ✓ Scripts validated                                  │
└─────────────────────────────────────────────────────────┘
```

---

## Real-World Examples

### Example 1: Correct Template (All Pass)

**Template**:
```yaml
template:
  spec:
    type: "Custom"
    spec:
      execution:
        steps:
          - step:
              type: "ShellScript"
              script: "kubectl apply -f app.yaml"
```

**Execution**:
```yaml
stages[0].stage:
  type: "Custom"
  spec:
    execution:
      steps:
        - step:
            type: "ShellScript"
            script: "kubectl apply -f app.yaml"
```

**Results**:
```
✓ Stage_Template referenced 1 time(s) in pipeline YAML
✓ Stage_Template structure validated (match: 95.0%)
✓ Content hash matched (confidence: high)
✓ Scripts validated (similarity: 100%)
```

**Confidence**: **HIGH** - All 4 levels pass!

---

### Example 2: Wrong Script Detected

**Template**:
```yaml
template:
  spec:
    steps:
      - step:
          script: "kubectl apply -f deployment.yaml"
```

**Execution**:
```yaml
stages[0].stage:
  spec:
    execution:
      steps:
        - step:
            script: "terraform destroy --auto-approve"
```

**Results**:
```
✓ Stage_Template referenced 1 time(s) in pipeline YAML
✓ Stage_Template structure validated (match: 90.0%)
⚠ Content hash mismatch (confidence: low, similarity: 45.2%)
⚠ Script validation warning: Scripts differ
  Lowest similarity: 20%
  Template: kubectl apply -f deployment.yaml
  Execution: terraform destroy --auto-approve
```

**Confidence**: **LOW** - Hash and script validation failed!

**Action**: ⚠️ **Review extracted template manually!**

---

### Example 3: Environment Differences (OK)

**Template (Dev)**:
```yaml
template:
  spec:
    connectorRef: "aws_dev_connector"
    script: "deploy.sh --env dev"
```

**Execution (Prod)**:
```yaml
stages[0].stage:
  spec:
    connectorRef: "aws_prod_connector"
    script: "deploy.sh --env prod"
```

**Results**:
```
✓ Stage_Template referenced 1 time(s) in pipeline YAML
✓ Stage_Template structure validated (match: 95.0%)
✓ Content hash matched (confidence: high)
✓ Scripts validated (similarity: 90%)
```

**Why hash matches**:
- `connectorRef` ignored (environment-specific)
- Script keywords match: `deploy.sh`
- Only env variable differs (ignored)

**Confidence**: **HIGH** - Template correct, environment differs (expected)

---

### Example 4: Child Template (Expected Low Match)

**Template**: `SG_Template` (child of Stage_Template)

**Results**:
```
⚠ SG_Template not directly referenced (may be child dependency)
⚠ SG_Template structure validation: No structural match found
⚠ Content hash mismatch (confidence: low, similarity: 0.0%)
⚠ Script validation warning: No scripts found
```

**Why this is OK**:
- Child templates are already expanded by parent
- Structure not visible in execution (flattened)
- Hash won't match (content transformed)

**Confidence**: **N/A** - Child template (expected behavior)

---

## Confidence Levels

### High Confidence ✅
**All 4 levels pass**:
- ✓ Reference found
- ✓ Structure match > 80%
- ✓ Hash matched
- ✓ Scripts match > 80%

**Action**: Extract with confidence!

---

### Medium Confidence ⚠️
**3 of 4 levels pass**:
- ✓ Reference found
- ✓ Structure match > 70%
- ⚠ Hash mismatch OR script mismatch
- Similarity > 60%

**Action**: Review extracted template, likely OK

---

### Low Confidence ❌
**2 or fewer levels pass**:
- ⚠ Structure match < 70%
- ⚠ Hash mismatch
- ⚠ Script mismatch
- Similarity < 50%

**Action**: ⚠️ **Manual review required!**

---

## Configuration

### Hash Validation
```python
# Ignores these keys
IGNORE_KEYS = {
    'secretRef',
    'connectorRef',
    'value',
    'uuid',
    'executionInputTemplate',
    'timeout'
}

# Replaces expressions with placeholder
EXPRESSION_PATTERN = r'<\+[^>]+>|\$\{[^}]+\}'
```

### Script Fuzzy Matching
```python
# Similarity threshold (50%)
threshold = 0.5

# Ignored shell keywords
SHELL_KEYWORDS = {
    'if', 'then', 'else', 'fi',
    'echo', 'set', 'export', 'env'
}
```

---

## Benefits

### ✅ Catches Real Issues

**Before (Structure Only)**:
```
✓ Structure validated (match: 100%)
# But script was completely different!
```

**After (4-Level Validation)**:
```
✓ Structure validated (match: 100%)
⚠ Content hash mismatch (confidence: low)
⚠ Script validation: Scripts differ
  Template: kubectl apply
  Execution: terraform destroy
```

---

### ✅ Ignores Environment Differences

**Different Connectors** (OK):
```
Template:  connectorRef: "aws_dev"
Execution: connectorRef: "aws_prod"
Result: ✓ Hash matched (ignored)
```

**Different Secrets** (OK):
```
Template:  secretRef: "token_dev"
Execution: secretRef: "token_prod"
Result: ✓ Hash matched (ignored)
```

---

### ✅ Provides Confidence Levels

**High Confidence**:
```
✓ All validations passed
Extract with confidence!
```

**Low Confidence**:
```
⚠ Hash and script validation failed
⚠ Review extracted template manually
```

---

## Usage

### Enable Enhanced Validation

Enhanced validation runs automatically during extraction:

```bash
python scripts/validate_and_extract.py \
  --execution-url "https://app.harness.io/.../exec-123" \
  --template-id "Stage_Template" \
  --project-id "Twilio" \
  --mode single
```

**Output includes all 4 levels**:
```
Validating Stage_Template reference in pipeline YAML...
✓ Stage_Template referenced 1 time(s) in pipeline YAML

Validating Stage_Template structure in compiled execution YAML...
✓ Stage_Template structure validated (match: 90.0%)

Validating Stage_Template content hash...
✓ Content hash matched (confidence: high)

Validating Stage_Template scripts/commands...
✓ Scripts validated (similarity: 85%)
```

---

## Troubleshooting

### "Content hash mismatch"

**Possible Causes**:
1. Wrong template version extracted
2. Template modified after execution
3. Template content differs from execution

**Action**:
- Check execution date vs template last modified
- Compare extracted YAML with expected content
- Verify template version matches execution

---

### "Script validation warning"

**Possible Causes**:
1. Different script content
2. Script modified after execution
3. Different template version

**Action**:
- Review script content in extracted template
- Compare with expected script
- Check if correct version was extracted

---

### "Hash matched but structure low"

**Possible Causes**:
1. Child template (expected)
2. Template deeply nested
3. Harness transformation

**Action**:
- If child template: Expected behavior
- If root template: Review structure

---

## Summary

### 4-Level Validation

| Level | Checks | Catches | Ignores |
|-------|--------|---------|---------|
| **1. Reference** | templateRef in pipeline | Missing reference | - |
| **2. Structure** | Keys exist in execution | Structure mismatch | Values |
| **3. Hash** | Content hash matches | Content differences | Secrets, connectors |
| **4. Scripts** | Commands similar | Wrong scripts | Variables, paths |

### Confidence

- **High**: All 4 pass → Extract confidently
- **Medium**: 3 pass → Likely OK, review recommended
- **Low**: ≤2 pass → Manual review required

### Benefits

✅ Detects real content differences  
✅ Ignores environment-specific values  
✅ Catches wrong scripts/commands  
✅ Provides confidence levels  
✅ Non-blocking (warnings only)

**Result**: You can trust extracted templates match execution!
