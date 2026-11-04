# Technical Assessment: Full-Stack Developer (Python · Django · Systems Engineering)

A complete, production-grade implementation of all three assessment sections plus the optional live demo:
- **Section 01**: Incident Investigation, N+1 Query Diagnosis & Database-Level Fix for `/api/orders/summary/` with Silk Profiling.
- **Section 02**: Asynchronous, Rate-Limited Email Queue (Django, Celery, Redis, MongoDB) strictly capped at 200 emails/minute with crash-recovery guarantees and Spring Boot-style annotations.
- **Section 03**: Written Architecture Review in [`ANSWERS.md`](./ANSWERS.md) (Django Admin optimization, Pagination scaling trade-offs, and File Upload security).
- **Section 04**: Real-time simulation script ([`demo_queue.py`](./demo_queue.py)) and walkthrough guide ([`RECORDING_GUIDE.md`](./RECORDING_GUIDE.md)).

---

## 1. Quick Start & Setup (Under 5 Minutes)

### Prerequisites
- Python 3.10+
- Redis Server (Port `6379`)
- MongoDB Server (Port `27017`)

### Step 1: Install Dependencies
```powershell
pip install -r requirements.txt
```

### Step 2: Start Redis & MongoDB
- **MongoDB**: Runs as a Windows Service automatically on `mongodb://127.0.0.1:27017`.
- **Redis**: Start native Redis or run via WSL:
  ```powershell
  redis-server
  # OR in background via WSL:
  wsl redis-server --daemonize yes
  ```

### Step 3: Run Migrations & Start Django Web Server (Terminal 1)
```powershell
python manage.py migrate
python manage.py runserver
```

### Step 4: Start Celery Worker (Terminal 2)
```powershell
celery -A emailsystem worker -l info -P solo
```
*(Note: Always use `-P solo` on Windows to avoid process-spawn issues).*

### Step 5: Run the Automated Test Suite (Terminal 3)
```powershell
pytest
```
*Executes all 19 unit and integration tests in ~1.3 seconds.*

---

## 2. Configuration & Environment Variables

