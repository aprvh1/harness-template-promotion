variable "identifier" {
  description = "Unique identifier for the pipeline"
  type        = string
}

variable "name" {
  description = "Display name for the pipeline"
  type        = string
}

variable "description" {
  description = "Description of the pipeline"
  type        = string
  default     = ""
}

variable "org_id" {
  description = "Harness organization identifier"
  type        = string
}

variable "project_id" {
  description = "Harness project identifier"
  type        = string
}

variable "pipeline_template_ref" {
  description = "Reference to the pipeline template"
  type        = string
}

variable "template_version" {
  description = "Version of the template to use"
  type        = string
}

variable "template_inputs" {
  description = "Input values for template runtime inputs"
  type        = map(string)
  default     = {}
}

variable "tags" {
  description = "Tags to apply to the pipeline"
  type        = map(string)
  default     = {}
}
