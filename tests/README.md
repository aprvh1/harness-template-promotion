# Template Promotion Test Suite

Comprehensive tests for template extraction and promotion workflows.

## Quick Start

### Run Quick Tests
```bash
cd /Users/apoorvharsh/Downloads/template-promotion
./quick_test.sh
```

### Run Full Test Suite
```bash
cd tests
../venv/bin/python run_tests.py
```

## Test Scenarios

### 1. Extraction Mode Tests

#### Test: Extract Single Template
**Purpose**: Extract a single template without dependencies

**Command**:
```bash
python scripts/validate_and_extract.py \
  --execution-url "https://app.harness.io/.../exec-123" \
  --template-id "Stage_Template" \
  --project-id "Twilio" \
  --changelog "Test extraction" \
  --mode single
```

**Expected**:
- ✓ Stage_Template-v1.yaml created
- ✓ versions.yaml updated with version metadata
- ✓ Template type auto-detected (stage)

**Validation**:
- File exists: `templates/stage/Stage_Template-v1.yaml`
- YAML is valid
- versions.yaml contains Stage_Template entry

---

#### Test: Extract Template Tree (with Dependencies)
**Purpose**: Extract template with all child dependencies recursively

**Command**:
```bash
python scripts/validate_and_extract.py \
  --execution-url "https://app.harness.io/.../exec-123" \
  --template-id "Stage_Template" \
  --project-id "Twilio" \
  --changelog "Test tree extraction" \
  --mode tree
```

**Expected**:
- ✓ Stage_Template-v1.yaml created (root)
- ✓ SG_Template-v1.yaml created (child)
- ✓ Step-v1.yaml created (grandchild)
- ✓ All 3 templates validated against execution YAML

**Validation**:
- All dependency files exist
- Dependency relationships preserved
- Each template validated independently

---

#### Test: Extract with Sanitization
**Purpose**: Convert secrets, connectors, and variables to runtime inputs

**Command**:
```bash
python scripts/validate_and_extract.py \
  --execution-url "https://app.harness.io/.../exec-123" \
  --template-id "Stage_Template" \
  --project-id "Twilio" \
  --changelog "Test sanitization" \
  --mode single \
  --sanitize
```

**Expected**:
- ✓ connectorRef → `<+input>`
- ✓ secretRef → `<+input>`
- ✓ `<+secrets.getValue("...")>` → `<+input>`
- ✓ `<+project.variables.X>` → `<+input>`
- ✓ `<+env.variables.Y>` → `<+input>`

**What Gets Sanitized**:
- **Connectors**: All `connectorRef` fields
- **Secrets**: `secretRef`, `passwordRef`, `tokenRef`, etc.
- **Expressions**: `<+secrets.getValue(...)>`, `<+project.*>`, `<+org.*>`
- **Variables**: Environment-specific variable references

**Why Sanitization Matters**:
Templates should be portable across environments. Hardcoded connector IDs, secret names, and project variables are environment-specific and should be runtime inputs.

---

### 2. Promotion Mode Tests

#### Test: Sequential Promotion (tier-1 → tier-2)
**Purpose**: Promote template from tier-1 to tier-2

**Prerequisites**:
- Template extracted
- tier-1 deployed to Harness via Terraform

**Command**:
```bash
python scripts/validate_and_extract.py \
  --template-id "Stage_Template" \
  --to-tier 2 \
  --no-pr  # Skip PR creation for testing
```

**Expected**:
- ✓ Reads tier-1 from Harness API
- ✓ Creates `Stage_Template-tier-2.yaml` (copy of tier-1)
- ✓ Updates `versions.yaml` (tier_snapshots.tier-2 = v1)
- ✓ tier-1 unchanged

**Validation**:
- File exists: `templates/stage/Stage_Template-tier-2.yaml`
- Content matches tier-1
- versions.yaml updated with tier-2

---

#### Test: Tier Skip (tier-1 → tier-4)
**Purpose**: Skip intermediate tiers and promote directly

**Command**:
```bash
python scripts/validate_and_extract.py \
  --template-id "Stage_Template" \
  --to-tier 4 \
  --tier-skip \
  --no-pr
```

**Expected**:
- ✓ Finds highest tier below 4 (tier-1)
- ✓ Creates `Stage_Template-tier-4.yaml` (copy of tier-1)
- ✓ tier-2 and tier-3 NOT created (skipped)

**Validation**:
- File exists: `templates/stage/Stage_Template-tier-4.yaml`
- tier-2 and tier-3 files DO NOT exist
- versions.yaml shows tier-1 and tier-4 only

**Use Case**: Fast-track critical fixes to production tiers

