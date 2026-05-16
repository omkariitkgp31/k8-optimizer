import logging
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .models import OptimizationRecommendation, OptimizationRequest
from .optimizer import optimize_all
from .metrics import instrumentator, recommendations_total

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Lifespan: runs at startup (before yield) and shutdown (after yield)
# ------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: register /metrics route on the live app instance
    instrumentator.expose(app)
    yield
    # Shutdown: nothing to clean up

# ------------------------------------------------------------------
# FastAPI Application
# ------------------------------------------------------------------
app = FastAPI(
    title="K8s Resource Optimizer",
    description="Analyzes Kubernetes workload metrics and recommends safer CPU/memory values.",
    version="1.0.0",
    lifespan=lifespan,
)

# Wire HTTP instrumentation middleware (latency, count, in-progress)
instrumentator.instrument(app).expose(app)

# ------------------------------------------------------------------
# Error Handlers
# ------------------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"] if loc != "body")
        errors.append({"field": field, "message": error["msg"], "type": error["type"]})

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Invalid input",
            "message": "Request validation failed. See 'details' for specific fields.",
            "details": errors,
        },
    )

@app.exception_handler(Exception)
async def handle_general_error(request: Request, exc: Exception):
    logger.exception("Unhandled exception in optimize endpoint")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred. Please try again later.",
        },
    )

# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------
@app.post("/optimize", response_model=List[OptimizationRecommendation])
async def optimize(request: OptimizationRequest):
    """
    Accept a list of workload metrics and return optimization recommendations.
    """
    results = optimize_all(request.workloads)
    return results

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/metrics")
async def metrics():
    """
    Prometheus metrics endpoint. Exposes HTTP request counters,
    latency histograms, in-progress gauges, and custom business metrics.
    Also auto-exposed by the Instrumentator — explicit route guarantees
    Swagger UI discoverability.
    """
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    from starlette.responses import Response
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
