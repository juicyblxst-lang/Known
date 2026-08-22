from app.models import Customer, Message, Order, SupportRequest, SupportResponse


def test_support_request_defaults_are_safe():
    request = SupportRequest(
        customer=Customer(id="c1", name="Maya", email="maya@example.com"),
        message="Help with my order",
    )

    assert request.conversation == []
    assert request.orders == []
    assert request.customer.tier == "standard"


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
