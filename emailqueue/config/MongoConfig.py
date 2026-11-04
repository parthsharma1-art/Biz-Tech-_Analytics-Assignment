import os
import threading
from typing import Optional
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection
from django.conf import settings

class MongoConfig:
    _instance: Optional["MongoConfig"] = None
    _lock: threading.Lock = threading.Lock()

    def __init__(self):
        self.mongoUri = getattr(settings, "MONGO_URI", os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017"))
        self.dbName = getattr(settings, "MONGO_DB_NAME", os.getenv("MONGO_DB_NAME", "email_queue_db"))
        self.emailsCollectionName = getattr(settings, "MONGO_EMAILS_COLLECTION", os.getenv("MONGO_EMAILS_COLLECTION", "emails"))
        self._client: Optional[MongoClient] = None
        self._overrideDatabase: Optional[Database] = None

    @classmethod
    def getInstance(cls) -> "MongoConfig":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def setDatabaseOverride(cls, mockDatabase: Optional[Database]) -> None:
        instance = cls.getInstance()
        instance._overrideDatabase = mockDatabase

    def getClient(self) -> MongoClient:
        if self._client is None:
            with self._lock:
                if self._client is None:
                    self._client = MongoClient(self.mongoUri, serverSelectionTimeoutMS=5000)
        return self._client

    def getDatabase(self) -> Database:
        if self._overrideDatabase is not None:
            return self._overrideDatabase
        return self.getClient()[self.dbName]

    def getEmailsCollection(self) -> Collection:
        return self.getDatabase()[self.emailsCollectionName]

    def close(self) -> None:
        with self._lock:
            if self._client is not None:
                self._client.close()
                self._client = None

