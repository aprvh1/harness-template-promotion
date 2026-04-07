#!/bin/bash
set -e

# Template Validation Script
# Validates template files before promotion

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

usage() {
    cat << EOF
Usage: $0 [VERSION]

Validate template files and Terraform configuration.

ARGUMENTS:
    VERSION    Template version to validate (e.g., v1.0.0)

EXAMPLES:
    $0 v1.0.0
EOF
    exit 1
}

VERSION="$1"

if [ -z "$VERSION" ]; then
    print_error "Template version required"
    usage
fi

print_info "Starting validation for version: $VERSION"

# Check if version directory exists
STAGE_TEMPLATE_DIR="$PROJECT_ROOT/templates/stage-templates/$VERSION"
PIPELINE_TEMPLATE_DIR="$PROJECT_ROOT/templates/pipeline-templates/$VERSION"

if [ ! -d "$STAGE_TEMPLATE_DIR" ]; then
    print_error "Stage template directory not found: $STAGE_TEMPLATE_DIR"
    exit 1
fi

if [ ! -d "$PIPELINE_TEMPLATE_DIR" ]; then
    print_error "Pipeline template directory not found: $PIPELINE_TEMPLATE_DIR"
    exit 1
fi

# Validation Layer 1: File existence
print_info "[1/5] Checking file existence..."
REQUIRED_FILES=(
    "$STAGE_TEMPLATE_DIR/deploy-stage.yaml"
    "$STAGE_TEMPLATE_DIR/metadata.yaml"
    "$PIPELINE_TEMPLATE_DIR/ci-pipeline.yaml"
    "$PIPELINE_TEMPLATE_DIR/metadata.yaml"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        print_error "Required file not found: $file"
        exit 1
    fi
    print_info "  ✓ Found: $(basename $file)"
done

# Validation Layer 2: YAML syntax
print_info "[2/5] Validating YAML syntax..."
if command -v yamllint &> /dev/null; then
    for file in "${REQUIRED_FILES[@]}"; do
        if yamllint "$file" > /dev/null 2>&1; then
            print_info "  ✓ Valid YAML: $(basename $file)"
        else
            print_error "  ✗ Invalid YAML: $(basename $file)"
            yamllint "$file"
            exit 1
        fi
    done
else
    print_warning "  yamllint not installed, skipping YAML syntax validation"
    print_info "  Install with: pip install yamllint"
fi

# Validation Layer 3: Terraform format check
print_info "[3/5] Checking Terraform formatting..."
cd "$TERRAFORM_DIR"
if terraform fmt -check -recursive > /dev/null 2>&1; then
    print_info "  ✓ Terraform files properly formatted"
else
    print_warning "  Some Terraform files need formatting"
    print_info "  Run: terraform fmt -recursive"
fi

# Validation Layer 4: Terraform validation
print_info "[4/5] Running Terraform validation..."
cd "$TERRAFORM_DIR"
terraform init -backend=false > /dev/null 2>&1
if terraform validate > /dev/null 2>&1; then
    print_info "  ✓ Terraform configuration valid"
else
    print_error "  ✗ Terraform validation failed"
    terraform validate
    exit 1
fi

# Validation Layer 5: Metadata validation
print_info "[5/5] Validating metadata..."
for metadata_file in "$STAGE_TEMPLATE_DIR/metadata.yaml" "$PIPELINE_TEMPLATE_DIR/metadata.yaml"; do
    if grep -q "version: \"$VERSION\"" "$metadata_file"; then
        print_info "  ✓ Version matches in $(basename $(dirname $metadata_file))/metadata.yaml"
    else
        print_error "  ✗ Version mismatch in $metadata_file"
        print_error "    Expected: $VERSION"
        print_error "    Found: $(grep 'version:' $metadata_file)"
        exit 1
    fi
done

print_info ""
print_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
print_info "✓ All validations passed for version $VERSION"
print_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
print_info ""
print_info "Template is ready for promotion!"
