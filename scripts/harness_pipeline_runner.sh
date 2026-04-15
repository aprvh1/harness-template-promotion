#!/usr/bin/env bash
#
# Harness Pipeline Runner - Wrapper script for template extraction and promotion
#
# This script provides an environment-variable-based interface to validate_and_extract.py
# for easy integration with Harness CI/CD pipelines.
#
# Usage: Set environment variables and run:
#   bash scripts/harness_pipeline_runner.sh
#
# Required Environment Variables:
#   HARNESS_API_KEY       - Harness API key for authentication
#   HARNESS_ACCOUNT_ID    - Harness account identifier
#   TEMPLATE_ID           - Template identifier to extract or promote
#
# Mode: EXTRACTION (when EXECUTION_URL is set)
#   EXECUTION_URL         - Full Harness execution URL (required)
#   PROJECT_ID            - Project ID where template was tested (required)
#   CHANGELOG             - Description of changes (optional)
#   MODE                  - "single" or "tree" (optional, default: single)
#   SOURCE_VERSION        - Semantic version label like v1.0 (optional)
#   SANITIZE              - "true" to sanitize secrets (optional)
#   TO_TIER               - Create tier-N during extraction (optional)
#
# Mode: PROMOTION (when EXECUTION_URL is NOT set)
#   TO_TIER               - Target tier 1-5 (required)
#   TIER_SKIP             - "true" to allow skipping tiers (optional)
#   NO_PR                 - "true" to skip PR creation (optional)
#

set -euo pipefail  # Exit on error, undefined var, pipe failure

# ============================================================================
# Section 1: Constants and Setup
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors (only if terminal supports it)
if [ -t 1 ]; then
  GREEN='\033[0;32m'
  RED='\033[0;31m'
  YELLOW='\033[1;33m'
  BLUE='\033[0;34m'
  CYAN='\033[0;36m'
  BOLD='\033[1m'
  NC='\033[0m'  # No Color
else
  GREEN='' RED='' YELLOW='' BLUE='' CYAN='' BOLD='' NC=''
fi

# ============================================================================
# Section 2: Logging Functions
# ============================================================================

log_info() {
  echo -e "${BLUE}[INFO]${NC} $*"
}

log_error() {
  echo -e "${RED}[ERROR]${NC} $*" >&2
}

log_success() {
  echo -e "${GREEN}[SUCCESS]${NC} $*"
}

log_warning() {
  echo -e "${YELLOW}[WARNING]${NC} $*"
}

log_header() {
  echo -e "${CYAN}${BOLD}$*${NC}"
}

log_separator() {
  echo -e "${CYAN}================================================================${NC}"
}

# ============================================================================
# Section 3: Validation Functions
# ============================================================================

# Detect Python executable
detect_python() {
  # Try venv first (local development)
  if [ -f "$REPO_ROOT/venv/bin/python" ]; then
    echo "$REPO_ROOT/venv/bin/python"
  # Try python3 (Harness pipeline, most common)
  elif command -v python3 &> /dev/null; then
    echo "python3"
  # Try python
  elif command -v python &> /dev/null; then
    echo "python"
  else
    log_error "Python not found. Please install Python 3.7+"
    log_error "Or ensure 'python3' or 'python' is in PATH"
    exit 1
  fi
}

