import logging
from typing import Dict, Any, Optional
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError

from emailqueue.models.EmailDocument import EmailStatus
from emailqueue.repositories.EmailRepository import EmailRepository
from emailqueue.services.EmailProcessor import EmailProcessor, TransientEmailException, PermanentEmailException
from emailqueue.services.RateLimiterService import RateLimiterService

logger = logging.getLogger(__name__)

MAX_RETRIES = 3

class EmailTaskService:
    @staticmethod
    def executeEmailProcessing(
        taskInstance,
        emailId: str,
        emailRepository: Optional[EmailRepository] = None,
        rateLimiterService: Optional[RateLimiterService] = None,
        emailProcessor: Optional[EmailProcessor] = None,
    ) -> Dict[str, Any]:
        """
        Executes the email processing lifecycle for a single email:
        1. Validates email exists and is not already processed (idempotency).
        2. Enforces global sliding-window rate limit (max 200/min).
        3. Attempts delivery via EmailProcessor.
        4. Transitions status to SUCCESS or handles retries/FAILED.
        """
        repo = emailRepository or EmailRepository()
        limiter = rateLimiterService or RateLimiterService()
        processor = emailProcessor or EmailProcessor()

        emailDocument = repo.findById(emailId)
        if emailDocument is None:
            logger.error("Email document with ID '%s' not found.", emailId)
            return {"status": "NOT_FOUND", "emailId": emailId}

        # Idempotency check: avoid duplicate processing
        if emailDocument.status == EmailStatus.SUCCESS:
            logger.info("Email '%s' is already marked SUCCESS. Skipping duplicate processing.", emailId)
            return {"status": EmailStatus.SUCCESS, "emailId": emailId}

        # Rate Limiting: Redis sliding-window check (atomic)
        allowed, retryAfterSeconds = limiter.acquirePermission()
        if not allowed:
            logger.warning(
                "Rate limit of %s emails/minute reached. Deferring email '%s' by %s seconds.",
                limiter.maxLimit,
                emailId,
                retryAfterSeconds,
            )
            if taskInstance is not None:
                raise taskInstance.retry(
                    countdown=retryAfterSeconds,
                    max_retries=None,
                )
            return {"status": "RATE_LIMITED", "retryAfter": retryAfterSeconds}

        # Atomic transition to PROCESSING
        repo.markAsProcessing(emailId)

        # Attempt sending email
        try:
            processor.sendEmail(
                recipient=emailDocument.recipient,
                subject=emailDocument.subject,
                body=emailDocument.body,
            )
            repo.markAsSuccess(emailId)
            logger.info("Email '%s' processed successfully.", emailId)
            return {"status": EmailStatus.SUCCESS, "emailId": emailId}

        except PermanentEmailException as permError:
            failureReason = str(permError)
            currentRetries = taskInstance.request.retries if taskInstance else 0
            logger.error("Permanent failure processing email '%s': %s", emailId, failureReason)
            repo.markAsFailed(emailId, failureReason=failureReason, retryCount=currentRetries)
            return {"status": EmailStatus.FAILED, "emailId": emailId, "error": failureReason}

        except Exception as transientError:
            currentRetries = taskInstance.request.retries if taskInstance else 0
            failureReason = str(transientError)

            if currentRetries >= MAX_RETRIES:
                exhaustedReason = f"Exhausted maximum retries ({MAX_RETRIES}): {failureReason}"
                logger.error("Email '%s' exhausted max retries. Marking FAILED.", emailId)
                repo.markAsFailed(emailId, failureReason=exhaustedReason, retryCount=MAX_RETRIES)
                return {"status": EmailStatus.FAILED, "emailId": emailId, "error": exhaustedReason}

            # Record retry attempt in MongoDB before queuing retry
            repo.recordRetryAttempt(
                emailId=emailId,
                attemptNumber=currentRetries + 1,
                transientReason=failureReason,
            )

            if taskInstance is not None:
                try:
                    logger.info("Scheduling retry %s/%s for email '%s'.", currentRetries + 1, MAX_RETRIES, emailId)
                    raise taskInstance.retry(
                        exc=transientError,
                        retry_backoff=True,
                        retry_kwargs={"max_retries": MAX_RETRIES},
                    )
                except MaxRetriesExceededError:
                    exhaustedReason = f"Exhausted maximum retries ({MAX_RETRIES}): {failureReason}"
                    repo.markAsFailed(emailId, failureReason=exhaustedReason, retryCount=MAX_RETRIES)
                    return {"status": EmailStatus.FAILED, "emailId": emailId, "error": exhaustedReason}

            return {"status": "RETRY_TRIGGERED", "emailId": emailId, "retryCount": currentRetries + 1}


@shared_task(
    bind=True,
    acks_late=True,
    retry_backoff=True,
    retry_kwargs={"max_retries": MAX_RETRIES},
    ignore_result=True,
    name="emailqueue.tasks.processEmailTask",
)
def processEmailTask(self, emailId: str) -> Dict[str, Any]:
    return EmailTaskService.executeEmailProcessing(taskInstance=self, emailId=emailId)


@shared_task(name="emailqueue.tasks.reprocessFailedEmailsTask")
def reprocessFailedEmailsTask(failedEmailIds: list) -> int:
    repo = EmailRepository()
    dispatchedCount = 0
    for emailId in failedEmailIds:
        resetDoc = repo.resetToPendingForReprocess(emailId)
        if resetDoc is not None:
            processEmailTask.delay(emailId)
            dispatchedCount += 1
    return dispatchedCount

