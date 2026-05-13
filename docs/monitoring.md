# SMN Monitoring & Alerting Guide

This document defines the observability stack for production SMN deployments.
SMN ships with built-in OpenTelemetry instrumentation — this guide shows how to
collect, visualize, and alert on that telemetry.

---

## Architecture

```
SMN API / Workers
    │  (OTLP gRPC :4317)
    ▼
OpenTelemetry Collector
    ├──► Prometheus  ──► Grafana dashboards
    ├──► Loki        ──► Grafana log explorer
    └──► Jaeger      ──► Distributed traces
             │
         AlertManager ──► PagerDuty / Slack / Email
```

---

## 1. OpenTelemetry Collector Configuration

Save as `otel-collector-config.yaml`:

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: "0.0.0.0:4317"
      http:
        endpoint: "0.0.0.0:4318"

processors:
  batch:
    send_batch_size: 1024
    timeout: 5s
  memory_limiter:
    check_interval: 1s
    limit_mib: 512
    spike_limit_mib: 128
  resource:
    attributes:
      - key: service.namespace
        value: smn
        action: upsert

exporters:
  prometheus:
    endpoint: "0.0.0.0:8889"
    namespace: smn
    resource_to_telemetry_conversion:
      enabled: true
  otlp/jaeger:
    endpoint: "jaeger:4317"
    tls:
      insecure: true
  loki:
    endpoint: "http://loki:3100/loki/api/v1/push"

extensions:
  health_check:
    endpoint: "0.0.0.0:13133"
  zpages:
    endpoint: "0.0.0.0:55679"

service:
  extensions: [health_check, zpages]
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [memory_limiter, batch, resource]
      exporters: [prometheus]
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch, resource]
      exporters: [otlp/jaeger]
    logs:
      receivers: [otlp]
      processors: [memory_limiter, batch, resource]
      exporters: [loki]
```

### Docker Compose Addition

Add to `docker-compose.yml`:

```yaml
  otel-collector:
    image: otel/opentelemetry-collector-contrib:0.96.0
    command: ["--config=/etc/otel-collector-config.yaml"]
    volumes:
      - ./monitoring/otel-collector-config.yaml:/etc/otel-collector-config.yaml:ro
    ports:
      - "4317:4317"   # OTLP gRPC
      - "4318:4318"   # OTLP HTTP
      - "8889:8889"   # Prometheus scrape
      - "13133:13133" # Health check
    depends_on:
      - jaeger
    restart: unless-stopped

  prometheus:
    image: prom/prometheus:v2.51.0
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./monitoring/alerts.yml:/etc/prometheus/alerts.yml:ro
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"
    command:
      - "--config.file=/etc/prometheus/prometheus.yml"
      - "--storage.tsdb.retention.time=30d"
      - "--web.enable-lifecycle"
    restart: unless-stopped

  grafana:
    image: grafana/grafana:10.4.0
    volumes:
      - ./monitoring/grafana-datasources.yml:/etc/grafana/provisioning/datasources/datasources.yml:ro
      - ./monitoring/grafana-dashboards.yml:/etc/grafana/provisioning/dashboards/dashboards.yml:ro
      - ./monitoring/dashboards:/var/lib/grafana/dashboards:ro
      - grafana_data:/var/lib/grafana
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: "${GRAFANA_ADMIN_PASSWORD:-changeme}"
      GF_USERS_ALLOW_SIGN_UP: "false"
    restart: unless-stopped

  jaeger:
    image: jaegertracing/all-in-one:1.55
    ports:
      - "16686:16686" # Jaeger UI
      - "4317"        # OTLP gRPC (internal)
    environment:
      COLLECTOR_OTLP_ENABLED: "true"
    restart: unless-stopped

  loki:
    image: grafana/loki:2.9.5
    ports:
      - "3100:3100"
    volumes:
      - loki_data:/loki
    restart: unless-stopped

volumes:
  prometheus_data:
  grafana_data:
  loki_data:
```

---

## 2. Prometheus Configuration

Save as `monitoring/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "alerts.yml"

alerting:
  alertmanagers:
    - static_configs:
        - targets: ["alertmanager:9093"]

