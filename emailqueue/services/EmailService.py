import uuid
import logging
from typing import Dict, Any, List, Optional, Tuple

from emailqueue.models.EmailDocument import EmailDocument, EmailStatus
from emailqueue.repositories.EmailRepository import EmailRepository
from emailqueue.tasks.EmailTasks import processEmailTask

logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self, emailRepository: Optional[EmailRepository] = None):
        self.emailRepository = emailRepository or EmailRepository()

    def enqueueEmail(
        self,
        recipient: str,
        subject: str,
        body: str,
        emailId: Optional[str] = None
    ) -> EmailDocument:
        """
        Scenario 1:
        1. Assigns a unique email/job ID.
        2. Sets initial status to PENDING.
        3. Persists the document in MongoDB.
        4. Enqueues processing through Celery using Redis.
        """
        assignedId = emailId or str(uuid.uuid4())
        emailDocument = EmailDocument(
            _id=assignedId,
            recipient=recipient,
            subject=subject,
            body=body,
            status=EmailStatus.PENDING,
            retryCount=0,
            maxRetries=3,
            failureReason=None,
        )

        savedDocument = self.emailRepository.saveEmail(emailDocument)

        # Enqueue processing task via Celery
        processEmailTask.delay(savedDocument._id)
        logger.info("Enqueued email job '%s' for recipient '%s'.", savedDocument._id, recipient)
        return savedDocument

    def enqueueBatchEmails(self, emailList: List[Dict[str, str]]) -> List[EmailDocument]:
        """Submits a batch of email jobs."""
        enqueuedEmails: List[EmailDocument] = []
        for item in emailList:
            emailDoc = self.enqueueEmail(
                recipient=item["recipient"],
                subject=item["subject"],
                body=item["body"],
                emailId=item.get("emailId") or item.get("_id"),
            )
            enqueuedEmails.append(emailDoc)
        return enqueuedEmails

    def getQueueCounts(self) -> Dict[str, int]:
        """
        Returns the counts for the logical queues from MongoDB:
        {
            "succeeded_queue_count": X,
            "failed_queue_count": Y
        }
        """
        rawCounts = self.emailRepository.getQueueCounts()
        return {
            "succeeded_queue_count": rawCounts["succeeded_queue_count"],
            "failed_queue_count": rawCounts["failed_queue_count"],
        }

    def prepareReprocessFailedEmails(self, batchLimit: int = 100) -> Tuple[Dict[str, int], List[str]]:
        """
        Scenario 3 Step 1-3:
        1. Queries MongoDB for current queue counts.
        2. Queries failed email IDs eligible for reprocessing.
        3. Returns the queue counts and the target email IDs.
        Counts are returned BEFORE triggering the actual reprocessing tasks.
        """
        currentQueueCounts = self.getQueueCounts()
        failedEmailDocs = self.emailRepository.findFailedEmails(limit=batchLimit)
        failedEmailIds = [doc._id for doc in failedEmailDocs]
        return currentQueueCounts, failedEmailIds

    def executeReprocessFailedEmails(self, failedEmailIds: List[str]) -> int:
        """
        Scenario 3 Step 4-8:
        Dispatches failed emails one-by-one to Celery for reprocessing.
        Atomically resets each to PENDING before dispatch.
        """
        dispatchedCount = 0
        for emailId in failedEmailIds:
            # Atomically reset status to PENDING for reprocess
            resetDoc = self.emailRepository.resetToPendingForReprocess(emailId)
            if resetDoc is not None:
                processEmailTask.delay(emailId)
                dispatchedCount += 1
                logger.info("Dispatched failed email '%s' for reprocessing.", emailId)
        return dispatchedCount

    def getEmailStatus(self, emailId: str) -> Optional[EmailDocument]:
        """Retrieves an email job by ID."""
        return self.emailRepository.findById(emailId)

