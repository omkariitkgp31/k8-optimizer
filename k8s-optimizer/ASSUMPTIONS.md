### Unit Definitions

| Resource | Unit       | Notes                                                                 |
|----------|------------|-----------------------------------------------------------------------|
| CPU      | millicores | 1000m = 1 vCPU. All cpu_request / cpu_usage_avg values are in millicores. |
| Memory   | MiB        | 1 MiB = 1048576 bytes. All memory_request / memory_usage_avg values in MiB. |

### Input Assumptions

1. Metrics are averages — cpu_usage_avg and memory_usage_avg are time-averaged,
   NOT p95/p99. To compensate for hidden spikes, apply a larger safety buffer (1.5×)
   when downsizing heavily overprovisioned workloads.

2. Best-effort workloads are skipped — if cpu_request == 0 OR memory_request == 0,
   the workload is Kubernetes best-effort QoS. There is no baseline to measure
   against, so optimization must be skipped gracefully (no error, just omit).

3. Static requests only — this version assumes fixed resource requests.
   HPA and VPA interaction is out of scope.

4. No namespace or node-pressure context — recommendations are made purely from
   workload-level utilization data.

### Safety Design Choices

- Memory is treated more conservatively than CPU.
  CPU throttling is recoverable. OOMKill is fatal.
  Memory uses wider no-change bands before a recommendation is issued.

- Hard floors enforced on all recommendations:
  - Minimum CPU:    50m
  - Minimum Memory: 128 MiB

- Kubernetes-friendly rounding:
  - CPU    → round UP to nearest 50m
  - Memory → round UP to nearest 128 MiB
  (Avoids unreadable values like 273m or 1153 MiB in kubectl output)

- Churn prevention (noise gate):
  If both CPU and memory reductions are each < 15% of the current request,
  do NOT issue a recommendation. Restarting a pod to reclaim 8 MiB costs
  more in disruption than it saves.

---

## Constants Summary (to be reused in all future steps)

MIN_CPU        = 50       # millicores
MIN_MEMORY     = 128      # MiB
CPU_ROUND_STEP = 50       # millicores
MEM_ROUND_STEP = 128      # MiB
NOISE_GATE_PCT = 0.15     # 15% — minimum meaningful change to trigger a recommendation
