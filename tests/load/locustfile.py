"""SMN Load Testing — Locust-based performance validation.

Install:  pip install locust
Run:      locust -f tests/load/locustfile.py --host=http://localhost:8000
Web UI:   http://localhost:8089

For CI headless mode:
  locust -f tests/load/locustfile.py --host=http://localhost:8000 \
    --headless -u 100 -r 10 --run-time 5m \
    --csv=results/load-test
"""

from __future__ import annotations

import json
import os
import random
import string

from locust import HttpUser, between, task, events


# ── Configuration ─────────────────────────────────────────────

API_KEY = os.environ.get("SMN_LOAD_TEST_API_KEY", "smn_test_key")
BASE_PATH = "/api/v1"


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {API_KEY}"}


def _random_name(prefix: str = "load") -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{prefix}-{suffix}"


# ── User Behaviors ────────────────────────────────────────────


class HealthCheckUser(HttpUser):
    """Lightweight user that only checks health — use to validate baseline."""

    weight = 1
    wait_time = between(1, 3)

    @task
    def health(self):
        self.client.get(f"{BASE_PATH}/health")


class AgentOperationsUser(HttpUser):
    """Simulates typical agent CRUD operations."""

    weight = 3
    wait_time = between(1, 5)

    def on_start(self):
        self.agent_ids: list[str] = []
        self.headers = _auth_headers()

    @task(5)
    def list_agents(self):
        self.client.get(f"{BASE_PATH}/agents", headers=self.headers)

    @task(3)
    def create_agent(self):
        payload = {
            "name": _random_name("agent"),
            "model": random.choice(["gpt-4o", "claude-3-5-sonnet", "gpt-4o-mini"]),
            "system_prompt": "You are a load test agent.",
            "risk_level": random.choice(["minimal", "limited"]),
        }
        with self.client.post(
            f"{BASE_PATH}/agents", json=payload, headers=self.headers,
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 201):
                data = resp.json()
                agent_id = data.get("id") or data.get("agent_id")
                if agent_id:
                    self.agent_ids.append(agent_id)
                resp.success()
            elif resp.status_code == 429:
                resp.success()  # Rate limiting is expected under load
            else:
                resp.failure(f"Unexpected {resp.status_code}")

    @task(2)
    def get_agent(self):
        if not self.agent_ids:
            return
        agent_id = random.choice(self.agent_ids)
        self.client.get(f"{BASE_PATH}/agents/{agent_id}", headers=self.headers)


class TaskExecutionUser(HttpUser):
    """Simulates submitting and polling tasks — the core workload."""

    weight = 5
    wait_time = between(2, 8)

    def on_start(self):
        self.headers = _auth_headers()
        self.task_ids: list[str] = []

    @task(4)
    def submit_task(self):
        payload = {
            "input": f"Load test task {_random_name('task')}. Respond with a short summary.",
        }
        # Pick a random agent name or use default
        with self.client.post(
            f"{BASE_PATH}/tasks",
            json=payload,
            headers=self.headers,
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 201, 202):
                data = resp.json()
                task_id = data.get("id") or data.get("task_id")
                if task_id:
                    self.task_ids.append(task_id)
                resp.success()
            elif resp.status_code == 429:
                resp.success()  # Expected rate limiting
            else:
                resp.failure(f"Unexpected {resp.status_code}")

    @task(3)
    def poll_task(self):
        if not self.task_ids:
            return
        task_id = random.choice(self.task_ids)
        self.client.get(f"{BASE_PATH}/tasks/{task_id}", headers=self.headers)

    @task(1)
    def list_tasks(self):
        self.client.get(
            f"{BASE_PATH}/tasks",
            params={"limit": 20},
            headers=self.headers,
        )


class PolicyAndAuditUser(HttpUser):
    """Simulates compliance/governance read-heavy patterns."""

    weight = 2
    wait_time = between(3, 10)

    def on_start(self):
        self.headers = _auth_headers()

    @task(3)
    def list_policies(self):
        self.client.get(f"{BASE_PATH}/policies", headers=self.headers)

    @task(5)
    def query_audit_log(self):
        self.client.get(
            f"{BASE_PATH}/audit",
            params={"limit": 50},
            headers=self.headers,
        )


class AdminUser(HttpUser):
    """Simulates admin operations — low frequency, high importance."""

    weight = 1
    wait_time = between(10, 30)

    def on_start(self):
        self.headers = _auth_headers()

    @task
    def admin_health(self):
        self.client.get(f"{BASE_PATH}/health", headers=self.headers)


# ── Event Hooks ───────────────────────────────────────────────

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print("╔══════════════════════════════════════╗")
    print("║     SMN Load Test — Starting         ║")
    print("╚══════════════════════════════════════╝")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    stats = environment.runner.stats
    print("\n╔══════════════════════════════════════╗")
    print("║     SMN Load Test — Results          ║")
    print("╠══════════════════════════════════════╣")
    total = stats.total
    print(f"║  Requests:      {total.num_requests:>10}         ║")
    print(f"║  Failures:      {total.num_failures:>10}         ║")
    print(f"║  Avg Response:  {total.avg_response_time:>8.0f} ms       ║")
    print(f"║  P95 Response:  {total.get_response_time_percentile(0.95) or 0:>8.0f} ms       ║")
    print(f"║  P99 Response:  {total.get_response_time_percentile(0.99) or 0:>8.0f} ms       ║")
    print(f"║  RPS:           {total.current_rps:>10.1f}         ║")
    print("╚══════════════════════════════════════╝")

    # Fail CI if error rate > 5% (excluding rate-limited requests)
    if total.num_requests > 0:
        error_rate = total.num_failures / total.num_requests
        if error_rate > 0.05:
            print(f"\n❌ FAILED: Error rate {error_rate:.1%} exceeds 5% threshold")
            environment.process_exit_code = 1
