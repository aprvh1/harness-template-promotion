# Per-Template Terraform Workspaces (Simplified Approach)

## Architecture

Instead of IaCM workspaces (not available in provider), we use **separate Terraform directories** per template type with **Terraform workspaces** for isolation.

## Structure

```
terraform/workspaces/
├── README.md (this file)
│
├── stages/              # All stage templates
│   ├── main.tf         # Manages all stage templates
│   ├── variables.tf
│   └── backend.tf
│
├── steps/               # All step templates
│   ├── main.tf
│   ├── variables.tf
│   └── backend.tf
│
├── step-groups/         # All step-group templates
│   ├── main.tf
│   ├── variables.tf
│   └── backend.tf
│
└── pipelines/           # All pipeline templates
    ├── main.tf
    ├── variables.tf
    └── backend.tf
```

## How It Works

### Each directory manages one template type
- `stages/` → All stage templates
- `steps/` → All step templates
- etc.

### Within each directory, use Terraform workspaces for isolation
```bash
cd terraform/workspaces/stages

# Create workspace for Stage_Template
terraform workspace new Stage_Template
terraform workspace select Stage_Template
terraform apply

# Create workspace for deploy_stage
terraform workspace new deploy_stage
terraform workspace select deploy_stage
terraform apply
```

### Each workspace manages one template's versions
- Workspace: `Stage_Template`
- Reads: `templates/stage/Stage_Template/*.yaml`
- Creates: All versions (v1, tier-1, tier-2, etc.)

## Advantages

✅ **Isolation**: Each template has its own workspace
✅ **Simple**: No IaCM dependencies
✅ **Native**: Uses Terraform's built-in workspace feature
✅ **Scalable**: Add templates = add workspaces
✅ **Works now**: No provider limitations

## Usage

See individual README in each directory for specific instructions.
