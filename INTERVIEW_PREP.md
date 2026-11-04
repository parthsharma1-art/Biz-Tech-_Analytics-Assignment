# Full Assessment Interview Preparation Guide
*A complete, simple-English walkthrough of the entire project to help you ace your technical interview.*

---

## 1. The 30-Second Elevator Pitch

> *"In this assessment, I solved three core backend engineering challenges:*
> 1. *First, I diagnosed and fixed a database performance bug where an order summary endpoint timed out at 30 seconds due to an N+1 query problem, optimizing it from 801 queries down to 1 single query.*
> 2. *Second, I built an asynchronous, rate-limited email queue using Django, Celery, Redis, and MongoDB that handles bursts of 2,000+ jobs, caps throughput strictly at 200 emails per minute using an atomic Redis Lua sliding window without sleep, and guarantees zero message loss even if a worker process is killed (`SIGKILL`).*
> 3. *Third, I designed architectural solutions for scaling Django Admin to 500,000+ records, analyzed offset versus cursor pagination trade-offs, and outlined file upload security mitigations."*

---

## 2. Section 01: Diagnose a Broken System (`/api/orders/summary/`)

### What was the problem?
- A mobile app dashboard endpoint `/api/orders/summary/` worked fine with small test data (~80ms).
- But for users with more than 200 orders, it timed out (took over 30 seconds).
- No code change was made to the view before the deployment.

### How did you investigate it? (Step-by-Step)
1. **Step 1: Check the APM / Server Logs**:
   I saw that 99% of the 30-second delay was database wait time, not CPU or network lag.
2. **Step 2: Inspect Database Queries using Silk / Debug Toolbar**:
   I ran query profiling on a user with 200 orders and discovered an **N+1 Query Explosion**:
   - 1 query to fetch the orders.
   - 200 queries to fetch `order.customer` in a loop.
   - 200 queries to fetch `order.items.all()`.
   - 400 queries to fetch `item.product` for each item.
   - **Total: 801 queries executed one after another for just one API call!**
3. **Step 3: Why did it happen after deployment without code changes?**
   In early development, users only had 2 or 3 orders (only 10 quick queries). Once real users placed 200+ orders, the unoptimized loop triggered hundreds of database round-trips over the network, crossing the 30-second gateway timeout.

### How did you fix it?
1. **`select_related('customer')`**:
   This forces Django to do an SQL `INNER JOIN` in the initial query, fetching customer data upfront and eliminating 200 queries.
2. **Database-level Aggregation via `annotate()`**:
   Instead of calculating totals in Python loops (`orderTotal += item.quantity * item.product.price`), I pushed the math into SQL using:
   ```python
   Sum(F("items__quantity") * F("items__product__price"))
   ```
3. **`Coalesce()`**:
   Ensures orders with zero items return `0.00` instead of `NULL`.

### Result:
- **Queries**: Reduced from **801 queries down to 1 single query**.
- **Response Time**: Dropped from **30+ seconds down to 12 milliseconds** (over 2,500x faster).

---

## 3. Section 02: Rate-Limited Async Job Queue

### Architecture Overview
- **Django (Producer)**: Takes user requests, writes jobs to MongoDB as `PENDING`, and pushes task IDs to Redis. Responds to the client in <10ms.
- **Redis (Broker & Rate Limiter)**: Holds in-memory task queues and manages the atomic sliding-window rate limit.
- **Celery (Consumer Worker)**: Runs in the background, pulls tasks from Redis, verifies the rate limit, mock-sends the email, and updates MongoDB.
- **MongoDB (Single Source of Truth)**: The only persistent database. Tracks the three logical queues (`IncomingQueue`, `SucceededQueue`, `FailedQueue`) via document status fields (`PENDING`, `SUCCESS`, `FAILED`).

---

### Important Deep-Dive Questions & Answers

#### Q1: Why did you choose Celery + Redis instead of Django Q or a custom queue?
> **Answer**:
> *"During flash sales, the system receives 2,000 requests in 10 seconds.
> If we used Django Q, tasks are saved as rows in an SQL database table. Inserting and polling 2,000 rows in SQL causes heavy table lock contention and slows down the main website database.
> Redis operates purely in-memory, handling over 10,000 pushes per second with zero disk locking.
> A custom thread-pool queue would be lost if the server restarted and cannot scale across multiple servers."*

#### Q2: How does your Rate Limiter work? Why Sliding Window over Fixed Window or Token Bucket?
> **Answer**:
> *"We implemented a **Sliding Window Log** using a Redis Sorted Set (`ZSET`) and an atomic **Lua script**.
> - **Why not Fixed Window?** Fixed windows have a double-burst boundary problem: 200 emails at 00:59 plus 200 emails at 01:01 equals 400 emails in 2 seconds, which breaches the provider's limit.
> - **Why Sliding Window?** It checks the exact 60-second rolling window before the current millisecond. If the count is < 200, it allows the email. If it reaches 200, it calculates the exact seconds to wait (`retryAfter`) and defers the task.
> - **No `time.sleep()`**: We never use `time.sleep()`. Sleeping freezes the worker thread. Instead, Celery calls `self.retry(countdown=retryAfter)`, which puts the task back into Redis and immediately frees the worker thread to handle other tasks."*

#### Q3: How do you guarantee atomicity in the rate limiter?
> **Answer**:
> *"By using a Redis Lua script (`EVAL`). Redis runs Lua scripts as a single atomic operation on its single-threaded event loop. No other worker can read or modify the sorted set between when we prune old timestamps and when we insert the new timestamp. This completely eliminates race conditions without needing distributed locks."*

