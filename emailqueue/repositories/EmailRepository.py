from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pymongo import ASCENDING, DESCENDING
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from emailqueue.config.MongoConfig import MongoConfig
from emailqueue.models.EmailDocument import EmailDocument, EmailStatus, EmailHistoryEntry

class DuplicateEmailJobException(Exception):
    """Raised when an email job with the same ID already exists."""
    pass

class EmailNotFoundException(Exception):
    """Raised when an email job cannot be found in MongoDB."""
    pass

class EmailRepository:
    def __init__(self, mongoConfig: Optional[MongoConfig] = None):
        self.mongoConfig = mongoConfig or MongoConfig.getInstance()

    def getCollection(self) -> Collection:
        return self.mongoConfig.getEmailsCollection()

    def createIndexes(self) -> None:
        collection = self.getCollection()
        collection.create_index([("status", ASCENDING)], name="idx_status")
        collection.create_index([("createdAt", ASCENDING)], name="idx_created_at")
        collection.create_index([("status", ASCENDING), ("createdAt", ASCENDING)], name="idx_status_created")

    def saveEmail(self, emailDocument: EmailDocument) -> EmailDocument:
        collection = self.getCollection()
        documentDict = emailDocument.toDict()
        try:
            collection.insert_one(documentDict)
            return emailDocument
        except DuplicateKeyError as duplicateError:
            raise DuplicateEmailJobException(
                f"Email job with ID '{emailDocument._id}' already exists."
            ) from duplicateError

    def findById(self, emailId: str) -> Optional[EmailDocument]:
        collection = self.getCollection()
        rawDocument = collection.find_one({"_id": emailId})
        if rawDocument is None:
            return None
        return EmailDocument.fromDict(rawDocument)

    def markAsProcessing(self, emailId: str) -> Optional[EmailDocument]:
        nowTimestamp = datetime.now(timezone.utc).isoformat()
        historyEntry = EmailHistoryEntry(
            timestamp=nowTimestamp,
            status=EmailStatus.PROCESSING,
            message="Processing initiated by worker."
        ).toDict()

        collection = self.getCollection()
        updatedRaw = collection.find_one_and_update(
            {"_id": emailId},
            {
                "$set": {
                    "status": EmailStatus.PROCESSING,
                    "updatedAt": nowTimestamp,
                },
                "$push": {
                    "processingHistory": historyEntry
                }
            },
            return_document=True
        )
        if updatedRaw is None:
            return None
        return EmailDocument.fromDict(updatedRaw)

    def markAsSuccess(self, emailId: str) -> Optional[EmailDocument]:
        nowTimestamp = datetime.now(timezone.utc).isoformat()
        historyEntry = EmailHistoryEntry(
            timestamp=nowTimestamp,
            status=EmailStatus.SUCCESS,
            message="Email successfully processed and delivered."
        ).toDict()

        collection = self.getCollection()
        updatedRaw = collection.find_one_and_update(
            {"_id": emailId},
            {
                "$set": {
                    "status": EmailStatus.SUCCESS,
                    "completedAt": nowTimestamp,
                    "updatedAt": nowTimestamp,
                },
                "$push": {
                    "processingHistory": historyEntry
                }
            },
            return_document=True
        )
        if updatedRaw is None:
            return None
        return EmailDocument.fromDict(updatedRaw)

    def markAsFailed(self, emailId: str, failureReason: str, retryCount: int) -> Optional[EmailDocument]:
        nowTimestamp = datetime.now(timezone.utc).isoformat()
        historyEntry = EmailHistoryEntry(
            timestamp=nowTimestamp,
            status=EmailStatus.FAILED,
            message=f"Processing failed: {failureReason}",
            retryCount=retryCount
        ).toDict()

        collection = self.getCollection()
        updatedRaw = collection.find_one_and_update(
            {"_id": emailId},
            {
                "$set": {
                    "status": EmailStatus.FAILED,
                    "failureReason": failureReason,
                    "retryCount": retryCount,
                    "updatedAt": nowTimestamp,
                },
                "$push": {
                    "processingHistory": historyEntry
                }
            },
            return_document=True
        )
        if updatedRaw is None:
            return None
        return EmailDocument.fromDict(updatedRaw)

    def recordRetryAttempt(self, emailId: str, attemptNumber: int, transientReason: str) -> Optional[EmailDocument]:
        nowTimestamp = datetime.now(timezone.utc).isoformat()
        historyEntry = EmailHistoryEntry(
            timestamp=nowTimestamp,
            status=EmailStatus.PENDING,
            message=f"Retry attempt #{attemptNumber} scheduled. Reason: {transientReason}",
            retryCount=attemptNumber
        ).toDict()

        collection = self.getCollection()
        updatedRaw = collection.find_one_and_update(
            {"_id": emailId},
            {
                "$set": {
                    "retryCount": attemptNumber,
                    "failureReason": transientReason,
                    "updatedAt": nowTimestamp,
                },
                "$push": {
                    "processingHistory": historyEntry
                }
            },
            return_document=True
        )
        if updatedRaw is None:
            return None
        return EmailDocument.fromDict(updatedRaw)

    def resetToPendingForReprocess(self, emailId: str) -> Optional[EmailDocument]:
        nowTimestamp = datetime.now(timezone.utc).isoformat()
        historyEntry = EmailHistoryEntry(
            timestamp=nowTimestamp,
            status=EmailStatus.PENDING,
            message="Job queued for failed-email reprocessing.",
            retryCount=0
        ).toDict()

        collection = self.getCollection()
        updatedRaw = collection.find_one_and_update(
            {"_id": emailId, "status": EmailStatus.FAILED},
            {
                "$set": {
                    "status": EmailStatus.PENDING,
                    "retryCount": 0,
                    "updatedAt": nowTimestamp,
                },
                "$push": {
                    "processingHistory": historyEntry
                }
            },
            return_document=True
        )
        if updatedRaw is None:
            return None
        return EmailDocument.fromDict(updatedRaw)

    def getQueueCounts(self) -> Dict[str, int]:
        collection = self.getCollection()
        pipeline = [
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
        ]
        results = list(collection.aggregate(pipeline))
        statusMap = {entry["_id"]: entry["count"] for entry in results}

        return {
            "incoming_queue_count": statusMap.get(EmailStatus.PENDING, 0) + statusMap.get(EmailStatus.PROCESSING, 0),
            "succeeded_queue_count": statusMap.get(EmailStatus.SUCCESS, 0),
            "failed_queue_count": statusMap.get(EmailStatus.FAILED, 0),
        }

    def findFailedEmails(self, limit: int = 100) -> List[EmailDocument]:
        collection = self.getCollection()
        cursor = collection.find({"status": EmailStatus.FAILED}).sort("createdAt", ASCENDING).limit(limit)
        return [EmailDocument.fromDict(doc) for doc in cursor]

    def countAll(self) -> int:
        return self.getCollection().count_documents({})

