# Terraform IaCM Workspace Architecture

## Overview

This Terraform setup creates **one IaCM workspace per template**, with each workspace managing all versions of that specific template.

## Architecture

```
Control Workspace (terraform/control-workspace/)
  │
  ├─ Scans templates/ directory
  ├─ Creates IaCM workspaces (one per template)
  │
  └─ Each IaCM workspace uses template-workspace/ code
       │
       ├─ Reads all YAML files in template directory
       └─ Creates harness_platform_template resources
```

### Directory Structure

```
terraform/
├── control-workspace/        # Creates IaCM workspaces
│   ├── main.tf              # Scans templates and creates workspaces
│   ├── variables.tf         # Configuration variables
│   ├── outputs.tf           # Workspace information
│   └── terraform.tfvars.example
│
├── template-workspace/       # Code used by each IaCM workspace
│   ├── main.tf              # Creates template versions
│   ├── variables.tf         # Template-specific variables
│   └── outputs.tf           # Deployment information
│
└── (old files - can be archived)
    ├── main.tf              # Old monolithic setup
    ├── providers.tf
    ├── outputs.tf
    └── variables.tf
```

## How It Works

### 1. Control Workspace

**Location**: `terraform/control-workspace/`

**Purpose**: Creates and manages IaCM workspaces

**What it does**:
1. Scans `templates/` directory to find all templates
2. For each template directory (e.g., `templates/stage/Stage_Template/`):
   - Creates one IaCM workspace
   - Configures workspace to use `template-workspace/` code
   - Passes template-specific variables

**Example**: If you have:
```
templates/
├── stage/
│   ├── Stage_Template/
│   │   ├── v1.yaml
│   │   └── tier-1.yaml
│   └── deploy_stage/
│       ├── v1.0.yaml
│       └── tier-1.yaml
└── step/
    └── Step/
        ├── v1.yaml
        └── tier-1.yaml
```

**It creates 3 IaCM workspaces:**
- `stage_Stage_Template`
- `stage_deploy_stage`
- `step_Step`

### 2. Template Workspace

**Location**: `terraform/template-workspace/`

**Purpose**: Reusable Terraform code that runs in each IaCM workspace

**What it does**:
1. Takes `template_path` as input (e.g., `stage/Stage_Template`)
2. Reads all YAML files in that directory
3. Creates `harness_platform_template` resource for each version
4. Gets scope info from `versions.yaml`

**Example**: The `stage_Stage_Template` workspace:
- Reads `templates/stage/Stage_Template/v1.yaml`
- Reads `templates/stage/Stage_Template/tier-1.yaml`
- Creates 2 template versions in Harness:
  - `Stage_Template` version `v1`
  - `Stage_Template` version `tier-1`

## Setup Instructions

### Step 1: Configure Control Workspace

```bash
cd terraform/control-workspace

# Copy example config
cp terraform.tfvars.example terraform.tfvars

# Edit with your values
vim terraform.tfvars
```

**Required variables**:
- `harness_account_id` - Your Harness account ID
- `git_connector_ref` - Git connector for IaCM workspaces
- `repository_name` - Your git repository name
- `harness_connector_ref` - Harness connector for provider credentials

### Step 2: Initialize and Apply

```bash
# Set environment variables
export HARNESS_API_KEY="your-api-key"
export HARNESS_ACCOUNT_ID="your-account-id"

# Initialize Terraform
terraform init

# Review plan
terraform plan

# Apply (creates IaCM workspaces)
terraform apply
```

### Step 3: IaCM Workspaces Auto-Execute

Once created, each IaCM workspace will:
1. Pull code from `terraform/template-workspace/`
2. Execute with template-specific variables
3. Create template versions in Harness

## Benefits

### ✅ Isolation
- Each template has its own workspace
- Changes to one template don't affect others
- Independent state management

### ✅ Scalability
- Add new templates by creating directories
- No Terraform code changes needed
- Automatic workspace creation

### ✅ Clarity
- Easy to see which versions exist (check template directory)
- Clear ownership (one workspace per template)
- Simple troubleshooting (check specific workspace)

### ✅ Idempotency
- Control workspace is idempotent (re-run safe)
- Template workspaces are idempotent
- Can re-apply anytime safely

## Workflows

