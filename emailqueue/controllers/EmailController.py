import json
import logging
from typing import Optional
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from emailqueue.services.EmailService import EmailService
from emailqueue.tasks.EmailTasks import reprocessFailedEmailsTask
from emailqueue.controllers.RouteRegistry import (
    RequestMapping,
    GetMapping,
    PostMapping,
)

logger = logging.getLogger(__name__)

class EmailController:
    def __init__(self, emailService: Optional[EmailService] = None):
        self.emailService = emailService or EmailService()

    def handleEnqueueEmail(self, request: HttpRequest) -> JsonResponse:
        """Handles POST /api/v1/emails/ for single or batch submission."""
        try:
            requestData = json.loads(request.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"error": "Invalid JSON body provided."}, status=400)

        # Batch submission support
        if "emails" in requestData and isinstance(requestData["emails"], list):
            emailsList = requestData["emails"]
            if not emailsList:
                return JsonResponse({"error": "Batch email list cannot be empty."}, status=400)
            
            createdDocs = self.emailService.enqueueBatchEmails(emailsList)
            return JsonResponse(
                {
                    "message": f"Successfully enqueued {len(createdDocs)} email jobs.",
                    "jobs": [doc.toDict() for doc in createdDocs]
                },
                status=201
            )

        # Single email submission
        recipient = requestData.get("recipient")
        subject = requestData.get("subject")
        body = requestData.get("body")
        customEmailId = requestData.get("emailId") or requestData.get("_id")

        if not recipient or not subject or body is None:
            return JsonResponse(
                {"error": "Missing required fields: 'recipient', 'subject', and 'body' are required."},
                status=400
            )

        try:
            createdDoc = self.emailService.enqueueEmail(
                recipient=recipient,
                subject=subject,
                body=body,
                emailId=customEmailId
            )
            return JsonResponse(createdDoc.toDict(), status=201)
        except Exception as error:
            logger.exception("Failed to enqueue email job: %s", str(error))
            return JsonResponse({"error": str(error)}, status=409 if "already exists" in str(error) else 500)

    def handleGetQueueCounts(self, request: HttpRequest) -> JsonResponse:
        """Handles GET /api/v1/emails/counts/."""
        queueCounts = self.emailService.getQueueCounts()
        return JsonResponse(queueCounts, status=200)

    def handleReprocessFailedEmails(self, request: HttpRequest) -> JsonResponse:
        """
        Scenario 3:
        1. Query MongoDB for successful email count.
        2. Query MongoDB for permanently failed email count.
        3. Return both counts FIRST.
        4. Trigger failed-email reprocessing asynchronously.
        """
        # Step 1-3: Retrieve counts and eligible failed email IDs first
        queueCounts, failedEmailIds = self.emailService.prepareReprocessFailedEmails()

        # Step 4: Trigger failed-email reprocessing asynchronously
        if failedEmailIds:
            reprocessFailedEmailsTask.delay(failedEmailIds)

        # Return the queue counts to caller
        return JsonResponse(queueCounts, status=200)

    def handleGetEmailById(self, request: HttpRequest, emailId: str) -> JsonResponse:
        """Handles GET /api/v1/emails/<emailId>/."""
        emailDoc = self.emailService.getEmailStatus(emailId)
        if emailDoc is None:
            return JsonResponse({"error": f"Email job '{emailId}' not found."}, status=404)
        return JsonResponse(emailDoc.toDict(), status=200)


# ==============================================================================
# Spring Boot-Inspired API Views (Self-declared endpoints and HTTP methods)
# ==============================================================================

@PostMapping(path="", name="enqueueEmail")
@method_decorator(csrf_exempt, name="dispatch")
class EnqueueEmailView(View):
    def post(self, request: HttpRequest) -> HttpResponse:
        controller = EmailController()
        return controller.handleEnqueueEmail(request)


@RequestMapping(path="counts", methods=["GET", "POST"], name="queueCounts")
@method_decorator(csrf_exempt, name="dispatch")
class QueueCountsView(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        controller = EmailController()
        return controller.handleGetQueueCounts(request)

    def post(self, request: HttpRequest) -> HttpResponse:
        controller = EmailController()
        return controller.handleGetQueueCounts(request)


@PostMapping(path="reprocess-failed", name="reprocessFailedEmails")
@method_decorator(csrf_exempt, name="dispatch")
class ReprocessFailedEmailsView(View):
    def post(self, request: HttpRequest) -> HttpResponse:
        controller = EmailController()
        return controller.handleReprocessFailedEmails(request)


@GetMapping(path="{emailId}", name="emailDetail")
@method_decorator(csrf_exempt, name="dispatch")
class EmailDetailView(View):
    def get(self, request: HttpRequest, emailId: str) -> HttpResponse:
        controller = EmailController()
        return controller.handleGetEmailById(request, emailId)


@GetMapping(path="health", name="emailQueueHealth")
@method_decorator(csrf_exempt, name="dispatch")
class EmailQueueHealthView(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        from emailsystem.views import healthCheckView
        return healthCheckView(request)

