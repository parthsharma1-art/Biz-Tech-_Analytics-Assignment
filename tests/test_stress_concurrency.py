import pytest
from unittest.mock import patch

from emailqueue.models.EmailDocument import EmailDocument, EmailStatus
from emailqueue.repositories.EmailRepository import EmailRepository, DuplicateEmailJobException
from emailqueue.services.EmailService import EmailService
from emailqueue.services.RateLimiterService import RateLimiterService

class TestStressAndConcurrency:

    def testSubmit500EmailJobs_NoJobsLost_NoDuplicates(
        self,
        emailRepository: EmailRepository,
        emailService: EmailService,
        rateLimiterService: RateLimiterService
    ):
        """
        Requirements 6, 7, 8:
        - Submit 500 email jobs.
        - No jobs are lost (total count in MongoDB is 500).
        - No duplicate email records are created.
        """
        TOTAL_JOBS = 500

        # Create 500 unique email job payloads
        batchJobs = [
            {
                "recipient": f"customer_{index}@company.com",
                "subject": f"Notice #{index}",
                "body": f"Notice content for customer #{index}",
                "emailId": f"job-uuid-{index:04d}"
            }
            for index in range(TOTAL_JOBS)
        ]

        # Ingest all 500 jobs with Celery dispatch mocked to isolate submission
        with patch("emailqueue.services.EmailService.processEmailTask.delay") as mockDelay:
            enqueuedDocuments = emailService.enqueueBatchEmails(batchJobs)
            assert len(enqueuedDocuments) == TOTAL_JOBS
            assert mockDelay.call_count == TOTAL_JOBS

        # Requirement 7: Verify all 500 jobs are persisted in MongoDB (none lost)
        totalSavedInDb = emailRepository.countAll()
        assert totalSavedInDb == TOTAL_JOBS

        # Requirement 8: Verify duplicate insertion is rejected
        duplicateJob = EmailDocument(
            _id="job-uuid-0000",
            recipient="duplicate@company.com",
            subject="Duplicate",
            body="Duplicate body",
            status=EmailStatus.PENDING
        )
        with pytest.raises(DuplicateEmailJobException):
            emailRepository.saveEmail(duplicateJob)

        # Confirm count remains exactly 500
        assert emailRepository.countAll() == TOTAL_JOBS

    def testRateLimiterNeverExceeds200EmailsPerMinute(
        self,
        rateLimiterService: RateLimiterService
    ):
        """
        Requirement 9:
        - Rate limiting strictly enforces at most 200 emails per minute globally.
        - Tests that even if 500 attempts arrive at once, only 200 are allowed,
          and remaining 300 receive proper backoff countdown.
        """
        MAX_PER_MINUTE = 200
        TOTAL_BURST_REQUESTS = 500

        allowedTotal = 0
        rejectedTotal = 0

        for reqIndex in range(TOTAL_BURST_REQUESTS):
            allowed, retryAfter = rateLimiterService.acquirePermission()
            if allowed:
                allowedTotal += 1
            else:
                rejectedTotal += 1
                assert retryAfter >= 1

        assert allowedTotal == MAX_PER_MINUTE
        assert rejectedTotal == (TOTAL_BURST_REQUESTS - MAX_PER_MINUTE)

        # Assert Redis sliding-window count is exactly 200
        assert rateLimiterService.getCurrentCount() == MAX_PER_MINUTE
