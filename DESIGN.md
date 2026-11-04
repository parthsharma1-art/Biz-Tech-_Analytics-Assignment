# Architectural and Technical Design Document

## 1. Architecture Choice & Comparative Trade-offs

### Evaluated Options

| Dimension | Celery + Redis (Chosen) | Django Q | Custom Queue (Threads/DB Table) |
|---|---|---|---|
| **Broker Architecture** | In-memory distributed broker (Redis) decoupled from relational DB | Django ORM / Relational DB polling | In-process memory or database row locking |
| **Throughput & Latency** | Extreme throughput (>10,000 tasks/sec), sub-millisecond dispatch | Moderate (~500–1,000 tasks/sec), limited by DB write locks | Low to moderate; scales poorly across multiple servers |
| **Worker Crash Recovery** | Built-in via Redis unacknowledged queue visibility + `acks_late` | Relational table row lock timeout / heartbeat monitoring | Complex manual implementation; prone to orphaned running locks |
| **Ecosystem & Maturity** | Battle-tested, native rate-limiting integration, exponential backoff | Simpler setup in small Django apps, but couples queue to SQL DB load | High engineering cost, high risk of edge-case bugs under concurrency |
| **Operational Overhead** | Requires maintaining a Redis instance | Minimal (shares existing relational database) | Zero external dependencies, but unmaintainable at scale |

### Why Celery + Redis Was Chosen
1. **Flash Sale Bursts (2,000 requests in <10s)**:
   - Pushing 2,000 tasks in 10 seconds to an SQL database (as Django Q does) floods the application database with row inserts, lock contention, and constant polling queries (`SELECT ... FOR UPDATE`), degrading database performance for web users.
   - Redis operates purely in-memory with non-blocking single-threaded event loops, easily absorbing thousands of task dispatches per second without touching disk storage.
2. **Decoupled Failure Domains**:
   - If the main database experiences high load or temporary maintenance, the queue ingestion layer (Django + Redis) remains fully responsive.
3. **Robust Late Acknowledgement**:
   - Celery's native `task_acks_late=True` and `task_reject_on_worker_lost=True` ensure that tasks killed by OS signals (`SIGKILL`) or node failure are never lost and are redelivered cleanly.

---

## 2. Rate Limiting Strategy: Pattern Evaluation & Guarantees

### Evaluated Rate Limiting Patterns

```
Window Comparison:
Fixed Window:     | [ 200 emails ] | [ 200 emails ] |  <- Vulnerable to 400 burst across boundary
Sliding Window:   <------- Continuous 60-Second Rolling Window (Max 200) ------->
```

| Strategy | Mechanism | Pros | Cons / Vulnerability |
|---|---|---|---|
| **Option A: Token Bucket** | Redis `DECR` + Periodic refill via TTL/cron | Supports controlled micro-bursts up to bucket capacity | Refill math under asynchronous multi-worker access requires continuous state updates or secondary timer threads. |
| **Option B: Sliding Window Log (Chosen)** | Redis Sorted Set (`ZSET`) + `ZREMRANGEBYSCORE` + `ZCARD` | **Zero boundary vulnerabilities**; strictly caps requests to 200 in *any* rolling 60-second slice. Calculates precise `retryAfter` wait times. | Higher memory footprint than a simple integer (mitigated by automated key expiration). |
| **Option C: Fixed Window** | Redis `INCR` + `EXPIRE` | Minimal memory footprint (single integer counter) | **Double-burst boundary vulnerability**: 200 requests at 00:59 followed by 200 requests at 01:01 yields 400 requests in 2 seconds, violating provider limits. |

### 1. Why Sliding Window Was Chosen
The third-party email provider enforces a hard limit of **200 emails per minute**. Fixed Window allows up to 400 emails across the boundary minute, risking immediate IP blacklisting. The Sliding Window Log records the exact millisecond timestamps of executed emails, guaranteeing that no rolling 60-second window ever contains more than 200 emails.

### 2. How Atomicity Is Guaranteed
Atomicity is guaranteed using a **Redis Lua script** executed via the `EVAL` command:
- In Redis, Lua scripts execute as an uninterrupted atomic transaction.
- Between removing expired timestamps (`ZREMRANGEBYSCORE`), inspecting the set cardinality (`ZCARD`), and conditionally inserting the timestamp (`ZADD`), no other worker process can interleave execution.
- This eliminates race conditions across distributed worker processes without requiring distributed locks (`Redlock`).

