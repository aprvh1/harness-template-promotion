# Template Tier Control Policy (OPA)

Open Policy Agent (OPA) policy for enforcing tier-based template access control in Harness pipelines.

---

## Overview

This policy implements a **gradual rollout system** for Harness templates, preventing projects from using template versions they're not ready for.

**Key Principle**: Higher-tier (production) projects can only use thoroughly validated templates, while lower-tier (canary) projects test new versions first.

---

## Project Tier System

| Tier | Name | Purpose | Can Use |
|------|------|---------|---------|
| `dev` | Development | Template development & testing | **Everything** (v1, v2, all tiers, any scope) |
| `1` | Canary | First rollout group | tier-1, tier-2, tier-3, tier-4, tier-5, stable (account.* only) |
| `2` | Early Adopters | Second wave | tier-2, tier-3, tier-4, tier-5, stable (account.* only) |
| `3` | Wave 1 | Third wave | tier-3, tier-4, tier-5, stable (account.* only) |
| `4` | Wave 2 | Fourth wave | tier-4, tier-5, stable (account.* only) |
| `5` | Production | Stable only | tier-5, stable (account.* only) |

---

## Template Scope Restrictions

### Account-Level Templates (`account.*`)
- ✅ **Required** for tier 1-5 projects
- 🎯 Purpose: Standardized, governed templates for production

### Org/Project-Level Templates (`org.*` or `ProjectName`)
- ✅ **Only allowed** for `tier:dev` projects
- 🎯 Purpose: Experimentation and development

---

## How to Use

### 1. Tag Your Projects

Add a `tier` tag to each project in Harness:

```yaml
# Development project (full access)
tags:
  tier: "dev"

# Canary project (test new templates first)
tags:
  tier: "1"

# Production project (stable only)
tags:
  tier: "5"
```

### 2. Version Your Templates

Use the tier-based versioning system:

```yaml
# In pipeline YAML
template:
  templateRef: account.Stage_Template
  versionLabel: tier-3  # This template is at tier-3

# Stable template (no version label)
template:
  templateRef: account.Stable_Template
  # No versionLabel = stable (everyone can use)
```

### 3. Policy Enforcement

The policy automatically blocks invalid combinations:

**✅ Allowed:**
```yaml
# tier:1 project using tier-3 template
project: { tier: "1" }
template: { templateRef: "account.MyTemplate", versionLabel: "tier-3" }
```

**❌ Denied:**
```yaml
# tier:5 project trying to use tier-2 template
project: { tier: "5" }
template: { templateRef: "account.MyTemplate", versionLabel: "tier-2" }

Error: "Template 'account.MyTemplate' version 'tier-2' (Tier 2 Early Adopters) 
        is below your project's tier. Your project (tier: 5) is in Tier 5 (Production) 
        and can only use tier-5 or higher."
```

---

## Promotion Workflow

### Week 1: Development
```
tier:dev project creates template → version: v1
↓
Only tier:dev can use it
```

### Week 2: Canary Rollout
```
Promote v1 → tier-1
↓
tier:1 through tier:5 projects can use tier-1
```

### Week 3-6: Progressive Rollout
```
tier-1 → tier-2 → tier-3 → tier-4 → tier-5
Each promotion allows one more tier to safely adopt
```

### Week 7: Production Stable
```
tier-5 → stable (no version label)
↓
ALL projects can use stable templates
```

---

## Common Scenarios

### Scenario 1: New Template Development
**Project**: `tier: "dev"`  
**Action**: Create and test `v1` template  
**Result**: ✅ Allowed (dev can use anything)

### Scenario 2: Canary Testing
**Project**: `tier: "1"`  
**Action**: Use `tier-1` template  
**Result**: ✅ Allowed (tier-1 can use tier-1+)

### Scenario 3: Production Safety
**Project**: `tier: "5"`  
**Action**: Try to use `tier-2` template  
**Result**: ❌ Denied (tier-5 needs tier-5 or stable)

### Scenario 4: Stable Template
**Project**: Any tier  
**Action**: Use template without `versionLabel`  
**Result**: ✅ Allowed (stable = universal access)

### Scenario 5: Testing Non-Account Template
**Project**: `tier: "2"`  
**Action**: Use `org.CustomTemplate`  
**Result**: ❌ Denied (only tier:dev can use non-account templates)

---

## Error Messages

The policy provides clear, actionable error messages:

