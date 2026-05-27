from agent.router.capability_registry import (
    CAPABILITIES,
    SURFACE_MODE_POLICY,
    capability_allowed,
    capabilities_for_surface,
)
from agent.router.contracts import NodeSpec


def test_chat_surface_excludes_action_capabilities():
    allowed_modes = SURFACE_MODE_POLICY["chat"]["allowed_modes"]

    assert CAPABILITIES["quality.inspection.execute"].mode == "action"
    assert capability_allowed(CAPABILITIES["chat.general"], "chat", allowed_modes)
    assert not capability_allowed(CAPABILITIES["quality.inspection.execute"], "chat", allowed_modes)


def test_quality_task_surface_allows_formal_inspection_action():
    allowed_modes = SURFACE_MODE_POLICY["quality_task"]["allowed_modes"]

    assert capability_allowed(CAPABILITIES["quality.inspection.execute"], "quality_task", allowed_modes)


def test_capabilities_for_surface_only_returns_allowed_agents_and_modes():
    chat_capabilities = capabilities_for_surface("chat")
    quality_capabilities = capabilities_for_surface("quality_task")

    assert "quality.inspection.execute" not in chat_capabilities
    assert "data.analysis" in chat_capabilities
    assert "file.paper_format_check" in chat_capabilities
    assert "quality.inspection.execute" in quality_capabilities
    assert all(item.mode in {"answer", "report"} for item in chat_capabilities.values())


def test_node_spec_declares_local_routing_model_requirements():
    spec = NodeSpec(
        node_key="inspection.vision_node",
        accepted_input_kinds=["image"],
        required_model_types=["vision", "multimodal"],
        mode="report",
        output_artifact_types=["image_understanding"],
    )

    assert spec.node_key == "inspection.vision_node"
    assert spec.required_model_types == ["vision", "multimodal"]
