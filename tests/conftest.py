import pytest
import mongomock
import fakeredis
from django.conf import settings

from emailqueue.config.MongoConfig import MongoConfig
from emailqueue.config.RedisConfig import RedisConfig
from emailqueue.repositories.EmailRepository import EmailRepository
from emailqueue.services.RateLimiterService import RateLimiterService
from emailqueue.services.EmailProcessor import EmailProcessor
from emailqueue.services.EmailService import EmailService

@pytest.fixture(autouse=True)
def configureEnvironment(monkeypatch):
    """Ensures test settings and eager Celery execution."""
    from emailsystem.celery import celeryApp
    monkeypatch.setattr(settings, "CELERY_TASK_ALWAYS_EAGER", True)
    monkeypatch.setattr(settings, "CELERY_TASK_EAGER_PROPAGATES", False)
    celeryApp.conf.update(
        task_always_eager=True,
        task_eager_propagates=False,
    )

@pytest.fixture(autouse=True)
def mockMongoDatabase():
    """Provides a fresh isolated mongomock Database."""
    mongoMockClient = mongomock.MongoClient()
    testDatabase = mongoMockClient["test_email_queue_db"]
    MongoConfig.setDatabaseOverride(testDatabase)
    yield testDatabase
    MongoConfig.setDatabaseOverride(None)

@pytest.fixture(autouse=True)
def mockRedisClient():
    """Provides a fresh isolated fakeredis Redis client with Lua support."""
    fakeRedis = fakeredis.FakeRedis()
    RedisConfig.setClientOverride(fakeRedis)
    yield fakeRedis
    RedisConfig.setClientOverride(None)

@pytest.fixture
def emailRepository(mockMongoDatabase):
    """Provides an EmailRepository wired to the mock MongoDB."""
    repository = EmailRepository()
    repository.createIndexes()
    return repository

@pytest.fixture
def rateLimiterService(mockRedisClient):
    """Provides a RateLimiterService wired to the mock Redis client."""
    limiter = RateLimiterService()
    limiter.reset()
    return limiter

@pytest.fixture
def emailProcessor():
    """Provides a mock EmailProcessor."""
    return EmailProcessor()

@pytest.fixture
def emailService(emailRepository):
    """Provides an EmailService wired to the mock EmailRepository."""
    return EmailService(emailRepository=emailRepository)