### Missing Tier Tag
```
❌ Project must have a 'tier' tag (e.g., tier: "dev" or tier: "1"). 
   This determines which template versions are allowed.
```

### Invalid Tier Value
```
❌ Invalid tier tag 'production'. Must be 'dev' or numeric (1-5).
```

### Development Version in Production
```
❌ Template 'account.MyTemplate' version 'v1' is a development version. 
   Only tier:dev projects can use semantic versions (v1, v2, etc.). 
   Promote to tier-1 first.
```

### Non-Account Template
```
❌ Template 'org.CustomTemplate' must be account-level (account.*). 
   Tier 1-5 projects can only use account-level templates for governance. 
   Use tier:dev for testing org/project-level templates.
```

### Template Too Low for Tier
```
❌ Template 'account.Stage_Template' version 'tier-2' (Tier 2 Early Adopters) 
   is below your project's tier. Your project (tier: 5) is in Tier 5 (Production) 
   and can only use tier-5 or higher. Wait for the template to be promoted to tier-5 or higher.
```

---

## Integration with Template Promotion System

This OPA policy works seamlessly with the [Template Promotion Plugin](../template-promotion-plugin/):

1. **Plugin**: Creates versioned template files (`tier-1.yaml`, `tier-2.yaml`, etc.)
2. **Terraform**: Deploys those versions to Harness
3. **OPA Policy**: Enforces which projects can use which versions
4. **Result**: Controlled, safe rollout with automatic enforcement

---

## Policy Configuration

### Harness Setup

1. **Enable OPA**: Go to Account Settings → Governance → OPA
2. **Create Policy Set**: Add this policy to a new policy set
3. **Apply to Pipelines**: Enforce on pipeline save/run events
4. **Test Mode**: Start with "dry run" mode to see what would be blocked

### Policy Events

This policy runs on:
- ✅ **Pipeline Save** (`onsave`): Prevents saving invalid pipelines
- ✅ **Pipeline Run** (`onrun`): Blocks execution of non-compliant pipelines

---

## Testing the Policy

### Using OPA CLI

```bash
# Install OPA
brew install opa

# Test policy
opa test template-tier-control.rego

# Evaluate specific input
opa eval -d template-tier-control.rego -i test-input.json "data.pipeline_environment.deny"
```

### Example Test Input

```json
{
  "metadata": {
    "projectMetadata": {
      "tags": {
        "tier": "5"
      }
    }
  },
  "pipeline": {
    "stages": [
      {
        "stage": {
          "template": {
            "templateRef": "account.Stage_Template",
            "versionLabel": "tier-2"
          }
        }
      }
    ]
  }
}
```

**Expected Result**: Denial (tier-5 project cannot use tier-2 template)

---

## Best Practices

### 1. Start with Development Projects
Tag a few projects as `tier:dev` for template development and testing.

### 2. Define Your Tiers Strategically
- **Tier 1**: Small team, willing to encounter issues
- **Tier 2-4**: Gradual expansion
- **Tier 5**: Critical production systems

### 3. Use Stable for Proven Templates
Once a template is battle-tested, mark it as stable (no version label) so all projects can use it.

### 4. Monitor Policy Violations
Review OPA policy logs to understand which teams are blocked and why.

### 5. Communicate Rollout Schedule
Let teams know when their tier will get access to new template versions.

---

## FAQ

**Q: What if I need to skip tiers?**  
A: Use `tier:dev` for testing, then promote directly to the target tier using the promotion plugin.

**Q: Can tier-5 projects ever use tier-1 templates?**  
A: No. Tier-5 (production) projects should only use thoroughly validated templates (tier-5 or stable).

**Q: How do I mark a template as stable?**  
A: Remove the `versionLabel` from the template reference, or use the promotion plugin to create a stable version.

**Q: What happens if a project has no tier tag?**  
A: The policy blocks all pipeline operations and requires adding a tier tag.

**Q: Can I customize the tier names?**  
A: Yes, edit the `tier_names` map in the policy (lines 162-168).

---

## Support

For issues or questions:
- See [Template Promotion System Documentation](../SETUP.md)
- Check [CLAUDE.md](../CLAUDE.md) for project context
- Review [OPA Documentation](https://www.openpolicyagent.org/docs/latest/)

---

**Version**: 1.0  
**Last Updated**: 2026-04-21  
**Compatibility**: Harness OPA integration, OPA 0.40+
