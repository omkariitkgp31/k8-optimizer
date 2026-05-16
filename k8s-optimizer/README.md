# Kubernetes Resource Optimizer

A FastAPI-based service that analyzes Kubernetes workload resource usage and recommends optimal CPU and memory requests/limits based on configurable safety thresholds.

## Features
- **Smart Sizing**: Recommends resource adjustments based on actual usage and safety buffers.
- **Noise Gate**: Ignores trivial changes (<15%) to prevent unnecessary pod restarts.
- **Safety Floors**: Ensures minimum resources (50m CPU, 128Mi Memory) are always maintained.
- **Prometheus Metrics**: Exposes `recommendations_issued_total` to track optimization actions.
- **K8s Configurable**: Thresholds and buffers can be tuned via Kubernetes ConfigMap without rebuilding the image.

## Setup & Run Instructions

### Prerequisites
- Python 3.11+
- Docker
- Kubernetes Cluster (Minikube, Docker Desktop, etc.) - Optional for local run

### Local Development
1. Clone the repository
2. Install dependencies
   ```bash
   pip install -r requirements.txt
   ```
3. Run the FastAPI server
   ```bash
   uvicorn app.main:app --reload
   ```

### Docker
1. Build the image
   ```bash
   docker build -t k8s-optimizer:latest .
   ```
2. Run the container
   ```bash
   docker run -d -p 8000:8000 --name k8s-optimizer k8s-optimizer:latest
   ```

### Kubernetes
1. Apply the manifests
   ```bash
   kubectl apply -f k8s/
   ```

## Assumptions Made
A comprehensive list of mathematical thresholds, floor constants, and safety buffer calculations is documented in the [`ASSUMPTIONS.md`](ASSUMPTIONS.md) file.
- All incoming CPU requests/usages are measured in **millicores** (1000m = 1 vCPU).
- All incoming Memory requests/usages are measured in **MiB**.
- A noise-gate of 15% is required to prevent Kubernetes API churn and unnecessary pod restarts.

## API Endpoints
- `POST /optimize`: Accepts a list of workloads and returns optimization recommendations.
- `GET /health`: Liveness probe for Kubernetes.
- `GET /metrics`: Prometheus-compatible telemetry endpoint.
- `GET /docs`: Swagger UI for interactive API exploration.

## Sample Input / Output

**Request:**
```bash
curl -X POST http://localhost:8000/optimize \
  -H "Content-Type: application/json" \
  -d '{
    "workloads": [
      {
        "deployment": "api-service",
        "cpu_request": 1000,
        "cpu_usage_avg": 180,
        "memory_request": 2048,
        "memory_usage_avg": 700
      }
    ]
  }'
```

**Response:**
```json
[
  {
    "deployment": "api-service",
    "recommended_cpu": 300,
    "recommended_memory": 1152,
    "reason": "CPU overprovisioned: usage is 18% of request; Memory overprovisioned: usage is 34% of request"
  }
]
```

## Additional Improvements & Ideas (Discussion)

To transition this proof-of-concept into a production-grade, large-scale Kubernetes optimizer, several architectural shifts are required:

### 1. Kubernetes APIs Integration
Instead of relying on manual JSON payloads, the system should operate as a **Custom Kubernetes Controller** or **Mutating Admission Webhook**. 
- It would watch the `metrics.k8s.io` API to fetch real-time utilization.
- It could create a CRD (Custom Resource Definition) like `OptimizationRecommendation` directly within the cluster so cluster admins can track recommendations natively using `kubectl`.
- Using a Mutating Webhook, it could auto-inject recommended resource requests/limits during pod creation (similar to how the Vertical Pod Autoscaler operates).

### 2. Metrics Collection
Relying on "average usage" is risky in production. 
- We must integrate directly with **Prometheus, Thanos, or Datadog** to run continuous PromQL queries targeting historical `p95` and `p99` percentiles over a 7-to-14 day window. 
- This protects against OOMKills during sudden traffic spikes, which averages fail to reveal. 
- The system should distinguish between CPU throttling metrics (e.g., `container_cpu_cfs_throttled_seconds_total`) and pure utilization to make safer CPU limit recommendations.

### 3. Scalability Considerations
In a cluster with 10,000+ pods, running optimization synchronously on a single API thread is unfeasible.
- We would implement a worker-queue architecture using **Kafka, RabbitMQ, or Celery**. A lightweight agent gathers pod usage, pushes events to a message broker, and horizontally-scaled workers process the rules engine asynchronously.
- Caching API Server responses (using SharedInformer caches natively in the Python/Go client) is critical to prevent the optimizer from overwhelming the Kubernetes API control plane.

### 4. Real-time Recommendations
Constantly updating pod resource requests requires restarting the pods, causing extreme churn and potential outages.
- Real-time "immediate" recommendations must be gated aggressively (e.g., only trigger an immediate emergency restart if memory usage is > 95% to prevent an imminent OOM crash).
- Standard optimizations should be batched and applied during scheduled maintenance windows, CI/CD deployment rollouts (e.g., GitOps updates via ArgoCD/Flux), or non-peak hours.

### 5. Multi-cluster Environments
For multi-cluster setups across different regions or cloud providers (AWS EKS, GCP GKE):
- A centralized control plane architecture is required.
- Lightweight agents deployed on edge/spoke clusters would forward sanitized metric aggregates to a central processing hub via gRPC.
- Recommendations must account for hardware differences (e.g., ARM vs x86 nodes) because CPU millicores behave differently across architectures.

### 6. Reliability Challenges
- **Interference with HPA/VPA:** Our optimizer could fatally conflict with the Horizontal Pod Autoscaler (HPA), which scales based on utilization percentages. If we blindly lower a pod's requested CPU, we artificially inflate its utilization percentage, which could trigger a massive, unwarranted HPA scale-out. The optimizer must be deeply "HPA-aware".
- **Fail-open design:** If the optimizer goes down, standard cluster scheduling and scaling must remain unaffected. It must never act as a single point of failure in the critical path of application deployments.
