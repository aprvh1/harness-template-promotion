variable "identifier" {
  description = "Unique identifier for the stage template"
  type        = string
}

variable "name" {
  description = "Display name for the stage template"
  type        = string
}

variable "description" {
  description = "Description of the stage template"
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

variable "version" {
  description = "Template version label"
  type        = string
}

variable "is_stable" {
  description = "Mark template version as stable"
  type        = bool
  default     = true
}

variable "yaml_content" {
  description = "YAML content of the stage template"
  type        = string
}

variable "tags" {
  description = "Tags to apply to the template"
  type        = map(string)
  default     = {}
}
