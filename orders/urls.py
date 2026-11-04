from django.urls import path
from orders.views import OrdersSummaryOptimizedView, OrdersSummaryUnoptimizedView

urlpatterns = [
    path("summary/", OrdersSummaryOptimizedView.as_view(), name="ordersSummary"),
    path("summary/slow/", OrdersSummaryUnoptimizedView.as_view(), name="ordersSummarySlow"),
]
