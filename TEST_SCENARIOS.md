# Test Scenarios for Harness Pipeline Runner

This document describes all test scenarios for `harness_pipeline_runner.sh` with `NO_PR=true`.

## Test Coverage

### ✅ Extraction Mode Tests

| # | Scenario | Env Vars | Expected Result |
|---|----------|----------|-----------------|
| 1 | Basic single extraction | `EXECUTION_URL`, `TEMPLATE_ID`, `PROJECT_ID`, `MODE=single` | Creates `v1.yaml` |
| 2 | Single with tier creation | `EXECUTION_URL`, `TEMPLATE_ID`, `PROJECT_ID`, `MODE=single`, `TO_TIER=1` | Creates `v1.yaml` + `tier-1.yaml` |
| 3 | Tree mode (dependencies) | `EXECUTION_URL`, `TEMPLATE_ID`, `PROJECT_ID`, `MODE=tree`, `TO_TIER=1` | Creates multiple templates with dependencies |
| 4 | With sanitization | `EXECUTION_URL`, `TEMPLATE_ID`, `PROJECT_ID`, `SANITIZE=true`, `TO_TIER=1` | Sanitizes secrets to runtime inputs |
| 5 | Custom source version | `EXECUTION_URL`, `TEMPLATE_ID`, `PROJECT_ID`, `SOURCE_VERSION=v2`, `TO_TIER=1` | Creates `v2.yaml` + `tier-1.yaml` |

### ✅ Promotion Mode Tests

| # | Scenario | Env Vars | Expected Result |
|---|----------|----------|-----------------|
| 6 | Sequential promotion | `TEMPLATE_ID`, `TO_TIER=2` (no `EXECUTION_URL`) | Creates `tier-2.yaml` from tier-1 |
| 7 | Tier skip promotion | `TEMPLATE_ID`, `TO_TIER=4`, `TIER_SKIP=true` | Creates `tier-4.yaml` from tier-1 (skips 2,3) |

### ✅ Error Handling Tests

| # | Scenario | Env Vars | Expected Result |
|---|----------|----------|-----------------|
| 8 | Missing TEMPLATE_ID | No `TEMPLATE_ID` | Error: Missing required variables |
| 9 | Invalid TO_TIER | `TO_TIER=10` | Error: Invalid TO_TIER (must be 1-5) |
| 10 | Invalid MODE | `MODE=invalid_mode` | Error: Invalid MODE (must be single/tree) |
| 11 | Boolean variations | `TIER_SKIP=1`, `TIER_SKIP=yes` | Both accepted and normalized |

## Running Tests

### Run All Tests
```bash
bash test_all_scenarios.sh
```

### Run Individual Test
```bash
# Test 1: Basic extraction
export HARNESS_API_KEY="pat.xxx..."
export HARNESS_ACCOUNT_ID="Pt_YA3aYQT6g6ZW7MZOMJw"
export TEMPLATE_ID="Stage_Template"
export EXECUTION_URL="https://app.harness.io/ng/.../executions/abc123"
export PROJECT_ID="Twilio"
export MODE="single"
export NO_PR="true"

bash scripts/harness_pipeline_runner.sh
```

### Harness Pipeline Test
```yaml
- step:
    identifier: test_extraction
    name: Test Extraction
    type: Run
    spec:
      shell: Bash
      envVariables:
        HARNESS_API_KEY: <+secrets.getValue("harness_api_key")>
        HARNESS_ACCOUNT_ID: <+account.identifier>
        TEMPLATE_ID: "Stage_Template"
        EXECUTION_URL: <+pipeline.variables.execution_url>
        PROJECT_ID: "Twilio"
        MODE: "single"
        TO_TIER: "1"
        NO_PR: "true"
      command: |
        pip3 install -r requirements.txt
        /bin/bash scripts/harness_pipeline_runner.sh
```

## Expected Files Created

### After Extraction (Test 1)
```
templates/
  stage/
    Stage_Template/
      v1.yaml          ← Semantic version
```

### After Extraction with Tier (Test 2)
```
templates/
  stage/
    Stage_Template/
      v1.yaml          ← Semantic version
      tier-1.yaml      ← Tier version (copy of v1)
```