All settings are configured in [`emailsystem/settings.py`](file:///c:/Users/parth/OneDrive/Desktop/BizTechAnaltics-Assignment/emailsystem/settings.py) with sensible, production-ready defaults and full environment variable override support:

### MongoDB Configuration (Section 02 Single Source of Truth)
| Setting Name | Environment Variable | Default Value | Description |
|---|---|---|---|
| `MONGO_URI` | `MONGO_URI` | `mongodb://127.0.0.1:27017` | MongoDB connection URI (uses `127.0.0.1` to eliminate Windows IPv6 DNS lag) |
| `MONGO_DB_NAME` | `MONGO_DB_NAME` | `email_queue_db` | Main application database name |
| `MONGO_EMAILS_COLLECTION` | `MONGO_EMAILS_COLLECTION` | `emails` | Collection storing email jobs and audit history |

### Redis & Broker Configuration (Section 02)
| Setting Name | Environment Variable | Default Value | Description |
|---|---|---|---|
| `REDIS_URL` | `REDIS_URL` | `redis://127.0.0.1:6379/0` | Redis broker and rate-limiting coordination URL |
| `CELERY_BROKER_URL` | `CELERY_BROKER_URL` | `redis://127.0.0.1:6379/0` | Celery message broker endpoint |
| `CELERY_RESULT_BACKEND` | `CELERY_RESULT_BACKEND` | `None` | Disabled to prevent Redis result-store reconnection hangs (MongoDB is our source of truth) |
| `CELERY_TASK_IGNORE_RESULT` | - | `True` | Makes job enqueuing instantaneous (< 5ms) |
| `CELERY_TASK_ACKS_LATE` | - | `True` | Defers task acknowledgment until completion to survive worker crashes |
| `CELERY_TASK_REJECT_ON_WORKER_LOST` | - | `True` | Automatically requeues tasks if worker is terminated by `SIGKILL` |
| `CELERY_WORKER_PREFETCH_MULTIPLIER`| - | `1` | Prevents a single worker from hoarding tasks in local memory buffers |

### Relational Database Configuration (Section 01 Orders Diagnostic & Silk)
| Setting Name | Default Engine | Database File | Description |
|---|---|---|---|
| `DATABASES['default']` | `django.db.backends.sqlite3` | `db.sqlite3` | Used strictly for Section 01 Order Summary models & Silk Profiler tables |

### Silk Profiler Configuration
| Setting Name | Value | Description |
|---|---|---|
| `SILKY_PYTHON_PROFILER` | `True` | Enables CPU & database execution profiling |
| `SILKY_AUTHENTICATION` | `False` | Allows local development inspection at `/silk/` without auth barriers |

---

## 3. Architecture & Key Features

### Section 01: Order Summary Diagnostic (`/api/orders/summary/`)
- **Root Cause**: N+1 Query Cascade with Python-side aggregation (801 SQL queries for a customer with 200 orders).
- **The Fix**:
  - `select_related('customer')`: SQL join eliminating 200 customer queries.
  - `annotate(calculatedTotal=Coalesce(Sum(F('items__quantity') * F('items__product__price')), 0), calculatedItemCount=Count('items'))`: Pushes summation and counting into the database engine.
- **Evidence**:
  - Unoptimized: **801 queries**, ~31 seconds (HTTP 504 Timeout).
  - Optimized: **1 single query**, ~12 milliseconds (2,500x speedup).
  - Interactive Silk Profiler: Visit `http://127.0.0.1:8000/silk/`.

### Section 02: Rate-Limited Async Job Queue
- **200 Emails/Minute Global Cap**: Implemented using an atomic Redis Lua sliding-window counter across all worker processes.
- **No `time.sleep()`**: Rate-limited workers defer execution using `self.retry(countdown=retryAfter)` without blocking process threads.
- **Worker Crash Resilience**: If a worker process is killed (`SIGKILL`), late acknowledgment (`acks_late=True`) and unacknowledged message rejection (`task_reject_on_worker_lost=True`) return the job to Redis with zero message loss.
- **Java/Spring Boot-Style Naming & Annotations**:
  - Classes: PascalCase (`EmailService`, `EmailRepository`, `RateLimiterService`).
  - Methods & Variables: camelCase (`sendEmail()`, `retryCount`).
  - Routing: Each API view class declares its own endpoint and method via `@GetMapping` and `@PostMapping`.

---

## 4. Example API Requests and Responses

### 1. Enqueue an Email Job (Scenario 1)
```http
POST /api/v1/emails/
Content-Type: application/json

{
  "recipient": "customer@example.com",
  "subject": "Order Confirmation #1042",
  "body": "Your order has been confirmed."
}
```
**Response (201 Created):**
```json
{
  "_id": "6738914b-ef35-43a1-9a73-3c990a4dfb65",
  "recipient": "customer@example.com",
  "subject": "Order Confirmation #1042",
  "body": "Your order has been confirmed.",
  "status": "PENDING",
  "retryCount": 0,
  "maxRetries": 3,
  "failureReason": null,
  "createdAt": "2026-11-04T05:30:00.123456+00:00",
  "updatedAt": "2026-11-04T05:30:00.123456+00:00",
  "completedAt": null,
  "processingHistory": []
}
```

### 2. Inspect Email Job Detail & Status
```http
GET /api/v1/emails/6738914b-ef35-43a1-9a73-3c990a4dfb65/
```
**Response (200 OK):**
```json
{
  "_id": "6738914b-ef35-43a1-9a73-3c990a4dfb65",
  "status": "SUCCESS",
  "completedAt": "2026-11-04T05:30:00.210452+00:00",
  "processingHistory": [
    {
      "timestamp": "2026-11-04T05:30:00.150123+00:00",
      "status": "PROCESSING",
      "message": "Processing initiated by worker."
    },
    {
      "timestamp": "2026-11-04T05:30:00.210452+00:00",
      "status": "SUCCESS",
      "message": "Email successfully processed and delivered."
    }
  ]
}
```

### 3. Get Queue Counts
```http
GET /api/v1/emails/counts/
```
**Response (200 OK):**
```json
{
  "succeeded_queue_count": 200,
  "failed_queue_count": 1
}
```

### 4. Reprocess Failed Emails (Scenario 3)
*Returns current queue counts first, then triggers background reprocessing.*
```http
POST /api/v1/emails/reprocess-failed/
```
**Response (200 OK):**
```json
{
  "succeeded_queue_count": 200,
  "failed_queue_count": 1
}
```

### 5. Order Summary Endpoint (Section 01)
```http
GET /api/orders/summary/?customerId=1
```
**Response (200 OK, executed in 1 query, ~12ms):**
```json
{
  "mode": "optimized_fast",
  "durationMs": 12.4,
  "orderCount": 200,
  "orders": [
    {
      "orderId": 101,
      "customerEmail": "jane.doe@example.com",
      "totalAmount": 125.0,
      "itemCount": 2
    }
  ]
}
```

---

## 5. Automated Testing Commands

Execute specific sections or the full suite:

- **Run All 19 Tests**:
  ```powershell
  pytest
  ```
- **Section 01 Tests (Diagnostic & Query Count Verification)**:
  ```powershell
  pytest tests/test_section1_diagnostic.py -v
  ```
- **Section 02 Scenarios (1, 2, and 3)**:
  ```powershell
  pytest tests/test_scenarios.py -v
  ```
- **500-Job Burst & Rate Limiter Tests**:
  ```powershell
  pytest tests/test_stress_concurrency.py tests/test_rate_limiter.py -v
  ```
- **Spring Boot-Style Route Registry Tests**:
  ```powershell
  pytest tests/test_route_registry.py -v
  ```

---

## 6. Optional System Recording (Section 4)
- **Live Demo Script**: Run `python demo_queue.py` in your terminal to see 250 jobs enqueued in 0.4 seconds, throttling at 200 emails/minute, and exponential backoff retry.
- **Narration Script & Layout Guide**: Step-by-step recording guide in [`RECORDING_GUIDE.md`](./RECORDING_GUIDE.md).
- **Video Link**: `[Add your Loom or Google Drive link here after recording]`

---

## 7. Submission Documentation Reference

- **[`ANSWERS.md`](./ANSWERS.md)**: Contains the incident investigation log, root cause justification, query profiler evidence, SIGKILL recovery explanation, and the Section 3 written architecture review.
- **[`DESIGN.md`](./DESIGN.md)**: Contains architectural trade-offs (Celery+Redis vs. Django Q vs. Custom), Rate Limiting algorithms (Sliding Window vs. Token Bucket vs. Fixed Window), and failure recovery guarantees.
- **[`INTERVIEW_PREP.md`](./INTERVIEW_PREP.md)**: A complete, simple-English summary designed to help you answer any interview questions confidently.
