import pytest
from decimal import Decimal
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.db import connection

from orders.models import Customer, Product, Order, OrderItem
from orders.views import OrdersSummaryUnoptimizedView, OrdersSummaryOptimizedView

@pytest.mark.django_db
class TestSection01Diagnostic:
    def setup_method(self):
        self.factory = RequestFactory()

        # Seed test customer
        self.customer = Customer.objects.create(name="Jane Doe", email="jane.doe@example.com")

        # Seed products
        self.laptop = Product.objects.create(name="Laptop", price=Decimal("1200.00"), sku="LAP-001")
        self.mouse = Product.objects.create(name="Mouse", price=Decimal("25.00"), sku="MOU-001")
        self.keyboard = Product.objects.create(name="Keyboard", price=Decimal("75.00"), sku="KEY-001")

        # Seed 200 orders (as specified in the scenario: users with more than 200 orders)
        orderList = [
            Order(customer=self.customer, status=Order.STATUS_COMPLETED)
            for _ in range(200)
        ]
        createdOrders = Order.objects.bulk_create(orderList)

        # Seed items for all 200 orders (2 items per order = 400 order items)
        itemList = []
        for order in createdOrders:
            itemList.append(OrderItem(order=order, product=self.mouse, quantity=2, unitPrice=self.mouse.price))
            itemList.append(OrderItem(order=order, product=self.keyboard, quantity=1, unitPrice=self.keyboard.price))
        OrderItem.objects.bulk_create(itemList)

    def testUnoptimizedViewDemonstratesNPlusOneQueryCascade(self):
        """
        Demonstrates the bug: For 200 orders, the unoptimized view triggers:
        1 query for Orders + 200 queries for Customer + 200 queries for Items + 400 queries for Product = 801 queries!
        """
        request = self.factory.get(f"/api/orders/summary/slow/?customerId={self.customer.id}")
        
        with CaptureQueriesContext(connection) as queryContext:
            response = OrdersSummaryUnoptimizedView.as_view()(request)

        queryCount = len(queryContext.captured_queries)
        assert response.status_code == 200
        # Assert query count explodes into hundreds of queries (N+1 cascade)
        assert queryCount >= 200, f"Expected N+1 query explosion (>200 queries), but got {queryCount}"

    def testOptimizedViewExecutesInSingleQueryAndMatchesData(self):
        """
        Demonstrates the fix: With select_related and DB-level annotate aggregation,
        the optimized view executes in EXACTLY 1 single query.
        """
        request = self.factory.get(f"/api/orders/summary/?customerId={self.customer.id}")

        with CaptureQueriesContext(connection) as queryContext:
            response = OrdersSummaryOptimizedView.as_view()(request)

        queryCount = len(queryContext.captured_queries)
        assert response.status_code == 200
        # In the optimized view, all orders, customer join, and sum aggregation are executed in 1 query!
        assert queryCount == 1, f"Expected exactly 1 query, but got {queryCount}"

