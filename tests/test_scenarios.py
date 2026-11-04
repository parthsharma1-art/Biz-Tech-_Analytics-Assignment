from unittest.mock import Mock
import pytest

from emailqueue.models.EmailDocument import EmailStatus
from emailqueue.repositories.EmailRepository import EmailRepository
from emailqueue.services.EmailProcessor import EmailProcessor, TransientEmailException, PermanentEmailException
from emailqueue.services.EmailService import EmailService
from emailqueue.services.RateLimiterService import RateLimiterService
from emailqueue.tasks.EmailTasks import EmailTaskService

class TestEmailScenarios:

    def testScenario1_SuccessfulEmailProcessing(
        self,
        emailRepository: EmailRepository,
        emailService: EmailService,
        rateLimiterService: RateLimiterService
    ):
        """
        Scenario 1:
        1. Receive multiple incoming emails.
        2. Save in MongoDB with PENDING status.
        3. Add tasks to Celery and process one-by-one.
        4. Update status to SUCCESS and record completedAt timestamp.
        5. Verify presence in SucceededQueue and accurate counts.
        """
        # Step 1 & 2: Receive multiple emails and persist
        emailJobs = [
            {"recipient": f"user{i}@example.com", "subject": f"Order #{i}", "body": f"Details for order #{i}"}
            for i in range(5)
        ]
        createdDocs = emailService.enqueueBatchEmails(emailJobs)
        assert len(createdDocs) == 5

        # With CELERY_TASK_ALWAYS_EAGER=True, tasks run during enqueue
        # Step 4 & 5: Check each email transitioned to SUCCESS
        for doc in createdDocs:
            refreshedDoc = emailRepository.findById(doc._id)
            assert refreshedDoc is not None
            assert refreshedDoc.status == EmailStatus.SUCCESS
            assert refreshedDoc.completedAt is not None
            assert refreshedDoc.retryCount == 0
            assert refreshedDoc.failureReason is None
            assert len(refreshedDoc.processingHistory) >= 2  # PROCESSING + SUCCESS

        # Step 6: Verify accurate logical queue counts
        queueCounts = emailService.getQueueCounts()
        assert queueCounts["succeeded_queue_count"] == 5
        assert queueCounts["failed_queue_count"] == 0

    def testScenario2_TransientFailuresAndExponentialBackoffRetry(
        self,
        emailRepository: EmailRepository,
        rateLimiterService: RateLimiterService
    ):
        """
        Scenario 2:
        1. If processing fails temporarily, retry using Celery.
        2. Set maximum retries to 3.
        3. Do not immediately mark temporary failures as permanently failed.
        4. Once retries are exhausted:
           - Update status to FAILED.
           - Save failure reason.
           - Save retry count (= 3).
           - Available in FailedQueue.
        """
        # Create an email document directly in MongoDB
        emailDoc = emailRepository.saveEmail(
            emailRepository.saveEmail.__annotations__["emailDocument"](
                _id="transient-test-job-001",
                recipient="retry-user@transient-fail.com",
                subject="Transient Test",
                body="Testing retry logic",
                status=EmailStatus.PENDING,
            )
        )

        mockTask = Mock()
        mockTask.retry.side_effect = Exception("Celery retry triggered")

        # Mock EmailProcessor that always throws TransientEmailException
        processor = EmailProcessor()

        # Attempt 1: Should NOT mark as FAILED; should record attempt 1
        mockTask.request.retries = 0
        with pytest.raises(Exception):
            EmailTaskService.executeEmailProcessing(
                taskInstance=mockTask,
                emailId=emailDoc._id,
                emailRepository=emailRepository,
                rateLimiterService=rateLimiterService,
                emailProcessor=processor,
            )

        docAfterAttempt1 = emailRepository.findById(emailDoc._id)
        assert docAfterAttempt1.status != EmailStatus.FAILED
        assert docAfterAttempt1.retryCount == 1

        # Attempt 2: Still not marked FAILED; should record attempt 2
        mockTask.request.retries = 1
        with pytest.raises(Exception):
            EmailTaskService.executeEmailProcessing(
                taskInstance=mockTask,
                emailId=emailDoc._id,
                emailRepository=emailRepository,
                rateLimiterService=rateLimiterService,
                emailProcessor=processor,
            )

        docAfterAttempt2 = emailRepository.findById(emailDoc._id)
        assert docAfterAttempt2.status != EmailStatus.FAILED
        assert docAfterAttempt2.retryCount == 2

        # Attempt 3: Still not exhausted
        mockTask.request.retries = 2
        with pytest.raises(Exception):
            EmailTaskService.executeEmailProcessing(
                taskInstance=mockTask,
                emailId=emailDoc._id,
                emailRepository=emailRepository,
                rateLimiterService=rateLimiterService,
                emailProcessor=processor,
            )

        docAfterAttempt3 = emailRepository.findById(emailDoc._id)
        assert docAfterAttempt3.retryCount == 3

        # Attempt 4 (Retries exhausted at 3): Must transition to FAILED
        mockTask.request.retries = 3
        result = EmailTaskService.executeEmailProcessing(
            taskInstance=mockTask,
            emailId=emailDoc._id,
            emailRepository=emailRepository,
            rateLimiterService=rateLimiterService,
            emailProcessor=processor,
        )

        assert result["status"] == EmailStatus.FAILED
        failedDoc = emailRepository.findById(emailDoc._id)
        assert failedDoc.status == EmailStatus.FAILED
        assert failedDoc.retryCount == 3
        assert "Exhausted maximum retries" in failedDoc.failureReason

        # Verify logical queue reflection
        counts = emailRepository.getQueueCounts()
        assert counts["failed_queue_count"] == 1
        assert counts["succeeded_queue_count"] == 0

    def testScenario2_PermanentFailureMarksFailedImmediately(
        self,
        emailRepository: EmailRepository,
        rateLimiterService: RateLimiterService
    ):
        """Permanent failures (e.g. invalid recipient address) mark FAILED immediately without retry."""
        emailDoc = emailRepository.saveEmail(
            emailRepository.saveEmail.__annotations__["emailDocument"](
                _id="permanent-test-job-001",
                recipient="bad-user@permanent-fail.com",
                subject="Invalid Address",
                body="Testing permanent failure",
                status=EmailStatus.PENDING,
            )
        )

        mockTask = Mock()
        mockTask.request.retries = 0
        processor = EmailProcessor()

        result = EmailTaskService.executeEmailProcessing(
            taskInstance=mockTask,
            emailId=emailDoc._id,
            emailRepository=emailRepository,
            rateLimiterService=rateLimiterService,
            emailProcessor=processor,
        )

        assert result["status"] == EmailStatus.FAILED
        failedDoc = emailRepository.findById(emailDoc._id)
        assert failedDoc.status == EmailStatus.FAILED
        assert "mailbox does not exist" in failedDoc.failureReason
        mockTask.retry.assert_not_called()

    def testScenario3_QueueCountsReturnedBeforeReprocessing(
        self,
        emailRepository: EmailRepository,
        emailService: EmailService,
        rateLimiterService: RateLimiterService
    ):
        """
        Scenario 3:
        1. Query MongoDB for successful email count.
        2. Query MongoDB for permanently failed email count.
        3. Return both counts first.
        4. Trigger failed-email reprocessing only after counts returned.
        5. Fetch failed emails from MongoDB.
        6. Reprocess them one by one through Celery.
        7. If successful, update status to SUCCESS.
        8. If unsuccessful, retain FAILED status and update failure information.
        """
        # Setup: 3 Succeeded emails and 2 Failed emails
        for i in range(3):
            emailRepository.saveEmail(
                emailRepository.saveEmail.__annotations__["emailDocument"](
                    _id=f"success-job-{i}",
                    recipient=f"success{i}@example.com",
                    subject="Success",
                    body="Body",
                    status=EmailStatus.SUCCESS,
                    completedAt="2026-11-04T00:00:00Z"
                )
            )

        # 1 failed email that will succeed upon reprocessing
        emailRepository.saveEmail(
            emailRepository.saveEmail.__annotations__["emailDocument"](
                _id="failed-job-recoverable",
                recipient="recoverable@example.com",
                subject="Recoverable Job",
                body="Body",
                status=EmailStatus.FAILED,
                failureReason="Simulated previous outage",
                retryCount=3
            )
        )

        # 1 failed email that will fail again (permanent)
        emailRepository.saveEmail(
            emailRepository.saveEmail.__annotations__["emailDocument"](
                _id="failed-job-unrecoverable",
                recipient="unrecoverable@permanent-fail.com",
                subject="Unrecoverable Job",
                body="Body",
                status=EmailStatus.FAILED,
                failureReason="Simulated previous outage",
                retryCount=3
            )
        )

        # Requirement 1, 2, 3: Query counts and return both counts FIRST
        initialCounts, targetFailedIds = emailService.prepareReprocessFailedEmails()

        # Assert counts returned match the snapshot BEFORE reprocessing begins
        assert initialCounts == {
            "succeeded_queue_count": 3,
            "failed_queue_count": 2,
        }
        assert set(targetFailedIds) == {"failed-job-recoverable", "failed-job-unrecoverable"}

        # Requirement 4, 5, 6: Trigger failed-email reprocessing
        dispatchedCount = emailService.executeReprocessFailedEmails(targetFailedIds)
        assert dispatchedCount == 2

        # Requirement 7: The recoverable email is updated to SUCCESS
        recoveredDoc = emailRepository.findById("failed-job-recoverable")
        assert recoveredDoc.status == EmailStatus.SUCCESS
        assert recoveredDoc.completedAt is not None

        # Requirement 8: The unrecoverable email retains FAILED status with updated failure info
        unrecoveredDoc = emailRepository.findById("failed-job-unrecoverable")
        assert unrecoveredDoc.status == EmailStatus.FAILED
        assert "mailbox does not exist" in unrecoveredDoc.failureReason

        # Verify updated queue counts after reprocessing
        updatedCounts = emailService.getQueueCounts()
        assert updatedCounts["succeeded_queue_count"] == 4
        assert updatedCounts["failed_queue_count"] == 1

