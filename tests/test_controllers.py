import json
import pytest
from django.test import RequestFactory

from emailqueue.controllers.EmailController import (
    EnqueueEmailView,
    QueueCountsView,
    ReprocessFailedEmailsView,
    EmailDetailView
)
from emailqueue.models.EmailDocument import EmailStatus
from emailqueue.repositories.EmailRepository import EmailRepository

class TestEmailControllers:
    def setup_method(self):
        self.factory = RequestFactory()

    def testEnqueueSingleEmail(self, emailRepository: EmailRepository):
        payload = {
            "recipient": "api-user@example.com",
            "subject": "Welcome",
            "body": "Welcome to our platform!"
        }
        request = self.factory.post(
            "/api/v1/emails/",
            data=json.dumps(payload),
            content_type="application/json"
        )
        response = EnqueueEmailView.as_view()(request)
        assert response.status_code == 201

        responseData = json.loads(response.content.decode("utf-8"))
        assert responseData["recipient"] == "api-user@example.com"
        assert responseData["status"] in (EmailStatus.PENDING, EmailStatus.SUCCESS)

    def testGetQueueCountsEndpoint(self, emailRepository: EmailRepository):
        # Insert 1 success and 1 failed
        emailRepository.saveEmail(
            emailRepository.saveEmail.__annotations__["emailDocument"](
                _id="cnt-success-1",
                recipient="u1@example.com",
                subject="Sub",
                body="Body",
                status=EmailStatus.SUCCESS,
                completedAt="2026-11-04T00:00:00Z"
            )
        )
        emailRepository.saveEmail(
            emailRepository.saveEmail.__annotations__["emailDocument"](
                _id="cnt-failed-1",
                recipient="u2@example.com",
                subject="Sub",
                body="Body",
                status=EmailStatus.FAILED,
                failureReason="Permanent failure"
            )
        )

        request = self.factory.get("/api/v1/emails/counts/")
        response = QueueCountsView.as_view()(request)
        assert response.status_code == 200

        data = json.loads(response.content.decode("utf-8"))
        assert data["succeeded_queue_count"] == 1
        assert data["failed_queue_count"] == 1

    def testReprocessFailedEmailsEndpointReturnsCountsFirst(self, emailRepository: EmailRepository):
        emailRepository.saveEmail(
            emailRepository.saveEmail.__annotations__["emailDocument"](
                _id="reprocess-test-1",
                recipient="failed-user@example.com",
                subject="Sub",
                body="Body",
                status=EmailStatus.FAILED,
                failureReason="Initial transient timeout"
            )
        )

        request = self.factory.post("/api/v1/emails/reprocess-failed/")
        response = ReprocessFailedEmailsView.as_view()(request)
        assert response.status_code == 200

        data = json.loads(response.content.decode("utf-8"))
        # Must return current counts
        assert "succeeded_queue_count" in data
        assert "failed_queue_count" in data
        assert data["failed_queue_count"] == 1

    def testGetEmailDetailNotFound(self, emailRepository: EmailRepository):
        request = self.factory.get("/api/v1/emails/non-existent-id/")
        response = EmailDetailView.as_view()(request, emailId="non-existent-id")
        assert response.status_code == 404