### Adding a New Template

1. **Extract template** (Python creates directory):
   ```bash
   venv/bin/python scripts/validate_and_extract.py \
     --execution-url "..." \
     --template-id "NewTemplate" \
     --project-id "MyProject" \
     --mode single \
     --to-tier 1
   ```

   Creates:
   ```
   templates/stage/NewTemplate/
   ├── v1.yaml
   └── tier-1.yaml
   ```

2. **Control workspace detects it**:
   ```bash
   cd terraform/control-workspace
   terraform apply
   ```

   Creates IaCM workspace: `stage_NewTemplate`

3. **IaCM workspace deploys versions**:
   - Workspace auto-executes
   - Creates 2 template versions in Harness

### Promoting a Template

1. **Python creates tier file**:
   ```bash
   venv/bin/python scripts/validate_and_extract.py \
     --template-id "Stage_Template" \
     --to-tier 2
   ```

   Creates: `templates/stage/Stage_Template/tier-2.yaml`

2. **IaCM workspace auto-detects new file**:
   - Workspace runs automatically (or trigger manually)
   - Creates new template version: `tier-2`

### Removing a Template

1. **Remove directory**:
   ```bash
   rm -rf templates/stage/OldTemplate/
   ```

2. **Update control workspace**:
   ```bash
   cd terraform/control-workspace
   terraform apply
   ```

   Destroys IaCM workspace: `stage_OldTemplate`

## Monitoring

### View All Workspaces

```bash
cd terraform/control-workspace
terraform output workspaces_created
```

### View Workspace Summary

```bash
terraform output summary
```

Example output:
```hcl
{
  "stage" = {
    "count" = 2
    "templates" = [
      "Stage_Template",
      "deploy_stage",
    ]
  }
  "step" = {
    "count" = 1
    "templates" = [
      "Step",
    ]
  }
}
```

### Check Template Workspace Output

In Harness IaCM UI:
1. Navigate to workspace (e.g., `stage_Stage_Template`)
2. View "Outputs" tab
3. See deployment summary

## Troubleshooting

### Workspace Not Created

**Check**: Does template directory have version files?
```bash
ls templates/stage/MyTemplate/
# Should see: v1.yaml, tier-1.yaml, etc.
```

**Fix**: Run extraction to create files

### Version Not Deployed

**Check**: Does YAML file exist?
```bash
ls templates/stage/Stage_Template/tier-2.yaml
```

**Fix**: Run promotion or extraction

### Workspace Failed to Apply

**Check**: Workspace logs in Harness IaCM UI

**Common issues**:
- Missing `versions.yaml` entry
- Invalid YAML syntax
- Scope mismatch (org/project doesn't exist)

## Migration from Old Structure

**Old structure**: Single workspace managed all templates
**New structure**: One workspace per template

### Migration Steps

1. **Backup old state**:
   ```bash
   cd terraform
   terraform state pull > old-state-backup.json
   ```

2. **Apply control workspace** (creates new workspaces):
   ```bash
   cd control-workspace
   terraform apply
   ```

3. **Import existing templates** (if needed):
   - Each IaCM workspace will create templates
   - Harness will detect if they already exist
   - No duplication due to identifier matching

4. **Archive old Terraform**:
   ```bash
   mkdir -p terraform/old
   mv terraform/main.tf terraform/old/
   mv terraform/providers.tf terraform/old/
   mv terraform/outputs.tf terraform/old/
   mv terraform/variables.tf terraform/old/
   ```

## Advanced Configuration

### Custom Workspace Names

Edit `control-workspace/main.tf`:
```hcl
identifier = "tmpl_${each.value.type}_${each.value.identifier}"
```

### Add Tags to Workspaces

Edit `control-workspace/main.tf`:
```hcl
tags = {
  template_type = each.value.type
  team          = "platform"
  environment   = "production"
}
```

### Change Repository Path

Edit `control-workspace/main.tf`:
```hcl
repository_path = "terraform/custom-path"
```

Then create: `terraform/custom-path/` with template workspace code

## Summary

**Architecture**: Control workspace → Creates IaCM workspaces → Each manages one template

**Workflow**: Python creates files → Terraform detects → IaCM workspace deploys

**Result**: Scalable, isolated, idempotent template management ✅