scrape_configs:
  - job_name: "otel-collector"
    static_configs:
      - targets: ["otel-collector:8889"]

  - job_name: "smn-api"
    metrics_path: /metrics
    static_configs:
      - targets: ["smn:8000"]

  - job_name: "redis"
    static_configs:
      - targets: ["redis-exporter:9121"]

  - job_name: "postgres"
    static_configs:
      - targets: ["postgres-exporter:9187"]
```

---

## 3. Alert Rules

Save as `monitoring/alerts.yml`:

```yaml
groups:
  # ──── API Health ────
  - name: smn_api
    rules:
      - alert: SMNApiDown
        expr: up{job="smn-api"} == 0
        for: 1m
        labels:
          severity: critical
          team: platform
        annotations:
          summary: "SMN API is down"
          description: "The SMN API target has been unreachable for >1 minute."
          runbook: "docs/deployment.md#restart-services"

      - alert: SMNHighErrorRate
        expr: |
          sum(rate(http_server_request_duration_seconds_count{http_status_code=~"5.."}[5m]))
          /
          sum(rate(http_server_request_duration_seconds_count[5m]))
          > 0.05
        for: 5m
        labels:
          severity: critical
          team: platform
        annotations:
          summary: "SMN error rate >5%"
          description: "{{ $value | humanizePercentage }} of requests returning 5xx over last 5 minutes."

      - alert: SMNHighLatencyP99
        expr: |
          histogram_quantile(0.99,
            sum(rate(http_server_request_duration_seconds_bucket[5m])) by (le)
          ) > 2
        for: 10m
        labels:
          severity: warning
          team: platform
        annotations:
          summary: "SMN P99 latency >2s"

      - alert: SMNHighLatencyP50
        expr: |
          histogram_quantile(0.50,
            sum(rate(http_server_request_duration_seconds_bucket[5m])) by (le)
          ) > 0.5
        for: 10m
        labels:
          severity: warning
          team: platform
        annotations:
          summary: "SMN P50 latency >500ms"

  # ──── Task Execution ────
  - name: smn_tasks
    rules:
      - alert: SMNTaskQueueBacklog
        expr: smn_celery_queue_length > 100
        for: 5m
        labels:
          severity: warning
          team: platform
        annotations:
          summary: "Celery task queue backlog >100"
          description: "Current queue length: {{ $value }}. Consider scaling workers."

      - alert: SMNTaskFailureRate
        expr: |
          sum(rate(smn_task_failures_total[10m]))
          /
          sum(rate(smn_task_completions_total[10m]))
          > 0.1
        for: 10m
        labels:
          severity: critical
          team: platform
        annotations:
          summary: "Task failure rate >10%"

      - alert: SMNTaskStuck
        expr: smn_task_running_duration_seconds > 300
        for: 1m
        labels:
          severity: warning
          team: platform
        annotations:
          summary: "Task running for >5 minutes"
          description: "Task may be stuck. Check task ID: {{ $labels.task_id }}"

  # ──── Database ────
  - name: smn_database
    rules:
      - alert: PostgreSQLDown
        expr: pg_up == 0
        for: 1m
        labels:
          severity: critical
          team: platform
        annotations:
          summary: "PostgreSQL is unreachable"

      - alert: PostgreSQLHighConnections
        expr: |
          sum(pg_stat_activity_count)
          /
          sum(pg_settings_max_connections)
          > 0.8
        for: 5m
        labels:
          severity: warning
          team: platform
        annotations:
          summary: "PostgreSQL connection pool >80% utilised"

      - alert: PostgreSQLSlowQueries
        expr: rate(pg_stat_activity_max_tx_duration{state="active"}[5m]) > 60
        for: 5m
        labels:
          severity: warning
          team: platform
        annotations:
          summary: "Long-running PostgreSQL transactions detected"

      - alert: PostgreSQLReplicationLag
        expr: pg_replication_lag > 30
        for: 5m
        labels:
          severity: critical
          team: platform
        annotations:
          summary: "PostgreSQL replication lag >30s"

  # ──── Redis ────
  - name: smn_redis
    rules:
      - alert: RedisDown
        expr: redis_up == 0
        for: 1m
        labels:
          severity: critical
          team: platform
        annotations:
          summary: "Redis is unreachable"

      - alert: RedisHighMemory
        expr: redis_memory_used_bytes / redis_memory_max_bytes > 0.85
        for: 5m
        labels:
          severity: warning
          team: platform
        annotations:
          summary: "Redis memory usage >85%"

      - alert: RedisHighEvictionRate
        expr: rate(redis_evicted_keys_total[5m]) > 10
        for: 5m
        labels:
          severity: warning
          team: platform
        annotations:
          summary: "Redis evicting >10 keys/s"

  # ──── Infrastructure ────
  - name: smn_infra
    rules:
      - alert: HighCPUUsage
        expr: |
          100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 85
        for: 10m
        labels:
          severity: warning
          team: platform
        annotations:
          summary: "CPU usage >85% on {{ $labels.instance }}"

      - alert: HighMemoryUsage
        expr: |
          (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100 > 90
        for: 5m
        labels:
          severity: critical
          team: platform
        annotations:
          summary: "Memory usage >90% on {{ $labels.instance }}"

      - alert: DiskSpaceLow
        expr: |
          (1 - node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}) * 100 > 85
        for: 10m
        labels:
          severity: warning
          team: platform
        annotations:
          summary: "Disk usage >85% on {{ $labels.instance }}"

      - alert: SSLCertExpiring
        expr: probe_ssl_earliest_cert_expiry - time() < 604800
        for: 1h
        labels:
          severity: warning
          team: platform
        annotations:
          summary: "SSL certificate expires in <7 days"

  # ──── Security ────
  - name: smn_security
    rules:
      - alert: SMNKillSwitchActivated
        expr: smn_kill_switch_active == 1
        for: 0m
        labels:
          severity: critical
          team: security
        annotations:
          summary: "SMN kill switch has been activated"
          description: "All agent executions are halted. Check audit logs."

      - alert: SMNHighAuthFailures
        expr: rate(smn_auth_failures_total[5m]) > 5
        for: 5m
        labels:
          severity: warning
          team: security
        annotations:
          summary: "High authentication failure rate (>5/s)"
          description: "Possible brute force attempt. Source IPs should be reviewed."

      - alert: SMNGuardrailViolations
        expr: rate(smn_guardrail_violations_total[10m]) > 1
        for: 10m
        labels:
          severity: warning
          team: security
        annotations:
          summary: "Elevated guardrail violations"
