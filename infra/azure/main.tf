########################################################################
# SMN — Azure Production Infrastructure (Terraform)
#
# Creates:
#   - Resource Group
#   - Virtual Network with subnets + NSGs
#   - Azure Container Registry (Premium, geo-replicated)
#   - Azure Database for PostgreSQL Flexible Server (HA)
#   - Azure Cache for Redis (Enterprise, TLS)
#   - Log Analytics Workspace + Application Insights
#   - Azure Container Apps Environment + Container App
#   - User-Assigned Managed Identity (no secrets in app)
#
# Usage:
#   cd infra/azure
#   terraform init
#   terraform plan -var="db_password=<secure>" -out=plan.tfplan
#   terraform apply plan.tfplan
########################################################################

terraform {
  required_version = ">= 1.5"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.100"
    }
  }

  backend "azurerm" {
    # Configure during init:
    #   -backend-config="resource_group_name=tfstate-rg"
    #   -backend-config="storage_account_name=tfstatesa"
    #   -backend-config="container_name=tfstate"
    #   -backend-config="key=smn.terraform.tfstate"
    resource_group_name  = "tfstate-rg"
    storage_account_name = "tfstatesa"
    container_name       = "tfstate"
    key                  = "smn.terraform.tfstate"
  }
}

provider "azurerm" {
  features {
    resource_group {
      prevent_deletion_if_contains_resources = true
    }
    key_vault {
      purge_soft_delete_on_destroy = false
    }
  }
}

