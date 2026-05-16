from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator

# ------------------------------------------------------------------
# 1. HTTP Instrumentator — auto-tracks latency, count, in-progress
#    for every FastAPI endpoint. Wired into the app in main.py.
# ------------------------------------------------------------------
instrumentator = Instrumentator(
    should_group_status_codes=True,
    should_ignore_untemplated=True,
    should_instrument_requests_inprogress=True,
    excluded_handlers=["/metrics", "/health", "/openapi.json", "/docs", "/redoc"],
    inprogress_name="http_requests_inprogress",
    inprogress_labels=True,
)

# ------------------------------------------------------------------
# 2. Business metric — counts optimization recommendations issued.
#    Emitted in optimizer.py at the point of each recommendation.
#    Labels: deployment, resource_type (cpu|memory), action (decrease|increase|no_change)
# ------------------------------------------------------------------
recommendations_total = Counter(
    "recommendations_issued_total",
    "Total number of optimization recommendations issued",
    labelnames=["deployment", "resource_type", "action"],
)
