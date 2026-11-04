"""
Streamlit Web Application & Interactive Dashboard
BizTech Analytics - Email Processing Queue & System Diagnostics Hub

Provides an interactive user interface for:
- Section 1: Database Query Profiler & N+1 Cascade Benchmark (801 vs 1 query)
- Section 2: Real-time Email Queue Monitor, Metrics, Job Inspector
- Section 2: Single & Batch Flash Sale Job Dispatcher
- Section 2: Scenario 3 Dead-Letter Queue (DLQ) & Failed Email Reprocessing
- Section 3: Architecture, System Design & Interview Reference
"""

import os
import sys
import time
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, List, Optional

import streamlit as st
import pandas as pd

# -----------------------------------------------------------------------------
# 1. Django Framework Initialization
# -----------------------------------------------------------------------------
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "emailsystem.settings")
try:
    import django
    django.setup()
except Exception as djangoInitError:
    st.error(f"Failed to initialize Django environment: {djangoInitError}")

from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.db import connection

from emailqueue.models.EmailDocument import EmailDocument, EmailStatus
from emailqueue.repositories.EmailRepository import EmailRepository
from emailqueue.services.EmailService import EmailService
from emailqueue.services.RateLimiterService import RateLimiterService
from emailqueue.config.RedisConfig import RedisConfig
from emailqueue.config.MongoConfig import MongoConfig
from emailsystem.celery import celeryApp

from orders.models import Customer, Product, Order, OrderItem
from orders.views import OrdersSummaryUnoptimizedView, OrdersSummaryOptimizedView

