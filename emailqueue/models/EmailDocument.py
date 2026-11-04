from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

class EmailStatus:
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

    @classmethod
    def isValid(cls, statusValue: str) -> bool:
        return statusValue in (cls.PENDING, cls.PROCESSING, cls.SUCCESS, cls.FAILED)

@dataclass
class EmailHistoryEntry:
    timestamp: str
    status: str
    message: Optional[str] = None
    retryCount: int = 0

    def toDict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "status": self.status,
            "message": self.message,
            "retryCount": self.retryCount,
        }

@dataclass
class EmailDocument:
    _id: str
    recipient: str
    subject: str
    body: str
    status: str = EmailStatus.PENDING
    retryCount: int = 0
    maxRetries: int = 3
    failureReason: Optional[str] = None
    createdAt: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updatedAt: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completedAt: Optional[str] = None
    processingHistory: List[Dict[str, Any]] = field(default_factory=list)

    def toDict(self) -> Dict[str, Any]:
        return {
            "_id": self._id,
            "recipient": self.recipient,
            "subject": self.subject,
            "body": self.body,
            "status": self.status,
            "retryCount": self.retryCount,
            "maxRetries": self.maxRetries,
            "failureReason": self.failureReason,
            "createdAt": self.createdAt,
            "updatedAt": self.updatedAt,
            "completedAt": self.completedAt,
            "processingHistory": self.processingHistory,
        }

    @classmethod
    def fromDict(cls, documentData: Dict[str, Any]) -> "EmailDocument":
        return cls(
            _id=documentData.get("_id"),
            recipient=documentData.get("recipient", ""),
            subject=documentData.get("subject", ""),
            body=documentData.get("body", ""),
            status=documentData.get("status", EmailStatus.PENDING),
            retryCount=documentData.get("retryCount", 0),
            maxRetries=documentData.get("maxRetries", 3),
            failureReason=documentData.get("failureReason"),
            createdAt=documentData.get("createdAt"),
            updatedAt=documentData.get("updatedAt"),
            completedAt=documentData.get("completedAt"),
            processingHistory=documentData.get("processingHistory", []),
        )

