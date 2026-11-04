# Technical Assessment: Full-Stack Developer (Python · Django · Systems Engineering)

A production-grade implementation of all required sections:
1. **Section 01**: Incident Investigation, N+1 Query Diagnosis & ORM Fix for `/api/orders/summary/` with Silk Profiling.
2. **Section 02**: Asynchronous Rate-Limited Email Queue (Celery + Redis + MongoDB) adhering to Java/Spring Boot conventions.
3. **Section 03**: Written Architecture Review answering Questions A, B, and C in `ANSWERS.md`.

---

## Quick Start (Run in under 5 minutes)

### 1. Prerequisites
- Python 3.10+
- Redis (Windows native or WSL on port `6379`)
- MongoDB (Running on port `27017`)

### 2. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 3. Run Migrations & Start Servers
```powershell
python manage.py migrate
python manage.py runserver
```

In a separate terminal, start the Celery worker for Section 02:
```powershell
celery -A emailsystem worker -l info -P solo
```

### 4. Run All Automated Tests
```powershell
pytest
```
*All 19 tests pass in ~1.2 seconds across all sections.*

---

## Section 01: Diagnose a Broken System (`/api/orders/summary/`)

- **Root Cause**: N+1 Query Cascade with Python-side aggregation (801 SQL queries for 200 orders).
- **The Fix**: Pushed joins and aggregation to the database using `select_related('customer')` and `annotate(calculatedTotal=Coalesce(Sum(F('quantity') * F('unitPrice')), 0))`.
- **Query Count Reduction**: Drops from **801 queries down to 1 single query**.
- **Execution Time**: Drops from **>30,000ms down to ~12ms**.
- **Silk Profiler UI**: Access interactive query profiling at `http://127.0.0.1:8000/silk/`.
- **Test Command**:
  ```powershell
  pytest tests/test_section1_diagnostic.py -v
  ```

---

## Section 02: Rate-Limited Async Job Queue

- **Technology Stack**: Celery, Redis broker, MongoDB (sole persistent queue database).
- **Rate Limiter**: Sliding Window Log capped at **200 emails per minute**, implemented as an atomic Redis Lua script.
- **Worker Crash Safety**: `task_acks_late=True` and `task_reject_on_worker_lost=True` ensure zero job loss on worker `SIGKILL`.
- **Java-Style Naming**: PascalCase classes (`EmailService`, `EmailController`, `EmailRepository`), camelCase methods and variables (`sendEmail()`, `retryCount`).
- **Spring Boot-Style API Routing**: `@PostMapping`, `@GetMapping`, and `@RequestMapping` declared directly on views.
- **Test Command**:
  ```powershell
  pytest tests/test_scenarios.py tests/test_rate_limiter.py tests/test_stress_concurrency.py -v
  ```

---

## Section 03: Written Architecture Review

All detailed written answers are documented in [`ANSWERS.md`](file:///c:/Users/parth/OneDrive/Desktop/BizTechAnaltics-Assignment/ANSWERS.md):
- **Question A**: Django Admin Performance Optimization on 500,000+ records.
- **Question B**: Offset-based vs. Cursor-based pagination trade-offs at scale.
- **Question C**: File Upload Security: 5 distinct attack vectors and Django application-layer mitigations.

---

## Submission Documentation Reference

- **[`ANSWERS.md`](file:///c:/Users/parth/OneDrive/Desktop/BizTechAnaltics-Assignment/ANSWERS.md)**: Investigation log, root cause justification, profiler evidence, and Section 3 review.
- **[`DESIGN.md`](file:///c:/Users/parth/OneDrive/Desktop/BizTechAnaltics-Assignment/DESIGN.md)**: Section 2 architecture trade-offs (Celery vs. Django Q vs. Custom), rate-limiter design, atomicity, and failure modes.