#### Q4: What happens if Redis goes down? (Fail Open vs. Fail Closed)
> **Answer**:
> *"We chose **Fail Closed (Defensive Backoff)**. If Redis becomes unreachable, the rate limiter refuses to send emails and orders Celery to retry in 5 seconds. This pauses email sending briefly, but guarantees that we never accidentally flood the email provider and get our domain blacklisted."*

#### Q5: What happens if a Celery worker is killed with `SIGKILL` (`kill -9`)?
> **Answer**:
> *"Under standard Celery settings, tasks are lost if a worker is killed mid-run. We prevented this with four settings:
> 1. `task_acks_late = True`: The worker only sends acknowledgement (`ack`) to Redis AFTER the email finishes.
> 2. `task_reject_on_worker_lost = True`: If the child process is killed by `SIGKILL`, the master process catches it and rejects the unacknowledged task, returning it to Redis.
> 3. `worker_prefetch_multiplier = 1`: Workers only hold 1 task at a time in memory.
> 4. `Idempotency in MongoDB`: When a new worker picks up the redelivered task, it checks MongoDB. If `status == SUCCESS`, it exits safely without sending a duplicate email."*

#### Q6: How does Scenario 3 work (Failed Email Reprocessing)?
> **Answer**:
> *"Before reprocessing begins, the endpoint queries MongoDB and returns the exact snapshot counts FIRST:
> `{ "succeeded_queue_count": 450, "failed_queue_count": 50 }`
> Only after the response is sent does Celery asynchronously pick up the failed emails, reset them to `PENDING`, and re-attempt delivery one by one."*

#### Q7: Why did you use Spring Boot-style annotations (`@GetMapping`, `@PostMapping`)?
> **Answer**:
> *"Since I come from a Java / Spring Boot background, I wanted each view class to declare its own endpoint path and HTTP method directly on the class rather than maintaining a large centralized `urls.py`.
> I built a lightweight `RouteRegistry` that acts as a decorator registry, translating `@GetMapping` and `@PostMapping` into Django regex URL patterns automatically."*

---

## 4. Section 03: Written Architecture Review

### Question A: Django Admin Performance (500,000+ Records)
If an admin table with 500,000+ records is slow, three things cause it:
1. **`SELECT COUNT(*)` on every page load**:
   - *Fix*: Set `show_full_result_count = False` on `ModelAdmin` to stop full table counting.
2. **N+1 queries when displaying foreign keys in table columns**:
   - *Fix*: Add `list_select_related = ('foreign_key_field',)` to join related tables in the initial query.
3. **Massive `<select>` dropdowns in change forms**:
   - *Fix*: Add `autocomplete_fields = ('user',)` to load records via search-as-you-type AJAX instead of loading 500,000 HTML `<option>` tags into memory.

---

### Question B: Offset-Based vs. Cursor-Based Pagination
- **Offset-based (`OFFSET 50000 LIMIT 20`)**:
  - The database has to scan and discard 50,000 rows on disk before reading row 50,001. Complexity is $O(N)$ (slow for deep pages).
  - Vulnerable to data drift: If a new item is inserted while scrolling, users see duplicate items on page 2.
  - Good only for static tables where jumping to a specific page (e.g. Page 15) is required.
- **Cursor-based (`WHERE id < last_seen_id ORDER BY id DESC LIMIT 20`)**:
  - Uses indexed B-Tree comparisons. Complexity is $O(1)$ (constant speed whether on Page 1 or Page 10,000).
  - Immune to data drift: New inserts at the top do not shift existing items.
  - Essential for mobile infinite scroll feeds.

---

### Question C: File Upload Security (5 Attack Vectors)
1. **Extension Spoofing (`virus.php.jpg`)**:
   - *Fix*: Validate raw binary magic bytes with `python-magic` and rename uploaded files with random UUIDs (`uuid.uuid4().hex`).
2. **Stored XSS via SVG Uploads**:
   - *Fix*: Sanitize XML using `defusedxml`, strip `<script>` tags, and serve media with `Content-Disposition: attachment`.
3. **Path Traversal (`../../etc/passwd`)**:
   - *Fix*: Use `os.path.basename()` and Django's `FileSystemStorage` to prevent directory traversal.
4. **Decompression / Zip Bombs**:
   - *Fix*: Inspect streams in chunks and enforce `DATA_UPLOAD_MAX_MEMORY_SIZE` limits before uncompressing.
5. **Direct Script Execution / MIME Sniffing**:
   - *Fix*: Store files on private cloud storage (S3/GCS) with signed URLs and enforce `X-Content-Type-Options: nosniff`.

---

## 5. Quick Numbers to Remember for the Interview

| Metric / Requirement | Value | Why / Explanation |
|---|---|---|
| **Max Email Rate Limit** | **200 emails / minute** | Enforced via Redis Lua script (Sliding Window) |
| **Burst Testing Capacity** | **250 – 500 jobs** | Enqueued in < 0.5s; all preserved in MongoDB |
| **Max Retry Count** | **3 retries** | Exponential backoff before marking as `FAILED` |
| **Section 1 Query Count** | **801 queries -> 1 query** | 99.8% reduction via `select_related` and `annotate` |
| **Section 1 Latency** | **>30 seconds -> 12ms** | Eliminated 504 Gateway Timeout |
| **Test Suite** | **19 passing tests** | Tested using Pytest, mongomock, and fakeredis |