---

#### Test: Idempotent Promotion
**Purpose**: Re-running same promotion should skip if unchanged

**Command**:
```bash
# Run promotion twice
python scripts/validate_and_extract.py --template-id Stage_Template --to-tier 2 --no-pr
python scripts/validate_and_extract.py --template-id Stage_Template --to-tier 2 --no-pr
```

**Expected**:
- First run: Creates tier-2
- Second run: Skips with message "tier-2 already matches tier-1"

**Validation**:
- Log contains "skipping"
- No duplicate commits
- tier-2 file unchanged

---

### 3. Error Scenario Tests

#### Test: Missing Source Tier
**Purpose**: Validate that promotion requires source tier to exist

**Command**:
```bash
# Try tier-1 → tier-3 when tier-2 missing
python scripts/validate_and_extract.py \
  --template-id "Stage_Template" \
  --to-tier 3 \
  --no-pr
```

**Expected**:
- ✗ Exit code 1
- ✗ Error: "Cannot promote to tier-3: tier-2 does not exist"

**Suggested Actions**:
1. Sequential: First promote to tier-2
2. Skip tiers: Use `--tier-skip` to copy from tier-1

---

#### Test: Semantic Version to tier > 1
**Purpose**: Block semantic versions from going directly to tier > 1

**Command**:
```bash
python scripts/validate_and_extract.py \
  --execution-url "..." \
  --template-id "Stage_Template" \
  --source-version "v1.5" \
  --to-tier 2
```

**Expected**:
- ✗ Exit code 1
- ✗ Error: "Semantic versions can ONLY be deployed to tier-1"

**Rationale**: Semantic versions are development versions. Only tier-1 can receive them. All other tiers get content via promotion from tier-1.

---

#### Test: Template Not Found
**Purpose**: Validate error handling for missing templates

**Command**:
```bash
python scripts/validate_and_extract.py \
  --template-id "NonExistent_Template" \
  --to-tier 2 \
  --no-pr
```

**Expected**:
- ✗ Exit code 1
- ✗ Error: "Template 'NonExistent_Template' not found in versions.yaml"

---

### 4. Integration Tests

#### Test: Full Workflow (Extract → Tier-5 Stable)
**Purpose**: Complete lifecycle from extraction to stable release

**Steps**:
1. Extract template with dependencies (tree mode)
2. Deploy tier-1 via Terraform
3. Promote tier-1 → tier-2
4. Deploy tier-2 via Terraform
5. Promote tier-2 → tier-3
6. Deploy tier-3 via Terraform
7. Promote tier-3 → tier-4
8. Deploy tier-4 via Terraform
9. Promote tier-4 → tier-5 (stable)
10. Deploy tier-5 via Terraform (is_stable = true)

**Validation**:
- All tier files exist (tier-1 through tier-5)
- versions.yaml shows all tiers
- tier-5 marked as stable in Terraform
- Dependency consistency maintained across all tiers

---

#### Test: Multi-Template Promotion
**Purpose**: Promote multiple dependent templates together

**Scenario**: Stage_Template depends on SG_Template depends on Step

**Steps**:
1. Extract all 3 templates (tree mode)
2. Deploy all to tier-1
3. Promote all to tier-2
4. Validate dependency consistency

**Validation**:
- All templates promoted successfully
- Dependency references remain valid
- No broken template references at tier-2

---

### 5. Sanitization Tests

#### Test: Sanitize Hardcoded Secrets
**Input**:
```yaml
template:
  spec:
    connectorRef: "my_connector_123"
    secretRef: "my_secret_456"
    script: echo <+secrets.getValue("test_secret")>
```

**Output**:
```yaml
template:
  spec:
    connectorRef: "<+input>"
    secretRef: "<+input>"
    script: echo <+input>
```

**Validation**:
- No hardcoded connector IDs
- No hardcoded secret names
- No secret expressions
- 3 runtime inputs created

---

#### Test: Sanitize Project Variables
**Input**:
```yaml
template:
  spec:
    environmentVariables:
      - name: REGION
        value: <+project.region>
      - name: ENV
        value: <+env.variables.environment>
```

**Output**:
```yaml
template:
  spec:
    environmentVariables:
      - name: REGION
        value: <+input>
      - name: ENV
        value: <+input>
```

**Validation**:
- No project-specific references
- No environment-specific references
- Variables converted to runtime inputs

---

## Running Tests

### Quick Test Script
```bash
./quick_test.sh
```

**What it tests**:
- ✓ Single template extraction
- ✓ Tree mode (dependencies)
- ✓ Sanitization
- ✓ Template type auto-detection
- ✓ File validation
- ✓ versions.yaml validation

