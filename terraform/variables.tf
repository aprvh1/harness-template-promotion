variable "harness_org_id" {
  description = "Harness organization identifier"
  type        = string
}

variable "harness_project_id" {
  description = "Harness project identifier"
  type        = string
}

variable "stage_template_version" {
  description = "Version of stage template to deploy"
  type        = string
  default     = "v1.0.0"
}

variable "pipeline_template_version" {
  description = "Version of pipeline template to deploy"
  type        = string
  default     = "v1.0.0"
}

variable "environment" {
  description = "Environment name (dev, test, prod)"
  type        = string
  validation {
    condition     = contains(["dev", "test", "prod"], var.environment)
    error_message = "Environment must be one of: dev, test, prod"
  }
}

variable "promotion_tier" {
  description = "Promotion tier for pipeline deployment (canary, early_adopters, stable, all)"
  type        = string
  default     = "all"
  validation {
    condition     = contains(["canary", "early_adopters", "stable", "all"], var.promotion_tier)
    error_message = "Promotion tier must be one of: canary, early_adopters, stable, all"
  }
}

variable "canary_pipelines" {
  description = "List of pipeline identifiers in the canary tier"
  type        = list(string)
  default     = []
}

variable "early_adopter_pipelines" {
  description = "List of pipeline identifiers in the early adopters tier"
  type        = list(string)
  default     = []
}

variable "stable_pipelines" {
  description = "List of pipeline identifiers in the stable tier"
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default     = {}
}
