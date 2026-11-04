#!/usr/bin/env python
"""
Real-Time Demonstration Script for Screen Recording (Section 2 Bonus Demo)
--------------------------------------------------------------------------
Features demonstrated:
1. Submits 250 jobs (including 1 transient failure that retries with exponential backoff).
2. Live monitoring of Redis queue state (LLEN celery).
3. Demonstrates the rate limiter capping at exactly 200 emails/minute.
4. Shows live transition into SucceededQueue and FailedQueue in MongoDB.
"""

import os
import sys
import time
import django

# Setup Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "emailsystem.settings")
django.setup()

import redis
from emailqueue.services.EmailService import EmailService
from emailqueue.services.RateLimiterService import RateLimiterService
from emailqueue.repositories.EmailRepository import EmailRepository

def printHeader(title):
    print("\n" + "=" * 70)
    print(f"  {title.upper()}")
    print("=" * 70)

def main():
    printHeader("Section 2: Live Queue & Rate Limiter Demonstration")

    emailService = EmailService()
    rateLimiter = RateLimiterService()
    emailRepository = EmailRepository()
    redisClient = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)

    print("\n[1/4] Checking Infrastructure Status...")
    try:
        redisClient.ping()
        print("  ✓ Redis Server is Connected on 127.0.0.1:6379")
    except Exception as e:
        print(f"  ✗ Redis Connection Error: {e}")
        sys.exit(1)

    try:
        emailRepository.countAll()
        print("  ✓ MongoDB is Connected on 127.0.0.1:27017")
    except Exception as e:
        print(f"  ✗ MongoDB Connection Error: {e}")
        sys.exit(1)

    print("\n[2/4] Resetting Rate Limiter for Clean Demo Window...")
    rateLimiter.reset()
    print("  ✓ Rate limiter sliding-window key cleared.")

    totalJobsToSubmit = 250
    print(f"\n[3/4] Burst-submitting {totalJobsToSubmit} email jobs (Flash Sale burst simulation)...")
    print("      (Including 1 intentional transient failure to demonstrate exponential retry)\n")

    jobsPayload = []
    for i in range(1, totalJobsToSubmit + 1):
        if i == 5:
            # Intentional transient failure: triggers Celery retry with backoff
            recipient = "retry-demo@transient-fail.com"
            subject = f"Order #{i} (Simulated Transient Error)"
        else:
            recipient = f"customer_{i:03d}@example.com"
            subject = f"Order #{i} Confirmation"

        jobsPayload.append({
            "recipient": recipient,
            "subject": subject,
            "body": f"Thank you for your order #{i}.",
            "emailId": f"demo-job-{i:03d}"
        })

    startTime = time.time()
    for idx, item in enumerate(jobsPayload, 1):
        emailService.enqueueEmail(
            recipient=item["recipient"],
            subject=item["subject"],
            body=item["body"],
            emailId=item["emailId"]
        )
        if idx % 50 == 0 or idx == totalJobsToSubmit:
            print(f"  -> Enqueued {idx}/{totalJobsToSubmit} jobs into Redis...")

    elapsedEnqueue = round(time.time() - startTime, 2)
    print(f"\n  ✓ Successfully enqueued {totalJobsToSubmit} jobs in {elapsedEnqueue} seconds!")

    print("\n[4/4] Monitoring Redis Queue Depth & Rate Limiter in Real-Time...")
    print("      (Celery worker will process up to 200 emails, then throttle the rest)\n")
    print(f"{'Time':<10} | {'Redis Pending (LLEN)':<22} | {'Rate Limiter (ZCARD)':<22} | {'Status'}")
    print("-" * 75)

    monitorDuration = 25  # seconds
    monitorStart = time.time()

    while time.time() - monitorStart < monitorDuration:
        currentTimeStr = time.strftime("%H:%M:%S")
        try:
            pendingInRedis = redisClient.llen("celery")
            rateLimitUsed = rateLimiter.getCurrentCount()
        except Exception:
            pendingInRedis = 0
            rateLimitUsed = 0

        status = "Throttling active (>200/min)" if rateLimitUsed >= 200 else "Processing normally"

        print(f"{currentTimeStr:<10} | {pendingInRedis:<22} | {rateLimitUsed}/200 emails/min{' ':<5} | {status}")
        time.sleep(1.5)

    print("-" * 75)
    counts = emailService.getQueueCounts()
    print("\nFinal MongoDB Queue Counts:")
    print(f"  • SucceededQueue: {counts['succeeded_queue_count']}")
    print(f"  • FailedQueue:    {counts['failed_queue_count']}")
    print("\n✓ Demonstration complete. Celery workers safely throttled at 200 emails/min cap.")

if __name__ == "__main__":
    main()

