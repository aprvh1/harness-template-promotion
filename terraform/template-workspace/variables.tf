# Variables for template workspace

variable "template_type" {
  description = "Template type (stage, step, step_group, pipeline)"
  type        = string
}

variable "template_identifier" {
  description = "Template identifier"
  type        = string
}

variable "template_path" {
  description = "Relative path to template directory (e.g., stage/Stage_Template)"
  type        = string
}
