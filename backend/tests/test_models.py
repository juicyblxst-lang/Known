from app.models import Message, Order, SupportRequest, SupportResponse


def test_support_request_defaults_are_safe():
    request = SupportRequest(customer_id="c1", message="Help with my order")

    assert request.customer_id == "c1"
    assert request.conversation_id is None


def test_support_response_carries_memory_and_action_metadata():
    response = SupportResponse(
        customer_id="c1",
        reply="I can help.",
        memories_used=[{"type": "preference", "content": "Expedited shipping"}],
        memory_written=True,
        recommended_action="Check shipment status",
    )

    assert response.memory_written is True
    assert response.memories_used[0]["type"] == "preference"
    assert response.recommended_action == "Check shipment status"
    assert response.degraded_memory is False
