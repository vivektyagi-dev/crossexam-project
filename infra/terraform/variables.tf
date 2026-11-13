variable "project_id" {
  type        = string
  description = "GCP project id"
}

variable "region" {
  type    = string
  default = "asia-south1" # Mumbai
}

variable "llm_provider" {
  type        = string
  default     = "gemini"
  description = "gemini (API key in Secret Manager) or vertex (uses the pods' Workload Identity)"
}

variable "langsmith_enabled" {
  type    = bool
  default = false
}

variable "llm_requests_per_minute" {
  type    = number
  default = 60
}

variable "github_repository" {
  type        = string
  description = "owner/repo allowed to deploy through Workload Identity Federation"
}

variable "alert_email" {
  type        = string
  description = "Where monitoring alerts are sent"
}

variable "keda_version" {
  type        = string
  default     = "2.21.0"
  description = "KEDA Helm chart version (https://github.com/kedacore/keda/releases)"
}

variable "sql_tier" {
  type    = string
  default = "db-custom-1-3840" # 1 vCPU, 3.75 GB
}

variable "daily_ai_budget_usd" {
  type    = number
  default = 5
}
