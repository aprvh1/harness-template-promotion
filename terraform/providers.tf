terraform {
  required_version = ">= 1.0"

  required_providers {
    harness = {
      source  = "harness/harness"
      version = "~> 0.32"
    }
  }
}

provider "harness" {
  # Authentication via environment variables:
  # HARNESS_ACCOUNT_ID - Your Harness account identifier
  # HARNESS_API_KEY    - Your Harness API key or PAT token
  # HARNESS_ENDPOINT   - (Optional) Custom endpoint, defaults to https://app.harness.io/gateway

  # Example:
  # export HARNESS_ACCOUNT_ID="your-account-id"
  # export HARNESS_API_KEY="your-api-key"
}
