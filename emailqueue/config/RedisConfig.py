import os
import threading
from typing import Optional
import redis
from django.conf import settings

class RedisConfig:
    _instance: Optional["RedisConfig"] = None
    _lock: threading.Lock = threading.Lock()

    def __init__(self):
        self.redisUrl = getattr(settings, "REDIS_URL", os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"))
        self._client: Optional[redis.Redis] = None
        self._overrideClient: Optional[redis.Redis] = None

    @classmethod
    def getInstance(cls) -> "RedisConfig":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def setClientOverride(cls, mockRedis: Optional[redis.Redis]) -> None:
        instance = cls.getInstance()
        instance._overrideClient = mockRedis

    def getClient(self) -> redis.Redis:
        if self._overrideClient is not None:
            return self._overrideClient
        if self._client is None:
            with self._lock:
                if self._client is None:
                    self._client = redis.Redis.from_url(
                        self.redisUrl,
                        decode_responses=False,
                        socket_timeout=5,
                        socket_connect_timeout=5
                    )
        return self._client

    def isConnected(self) -> bool:
        try:
            return bool(self.getClient().ping())
        except Exception:
            return False