### After Tree Extraction (Test 3)
```
templates/
  stage/
    Stage_Template/
      v1.yaml
      tier-1.yaml
  step-group/
    SG_Template/
      v1.yaml
      tier-1.yaml
  step/
    Step/
      v1.yaml
      tier-1.yaml
```

### After Promotion (Test 6)
```
templates/
  stage/
    Stage_Template/
      v1.yaml
      tier-1.yaml      ← Existing
      tier-2.yaml      ← NEW (copy of tier-1 from Harness)
```

### versions.yaml Structure
```yaml
templates:
  stage:
    Stage_Template:
      tier_snapshots:
        tier-1: v1      ← Which semantic version is at tier-1
        tier-2: v1      ← Which semantic version is at tier-2
      versions:
        - version: v1
          created: '2026-04-15'
          changelog: 'Initial version'
          scope: project
          created_from_execution: exec-123
```

## Test Output Examples

### Successful Extraction
```
================================================================
Harness Pipeline Runner for Template Extraction & Promotion
================================================================

[INFO] Working directory: /harness
[INFO] Mode: EXTRACTION (EXECUTION_URL is set)
[INFO] Using Python: python3
[INFO] Python version: 3.10
[INFO] Validating environment variables...
[SUCCESS] ✓ All required variables present and valid
[INFO] Building Python command...
[INFO] Command to execute:
  python3 scripts/validate_and_extract.py --template-id Stage_Template ...
[INFO] Configuration:
  Template ID: Stage_Template
  Project ID: Twilio
  Mode: single
  Create Tier: 1
================================================================
[INFO] Executing Python script...
================================================================

<extraction logs>

[SUCCESS] ✓ Script completed successfully!
```

### Successful Promotion
```
================================================================
[INFO] Mode: PROMOTION (EXECUTION_URL is not set)
[INFO] Configuration:
  Template ID: Stage_Template
  Target Tier: 2
================================================================
[INFO] Executing Python script...
================================================================

2026-04-15 - INFO - === PROMOTION MODE ===
2026-04-15 - INFO - Reading tier-1 from Harness API...
2026-04-15 - INFO -   ✓ Created tier-2.yaml
2026-04-15 - INFO - ✓ Updated versions.yaml

[SUCCESS] ✓ Script completed successfully!
```

### Error - Missing Variable
```
[INFO] Validating environment variables...
[ERROR] Missing required environment variables:
[ERROR]   - TEMPLATE_ID
[ERROR] 
[ERROR] For extraction mode, set: EXECUTION_URL, PROJECT_ID
[ERROR] For promotion mode, set: TO_TIER
```

### Error - Invalid Value
```
[INFO] Validating environment variables...
[ERROR] Invalid TO_TIER: '10'
[ERROR] Must be 1, 2, 3, 4, or 5
```

## Troubleshooting

### Test fails: "tier-1 does not exist"
**Cause:** Promotion requires tier-1 to exist in Harness (not just locally)

**Solution:**
1. Deploy tier-1 first: `cd terraform && terraform apply`
2. Then run promotion tests

### Test fails: "Module not found: harness_python_sdk"
**Cause:** Dependencies not installed

**Solution:**
```bash
pip3 install -r requirements.txt
```

### Test fails: Script execution error
**Cause:** Check individual test log

**Solution:**
```bash
# View test logs
cat test1.log  # For test 1
cat test2.log  # For test 2
# etc.
```

## CI/CD Integration

All tests use `NO_PR=true` which means:
- ✅ Files are created locally
- ✅ versions.yaml is updated
- ❌ No git commit
- ❌ No PR creation
- ❌ No git push

For full GitOps workflow, remove `NO_PR` or set it to `false`.

## Next Steps After Tests Pass

1. **Review generated files**
   ```bash
   ls -la templates/stage/Stage_Template/
   cat versions.yaml
   ```

2. **Deploy to Harness**
   ```bash
   cd terraform
   terraform plan
   terraform apply
   ```

3. **Test promotion in Harness**
   - Verify tier-1 exists in Harness UI
   - Run promotion pipeline
   - Verify tier-2 created

4. **Test OPA policy**
   - Create tier-1 project: `tags: {tier: "tier1"}`
   - Try using `versionLabel: tier-1` ✅
   - Try using `versionLabel: tier-2` ❌ (should be blocked)
