variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "smn"
}

variable "environment" {
  description = "Deployment environment (staging, production)"
  type        = string
  default     = "production"

  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "Environment must be 'staging' or 'production'."
  }
}

variable "azure_region" {
  description = "Azure region for deployment"
  type        = string
  default     = "eastus"
}

variable "db_password" {
  description = "PostgreSQL administrator password"
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.db_password) >= 16
    error_message = "Database password must be at least 16 characters."
  }
}

variable "db_sku" {
  description = "PostgreSQL Flexible Server SKU"
  type        = string
  default     = "GP_Standard_D4s_v3"
}

variable "db_storage_mb" {
  description = "PostgreSQL storage in MB"
  type        = number
  default     = 65536 # 64 GB
}

variable "redis_capacity" {
  description = "Redis cache capacity (size of the cache)"
  type        = number
  default     = 1
}

variable "redis_family" {
  description = "Redis cache family (C = Basic/Standard, P = Premium)"
  type        = string
  default     = "P"
}

variable "redis_sku" {
  description = "Redis cache SKU (Basic, Standard, Premium)"
  type        = string
  default     = "Premium"
}

variable "app_cpu" {
  description = "Container App CPU cores"
  type        = number
  default     = 1.0
}

variable "app_memory" {
  description = "Container App memory (e.g., '2Gi')"
  type        = string
  default     = "2Gi"
}

variable "smn_secret_key" {
  description = "SMN application secret key"
  type        = string
  sensitive   = true
}