**Duration**: ~2-3 minutes

---

### Full Test Suite
```bash
cd tests
../venv/bin/python run_tests.py
```

**What it tests**:
- All scenarios in `test_scenarios.yaml`
- Extraction tests (single, tree, sanitization)
- Promotion tests (sequential, tier-skip, idempotent)
- Error scenarios (missing tier, invalid input)
- Integration tests (full workflow, multi-template)
- Sanitization unit tests

**Duration**: ~10-15 minutes

**Output**: Test report saved to `test_report_YYYYMMDD_HHMMSS.txt`

---

## Test Data Requirements

### Harness Configuration
- **Account ID**: Set in `test.conf`
- **API Key**: Set in `test.conf`
- **Project**: Must have test templates
- **Execution**: Must be successful with templates

### Templates Required
For full test coverage, you need:
- **Stage Template**: With step-group reference
- **Step-Group Template**: With step reference
- **Step Template**: Leaf template

### Successful Execution
Must have a successful pipeline execution that uses the stage template, accessible via execution URL.

---

## Interpreting Results

### Success Indicators
```
✓ Test PASSED: Extract Single Template
✓ Test PASSED: Extract Template Tree
✓ Test PASSED: Sanitize Hardcoded Secrets
```

### Failure Indicators
```
✗ Test FAILED: Sequential Promotion
  Failed checks: file_exists, tier_snapshot_exists
```

### Warnings (Non-Fatal)
```
⚠ Step not directly referenced (may be child dependency)
⚠ Match percentage below 50%
```

---

## Common Issues

### Issue: "tier-1 does not exist"
**Cause**: Terraform hasn't deployed tier-1 yet  
**Solution**: Run `cd terraform && terraform apply`

### Issue: "Template not found in pipeline YAML"
**Cause**: Wrong template ID (using name instead of identifier)  
**Solution**: Check template identifier in Harness UI

### Issue: "No structural match found"
**Cause**: Template structure differs from execution YAML (expected)  
**Solution**: Non-fatal warning, extraction continues

### Issue: "harness_python_sdk not installed"
**Cause**: Using fallback HTTP client  
**Solution**: Informational only, script works without SDK

---

## Test Coverage

### Covered Scenarios
- ✅ Single template extraction
- ✅ Dependency tree extraction
- ✅ Template type auto-detection
- ✅ Two-phase validation
- ✅ Sanitization (secrets, connectors, variables)
- ✅ Sequential promotion
- ✅ Tier skip promotion
- ✅ Idempotency
- ✅ Error handling
- ✅ File creation
- ✅ versions.yaml updates

### Not Covered (Require External Systems)
- ⚠ Actual Terraform deployment
- ⚠ Actual Harness tier deployment
- ⚠ PR creation (GitHub/GitLab)
- ⚠ Multi-day promotion workflow
- ⚠ Cross-environment testing

---

## Best Practices

### 1. Always Sanitize for GitOps
```bash
--sanitize  # Convert secrets/connectors to runtime inputs
```

### 2. Use Tree Mode for Dependencies
```bash
--mode tree  # Extracts all child templates
```

### 3. Skip PR for Testing
```bash
--no-pr  # Faster testing without Git operations
```

### 4. Validate Before Promoting
- Check tier-1 deployed: `grep "tier-1" versions.yaml`
- Verify file exists: `ls templates/stage/*-tier-1.yaml`

### 5. Clean Test Artifacts
```bash
rm -rf tests/test_workspace  # Clean up after tests
```

---

## Extending Tests

### Adding New Test Scenario
Edit `tests/test_scenarios.yaml`:

```yaml
- id: "my_new_test"
  name: "My New Test"
  type: "extraction"
  command:
    template_id: "MyTemplate"
    mode: "single"
  expected:
    exit_code: 0
  validation:
    - check: "file_exists"
      file: "templates/step/MyTemplate-v1.yaml"
```

### Adding New Validation
Edit `tests/run_tests.py`:

```python
elif check_type == 'my_custom_check':
    # Implement validation logic
    validation_result['passed'] = check_something()
```

---

## Support

### Questions
- See [USAGE_GUIDE.md](../USAGE_GUIDE.md) for detailed usage
- See [FINAL_MODEL.md](../FINAL_MODEL.md) for architecture

### Issues
- Check logs in test output
- Verify Harness credentials
- Ensure execution URL is valid
- Check template identifiers

### Contributing
When adding new features, update:
1. `test_scenarios.yaml` with new test cases
2. `run_tests.py` with validation logic
3. `README.md` (this file) with documentation