```

---

## 4. Grafana Data Sources

Save as `monitoring/grafana-datasources.yml`:

```yaml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: false

  - name: Jaeger
    type: jaeger
    access: proxy
    url: http://jaeger:16686
    editable: false

  - name: Loki
    type: loki
    access: proxy
    url: http://loki:3100
    editable: false
```

---

## 5. Grafana Dashboard Provisioning

Save as `monitoring/grafana-dashboards.yml`:

```yaml
apiVersion: 1
providers:
  - name: SMN
    orgId: 1
    type: file
    disableDeletion: false
    updateIntervalSeconds: 30
    options:
      path: /var/lib/grafana/dashboards
      foldersFromFilesStructure: true
```

---

## 6. Key Metrics Reference

### Application Metrics (via OpenTelemetry)

| Metric | Type | Description |
|--------|------|-------------|
| `http_server_request_duration_seconds` | Histogram | API request latency |
| `http_server_active_requests` | Gauge | In-flight requests |
| `smn_task_completions_total` | Counter | Successfully completed tasks |
| `smn_task_failures_total` | Counter | Failed tasks |
| `smn_task_running_duration_seconds` | Gauge | Current task run time |
| `smn_celery_queue_length` | Gauge | Pending Celery tasks |
| `smn_auth_failures_total` | Counter | Authentication failures |
| `smn_guardrail_violations_total` | Counter | Policy violations |
| `smn_kill_switch_active` | Gauge | Kill switch state (0/1) |
| `smn_llm_request_duration_seconds` | Histogram | LLM provider latency |
| `smn_llm_tokens_total` | Counter | Token consumption |

### Infrastructure Metrics

| Metric | Source | Description |
|--------|--------|-------------|
| `pg_stat_activity_count` | postgres-exporter | Active DB connections |
| `pg_settings_max_connections` | postgres-exporter | Connection limit |
| `redis_memory_used_bytes` | redis-exporter | Redis memory |
| `redis_connected_clients` | redis-exporter | Redis clients |
| `node_cpu_seconds_total` | node-exporter | CPU time |
| `node_memory_MemAvailable_bytes` | node-exporter | Available RAM |

---

## 7. SLO Definitions

| SLI | Target | Window |
|-----|--------|--------|
| API availability (`up` probe) | 99.9% | 30 days |
| API P99 latency | < 2s | 30 days |
| API error rate (5xx) | < 0.1% | 30 days |
| Task completion rate | > 95% | 7 days |
| Database availability | 99.95% | 30 days |

---

## 8. AlertManager Configuration

Save as `monitoring/alertmanager.yml`:

```yaml
global:
  resolve_timeout: 5m

