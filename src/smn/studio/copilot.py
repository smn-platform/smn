"""Plain-English workflow draft planner for Studio.

This is intentionally deterministic for the first product milestone: it gives
users an immediate draft without requiring paid LLM credentials. The router API
can later swap this planner for an LLM-backed one while preserving the response
shape consumed by the frontend.
"""

from __future__ import annotations

import re

from smn.studio.schemas import NodeData, NodePosition, WorkflowDefinition, WorkflowEdge, WorkflowNode


def draft_workflow(prompt: str) -> tuple[str, str, WorkflowDefinition, list[str]]:
    """Return a reviewable workflow draft from a plain-English prompt."""
    clean_prompt = _compact(prompt)
    if not clean_prompt:
        raise ValueError("Describe the workflow you want to build.")

    lower = clean_prompt.lower()
    nodes: list[WorkflowNode] = []
    edges: list[WorkflowEdge] = []
    notes: list[str] = []

    trigger_id = "trigger"
    nodes.append(
        _node(
            trigger_id,
            "trigger",
            "When this workflow starts",
            {"source": _trigger_source(lower)},
            40,
            120,
        )
    )
    previous_id = trigger_id

    if _wants_delay(lower):
        delay_id = "wait"
        nodes.append(
            _node(
                delay_id,
                "delay",
                "Wait before continuing",
                {"seconds": _delay_seconds(lower)},
                300,
                120,
            )
        )
        edges.append(_edge(previous_id, delay_id))
        previous_id = delay_id

    if _wants_http_first(lower):
        http_id = "fetch-data"
        nodes.append(
            _node(
                http_id,
                "http",
                "Get source data",
                {
                    "method": "GET",
                    "url": "https://api.example.com/replace-me",
                    "headers": {},
                    "body": "",
                },
                560,
                120,
            )
        )
        edges.append(_edge(previous_id, http_id))
        previous_id = http_id
        notes.append("Replace the example API URL before running this workflow.")

    ai_id = "ai-task"
    nodes.append(
        _node(
            ai_id,
            "llm_prompt",
            _ai_label(lower),
            {
                "model": "",
                "system_prompt": _system_prompt(lower),
                "user_message": _user_message(clean_prompt, previous_id),
            },
            820 if previous_id != trigger_id else 300,
            120,
        )
    )
    edges.append(_edge(previous_id, ai_id))
    previous_id = ai_id

    if _wants_condition(lower):
        condition_id = "check-result"
        nodes.append(
            _node(
                condition_id,
                "condition",
                "Check the result",
                {"left": "{{ai-task.output}}", "op": "contains", "right": "yes"},
                1080 if len(nodes) > 3 else 560,
                120,
            )
        )
        edges.append(_edge(previous_id, condition_id))
        previous_id = condition_id
        notes.append("Update the branch condition to match the decision you need.")

    if _wants_notify_or_send(lower):
        notify_id = "send-result"
        x = 1340 if previous_id == "check-result" else 560 if len(nodes) <= 3 else 1080
        nodes.append(
            _node(
                notify_id,
                "http",
                _send_label(lower),
                {
                    "method": "POST",
                    "url": "https://api.example.com/replace-me",
                    "headers": {"Content-Type": "application/json"},
                    "body": {"message": "{{ai-task.output}}"},
                },
                x,
                120,
            )
        )
        edges.append(_edge(previous_id, notify_id, "true" if previous_id == "check-result" else None))
        notes.append("Connect the final HTTP step to your email, Slack, CRM, or webhook endpoint.")

    title = _title_from_prompt(clean_prompt)
    description = f"Drafted from: {clean_prompt}"
    notes.insert(0, "Review each step before running. The copilot creates a starting point, not a finished automation.")

    return title, description, WorkflowDefinition(nodes=nodes, edges=edges), notes


def _node(
    node_id: str,
    node_type: str,
    label: str,
    config: dict[str, object],
    x: float,
    y: float,
) -> WorkflowNode:
    return WorkflowNode(
        id=node_id,
        type=node_type,
        position=NodePosition(x=x, y=y),
        data=NodeData(label=label, config=config),
    )


def _edge(source: str, target: str, source_handle: str | None = None) -> WorkflowEdge:
    return WorkflowEdge(
        id=f"e-{source}-{target}",
        source=source,
        target=target,
        sourceHandle=source_handle,
        targetHandle=None,
    )


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def _title_from_prompt(prompt: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", prompt)[:7]
    if not words:
        return "Untitled workflow"
    title = " ".join(words)
    return title[:1].upper() + title[1:]


def _trigger_source(lower: str) -> str:
    if "webhook" in lower or "form" in lower or "submission" in lower:
        return "webhook"
    if "every " in lower or "daily" in lower or "morning" in lower:
        return "schedule"
    return "manual"


def _wants_delay(lower: str) -> bool:
    return any(word in lower for word in ("wait", "delay", "pause", "after 5", "after five"))


def _delay_seconds(lower: str) -> int:
    minutes = re.search(r"(\d+)\s*(minute|minutes|min|mins)", lower)
    if minutes:
        return min(max(int(minutes.group(1)) * 60, 1), 300)
    seconds = re.search(r"(\d+)\s*(second|seconds|sec|secs)", lower)
    if seconds:
        return min(max(int(seconds.group(1)), 1), 300)
    return 60


def _wants_http_first(lower: str) -> bool:
    api_terms = ("fetch", "get data", "api", "http", "url", "website", "web page")
    send_terms = ("send", "notify", "post to", "create a task", "draft")
    return any(term in lower for term in api_terms) and not any(term in lower for term in send_terms)


def _wants_condition(lower: str) -> bool:
    return any(term in lower for term in (" if ", "only if", "unless", "when it", "branch", "condition"))


def _wants_notify_or_send(lower: str) -> bool:
    return any(
        term in lower
        for term in (
            "send",
            "notify",
            "slack",
            "email",
            "whatsapp",
            "create a task",
            "crm",
            "webhook",
        )
    )


def _ai_label(lower: str) -> str:
    if any(term in lower for term in ("summarise", "summarize", "summary")):
        return "Summarise with AI"
    if any(term in lower for term in ("extract", "pull out", "find")):
        return "Extract key details"
    if any(term in lower for term in ("draft", "write", "reply", "respond")):
        return "Draft with AI"
    if any(term in lower for term in ("classify", "categorise", "categorize")):
        return "Classify with AI"
    return "AI task"


def _system_prompt(lower: str) -> str:
    if "legal" in lower or "solicitor" in lower or "lawyer" in lower:
        return "You help a legal team turn messy inputs into clear, careful business outputs."
    if "recruit" in lower or "candidate" in lower:
        return "You help a recruitment team summarise and organise candidate or client information."
    if "account" in lower or "invoice" in lower:
        return "You help an accounting team extract and summarise operational information accurately."
    return "You are a concise business assistant. Produce clear, useful output without unnecessary detail."


def _user_message(prompt: str, previous_id: str) -> str:
    source = "{{trigger.text}}" if previous_id == "trigger" else f"{{{{{previous_id}.output}}}}"
    return (
        "Workflow request:\n"
        f"{prompt}\n\n"
        "Use this input:\n"
        f"{source}\n\n"
        "Return the result in a format that can be used by the next workflow step."
    )


def _send_label(lower: str) -> str:
    if "slack" in lower:
        return "Send to Slack"
    if "email" in lower:
        return "Send email"
    if "whatsapp" in lower:
        return "Send WhatsApp message"
    if "task" in lower:
        return "Create task"
    return "Send result"
