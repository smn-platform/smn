output "api_fqdn" {
  description = "Container App API FQDN"
  value       = azurerm_container_app.api.latest_revision_fqdn
}

output "acr_login_server" {
  description = "Container Registry login server for Docker pushes"
  value       = azurerm_container_registry.main.login_server
}

output "database_fqdn" {
  description = "PostgreSQL Flexible Server FQDN"
  value       = azurerm_postgresql_flexible_server.main.fqdn
  sensitive   = true
}

output "redis_hostname" {
  description = "Redis Cache hostname"
  value       = azurerm_redis_cache.main.hostname
  sensitive   = true
}

output "log_analytics_workspace_id" {
  description = "Log Analytics Workspace ID for diagnostics"
  value       = azurerm_log_analytics_workspace.main.workspace_id
}

output "app_insights_connection_string" {
  description = "Application Insights connection string"
  value       = azurerm_application_insights.main.connection_string
  sensitive   = true
}
