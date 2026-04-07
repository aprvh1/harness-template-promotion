#!/bin/bash
set -e

# Template Promotion Script
# Promotes template versions through tiers: canary -> early_adopters -> stable

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROMOTION_CONFIG="$PROJECT_ROOT/promotion/promotion-config.yaml"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to show usage
usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Promote template versions through deployment tiers.

OPTIONS:
    -t, --tier TIER          Target tier: canary, early_adopters, stable, all
    -v, --version VERSION    Template version to promote (e.g., v1.1.0)
    -e, --env ENVIRONMENT    Environment: dev, test, prod
    -w, --workspace WORKSPACE Terraform workspace (default: same as environment)
    --dry-run               Show what would be done without applying
    -h, --help              Show this help message

EXAMPLES:
    # Promote v1.1.0 to canary tier in dev
    $0 --tier canary --version v1.1.0 --env dev

    # Dry run for early adopters in prod
    $0 --tier early_adopters --version v1.1.0 --env prod --dry-run

    # Promote to all tiers in test
    $0 --tier all --version v1.1.0 --env test
EOF
    exit 1
}

# Parse command line arguments
TIER=""
VERSION=""
ENVIRONMENT=""
WORKSPACE=""
DRY_RUN=false

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
        --dry-run)
            DRY_RUN=true
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

# Set workspace to environment if not specified
if [ -z "$WORKSPACE" ]; then
    WORKSPACE="$ENVIRONMENT"
fi

# Validate tier
if [[ ! "$TIER" =~ ^(canary|early_adopters|stable|all)$ ]]; then
    print_error "Invalid tier: $TIER"
    usage
fi

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(dev|test|prod)$ ]]; then
    print_error "Invalid environment: $ENVIRONMENT"
    usage
fi

print_info "Starting template promotion..."
print_info "Tier: $TIER"
print_info "Version: $VERSION"
print_info "Environment: $ENVIRONMENT"
print_info "Workspace: $WORKSPACE"
print_info "Dry Run: $DRY_RUN"

# Check if version directory exists
VERSION_DIR="$PROJECT_ROOT/templates/stage-templates/$VERSION"
if [ ! -d "$VERSION_DIR" ]; then
    print_error "Template version directory not found: $VERSION_DIR"
    exit 1
fi

# Change to terraform directory
cd "$TERRAFORM_DIR"

# Select workspace
print_info "Selecting Terraform workspace: $WORKSPACE"
terraform workspace select "$WORKSPACE" || terraform workspace new "$WORKSPACE"

# Run validation script
print_info "Running validation checks..."
"$SCRIPT_DIR/validate.sh" "$VERSION"

# Prepare terraform command
TF_VARS="-var-file=environments/${ENVIRONMENT}.tfvars"
TF_VARS="$TF_VARS -var=stage_template_version=$VERSION"
TF_VARS="$TF_VARS -var=pipeline_template_version=$VERSION"
TF_VARS="$TF_VARS -var=promotion_tier=$TIER"

# Run terraform plan
print_info "Running Terraform plan..."
if [ "$DRY_RUN" = true ]; then
    terraform plan $TF_VARS
    print_warning "Dry run completed. No changes applied."
    exit 0
fi

terraform plan $TF_VARS -out=promotion.tfplan

# Ask for confirmation
print_warning "Review the plan above."
read -p "Do you want to apply these changes? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    print_info "Promotion cancelled."
    rm -f promotion.tfplan
    exit 0
fi

# Apply changes
print_info "Applying Terraform changes..."
terraform apply promotion.tfplan
rm -f promotion.tfplan

print_info "✓ Promotion completed successfully!"
print_info "Next steps:"
print_info "  1. Monitor pipelines in the $TIER tier"
print_info "  2. Check logs and metrics"
print_info "  3. If issues occur, run: ./rollback.sh --tier $TIER --version <previous-version> --env $ENVIRONMENT"

# Update promotion config
print_info "Updating promotion configuration..."
# This would update the promotion-config.yaml file to track the deployment
# Implementation left as an exercise based on your YAML parsing preferences