route:
  receiver: default
  group_by: [alertname, severity]
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  routes:
    - match:
        severity: critical
      receiver: pagerduty
      repeat_interval: 1h
    - match:
        team: security
      receiver: security-team
      repeat_interval: 30m

receivers:
  - name: default
    slack_configs:
      - api_url: "${SLACK_WEBHOOK_URL}"
        channel: "#smn-alerts"
        title: '{{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.summary }}{{ end }}'

  - name: pagerduty
    pagerduty_configs:
      - service_key: "${PAGERDUTY_SERVICE_KEY}"
        severity: '{{ .CommonLabels.severity }}'

  - name: security-team
    slack_configs:
      - api_url: "${SLACK_SECURITY_WEBHOOK_URL}"
        channel: "#smn-security"
    pagerduty_configs:
      - service_key: "${PAGERDUTY_SECURITY_KEY}"

inhibit_rules:
  - source_match:
      severity: critical
    target_match:
      severity: warning
    equal: [alertname]
```

---

## 9. Cloud-Specific Monitoring

### AWS (CloudWatch)

ECS Container Insights are enabled automatically by the Terraform module.
Key CloudWatch alarms to add via AWS Console or Terraform:

- **RDS**: `CPUUtilization > 80%`, `FreeStorageSpace < 5GB`, `DatabaseConnections > 80% max`
- **ElastiCache**: `EngineCPUUtilization > 70%`, `DatabaseMemoryUsagePercentage > 85%`
- **ECS**: `CPUUtilization > 80%`, `MemoryUtilization > 85%`, `RunningTaskCount < DesiredTaskCount`
- **ALB**: `HTTPCode_Target_5XX_Count > threshold`, `TargetResponseTime > 2s`

### Azure (Monitor + App Insights)

Application Insights is provisioned automatically by the Terraform module.
The `APPLICATIONINSIGHTS_CONNECTION_STRING` is injected into Container Apps.

Key Azure Monitor alerts to configure:

- **PostgreSQL**: CPU > 80%, Storage > 85%, Connection failures > 0
- **Redis**: Memory usage > 85%, Connected clients > 80% max, Cache misses spike
- **Container Apps**: Replica count < minimum, Restart count > 3/hour
- **App Insights**: Failed requests > 5%, Response time P99 > 2s

---

## 10. On-Call Runbook Quick Reference

| Alert | First Response | Escalation |
|-------|---------------|------------|
| `SMNApiDown` | Check ECS/Container Apps status, restart if needed | Page on-call engineer |
| `SMNHighErrorRate` | Check application logs for stack traces | Investigate + rollback if deployment-related |
| `PostgreSQLDown` | Check RDS/Flexible Server status | Initiate failover if available |
| `RedisDown` | Check ElastiCache/Redis Cache status | Failover to replica |
| `SMNKillSwitchActivated` | Check audit logs for who activated | Security team review required |
| `SMNHighAuthFailures` | Check source IPs, consider rate limiting | Block IPs if confirmed attack |
| `DiskSpaceLow` | Check log rotation, clean old data | Expand storage |
| `SMNTaskStuck` | Check task logs, cancel if needed | Investigate root cause |