# -----------------------------------------------------------------------------
# 2. Page Configuration & Custom CSS
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="EmailQueue Enterprise Hub",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom styling for professional enterprise dashboard
st.markdown("""
<style>
    /* Metric Card Enhancements */
    div[data-testid="stMetricValue"] {
        font-size: 1.85rem !important;
        font-weight: 700 !important;
    }
    .metric-card {
        background-color: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 8px;
        padding: 14px;
        margin-bottom: 12px;
    }
    .status-badge-success {
        color: #155724;
        background-color: #d4edda;
        padding: 3px 8px;
        border-radius: 4px;
        font-weight: 600;
    }
    .status-badge-failed {
        color: #721c24;
        background-color: #f8d7da;
        padding: 3px 8px;
        border-radius: 4px;
        font-weight: 600;
    }
    .status-badge-pending {
        color: #856404;
        background-color: #fff3cd;
        padding: 3px 8px;
        border-radius: 4px;
        font-weight: 600;
    }
    .status-badge-processing {
        color: #004085;
        background-color: #cce5ff;
        padding: 3px 8px;
        border-radius: 4px;
        font-weight: 600;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 6px 6px 0 0;
        padding: 10px 18px;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 3. Helper Services & Singletons
# -----------------------------------------------------------------------------
@st.cache_resource
def getEmailService() -> EmailService:
    return EmailService()

@st.cache_resource
def getEmailRepository() -> EmailRepository:
    return EmailRepository()

@st.cache_resource
def getRateLimiterService() -> RateLimiterService:
    return RateLimiterService()

emailService = getEmailService()
emailRepository = getEmailRepository()
rateLimiterService = getRateLimiterService()

# -----------------------------------------------------------------------------
# 4. Infrastructure Health Checkers
# -----------------------------------------------------------------------------
def checkRedisHealth() -> Dict[str, Any]:
    try:
        redisClient = RedisConfig.getInstance().getClient()
        startTime = time.time()
        redisClient.ping()
        latencyMs = round((time.time() - startTime) * 1000, 2)
        celeryQueueLen = redisClient.llen("celery")
        return {
            "connected": True,
            "latencyMs": latencyMs,
            "celeryQueueLen": celeryQueueLen,
            "error": None
        }
    except Exception as exc:
        return {
            "connected": False,
            "latencyMs": 0,
            "celeryQueueLen": 0,
            "error": str(exc)
        }

def checkMongoHealth() -> Dict[str, Any]:
    try:
        mongoConfig = MongoConfig.getInstance()
        mongoClient = mongoConfig.getClient()
        startTime = time.time()
        mongoClient.admin.command("ping")
        latencyMs = round((time.time() - startTime) * 1000, 2)
        totalDocs = mongoConfig.getEmailsCollection().count_documents({})
        return {
            "connected": True,
            "latencyMs": latencyMs,
            "totalDocs": totalDocs,
            "error": None
        }
    except Exception as exc:
        return {
            "connected": False,
            "latencyMs": 0,
            "totalDocs": 0,
            "error": str(exc)
        }

def checkCeleryWorkerHealth() -> Dict[str, Any]:
    try:
        inspect = celeryApp.control.inspect(timeout=0.6)
        pingResult = inspect.ping()
        if pingResult:
            workers = list(pingResult.keys())
            return {"active": True, "workers": workers, "count": len(workers)}
        return {"active": False, "workers": [], "count": 0}
    except Exception:
        return {"active": False, "workers": [], "count": 0}

# -----------------------------------------------------------------------------
# 5. Sidebar Controls & Real-Time Monitoring
# -----------------------------------------------------------------------------
with st.sidebar:
    st.title("⚡ System Control")
    st.caption("BizTech Analytics - Technical Assessment")

    # Refresh Controls
    colRefresh1, colRefresh2 = st.columns([1, 1])
    with colRefresh1:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()
    with colRefresh2:
        autoRefresh = st.checkbox("Auto (3s)", value=False)

    st.divider()

    # Infrastructure Status
    st.subheader("🖥️ Infrastructure Health")
    redisHealth = checkRedisHealth()
    mongoHealth = checkMongoHealth()
    workerHealth = checkCeleryWorkerHealth()

    if redisHealth["connected"]:
        st.success(f"**Redis**: Connected ({redisHealth['latencyMs']} ms)")
    else:
        st.error(f"**Redis**: Disconnected\n`{redisHealth['error']}`")

    if mongoHealth["connected"]:
        st.success(f"**MongoDB**: Connected ({mongoHealth['latencyMs']} ms)")
    else:
        st.error(f"**MongoDB**: Disconnected\n`{mongoHealth['error']}`")

    if workerHealth["active"]:
        st.success(f"**Celery**: {workerHealth['count']} Worker(s) Online")
    else:
        st.warning("**Celery Worker**: Offline / Standby")
        st.caption("Start worker: `celery -A emailsystem worker --loglevel=info --pool=solo`")

    st.divider()

    # Rate Limiter Live Window Gauge
    st.subheader("⏱️ Rate Limiter (Sliding Window)")
    currentWindowCount = rateLimiterService.getCurrentCount()
    maxLimit = rateLimiterService.maxLimit
    windowPct = min(1.0, currentWindowCount / maxLimit)

    st.metric(
        label="Emails in Last 60 Seconds",
        value=f"{currentWindowCount} / {maxLimit}",
        delta=f"{maxLimit - currentWindowCount} capacity left",
        delta_color="normal" if currentWindowCount < maxLimit else "inverse"
    )
    st.progress(windowPct)

    if currentWindowCount >= maxLimit:
        st.error("⚠️ Rate limit reached! Tasks will backoff.")

    if st.button("🧹 Clear Rate Limiter Window", use_container_width=True):
        rateLimiterService.reset()
        st.toast("Sliding window rate limit key reset in Redis!", icon="✅")
        st.rerun()

    st.divider()
    st.caption(f"Broker Task Queue: **{redisHealth.get('celeryQueueLen', 0)}** pending jobs")
    st.caption(f"MongoDB Total Records: **{mongoHealth.get('totalDocs', 0)}** docs")

# -----------------------------------------------------------------------------
# 6. Main Dashboard Tabs
# -----------------------------------------------------------------------------
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Queue Monitor & Metrics",
    "🚀 Enqueue & Flash Sale",
    "🔁 DLQ & Failed Reprocessing",
    "⚡ Section 1: Query Profiler",
    "📚 Architecture & Specs"
])

# =============================================================================
# TAB 1: Real-Time Queue Monitor & Metrics
# =============================================================================
with tab1:
    st.header("📊 Real-Time Queue Monitor")
    st.caption("Asynchronous email queue state queried live from MongoDB (Source of Truth).")

    # Fetch counts
    counts = emailRepository.getQueueCounts()
    incomingCount = counts["incoming_queue_count"]
    succeededCount = counts["succeeded_queue_count"]
    failedCount = counts["failed_queue_count"]
    totalCount = incomingCount + succeededCount + failedCount

    colKpi1, colKpi2, colKpi3, colKpi4 = st.columns(4)
    with colKpi1:
        st.metric(label="📥 Incoming / In-Flight", value=incomingCount, delta="PENDING + PROCESSING")
    with colKpi2:
        st.metric(label="✅ Succeeded", value=succeededCount, delta="SUCCESS (Delivered)")
    with colKpi3:
        st.metric(label="❌ Failed (DLQ)", value=failedCount, delta="Dead-Letter Queue", delta_color="inverse")
    with colKpi4:
        st.metric(label="📦 Total Enqueued", value=totalCount, delta="Total Lifetime")

    # Queue Distribution Bar
    if totalCount > 0:
        pctSuccess = round((succeededCount / totalCount) * 100, 1)
        pctFailed = round((failedCount / totalCount) * 100, 1)
        pctIncoming = round((incomingCount / totalCount) * 100, 1)
        st.write(
            f"**Distribution:** Succeeded: `{pctSuccess}%` | Failed: `{pctFailed}%` | In-Flight: `{pctIncoming}%`"
        )
    st.divider()

    # Search and Filter Records
    st.subheader("📑 Job Repository Records")
    colFilter1, colFilter2, colFilter3 = st.columns([1, 2, 1])
    with colFilter1:
        statusFilter = st.selectbox(
            "Filter by Status:",
            ["ALL", EmailStatus.SUCCESS, EmailStatus.PENDING, EmailStatus.PROCESSING, EmailStatus.FAILED]
        )
    with colFilter2:
        searchQuery = st.text_input("Search by Recipient or Job ID:", placeholder="e.g. user_42 or @example.com")
    with colFilter3:
        recordLimit = st.selectbox("Show Records:", [25, 50, 100, 250], index=1)

    # Query MongoDB for records
    mongoQuery: Dict[str, Any] = {}
    if statusFilter != "ALL":
        mongoQuery["status"] = statusFilter
    if searchQuery.strip():
        searchClean = searchQuery.strip()
        mongoQuery["$or"] = [
            {"recipient": {"$regex": searchClean, "$options": "i"}},
            {"_id": {"$regex": searchClean, "$options": "i"}}
        ]

    try:
        rawDocs = list(
            emailRepository.getCollection()
            .find(mongoQuery)
            .sort("createdAt", -1)
            .limit(recordLimit)
        )
    except Exception as dbErr:
        st.error(f"Failed to query MongoDB: {dbErr}")
        rawDocs = []

    if rawDocs:
        tableData = []
        for doc in rawDocs:
            tableData.append({
                "Job ID": doc.get("_id"),
                "Recipient": doc.get("recipient"),
                "Subject": doc.get("subject"),
                "Status": doc.get("status"),
                "Retries": doc.get("retryCount", 0),
                "Created At": doc.get("createdAt", "")[:19].replace("T", " "),
                "Updated At": doc.get("updatedAt", "")[:19].replace("T", " "),
                "Failure Reason": doc.get("failureReason") or "-",
            })

        dfRecords = pd.DataFrame(tableData)
        st.dataframe(dfRecords, use_container_width=True, hide_index=True)
    else:
        st.info("No matching email records found in MongoDB.")

    # Email Detail Inspector
    st.subheader("🔍 Detailed Job Inspector")
    jobIds = [doc.get("_id") for doc in rawDocs]
    selectedJobId = st.selectbox("Select a Job ID to inspect audit trail:", ["-- Select Job --"] + jobIds)

    if selectedJobId and selectedJobId != "-- Select Job --":
        selectedDoc = emailRepository.findById(selectedJobId)
        if selectedDoc:
            docDict = selectedDoc.toDict()
            colDoc1, colDoc2 = st.columns([1, 1])
            with colDoc1:
                st.write("**Core Document Metadata:**")
                st.json({
                    "id": docDict.get("_id"),
                    "recipient": docDict.get("recipient"),
                    "subject": docDict.get("subject"),
                    "status": docDict.get("status"),
                    "retryCount": docDict.get("retryCount"),
                    "maxRetries": docDict.get("maxRetries"),
                    "failureReason": docDict.get("failureReason"),
                    "createdAt": docDict.get("createdAt"),
                    "completedAt": docDict.get("completedAt"),
                })
            with colDoc2:
                st.write("**`processingHistory` Audit Trail (Worker Events):**")
                history = docDict.get("processingHistory", [])
                if history:
                    for idx, entry in enumerate(history):
                        statusBadge = entry.get("status")
                        timestamp = entry.get("timestamp", "")[:19].replace("T", " ")
                        msg = entry.get("message")
                        retries = entry.get("retryCount", 0)
                        st.markdown(
                            f"**{idx + 1}. `{statusBadge}`** | *{timestamp}* | Retries: `{retries}`<br/>"
                            f"&nbsp;&nbsp;↳ {msg}",
                            unsafe_allow_html=True
                        )
                else:
                    st.caption("No history entries logged yet.")

# =============================================================================
# TAB 2: Enqueue & Flash Sale Burst Simulator
# =============================================================================
with tab2:
    st.header("🚀 Email Job Dispatcher & Flash Sale Simulation")
    st.caption("Submit single email requests or simulate high-volume flash sale bursts into Celery & Redis.")

    subTabSingle, subTabBatch = st.tabs(["✉️ Single Email Dispatch", "⚡ Flash Sale Burst (Scenario 2)"])

    # Single Email Form
    with subTabSingle:
        st.subheader("Submit Single Email Job")
        with st.form("single_email_form"):
            col1, col2 = st.columns(2)
            with col1:
                inputRecipient = st.text_input("Recipient Email:", value="customer@example.com")
            with col2:
                inputSubject = st.text_input("Subject:", value="Your Order Confirmation #4092")

            inputBody = st.text_area("Email Body:", value="Thank you for your purchase with BizTech Analytics!")
            simulateFailure = st.checkbox(
                "Simulate Intentional Transient Failure (Tests Exponential Retry Backoff)",
                value=False,
                help="Appends 'simulated_transient_failure' flag in payload to trigger simulated network dropout and worker retry."
            )

            submitSingle = st.form_submit_button("📨 Enqueue Email Job", use_container_width=True)

        if submitSingle:
            if not inputRecipient.strip():
                st.error("Recipient email cannot be empty!")
            else:
                bodyPayload = inputBody
                if simulateFailure:
                    bodyPayload += " [SIMULATE_FAILURE: intentional_network_timeout]"

                try:
                    customJobId = f"single_{int(time.time())}_{inputRecipient.split('@')[0]}"
                    enqueued = emailService.enqueueEmail(
                        recipient=inputRecipient.strip(),
                        subject=inputSubject.strip(),
                        body=bodyPayload,
                        emailId=customJobId
                    )
                    st.success(f"✅ Successfully enqueued email job `{enqueued._id}`! Status: `{enqueued.status}`")
                    st.toast("Email enqueued into Celery/Redis!", icon="🚀")
                except Exception as err:
                    st.error(f"Error enqueuing email: {err}")

    # Flash Sale Batch Simulation
    with subTabBatch:
        st.subheader("Flash Sale High-Volume Burst")
        st.info(
            "Simulates the assessment scenario: Burst-submitting up to 250 emails at once to demonstrate that "
            "the system enqueues all requests instantly into Redis & MongoDB, while the Celery worker throttles "
            "execution to exactly 200 emails per minute via the atomic Redis sliding window."
        )

        with st.form("flash_sale_form"):
            colBurst1, colBurst2 = st.columns(2)
            with colBurst1:
                burstCount = st.slider("Number of Email Jobs:", min_value=10, max_value=250, value=250, step=10)
            with colBurst2:
                failCount = st.slider("Simulated Transient Failures:", min_value=0, max_value=10, value=1, step=1)

            burstPrefix = st.text_input("Batch Identifier Prefix:", value=f"flash_{int(time.time())}")
            submitBurst = st.form_submit_button("⚡ Launch Flash Sale Burst", use_container_width=True)

        if submitBurst:
            startTime = time.time()
            emailList = []
            for i in range(1, burstCount + 1):
                isSimulatedFailure = (i <= failCount)
                body = f"Flash Sale Confirmation #{i} for user_{i}@biztech.io."
                if isSimulatedFailure:
                    body += " [SIMULATE_FAILURE: simulated_gateway_timeout]"

                emailList.append({
                    "emailId": f"{burstPrefix}_job_{i:03d}",
                    "recipient": f"user_{i:03d}@flashsale-biztech.io",
                    "subject": f"Flash Sale Order #{i:03d}",
                    "body": body,
                })

            progressBar = st.progress(0)
            statusText = st.empty()

            statusText.text(f"Submitting {burstCount} email jobs into MongoDB and Celery/Redis...")
            enqueuedDocs = emailService.enqueueBatchEmails(emailList)
            progressBar.progress(100)

            elapsedMs = round((time.time() - startTime) * 1000, 2)
            st.success(
                f"🎉 Successfully burst-enqueued **{len(enqueuedDocs)}** emails in **{elapsedMs} ms**!\n\n"
                f"- Initial Status: All persisted as `PENDING` in MongoDB\n"
                f"- Task Broker: 250 tasks dispatched to Redis queue `celery`\n"
                f"- Rate Limiter: The Celery worker will enforce ≤ 200 emails/min\n"
                f"- Intentional Failures: **{failCount}** jobs configured for exponential retry backoff."
            )

# =============================================================================
# TAB 3: Dead-Letter Queue & Failed Reprocessing (Scenario 3)
# =============================================================================
with tab3:
    st.header("🔁 Dead-Letter Queue (DLQ) & Failed Email Reprocessing")
    st.caption("Demonstration of Assessment Scenario 3: Reprocessing failed emails.")

    st.markdown("""
    **Scenario 3 Flow:**
    1. Returns current queue counts (`succeeded_queue_count`, `failed_queue_count`) **before** reprocessing starts.
    2. Identifies all emails in MongoDB with `status = FAILED`.
    3. Atomically updates their status to `PENDING` and resets `retryCount = 0`.
    4. Re-enqueues each task back into Celery and Redis.
    """)

    currentCounts = emailService.getQueueCounts()
    failedDocs = emailRepository.findFailedEmails(limit=100)
    failedCountCurrent = len(failedDocs)

    colStat1, colStat2, colStat3 = st.columns(3)
    with colStat1:
        st.metric("Succeeded Queue Count", currentCounts["succeeded_queue_count"])
    with colStat2:
        st.metric("Failed Queue Count (DLQ)", currentCounts["failed_queue_count"])
    with colStat3:
        st.metric("Eligible for Reprocessing", failedCountCurrent)

    st.subheader(f"Dead-Letter Queue Items ({failedCountCurrent} jobs)")
    if failedDocs:
        failedTable = []
        for doc in failedDocs:
            failedTable.append({
                "Job ID": doc._id,
                "Recipient": doc.recipient,
                "Subject": doc.subject,
                "Retries Exhausted": f"{doc.retryCount} / {doc.maxRetries}",
                "Failure Reason": doc.failureReason or "Unknown Error",
                "Last Updated": doc.updatedAt[:19].replace("T", " "),
            })
        st.dataframe(pd.DataFrame(failedTable), use_container_width=True, hide_index=True)

        if st.button("🔁 Trigger Reprocess All Failed Emails (Scenario 3)", type="primary", use_container_width=True):
            # Step 1: Pre-reprocessing snapshot
            preCounts, targetIds = emailService.prepareReprocessFailedEmails(batchLimit=100)
            # Step 2: Dispatch reprocessing
            dispatchedCount = emailService.executeReprocessFailedEmails(targetIds)

            st.success(
                f"✅ **Scenario 3 Reprocessing Executed Successfully!**\n\n"
                f"- **Pre-reprocess Snapshot**: Succeeded: `{preCounts['succeeded_queue_count']}`, Failed: `{preCounts['failed_queue_count']}`\n"
                f"- **Jobs Reset to PENDING & Dispatched**: `{dispatchedCount}` tasks\n"
                f"- Tasks are now re-queued in Celery and will be processed under rate limits."
            )
            st.rerun()
    else:
        st.info("No failed emails currently in the Dead-Letter Queue.")

    st.divider()
    st.subheader("🧹 System Reset & Maintenance Zone")
    colClean1, colClean2 = st.columns(2)
    with colClean1:
        if st.button("Clear Rate Limiter Window Only"):
            rateLimiterService.reset()
            st.toast("Rate limiter key deleted from Redis.")
            st.rerun()
    with colClean2:
        if st.button("⚠️ Purge All MongoDB Email Records (Fresh Start)"):
            emailRepository.getCollection().delete_many({})
            st.toast("All documents removed from MongoDB `emails` collection.")
            st.rerun()

# =============================================================================
# TAB 4: Section 1 Database Query Profiler (N+1 Diagnostic)
# =============================================================================
with tab4:
    st.header("⚡ Section 1: Database Query Diagnostic & Profiler")
    st.caption("Demonstration of the N+1 Query Cascade bug (801 queries -> 504 Timeout) vs DB-level aggregation (1 query).")

    # Check existing data in SQLite
    customerCount = Customer.objects.count()
    orderCount = Order.objects.count()
    itemCount = OrderItem.objects.count()

    colDb1, colDb2, colDb3 = st.columns(3)
    with colDb1:
        st.metric("Benchmark Customers", customerCount)
    with colDb2:
        st.metric("Benchmark Orders", orderCount)
    with colDb3:
        st.metric("Benchmark Order Items", itemCount)

    # Seeding button
    if orderCount < 200:
        st.warning("⚠️ Benchmark requires at least 200 orders for a customer to reproduce the N+1 bug.")
        if st.button("🌱 Seed Benchmark Dataset (1 Customer, 200 Orders, 400 Items)", use_container_width=True):
            with st.spinner("Seeding database with 200 orders..."):
                Customer.objects.all().delete()
                Product.objects.all().delete()
                Order.objects.all().delete()
                OrderItem.objects.all().delete()

                customer = Customer.objects.create(name="Jane Doe", email="jane.doe@enterprise.io")
                prod1 = Product.objects.create(name="Enterprise Server", price=Decimal("1500.00"), sku="SRV-01")
                prod2 = Product.objects.create(name="SAN Storage", price=Decimal("800.00"), sku="SAN-01")

                orderList = [Order(customer=customer, status=Order.STATUS_COMPLETED) for _ in range(200)]
                createdOrders = Order.objects.bulk_create(orderList)

                itemList = []
                for order in createdOrders:
                    itemList.append(OrderItem(order=order, product=prod1, quantity=2, unitPrice=prod1.price))
                    itemList.append(OrderItem(order=order, product=prod2, quantity=1, unitPrice=prod2.price))
                OrderItem.objects.bulk_create(itemList)

            st.success("✅ Successfully seeded 1 Customer, 200 Orders, and 400 OrderItems!")
            st.rerun()

    st.divider()

    # Benchmark Execution
    st.subheader("🚀 Live Side-by-Side Performance Comparison")
    if customerCount > 0:
        targetCustomer = Customer.objects.first()
        st.write(f"Testing customer: **{targetCustomer.name}** (`{targetCustomer.email}`) with **200 Orders**")

        if st.button("⚡ Execute Side-by-Side Benchmark", type="primary", use_container_width=True):
            rf = RequestFactory()

            # 1. Run Unoptimized View
            unoptRequest = rf.get(f"/api/orders/summary/slow/?customerId={targetCustomer.id}")
            startUnopt = time.time()
            with CaptureQueriesContext(connection) as unoptQueries:
                unoptResponse = OrdersSummaryUnoptimizedView.as_view()(unoptRequest)
            durationUnoptMs = round((time.time() - startUnopt) * 1000, 2)
            unoptCount = len(unoptQueries.captured_queries)

            # 2. Run Optimized View
            optRequest = rf.get(f"/api/orders/summary/?customerId={targetCustomer.id}")
            startOpt = time.time()
            with CaptureQueriesContext(connection) as optQueries:
                optResponse = OrdersSummaryOptimizedView.as_view()(optRequest)
            durationOptMs = round((time.time() - startOpt) * 1000, 2)
            optCount = len(optQueries.captured_queries)

            queryReduction = round(((unoptCount - optCount) / unoptCount) * 100, 2)
            speedup = round(durationUnoptMs / max(0.01, durationOptMs), 1)

            st.markdown("### 📊 Benchmark Results")
            colRes1, colRes2, colRes3 = st.columns(3)
            with colRes1:
                st.metric(
                    label="Unoptimized (Buggy View)",
                    value=f"{unoptCount} SQL Queries",
                    delta=f"{durationUnoptMs} ms latency",
                    delta_color="inverse"
                )
            with colRes2:
                st.metric(
                    label="Optimized (Single Query)",
                    value=f"{optCount} SQL Query",
                    delta=f"{durationOptMs} ms latency",
                    delta_color="normal"
                )
            with colRes3:
                st.metric(
                    label="Performance Improvement",
                    value=f"{queryReduction}% Fewer Queries",
                    delta=f"{speedup}x Faster Execution"
                )

            # Chart Comparison
            chartData = pd.DataFrame({
                "Implementation": ["Unoptimized (N+1 Bug)", "Optimized (SQL Aggregation)"],
                "SQL Queries Executed": [unoptCount, optCount],
                "Execution Time (ms)": [durationUnoptMs, durationOptMs]
            })

            colChart1, colChart2 = st.columns(2)
            with colChart1:
                st.write("**Total SQL Database Queries**")
                st.bar_chart(chartData, x="Implementation", y="SQL Queries Executed", color="Implementation")
            with colChart2:
                st.write("**Execution Time (ms)**")
                st.bar_chart(chartData, x="Implementation", y="Execution Time (ms)", color="Implementation")

            st.success(
                f"🎯 **Root Cause Explained:** The unoptimized view triggered 1 query for Orders + 200 for Customer "
                f"+ 200 for OrderItems + 400 for Products = **{unoptCount} queries**! Over a cloud database with network latency, "
                f"this caused 504 Gateway Timeouts. The optimized view uses `select_related` and DB-level `annotate(Sum(...))` "
                f"to fetch everything in **EXACTLY {optCount} query**."
            )

    st.info(
        "💡 **Django Silk Profiler:** You can inspect SQL query execution trees, database time breakdowns, "
        "and request timelines directly in Silk at `http://127.0.0.1:8000/silk/` when the Django server is running."
    )

# =============================================================================
# TAB 5: Architecture & Technical Specifications
# =============================================================================
with tab5:
    st.header("📚 System Architecture & Technical Specifications")

    st.subheader("1. System Component Architecture")
    st.markdown("""
    ```
    ┌───────────────────────┐         ┌────────────────────────┐
    │   Web / REST Client   │ ──────> │  Django REST Endpoints │
    │   & Streamlit Hub     │         │ (@GetMapping/@PostM.)  │
    └───────────────────────┘         └───────────┬────────────┘
                                                  │
                                                  ▼
                                      ┌────────────────────────┐
                                      │  MongoDB Job Store     │ (Persistent Source of Truth)
                                      │  - Initial: PENDING    │
                                      │  - History Audit Log   │
                                      └───────────┬────────────┘
                                                  │
                                                  ▼
                                      ┌────────────────────────┐
                                      │   Redis Broker Queue   │ (Celery Task Pipeline)
                                      └───────────┬────────────┘
                                                  │
                                                  ▼
                                      ┌────────────────────────┐
                                      │   Celery Worker Pool   │
                                      │   (acks_late = True)   │
                                      └───────────┬────────────┘
                                                  │
                                  ┌───────────────┴───────────────┐
                                  ▼                               ▼
                     ┌────────────────────────┐     ┌────────────────────────┐
                     │ Redis Lua Rate Limiter │     │ Mock Email Gateway     │
                     │ (Sliding 60s Window)   │     │ (Transient Retry / DLQ)│
                     │ Max 200 / minute       │     └────────────────────────┘
                     └────────────────────────┘
    ```
    """)

    st.divider()

    st.subheader("2. Critical Architectural Questions (Section 3)")

    with st.expander("Q1: How does the system survive worker crashes mid-processing without lost jobs?"):
        st.markdown("""
        - **`task_acks_late = True`**: Celery only acknowledges the task to Redis **after** the task function successfully completes, never when it is picked up.
        - **`task_reject_on_worker_lost = True`**: If a worker process is killed (`SIGKILL`, OOM, power cut), the broker detects disconnect and immediately re-queues the unacknowledged task.
        - **Atomic Claiming in MongoDB**: Before processing, the worker updates the MongoDB document status to `PROCESSING` with a timestamp. If a worker dies, dead-letter recovery can find jobs stuck in `PROCESSING` longer than a threshold.
        """)

    with st.expander("Q2: How does the sliding window rate limiter work and why is it better than a fixed window?"):
        st.markdown("""
        - **The Fixed-Window Flaw**: In a fixed window (e.g. 00:00 - 01:00), a client could send 200 requests at 00:59 and another 200 requests at 01:00. This results in **400 requests in 2 seconds**, violating upstream provider limits!
        - **The Sliding Window Solution**: We use a Redis Sorted Set (`ZSET`) with an atomic Lua script:
          1. `ZREMRANGEBYSCORE key -inf (now - 60)`: Prunes events older than 60 seconds.
          2. `ZCARD key`: Counts requests within the exact rolling 60-second window.
          3. If count < 200: adds `(timestamp, uuid)` and permits execution.
          4. If count ≥ 200: finds the oldest timestamp in the window and calculates exact seconds until the next slot opens.
        - **Zero Blocking**: The worker calls `self.retry(countdown=retryAfter)` without calling `time.sleep()`, leaving worker threads free to process other tasks.
        """)

    with st.expander("Q3: Exactly-Once vs At-Least-Once Delivery & Idempotency"):
        st.markdown("""
        - In distributed networks, true **Exactly-Once delivery is mathematically impossible** under arbitrary network partitions (Two Generals' Problem).
        - We implement **At-Least-Once delivery with Idempotent Consumer Processing**:
          1. Every email job has a deterministic or UUID-based `_id`.
          2. MongoDB enforces `_id` uniqueness, preventing duplicate submissions.
          3. When executing, the worker checks if `status == SUCCESS`. If so, it immediately exits without re-calling the external email gateway.
          4. When calling third-party providers (SES, SendGrid, Mailgun), we attach an `Idempotency-Key` header with `job._id`.
        """)

    with st.expander("Q4: Spring Boot Style Annotations in Python/Django"):
        st.markdown("""
        The project implements Java Spring Boot style decorators:
        - `@RestController`
        - `@RequestMapping("/api/mail")`
        - `@PostMapping("/send")`
        - `@GetMapping("/counts")`

        These decorators inspect HTTP methods, handle JSON body serialization/deserialization, and register routes automatically with Django's URL routing registry!
        """)

# Auto-refresh mechanism
if autoRefresh:
    time.sleep(3)
    st.rerun()