locals {
  prefix = "${var.project_name}-${var.environment}"
  tags = {
    Project     = "SMN"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# ───────────────────── Resource Group ─────────────────────

resource "azurerm_resource_group" "main" {
  name     = "rg-${local.prefix}"
  location = var.azure_region
  tags     = local.tags
}

# ───────────────────── Networking ─────────────────────

resource "azurerm_virtual_network" "main" {
  name                = "vnet-${local.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  address_space       = ["10.0.0.0/16"]
  tags                = local.tags
}

resource "azurerm_subnet" "app" {
  name                 = "snet-app"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.0.1.0/24"]

  delegation {
    name = "container-apps"
    service_delegation {
      name    = "Microsoft.App/environments"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_subnet" "db" {
  name                 = "snet-db"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.0.2.0/24"]

  delegation {
    name = "postgresql"
    service_delegation {
      name    = "Microsoft.DBforPostgreSQL/flexibleServers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

resource "azurerm_subnet" "redis" {
  name                 = "snet-redis"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.0.3.0/24"]
}

# NSGs

resource "azurerm_network_security_group" "app" {
  name                = "nsg-app-${local.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = local.tags

  security_rule {
    name                       = "AllowHTTPS"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

resource "azurerm_network_security_group" "db" {
  name                = "nsg-db-${local.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = local.tags

  security_rule {
    name                       = "AllowPostgresFromApp"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "5432"
    source_address_prefix      = "10.0.1.0/24"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "DenyAllInbound"
    priority                   = 4096
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

resource "azurerm_subnet_network_security_group_association" "app" {
  subnet_id                 = azurerm_subnet.app.id
  network_security_group_id = azurerm_network_security_group.app.id
}

resource "azurerm_subnet_network_security_group_association" "db" {
  subnet_id                 = azurerm_subnet.db.id
  network_security_group_id = azurerm_network_security_group.db.id
}

# ───────────────────── DNS (private zones) ─────────────────────

resource "azurerm_private_dns_zone" "postgres" {
  name                = "smn.postgres.database.azure.com"
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "postgres" {
  name                  = "postgres-vnet-link"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.postgres.name
  virtual_network_id    = azurerm_virtual_network.main.id
}

# ───────────────────── Managed Identity ─────────────────────

resource "azurerm_user_assigned_identity" "app" {
  name                = "id-${local.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = local.tags
}

# ───────────────────── Container Registry ─────────────────────

resource "azurerm_container_registry" "main" {
  name                   = replace("acr${local.prefix}", "-", "")
  resource_group_name    = azurerm_resource_group.main.name
  location               = azurerm_resource_group.main.location
  sku                    = "Premium"
  admin_enabled          = false
  anonymous_pull_enabled = false
  tags                   = local.tags

  retention_policy {
    days    = 30
    enabled = true
  }
}

resource "azurerm_role_assignment" "acr_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

# ───────────────────── PostgreSQL Flexible Server ─────────────────────

resource "azurerm_postgresql_flexible_server" "main" {
  name                          = "psql-${local.prefix}"
  resource_group_name           = azurerm_resource_group.main.name
  location                      = azurerm_resource_group.main.location
  version                       = "16"
  delegated_subnet_id           = azurerm_subnet.db.id
  private_dns_zone_id           = azurerm_private_dns_zone.postgres.id
  administrator_login           = "smnadmin"
  administrator_password        = var.db_password
  sku_name                      = var.db_sku
  storage_mb                    = var.db_storage_mb
  backup_retention_days         = 35
  geo_redundant_backup_enabled  = var.environment == "production"
  public_network_access_enabled = false
  tags                          = local.tags
  zone                          = "1"

  high_availability {
    mode                      = var.environment == "production" ? "ZoneRedundant" : "SameZone"
    standby_availability_zone = var.environment == "production" ? "2" : "1"
  }

  depends_on = [azurerm_private_dns_zone_virtual_network_link.postgres]
}

resource "azurerm_postgresql_flexible_server_database" "smn" {
  name      = "smn"
  server_id = azurerm_postgresql_flexible_server.main.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

resource "azurerm_postgresql_flexible_server_configuration" "extensions" {
  name      = "azure.extensions"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "uuid-ossp,pgcrypto"
}

# ───────────────────── Azure Cache for Redis ─────────────────────

resource "azurerm_redis_cache" "main" {
  name                          = "redis-${local.prefix}"
  resource_group_name           = azurerm_resource_group.main.name
  location                      = azurerm_resource_group.main.location
  capacity                      = var.redis_capacity
  family                        = var.redis_family
  sku_name                      = var.redis_sku
  minimum_tls_version           = "1.2"
  public_network_access_enabled = false
  redis_version                 = "6"
  tags                          = local.tags

  redis_configuration {
    maxmemory_policy       = "allkeys-lru"
    maxmemory_reserved     = 50
    maxfragmentationmemory_reserved = 50
  }
}

resource "azurerm_private_endpoint" "redis" {
  name                = "pe-redis-${local.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  subnet_id           = azurerm_subnet.redis.id
  tags                = local.tags

  private_service_connection {
    name                           = "redis-connection"
    private_connection_resource_id = azurerm_redis_cache.main.id
    is_manual_connection           = false
    subresource_names              = ["redisCache"]
  }
}

# ───────────────────── Observability ─────────────────────

resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-${local.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "PerGB2018"
  retention_in_days   = 90
  tags                = local.tags
}

resource "azurerm_application_insights" "main" {
  name                = "appi-${local.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  workspace_id        = azurerm_log_analytics_workspace.main.id
  application_type    = "web"
  tags                = local.tags
}

# ───────────────────── Container Apps ─────────────────────

resource "azurerm_container_app_environment" "main" {
  name                       = "cae-${local.prefix}"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  infrastructure_subnet_id   = azurerm_subnet.app.id
  tags                       = local.tags
}

resource "azurerm_container_app" "api" {
  name                         = "ca-api-${local.prefix}"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"
  tags                         = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  template {
    min_replicas = var.environment == "production" ? 2 : 1
    max_replicas = 10

    container {
      name   = "smn-api"
      image  = "${azurerm_container_registry.main.login_server}/smn:latest"
      cpu    = var.app_cpu
      memory = var.app_memory

      env {
        name  = "SMN_DATABASE_URL"
        value = "postgresql+asyncpg://smnadmin:${var.db_password}@${azurerm_postgresql_flexible_server.main.fqdn}/smn?sslmode=require"
      }
      env {
        name  = "SMN_REDIS_URL"
        value = "rediss://:${azurerm_redis_cache.main.primary_access_key}@${azurerm_redis_cache.main.hostname}:6380/0"
      }
      env {
        name  = "SMN_SECRET_KEY"
        value = var.smn_secret_key
      }
      env {
        name  = "SMN_ENVIRONMENT"
        value = var.environment
      }
      env {
        name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = azurerm_application_insights.main.connection_string
      }

      liveness_probe {
        transport = "HTTP"
        path      = "/api/v1/health"
        port      = 8000
      }

      readiness_probe {
        transport = "HTTP"
        path      = "/api/v1/health"
        port      = 8000
      }

      startup_probe {
        transport        = "HTTP"
        path             = "/api/v1/health"
        port             = 8000
        failure_count_threshold = 10
      }
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    transport        = "http"

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }
}

# Celery worker (no ingress)
resource "azurerm_container_app" "worker" {
  name                         = "ca-worker-${local.prefix}"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"
  tags                         = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  template {
    min_replicas = var.environment == "production" ? 2 : 1
    max_replicas = 8

    container {
      name    = "smn-worker"
      image   = "${azurerm_container_registry.main.login_server}/smn:latest"
      cpu     = var.app_cpu
      memory  = var.app_memory
      command = ["celery", "-A", "smn.worker", "worker", "--loglevel=info", "--concurrency=4"]

      env {
        name  = "SMN_DATABASE_URL"
        value = "postgresql+asyncpg://smnadmin:${var.db_password}@${azurerm_postgresql_flexible_server.main.fqdn}/smn?sslmode=require"
      }
      env {
        name  = "SMN_REDIS_URL"
        value = "rediss://:${azurerm_redis_cache.main.primary_access_key}@${azurerm_redis_cache.main.hostname}:6380/0"
      }
      env {
        name  = "SMN_SECRET_KEY"
        value = var.smn_secret_key
      }
      env {
        name  = "SMN_ENVIRONMENT"
        value = var.environment
      }
    }
  }
}
