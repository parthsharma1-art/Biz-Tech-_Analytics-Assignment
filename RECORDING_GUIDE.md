# Screen Recording Guide (Section 4 Optional Demo)

This guide provides a step-by-step walkthrough and word-for-word narration script for your 5–10 minute Loom recording.

---

## 1. Screen Layout Setup

Arrange your desktop into **two split terminal windows**:

| Left Window (50% screen) | Right Window (50% screen) |
|---|---|
| **Terminal 1: Celery Worker Logs** | **Terminal 2: Live Demo & Dashboard** |
| Run: `celery -A emailsystem worker -l info -P solo` | Run: `python demo_queue.py` |

---

## 2. Walkthrough & Narration Script (Minute-by-Minute)

### Minute 0:00 – 1:00 | Introduction & Architecture
- **Action**: Show your IDE and open terminals.
- **Narrate**:
  > *"Hello! In this recording, I will demonstrate our Section 2 asynchronous email processing queue built with Django, Celery, Redis, and MongoDB.
  > We implemented an atomic Redis sliding-window rate limiter capped strictly at 200 emails per minute, late task acknowledgement (`acks_late=True`) to survive worker crashes, and exponential backoff retry logic.
  > Let's start the Celery worker and run a burst simulation."*

---

### Minute 1:00 – 2:30 | Start Worker & Burst Ingestion
- **Action in Left Terminal**:
  ```powershell
  celery -A emailsystem worker -l info -P solo
  ```
- **Narrate**:
  > *"Here you can see the Celery worker connecting to our local Redis broker on port 6379 with solo concurrency for Windows.
  > Notice the registered tasks: `processEmailTask` and `reprocessFailedEmailsTask`."*
- **Action in Right Terminal**:
  ```powershell
  python demo_queue.py
  ```
- **Narrate**:
  > *"Now I am running `demo_queue.py`, which simulates a flash-sale burst by submitting 250 email jobs into Redis in under 2 seconds.
  > All jobs are persisted to MongoDB first with status `PENDING`, making MongoDB our single source of truth."*

---

### Minute 2:30 – 4:30 | Real-Time Throttling (200 Emails/Minute Cap)
- **Action**: Point to the live table output in Terminal 2 and the log stream in Terminal 1.
- **Narrate**:
  > *"Notice what is happening in real time:
  > The Celery worker rapidly processes the first 200 emails.
  > Look at the table column: `Rate Limiter (ZCARD)` reaches exactly 200/200 emails/min.
  > As soon as the 201st email arrives, the Redis Lua sliding window denies immediate execution without using blocking `time.sleep()`.
  > Instead, Celery reschedules the task with a countdown, deferring the remaining jobs so we never breach the provider's 200/min cap."*

---

### Minute 4:30 – 6:30 | Exponential Backoff Retry Demonstration
- **Action**: Point to Terminal 1 (Celery worker logs) where `retry-demo@transient-fail.com` is processed.
- **Narrate**:
  > *"Here in the Celery logs, notice job #5 for `retry-demo@transient-fail.com`.
  > We intentionally simulated a transient SMTP network failure.
  > Celery catches the exception and schedules retry #1 with exponential backoff (`retry_backoff=True`).
  > Notice that MongoDB does not prematurely mark it as `FAILED`; it increments `retryCount` in MongoDB and re-attempts with a backoff delay.
  > Only if all 3 retries are exhausted does it move to `FailedQueue` with the root cause diagnostics saved."*

---

### Minute 6:30 – 7:30 | MongoDB Queue Counts & Conclusion
- **Action**: Point to the final summary printed in Terminal 2 or query `/api/v1/emails/counts/` in Postman.
- **Narrate**:
  > *"To conclude, we inspect the logical queue counts in MongoDB:
  > The successfully delivered emails are counted in `succeeded_queue_count`.
  > Zero jobs were lost during the burst ingestion, and the global rate limiter strictly protected our email provider from being overwhelmed.
  > Thank you for watching!"*

---

## 3. Adding Your Link to README.md

After recording on [Loom.com](https://www.loom.com), open [`README.md`](file:///c:/Users/parth/OneDrive/Desktop/BizTechAnaltics-Assignment/README.md) and paste your link under the **Optional Demo Recording** section:

```markdown
## Optional System Recording
Watch the 5-minute live demonstration of the queue, rate limiter, and backoff retry:
- **Loom Recording**: [https://www.loom.com/share/your-recording-id](https://www.loom.com/share/your-recording-id)
```

