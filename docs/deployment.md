# SMN Deployment Guide

This guide covers deploying SMN to production environments. SMN supports three deployment models — all running the same software.

| Model | Best For | Who Operates |
|-------|----------|--------------|
| Multi-tenant SaaS | Mid-market, SaaS integrators | SMN team |
| Single-tenant VPC | Regulated enterprise (banking, healthcare) | SMN team in customer cloud |
| On-premises | Government, defense, sovereignty requirements | Customer |

---

## Prerequisites

- Docker 24+ and Docker Compose v2
- PostgreSQL 16+ (managed or self-hosted)
- Redis 7+ (managed or self-hosted)
- TLS certificate (Let's Encrypt, ACM, or equivalent)
- At least one LLM provider API key (Anthropic, OpenAI, Azure, or Google)

---

## 1. Environment Configuration

Copy `.env.example` to `.env` and configure all required values:

```bash
cp .env.example .env
```

### Critical Production Settings

```bash
# MUST change from default — use: python -c "import secrets; print(secrets.token_urlsafe(64))"
SMN_SECRET_KEY=<generated-64-byte-key>

# PostgreSQL (never use SQLite in production)
SMN_DATABASE_URL=postgresql+asyncpg://smn:<password>@<host>:5432/smn

# Redis
SMN_REDIS_URL=redis://<host>:6379/0
SMN_TASK_QUEUE_BACKEND=redis://<host>:6379/1

# Stripe (required for billing)
SMN_STRIPE_SECRET_KEY=sk_live_...
SMN_STRIPE_WEBHOOK_SECRET=whsec_...
SMN_STRIPE_PRICE_ID_CORE=price_...
SMN_STRIPE_PRICE_ID_GROWTH=price_...
SMN_STRIPE_PRICE_ID_USAGE=price_...

# LLM provider (at least one)
ANTHROPIC_API_KEY=sk-ant-...
```

### Security Checklist Before Deployment

- [ ] `SMN_SECRET_KEY` is a cryptographically random 64+ character string
- [ ] Database password is strong and unique
- [ ] Stripe keys are live (not test) keys
- [ ] LLM API keys have appropriate spending limits set at the provider
- [ ] `.env` file is not committed to version control
- [ ] Database is not publicly accessible (private subnet / VPC)
- [ ] Redis is not publicly accessible (no bind to 0.0.0.0 without auth)

---

## 2. Database Setup

### Option A: Managed PostgreSQL (Recommended)

| Provider | Service | Recommended Tier |
|----------|---------|-----------------|
| AWS | RDS PostgreSQL 16 | db.r6g.large |
| Azure | Azure Database for PostgreSQL Flexible | Standard_D2s_v3 |
| GCP | Cloud SQL PostgreSQL 16 | db-custom-2-8192 |

Create the database and user:

```sql
CREATE DATABASE smn;
CREATE USER smn WITH ENCRYPTED PASSWORD '<strong-password>';
GRANT ALL PRIVILEGES ON DATABASE smn TO smn;
```

### Option B: Docker Compose PostgreSQL

For single-server deployments, the included `docker-compose.yml` runs PostgreSQL:

```bash
docker compose up -d postgres
```

**Important:** Change the default credentials in `docker-compose.yml` for production:

```yaml
environment:
  POSTGRES_USER: smn
  POSTGRES_PASSWORD: <strong-password>  # Change this
  POSTGRES_DB: smn
```

### Apply Migrations

```bash
# From the project root (or inside the container)
alembic upgrade head
```

Verify:

```bash
alembic current
# Should show: eac278d89172 (head)
```

---

## 3. Application Deployment

### Option A: Docker Compose (Single Server)

```bash
# Build and start all services
docker compose up -d

# Verify health
curl http://localhost:8000/api/v1/health
```

### Option B: AWS ECS / Fargate

1. Push Docker image to ECR:
   ```bash
   aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account>.dkr.ecr.us-east-1.amazonaws.com
   docker tag smn:latest <account>.dkr.ecr.us-east-1.amazonaws.com/smn:latest
   docker push <account>.dkr.ecr.us-east-1.amazonaws.com/smn:latest
   ```

2. Use the Terraform modules in `infra/aws/` (see below) or create an ECS service manually.

3. Configure the task definition with environment variables from `.env`.

### Option C: Azure Container Apps

1. Push to Azure Container Registry:
   ```bash
   az acr login --name <registry>
   docker tag smn:latest <registry>.azurecr.io/smn:latest
   docker push <registry>.azurecr.io/smn:latest
   ```

2. Use the Terraform modules in `infra/azure/` or deploy via Azure Portal.

### Option D: Kubernetes

Use the GCP marketplace Kubernetes manifests in `marketplace/gcp/marketplace-listing.json` as a starting point, or create your own:

```bash
kubectl create namespace smn
kubectl create secret generic smn-env --from-env-file=.env -n smn
kubectl apply -f k8s/ -n smn
```

---

## 4. Reverse Proxy & TLS

**Never expose the SMN API server directly to the internet.**

### Caddy (Simplest)

```
smn.example.com {
    reverse_proxy localhost:8000
}
```

### Nginx

```nginx
server {
    listen 443 ssl http2;
    server_name smn.example.com;

    ssl_certificate /etc/letsencrypt/live/smn.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/smn.example.com/privkey.pem;

    # SSE streaming support
    proxy_buffering off;
    proxy_cache off;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE support
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        chunked_transfer_encoding off;
    }
}
```

### AWS ALB

Configure the target group with:
- Health check path: `/api/v1/health`
- Health check interval: 30 seconds
- Idle timeout: 300 seconds (for SSE streaming)
- Stickiness: disabled (app is stateless)

---

## 5. Post-Deployment Verification

```bash
# 1. Health check
curl https://smn.example.com/api/v1/health

# 2. Bootstrap first tenant
curl -X POST https://smn.example.com/api/v1/auth/bootstrap \
  -H "Content-Type: application/json" \
  -d '{"tenant_name": "my-org", "key_name": "admin"}'
# Save the returned API key

# 3. Create an agent
curl -X POST https://smn.example.com/api/v1/agents \
  -H "X-API-Key: smn_..." \
  -H "Content-Type: application/json" \
  -d '{"name": "test-agent", "model": "anthropic/claude-sonnet-4-6-20250415"}'

# 4. Run a task
curl -X POST https://smn.example.com/api/v1/tasks \
  -H "X-API-Key: smn_..." \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "<agent-id>", "input": "What is 2+2?"}'

# 5. Verify audit chain
curl https://smn.example.com/api/v1/audit/verify \
  -H "X-API-Key: smn_..."
```

---

## 6. Stripe Webhook Configuration

1. In Stripe Dashboard → Developers → Webhooks, create an endpoint:
   - URL: `https://smn.example.com/api/v1/billing/webhook`
   - Events: `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.paid`, `invoice.payment_failed`

2. Copy the webhook signing secret to `SMN_STRIPE_WEBHOOK_SECRET` in `.env`.

3. Restart the application.

---

## 7. Scaling

### Horizontal Scaling

SMN is stateless — scale by running multiple API server instances behind a load balancer:

```bash
# Docker Compose
docker compose up -d --scale smn=3

# ECS
aws ecs update-service --desired-count 3 --service smn --cluster smn-prod
```

### Celery Workers

Scale async task processing independently:

```bash
# More workers
docker compose up -d --scale worker=4

# Or adjust concurrency per worker
celery -A smn.worker worker --concurrency=8
```

### Database Scaling

- **Read replicas:** Add PostgreSQL read replicas for audit log queries and usage analytics.
- **Connection pooling:** Use PgBouncer in front of PostgreSQL for connection management.
- **Partitioning:** For high-volume tenants, consider partitioning `audit_entries` by `tenant_id` or `timestamp`.

---

## 8. Monitoring

See `docs/monitoring.md` for full OpenTelemetry configuration, Prometheus metrics, and alerting rules.

Key health indicators:
- API response time (p99 < 200ms for CRUD, < 30s for task execution)
- Task success rate (> 95%)
- Database connection pool utilization (< 80%)
- Redis memory usage
- Celery queue depth (alert if > 1000 pending tasks)
- Audit chain integrity (periodic `smn audit verify`)

---

## 9. Operational Runbook

### Restart Services

```bash
docker compose restart smn worker
```

### View Logs

```bash
docker compose logs -f smn
docker compose logs -f worker
```

### Emergency Kill Switch

Disable all agent execution for a tenant:

```bash
curl -X PATCH https://smn.example.com/api/v1/admin/tenants/<tenant-id> \
  -H "X-API-Key: smn_admin_..." \
  -H "Content-Type: application/json" \
  -d '{"is_active": false}'
```

### Database Recovery

See `docs/backup-dr.md` for backup procedures, point-in-time recovery, and disaster recovery playbook.

### Rotate API Keys

```bash
# Create new key
curl -X POST https://smn.example.com/api/v1/auth/keys \
  -H "X-API-Key: smn_old_key..." \
  -d '{"name": "rotated-key"}'

# Revoke old key
curl -X DELETE https://smn.example.com/api/v1/auth/keys/<old-key-id> \
  -H "X-API-Key: smn_new_key..."
```

### Rotate SMN_SECRET_KEY

1. Generate new key: `python -c "import secrets; print(secrets.token_urlsafe(64))"`
2. Update `.env` with new key
3. Restart all services: `docker compose restart`
4. Existing API keys remain valid (they use SHA-256, not the secret key)