### 3. Behavior Under Redis Failure (Fail-Safe Strategy)
- The application implements a **Fail-Closed (Defensive Backoff)** policy:
  - If Redis becomes unreachable (`redis.ConnectionError` or `redis.TimeoutError`), the rate limiter **denies immediate execution** and returns `(allowed=False, retryAfter=5)`.
  - The Celery worker reschedules the email task via `self.retry(countdown=5)` rather than allowing unmetered emails to flood the third-party provider.
  - **Trade-off**: Email dispatch is briefly paused during a Redis outage, but the system guarantees that the provider's rate limit is never breached and the domain is never blacklisted.

---

## 3. Worker Crash Recovery & SIGKILL Lifecycle

### What Happens When a Celery Worker Is Killed (SIGKILL)?

When a worker process running an in-flight email task is abruptly terminated (`kill -9` / `SIGKILL` / kernel OOM killer):

1. **The In-Flight Dilemma in Standard Queue Configurations**:
   - Under standard Celery settings, a task is acknowledged (`ack`) *as soon as it is pulled from the queue*. If `SIGKILL` strikes mid-run, the task is gone from Redis, the document remains stuck in `PROCESSING`, and the email is permanently lost.
2. **Our Implementation Safeguards**:
   - **`task_acks_late = True`**: The Celery worker does **not** acknowledge the message upon receiving it. Acknowledgement is strictly deferred until the task function successfully completes.
   - **`task_reject_on_worker_lost = True`**: When the child worker process is killed (`SIGKILL`), the Celery master supervisor catches the abnormal child termination (`exitcode != 0`), automatically rejects the unacknowledged message, and Kombu requeues the task into Redis.
   - **`worker_prefetch_multiplier = 1`**: Prevents a single worker from grabbing a batch of pending tasks into local memory buffers. If that worker dies, only the single active task needs redelivery.
3. **Idempotency on Re-Delivery**:
   - When a healthy worker picks up the requeued task, it queries MongoDB:
     ```python
     if emailDocument.status == EmailStatus.SUCCESS:
         return {"status": EmailStatus.SUCCESS, "emailId": emailId}
     ```
   - If the task was interrupted before completion, the document is `PROCESSING` or `PENDING` and is safely re-executed without duplicate delivery.

---

## 4. MongoDB Document Schema & Data Architecture

MongoDB is the persistent source of truth for the email queue:

```json
{
  "_id": "6738914b-ef35-43a1-9a73-3c990a4dfb65",
  "recipient": "customer@example.com",
  "subject": "Order Confirmation",
  "body": "Your order has been confirmed.",
  "status": "PENDING",
  "retryCount": 0,
  "maxRetries": 3,
  "failureReason": null,
  "createdAt": "2026-11-04T04:30:00.123456+00:00",
  "updatedAt": "2026-11-04T04:30:00.123456+00:00",
  "completedAt": null,
  "processingHistory": [
    {
      "timestamp": "2026-11-04T04:30:00.234567+00:00",
      "status": "PROCESSING",
      "message": "Processing initiated by worker.",
      "retryCount": 0
    }
  ]
}
```

### The Three Logical Queues
- **`IncomingQueue`**: Documents matching `{"status": {"$in": ["PENDING", "PROCESSING"]}}`.
- **`SucceededQueue`**: Documents matching `{"status": "SUCCESS"}` with ISO-8601 `completedAt`.
- **`FailedQueue`**: Documents matching `{"status": "FAILED"}` with root cause in `failureReason` and `retryCount: 3`.

---

## 5. Retry Mechanism & Dead-Letter Handling

1. **Transient Errors**: Network timeouts or provider 5xx responses trigger:
   `self.retry(exc=error, retry_backoff=True, retry_kwargs={"max_retries": 3})`
   - Delay intervals follow deterministic exponential backoff ($2^{\text{retries}}$ seconds).
   - Each attempt updates `retryCount` and logs an entry in `processingHistory`.
2. **Permanent Failures**: Invalid emails or permanent provider rejections bypass retries and transition immediately to `FAILED`.
3. **Dead-Letter State (FailedQueue)**:
   - Retries exhausted at attempt 3 transition the document to `FAILED`.
   - The document remains stored in MongoDB for diagnostic auditing.
4. **Reprocessing (Scenario 3)**:
   - Calling `/api/v1/emails/reprocess-failed/` retrieves and returns the current queue counts first:
     ```json
     {
       "succeeded_queue_count": 450,
       "failed_queue_count": 50
     }
     ```
   - Only after returning this count does Celery asynchronously re-dispatch failed emails for one-by-one reprocessing.
