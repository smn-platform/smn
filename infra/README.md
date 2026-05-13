# SMN Infrastructure as Code

Production-ready Terraform modules for deploying SMN on AWS and Azure.

## Directory Structure

```
infra/
├── aws/
│   ├── main.tf          # VPC, ECS, RDS, ElastiCache, ALB
│   ├── variables.tf     # Input variables
│   └── outputs.tf       # Connection strings, endpoints
└── azure/
    ├── main.tf          # VNET, Container Apps, PostgreSQL, Redis
    ├── variables.tf     # Input variables
    └── outputs.tf       # Connection strings, endpoints
```

## Usage

### AWS

```bash
cd infra/aws
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values
terraform init
terraform plan
terraform apply
```

### Azure

```bash
cd infra/azure
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values
terraform init
terraform plan
terraform apply
```

## What Gets Created

### AWS
- VPC with public/private subnets across 2 AZs
- ECS Fargate cluster running SMN server + Celery worker
- RDS PostgreSQL 16 (Multi-AZ)
- ElastiCache Redis 7
- Application Load Balancer with TLS
- ECR repository for Docker images
- CloudWatch log groups
- Security groups with least-privilege rules

### Azure
- Virtual Network with subnets
- Container Apps environment running SMN server + worker
- Azure Database for PostgreSQL Flexible Server
- Azure Cache for Redis
- Container Registry
- Log Analytics workspace

## Security Notes

- All databases are deployed in private subnets (no public access)
- All traffic between services stays within the VPC/VNET
- TLS is enforced on all external endpoints
- Secrets are passed via environment variables (use AWS Secrets Manager or Azure Key Vault for production)
- Default PostgreSQL credentials must be changed before deployment
