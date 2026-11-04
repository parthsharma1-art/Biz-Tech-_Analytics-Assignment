from django.urls import path, re_path, include
from emailsystem.views import healthCheckView

urlpatterns = [
    # Global Cloud Health Check Endpoints (e.g., Render, Kubernetes, AWS)
    path("health/", healthCheckView, name="healthCheck"),
    path("api/health/", healthCheckView, name="apiHealthCheck"),
    path("api/v1/health/", healthCheckView, name="apiV1HealthCheck"),

    # Section 01: Order summary diagnostic endpoints & Silk profiler
    path("api/orders/", include("orders.urls")),
    path("silk/", include("silk.urls", namespace="silk")),

    # Section 02: Rate-limited email queue system
    re_path(r"^api/v1/emails/?", include("emailqueue.urls")),
]