# Validate required environment variables
validate_required_vars() {
  local mode_type="$1"
  local missing_vars=()

  # Always required
  [ -z "${HARNESS_API_KEY:-}" ] && missing_vars+=("HARNESS_API_KEY")
  [ -z "${HARNESS_ACCOUNT_ID:-}" ] && missing_vars+=("HARNESS_ACCOUNT_ID")
  [ -z "${TEMPLATE_ID:-}" ] && missing_vars+=("TEMPLATE_ID")

  # Mode-specific requirements
  if [ "$mode_type" = "extraction" ]; then
    [ -z "${EXECUTION_URL:-}" ] && missing_vars+=("EXECUTION_URL")
    [ -z "${PROJECT_ID:-}" ] && missing_vars+=("PROJECT_ID")
  else
    [ -z "${TO_TIER:-}" ] && missing_vars+=("TO_TIER")
  fi

  if [ ${#missing_vars[@]} -gt 0 ]; then
    log_error "Missing required environment variables:"
    for var in "${missing_vars[@]}"; do
      log_error "  - $var"
    done
    log_error ""
    log_error "For extraction mode, set: EXECUTION_URL, PROJECT_ID"
    log_error "For promotion mode, set: TO_TIER"
    exit 1
  fi
}

# Validate enum values
validate_enums() {
  # Validate MODE (single or tree)
  if [ -n "${MODE:-}" ]; then
    if [[ ! "$MODE" =~ ^(single|tree)$ ]]; then
      log_error "Invalid MODE: '$MODE'"
      log_error "Must be 'single' or 'tree'"
      exit 1
    fi
  fi

  # Validate TO_TIER (1-5)
  if [ -n "${TO_TIER:-}" ]; then
    if [[ ! "$TO_TIER" =~ ^[1-5]$ ]]; then
      log_error "Invalid TO_TIER: '$TO_TIER'"
      log_error "Must be 1, 2, 3, 4, or 5"
      exit 1
    fi
  fi

  # Validate boolean flags
  for flag_name in SANITIZE TIER_SKIP NO_PR; do
    flag_value="${!flag_name:-}"
    if [ -n "$flag_value" ]; then
      if [[ ! "$flag_value" =~ ^(true|false|1|0|yes|no)$ ]]; then
        log_error "Invalid $flag_name: '$flag_value'"
        log_error "Must be 'true', 'false', '1', '0', 'yes', or 'no'"
        exit 1
      fi
    fi
  done
}

# Normalize boolean flag to true/false
normalize_boolean() {
  local value="${1:-false}"
  # Convert to lowercase (compatible with Bash 3.x+)
  local lower_value=$(echo "$value" | tr '[:upper:]' '[:lower:]')
  case "$lower_value" in
    true|1|yes) echo "true" ;;
    *) echo "false" ;;
  esac
}

# ============================================================================
# Section 4: Command Builder
# ============================================================================

# Build command arguments array from environment variables
# Populates the global CMD_ARRAY variable
build_command_array() {
  local mode_type="$1"

  # Always include template-id
  CMD_ARRAY+=("--template-id" "$TEMPLATE_ID") || return 1

  if [ "$mode_type" = "extraction" ]; then
    # Extraction mode arguments
    CMD_ARRAY+=("--execution-url" "$EXECUTION_URL") || return 1
    CMD_ARRAY+=("--project-id" "$PROJECT_ID") || return 1

    # Optional extraction arguments
    if [ -n "${CHANGELOG:-}" ]; then
      CMD_ARRAY+=("--changelog" "$CHANGELOG") || return 1
    fi

    if [ -n "${MODE:-}" ]; then
      CMD_ARRAY+=("--mode" "$MODE") || return 1
    fi

    if [ -n "${SOURCE_VERSION:-}" ]; then
      CMD_ARRAY+=("--source-version" "$SOURCE_VERSION") || return 1
    fi

    if [ -n "${TO_TIER:-}" ]; then
      CMD_ARRAY+=("--to-tier" "$TO_TIER") || return 1
    fi

    # Boolean flags
    local sanitize_normalized
    sanitize_normalized=$(normalize_boolean "${SANITIZE:-false}") || return 1
    if [ "$sanitize_normalized" = "true" ]; then
      CMD_ARRAY+=("--sanitize") || return 1
    fi

  else
    # Promotion mode arguments
    CMD_ARRAY+=("--to-tier" "$TO_TIER") || return 1

    # Boolean flags
    local tier_skip_normalized
    tier_skip_normalized=$(normalize_boolean "${TIER_SKIP:-false}") || return 1
    if [ "$tier_skip_normalized" = "true" ]; then
      CMD_ARRAY+=("--tier-skip") || return 1
    fi

    local no_pr_normalized
    no_pr_normalized=$(normalize_boolean "${NO_PR:-false}") || return 1
    if [ "$no_pr_normalized" = "true" ]; then
      CMD_ARRAY+=("--no-pr") || return 1
    fi
  fi

  return 0
}

# Format command array as string for display (with proper quoting)
format_command_for_display() {
  local args=("$@")
  local formatted=""

  for arg in "${args[@]}"; do
    # Quote arguments that contain spaces
    if [[ "$arg" =~ [[:space:]] ]]; then
      formatted="$formatted \"$arg\""
    else
      formatted="$formatted $arg"
    fi
  done

  # Trim leading space
  echo "${formatted# }"
}

# Mask sensitive data in command for logging
mask_sensitive_data() {
  local cmd="$1"
  local masked_cmd="$cmd"

  # Mask API key
  if [ -n "${HARNESS_API_KEY:-}" ]; then
    masked_cmd="${masked_cmd//$HARNESS_API_KEY/***MASKED***}"
  fi

  # Mask execution URL (contains account info)
  if [ -n "${EXECUTION_URL:-}" ]; then
    # Keep just the last part (execution ID)
    local exec_id
    exec_id=$(echo "$EXECUTION_URL" | grep -oE '[^/]+\?storeType' | cut -d'?' -f1)
    masked_cmd="${masked_cmd//$EXECUTION_URL/https://.../$exec_id}"
  fi

  echo "$masked_cmd"
}

