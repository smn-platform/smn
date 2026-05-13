# SMN Backup & Disaster Recovery Plan

This document defines backup procedures, recovery objectives, and disaster
recovery playbooks for production SMN deployments.

---

## 1. Recovery Objectives

| Component | RPO (Recovery Point Objective) | RTO (Recovery Time Objective) |
|-----------|-------------------------------|-------------------------------|
| PostgreSQL (primary) | 5 minutes (WAL archiving) | 30 minutes (failover) |
| PostgreSQL (catastrophic) | 24 hours (daily snapshot) | 2 hours (restore from backup) |
| Redis (cache layer) | N/A — ephemeral by design | 10 minutes (cold start) |
| Application containers | 0 (immutable images in registry) | 15 minutes (re-deploy) |
| Configuration/secrets | 0 (version-controlled / vault) | 15 minutes |
| Audit logs | 24 hours | 4 hours |

---

## 2. PostgreSQL Backup Strategy

### 2.1 Automated Backups (Managed Services)

**AWS RDS:**
- Automated daily snapshots with 30-day retention (configured in Terraform)
- Point-in-Time Recovery (PITR) enabled with 5-minute WAL granularity
- Multi-AZ standby with automatic failover (production)
- Cross-region read replicas for DR (optional — add to Terraform)

**Azure PostgreSQL Flexible Server:**
- Automated backups with 35-day retention (configured in Terraform)
- Geo-redundant backups enabled for production
- Point-in-Time Recovery to any second within retention window
- Zone-redundant high availability with automatic failover

### 2.2 Manual Backup Procedures

#### On-Demand Snapshot (AWS)
```bash
aws rds create-db-snapshot \
  --db-instance-identifier smn-production \
  --db-snapshot-identifier smn-manual-$(date +%Y%m%d-%H%M%S)
```

#### On-Demand Snapshot (Azure)
Azure Flexible Server does not support manual snapshots; use PITR instead
or export with `pg_dump`:

```bash
pg_dump "postgresql://smnadmin@psql-smn-production.postgres.database.azure.com/smn?sslmode=require" \
  --format=custom \
  --file=smn-backup-$(date +%Y%m%d-%H%M%S).dump
```

#### Self-Hosted (Docker Compose)
```bash
# Full backup
docker exec smn-postgres pg_dump -U smn -Fc smn > smn-$(date +%Y%m%d).dump

# WAL archiving for PITR (add to postgresql.conf)
# archive_mode = on
# archive_command = 'cp %p /backups/wal/%f'
```

### 2.3 Backup Verification

Run weekly backup verification:

```bash
#!/bin/bash
# scripts/verify-backup.sh
set -euo pipefail

BACKUP_FILE="$1"
VERIFY_DB="smn_verify_$(date +%s)"

echo "=== Restoring backup to verification database ==="
createdb "$VERIFY_DB"
pg_restore --dbname="$VERIFY_DB" --no-owner "$BACKUP_FILE"

echo "=== Running integrity checks ==="
psql "$VERIFY_DB" -c "SELECT COUNT(*) AS tenant_count FROM tenants;"
psql "$VERIFY_DB" -c "SELECT COUNT(*) AS agent_count FROM agents;"
psql "$VERIFY_DB" -c "SELECT COUNT(*) AS audit_count FROM audit_entries;"
psql "$VERIFY_DB" -c "SELECT COUNT(*) AS task_count FROM tasks;"
psql "$VERIFY_DB" -c "
  SELECT schemaname, tablename
  FROM pg_tables
  WHERE schemaname = 'public'
  ORDER BY tablename;
"

echo "=== Cleanup ==="
dropdb "$VERIFY_DB"
echo "Backup verification PASSED"
```

---

## 3. Redis Recovery

Redis in SMN is used as a **cache and task broker** — not as a primary data store.
All persistent state lives in PostgreSQL. Redis can be rebuilt from scratch.

### Recovery Procedure
1. If Redis becomes unavailable, SMN will return errors for task submission
2. Restart or replace the Redis instance
3. No data migration is needed — Celery will re-enqueue pending tasks
4. In-flight tasks will be retried automatically by Celery's `acks_late` setting

### Redis Persistence Settings (Self-Hosted)
```conf
# redis.conf — recommended for production
appendonly yes
appendfsync everysec
save 900 1
save 300 10
save 60 10000
```

---

## 4. Application Recovery

### Container Image Recovery
All images are stored in immutable registries (ECR/ACR) with scan-on-push.
To recover:

```bash
# AWS
docker pull <account>.dkr.ecr.<region>.amazonaws.com/smn:<version-tag>

# Azure
docker pull <registry>.azurecr.io/smn:<version-tag>
```

### Configuration Recovery
All configuration is stored in:
1. **Terraform state** — remote backend (S3/Azure Blob) with versioning
2. **Environment variables** — documented in `.env.example`
3. **Secrets** — stored in AWS Secrets Manager / Azure Key Vault (recommended)

---

## 5. Disaster Recovery Playbooks

### 5.1 Database Failure (Single-AZ / Unplanned)

**Symptoms:** Application returns 500 errors, logs show `connection refused` to PostgreSQL.

**AWS RDS — Automatic Failover (Multi-AZ):**
1. RDS automatically promotes standby (typically 60-120 seconds)
2. Application reconnects via the same DNS endpoint
3. Verify: `aws rds describe-db-instances --db-instance-identifier smn-production`
4. Post-incident: check replication status, review CloudWatch metrics

