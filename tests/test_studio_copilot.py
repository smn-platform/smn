from smn.studio.copilot import draft_workflow


def test_draft_workflow_creates_editable_ai_workflow() -> None:
    name, description, definition, notes = draft_workflow(
        "When a new client form arrives, extract key details and send a summary to my team"
    )

    assert name.startswith("When a new client")
    assert "Drafted from:" in description
    assert notes
    assert [node.id for node in definition.nodes] == ["trigger", "ai-task", "send-result"]
    assert [edge.source for edge in definition.edges] == ["trigger", "ai-task"]
    assert [edge.target for edge in definition.edges] == ["ai-task", "send-result"]

    ai_node = definition.nodes[1]
    assert ai_node.type == "llm_prompt"
    assert "extract" in ai_node.data.config["user_message"].lower()


def test_draft_workflow_adds_branch_for_conditional_prompt() -> None:
    _, _, definition, notes = draft_workflow(
        "Summarise the request and only if it is urgent send a WhatsApp message"
    )

    node_ids = [node.id for node in definition.nodes]
    assert "check-result" in node_ids
    assert "send-result" in node_ids
    assert any("branch condition" in note for note in notes)

    branch_edge = next(edge for edge in definition.edges if edge.target == "send-result")
    assert branch_edge.source == "check-result"
    assert branch_edge.sourceHandle == "true"


def test_draft_workflow_rejects_empty_prompt() -> None:
    try:
        draft_workflow("   ")
    except ValueError as exc:
        assert "Describe the workflow" in str(exc)
    else:
        raise AssertionError("Expected empty prompt to be rejected")
