# Variables for control workspace

variable "harness_account_id" {
  description = "Harness account ID"
  type        = string
}

variable "harness_platform_api_key" {
  description = "Harness Platform API Key for NextGen resources"
  type        = string
  sensitive   = true
}

variable "git_connector_ref" {
  description = "Git connector reference for IaCM workspaces"
  type        = string
}

variable "repository_name" {
  description = "Git repository name"
  type        = string
  default     = "template-promotion"
}

variable "repository_branch" {
  description = "Git repository branch"
  type        = string
  default     = "main"
}

variable "org_id" {
  description = "Harness organization ID"
  type        = string
}

variable "project_id" {
  description = "Harness project ID"
  type        = string
}

variable "terraform_version" {
  description = "Terraform version for workspaces"
  type        = string
  default     = "1.5.7"
}


