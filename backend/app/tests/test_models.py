from app.models import Customer, Message, Order, SupportRequest


def test_support_request_accepts_customer_orders_and_conversation():
    request = SupportRequest(
        customer=Customer(id="cust_1", name="Jane Doe", email="jane@example.com"),
        message="Where is my order?",
        conversation=[Message(role="user", content="I am checking on delivery.")],
        orders=[Order(id="ord_1", customer_id="cust_1", status="shipped", total=42.50, items=["Tee"])],
    )
    assert request.customer.id == "cust_1"
    assert request.orders[0].status == "shipped"
    assert request.conversation[0].role == "user"
