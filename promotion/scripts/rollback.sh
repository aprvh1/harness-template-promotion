#!/bin/bash
set -e

# Template Rollback Script
# Rolls back template versions to a previous stable version

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Rollback template versions to a previous stable version.

OPTIONS:
    -t, --tier TIER          Target tier: canary, early_adopters, stable, all
    -v, --version VERSION    Version to rollback to (e.g., v1.0.0)
    -e, --env ENVIRONMENT    Environment: dev, test, prod
    -w, --workspace WORKSPACE Terraform workspace (default: same as environment)
    --force                 Skip confirmation prompt
    -h, --help              Show this help message

EXAMPLES:
    # Rollback canary tier to v1.0.0 in prod
    $0 --tier canary --version v1.0.0 --env prod

    # Rollback all tiers (emergency)
    $0 --tier all --version v1.0.0 --env prod --force
EOF
    exit 1
}

# Parse arguments
TIER=""
VERSION=""
ENVIRONMENT=""
WORKSPACE=""
FORCE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -t|--tier)
            TIER="$2"
            shift 2
            ;;
        -v|--version)
            VERSION="$2"
            shift 2
            ;;
        -e|--env)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -w|--workspace)
            WORKSPACE="$2"
            shift 2
            ;;
        --force)
            FORCE=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            print_error "Unknown option: $1"
            usage
            ;;
    esac
done

# Validate required arguments
if [ -z "$TIER" ] || [ -z "$VERSION" ] || [ -z "$ENVIRONMENT" ]; then
    print_error "Missing required arguments"
    usage
fi

if [ -z "$WORKSPACE" ]; then
    WORKSPACE="$ENVIRONMENT"
fi

print_warning "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
print_warning "    TEMPLATE ROLLBACK OPERATION"
print_warning "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
print_info "Tier: $TIER"
print_info "Rollback to Version: $VERSION"
print_info "Environment: $ENVIRONMENT"
print_info "Workspace: $WORKSPACE"
print_warning "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check if rollback version exists
VERSION_DIR="$PROJECT_ROOT/templates/stage-templates/$VERSION"
if [ ! -d "$VERSION_DIR" ]; then
    print_error "Rollback version directory not found: $VERSION_DIR"
    exit 1
fi

# Confirmation
if [ "$FORCE" != true ]; then
    print_warning ""
    print_warning "This will rollback template versions for the $TIER tier."
    print_warning "This operation will affect running pipelines!"
    print_warning ""
    read -p "Are you sure you want to proceed? Type 'ROLLBACK' to confirm: " CONFIRM

    if [ "$CONFIRM" != "ROLLBACK" ]; then
        print_info "Rollback cancelled."
        exit 0
    fi
fi

# Change to terraform directory
cd "$TERRAFORM_DIR"

# Select workspace
print_info "Selecting Terraform workspace: $WORKSPACE"
terraform workspace select "$WORKSPACE"

# Prepare terraform command
TF_VARS="-var-file=environments/${ENVIRONMENT}.tfvars"
TF_VARS="$TF_VARS -var=stage_template_version=$VERSION"
TF_VARS="$TF_VARS -var=pipeline_template_version=$VERSION"
TF_VARS="$TF_VARS -var=promotion_tier=$TIER"

# Run terraform plan
print_info "Planning rollback..."
terraform plan $TF_VARS -out=rollback.tfplan

# Apply rollback
print_info "Applying rollback..."
terraform apply rollback.tfplan
rm -f rollback.tfplan

print_info ""
print_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
print_info "✓ Rollback completed successfully!"
print_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
print_info ""
print_info "Rolled back to version: $VERSION"
print_info "Affected tier: $TIER"
print_info ""
print_info "Next steps:"
print_info "  1. Verify pipelines are functioning correctly"
print_info "  2. Investigate the root cause of the issue"
print_info "  3. Update changelog and document the incident"
