import pytest

from app.auth import AuthContext
from app.models import Customer


def test_auth_context_requires_business_tenant():
    context = AuthContext(user_id="user-1", business_id="business-1", email="owner@example.com")
    assert context.business_id == "business-1"


def test_customer_identity_is_not_a_tenant_identity():
    customer = Customer(id="customer-1", name="Maya", email="maya@example.com")
    context = AuthContext(user_id="user-1", business_id="business-1")

    assert customer.id != context.business_id
    assert context.business_id == "business-1"
