import time
from datetime import datetime, timezone
from django.http import JsonResponse, HttpRequest

from emailqueue.config.RedisConfig import RedisConfig
from emailqueue.config.MongoConfig import MongoConfig
from django.db import connection

def healthCheckView(request: HttpRequest) -> JsonResponse:
    """
    Production-grade Health Check endpoint.
    Checks:
    - Django Relational Database (SQLite)
    - Redis (Ping & Latency)
    - MongoDB (Ping & Latency)
    Returns:
    - 200 OK with detailed service health diagnostics.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    services = {}
    isHealthy = True

    # 1. Check Relational DB
    try:
        startDb = time.time()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            cursor.fetchone()
        dbLatency = round((time.time() - startDb) * 1000, 2)
        services["database"] = {"status": "up", "latencyMs": dbLatency}
    except Exception as dbErr:
        isHealthy = False
        services["database"] = {"status": "down", "error": str(dbErr)}

    # 2. Check Redis
    try:
        startRedis = time.time()
        redisClient = RedisConfig.getInstance().getClient()
        redisClient.ping()
        redisLatency = round((time.time() - startRedis) * 1000, 2)
        services["redis"] = {"status": "up", "latencyMs": redisLatency}
    except Exception as redisErr:
        isHealthy = False
        services["redis"] = {"status": "down", "error": str(redisErr)}

    # 3. Check MongoDB
    try:
        startMongo = time.time()
        mongoClient = MongoConfig.getInstance().getClient()
        mongoClient.admin.command("ping")
        mongoLatency = round((time.time() - startMongo) * 1000, 2)
        services["mongodb"] = {"status": "up", "latencyMs": mongoLatency}
    except Exception as mongoErr:
        isHealthy = False
        services["mongodb"] = {"status": "down", "error": str(mongoErr)}

    httpStatus = 200 if isHealthy else 503
    payload = {
        "status": "healthy" if isHealthy else "degraded",
        "timestamp": timestamp,
        "services": services
    }
    return JsonResponse(payload, status=httpStatus)