**AWS RDS — Manual PITR:**
```bash
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier smn-production \
  --target-db-instance-identifier smn-recovery-$(date +%s) \
  --restore-time "2025-01-15T10:30:00Z" \
  --db-instance-class db.r6g.large \
  --multi-az
```

**Azure — Automatic Failover (Zone-Redundant):**
1. Flexible Server fails over to standby (typically 60-120 seconds)
2. Application reconnects via same FQDN
3. Verify: `az postgres flexible-server show --name psql-smn-production --resource-group rg-smn-production`

**Azure — Manual PITR:**
```bash
az postgres flexible-server restore \
  --resource-group rg-smn-production \
  --name psql-smn-recovery \
  --source-server psql-smn-production \
  --restore-time "2025-01-15T10:30:00Z"
```

### 5.2 Complete Region Failure

**Pre-requisites:**
- Cross-region read replica (AWS) or geo-redundant backup (Azure) enabled
- Terraform code parameterised for alternate region
- DNS managed via Route 53 / Azure DNS with health checks

**Procedure:**
1. **Assess**: Confirm region is down (check cloud provider status page)
2. **Activate DR region**:
   ```bash
   cd infra/aws  # or infra/azure
   terraform workspace select dr
   terraform apply -var="aws_region=us-west-2" -var="environment=production"
   ```
3. **Promote database replica** (AWS):
   ```bash
   aws rds promote-read-replica --db-instance-identifier smn-dr-replica
   ```
4. **Restore database** (Azure):
   ```bash
   az postgres flexible-server geo-restore \
     --resource-group rg-smn-dr \
     --name psql-smn-dr \
     --source-server "/subscriptions/.../psql-smn-production" \
     --location westus2
   ```
5. **Deploy application**: Push latest image to DR region registry, deploy via Terraform
6. **Update DNS**: Point domain to DR region load balancer
7. **Verify**: Run smoke tests from `docs/deployment.md` post-deployment checklist
8. **Notify**: Inform customers via status page

**Estimated DR activation time:** 30-60 minutes (with pre-provisioned infrastructure)

### 5.3 Data Corruption / Accidental Deletion

1. **Stop writes**: Activate kill switch to prevent further corruption
   ```bash
   curl -X POST https://smn.example.com/api/v1/admin/kill-switch \
     -H "Authorization: Bearer $ADMIN_KEY"
   ```
2. **Identify scope**: Query audit logs for recent destructive operations
   ```sql
   SELECT * FROM audit_entries
   WHERE timestamp > NOW() - INTERVAL '1 hour'
   ORDER BY timestamp DESC;
   ```
3. **PITR restore**: Restore to point before corruption (see 5.1)
4. **Selective restore** (if only specific tables affected):
   ```bash
   # Dump specific table from PITR-restored instance
   pg_dump -h recovery-instance -U smn -t affected_table -Fc smn > table.dump
   # Restore into production
   pg_restore --dbname=smn --data-only --table=affected_table table.dump
   ```
5. **Deactivate kill switch** and verify application health

### 5.4 Security Breach

1. **Rotate all credentials immediately:**
   ```bash
   # Rotate SMN secret key
   python -c "import secrets; print(secrets.token_urlsafe(64))"
   # Update in environment / secrets manager

   # Rotate database password
   # AWS: aws rds modify-db-instance --master-user-password <new>
   # Azure: az postgres flexible-server update --admin-password <new>

   # Invalidate all API keys
   psql smn -c "UPDATE api_keys SET revoked_at = NOW();"
   ```
2. **Review audit logs**: Check for unauthorized access patterns
3. **Snapshot current state**: For forensic analysis before remediation
4. **Patch vulnerability**: Deploy fix, then resume operations
5. **Notify**: Follow SECURITY.md disclosure process

---

## 6. Backup Schedule Summary

| What | How | Frequency | Retention | Verified |
|------|-----|-----------|-----------|----------|
| PostgreSQL automated snapshot | RDS/Flexible Server | Daily | 30-35 days | Weekly |
| PostgreSQL WAL / PITR | Continuous | Continuous | 30-35 days | Monthly |
| PostgreSQL manual snapshot | `scripts/verify-backup.sh` | Weekly | 90 days | At creation |
| Terraform state | S3/Blob versioning | On change | Indefinite | Monthly |
| Container images | ECR/ACR | On push | Indefinite (tagged) | On deploy |
| Audit log export | CloudWatch/Log Analytics | Daily | 1 year | Quarterly |

---

## 7. DR Testing Schedule

| Test Type | Frequency | Description |
|-----------|-----------|-------------|
| Backup restore verification | Weekly | Automated script restores and validates |
| Single-service failover | Monthly | Stop one component, verify auto-recovery |
| Full region failover | Quarterly | Activate DR region, full smoke test |
| Tabletop exercise | Semi-annually | Walk through each playbook with team |

---

## 8. Responsible Parties

| Role | Responsibility |
|------|---------------|
| On-call engineer | Execute playbooks, initial triage |
| Platform lead | Approve DR region activation, coordinate response |
| Security team | Lead breach response (5.4), audit log review |
| CTO | Approve comms to customers, final sign-off on recovery |
