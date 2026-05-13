output "alb_dns_name" {
  description = "ALB DNS name (point your domain CNAME here)"
  value       = aws_lb.main.dns_name
}

output "ecr_repository_url" {
  description = "ECR repository URL for Docker pushes"
  value       = aws_ecr_repository.main.repository_url
}

output "database_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = aws_db_instance.main.endpoint
  sensitive   = true
}

output "redis_endpoint" {
  description = "ElastiCache Redis primary endpoint"
  value       = aws_elasticache_replication_group.main.primary_endpoint_address
  sensitive   = true
}

output "database_url" {
  description = "Full SMN_DATABASE_URL for .env"
  value       = "postgresql+asyncpg://smn:${var.db_password}@${aws_db_instance.main.endpoint}/smn"
  sensitive   = true
}
