variable "identifier" {
  description = "Unique identifier for the test pipeline"
  type        = string
}

variable "name" {
  description = "Display name for the test pipeline"
  type        = string
}

variable "description" {
  description = "Description of the test pipeline"
  type        = string
  default     = "Standalone test pipeline for stage template validation"
}

variable "org_id" {
  description = "Harness organization identifier"
  type        = string
}

variable "project_id" {
  description = "Harness project identifier"
  type        = string
}

variable "stage_template_ref" {
  description = "Reference to the stage template to test"
  type        = string
  default     = "deploy_stage"
}

variable "stage_version" {
  description = "Version of the stage template to test"
  type        = string
}

variable "test_service" {
  description = "Test service name"
  type        = string
  default     = "test-service"
}

variable "tags" {
  description = "Tags to apply to the test pipeline"
  type        = map(string)
  default     = {}
}
