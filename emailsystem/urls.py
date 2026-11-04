from django.urls import path, re_path, include

urlpatterns = [
    # Section 01: Order summary diagnostic endpoints & Silk profiler
    path("api/orders/", include("orders.urls")),
    path("silk/", include("silk.urls", namespace="silk")),

    # Section 02: Rate-limited email queue system
    re_path(r"^api/v1/emails/?", include("emailqueue.urls")),
]

