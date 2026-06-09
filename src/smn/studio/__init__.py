"""SMN Studio — visual workflow builder and execution engine.

Provides a node-based workflow system (like n8n/Zapier) built on top of the
SMN governance and execution infrastructure.

Workflows are directed acyclic graphs of nodes. Each node is a governed unit
of work — an SMN agent call, a raw LLM prompt, an HTTP request, a condition
branch, or a time delay. Every execution runs through SMN's Trust Plane:
policy enforcement, cost tracking, and the immutable audit trail.
"""