# ============================================================================
# Section 5: Main Execution
# ============================================================================

main() {
  log_separator
  log_header "Harness Pipeline Runner for Template Extraction & Promotion"
  log_separator
  echo ""

  # Change to repo root
  cd "$REPO_ROOT"
  log_info "Working directory: $REPO_ROOT"

  # Verify Python script exists
  if [ ! -f "$SCRIPT_DIR/validate_and_extract.py" ]; then
    log_error "Python script not found at: $SCRIPT_DIR/validate_and_extract.py"
    log_error "SCRIPT_DIR: $SCRIPT_DIR"
    log_error "Files in scripts/:"
    ls -la "$SCRIPT_DIR/" 2>&1 || log_error "Cannot list scripts directory"
    exit 1
  fi

  # Detect mode based on EXECUTION_URL presence
  local mode_type
  if [ -n "${EXECUTION_URL:-}" ]; then
    mode_type="extraction"
    log_info "Mode: ${BOLD}EXTRACTION${NC} (EXECUTION_URL is set)"
  else
    mode_type="promotion"
    log_info "Mode: ${BOLD}PROMOTION${NC} (EXECUTION_URL is not set)"
  fi
  echo ""

  # Detect Python
  log_info "Detecting Python environment..."
  local python_cmd
  python_cmd=$(detect_python)
  log_info "Using Python: $python_cmd"

  # Verify Python version
  local python_version
  python_version=$($python_cmd --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
  log_info "Python version: $python_version"
  echo ""

  # Validate environment variables
  log_info "Validating environment variables..."
  validate_required_vars "$mode_type"
  validate_enums
  log_success "✓ All required variables present and valid"
  echo ""

  # Build command array
  log_info "Building Python command..."
  declare -a CMD_ARRAY=("$python_cmd" "$SCRIPT_DIR/validate_and_extract.py")
  build_command_array "$mode_type" || {
    log_error "Failed to build command array"
    exit 1
  }

  # Format command for display
  local cmd_display
  cmd_display=$(format_command_for_display "${CMD_ARRAY[@]}") || {
    log_error "Failed to format command for display"
    log_error "Python command: $python_cmd"
    log_error "Script path: $SCRIPT_DIR/validate_and_extract.py"
    log_error "Command array length: ${#CMD_ARRAY[@]}"
    exit 1
  }

  # Log command (with sensitive data masked)
  log_info "Command to execute:"
  log_info "  $(mask_sensitive_data "$cmd_display")"

  # Debug: Show argument count
  log_info "Total arguments: ${#CMD_ARRAY[@]}"
  echo ""

  # Log configuration summary
  log_info "Configuration:"
  log_info "  Template ID: $TEMPLATE_ID"

  if [ "$mode_type" = "extraction" ]; then
    log_info "  Project ID: $PROJECT_ID"
    log_info "  Mode: ${MODE:-single}"
    [ -n "${CHANGELOG:-}" ] && log_info "  Changelog: $CHANGELOG"
    [ -n "${SOURCE_VERSION:-}" ] && log_info "  Source Version: $SOURCE_VERSION"
    [ "$(normalize_boolean "${SANITIZE:-false}")" = "true" ] && log_info "  Sanitize: enabled"
    [ -n "${TO_TIER:-}" ] && log_info "  Create Tier: $TO_TIER"
  else
    log_info "  Target Tier: $TO_TIER"
    [ "$(normalize_boolean "${TIER_SKIP:-false}")" = "true" ] && log_info "  Tier Skip: enabled"
    [ "$(normalize_boolean "${NO_PR:-false}")" = "true" ] && log_info "  PR Creation: disabled"
  fi

  echo ""
  log_separator
  log_info "Executing Python script..."
  log_separator
  echo ""

  # Flush output before executing
  sync

  # Execute the command using the array (properly handles spaces in arguments)
  local exit_code=0
  if ! "${CMD_ARRAY[@]}" 2>&1; then
    exit_code=$?
    echo ""
    log_separator
    log_error "✗ Script failed with exit code: $exit_code"
    log_error "Command was: $(mask_sensitive_data "$cmd_display")"
    log_separator
    exit $exit_code
  fi

  echo ""
  log_separator
  log_success "✓ Script completed successfully!"
  log_separator
  exit 0
}

# Run main function
main "$@"
