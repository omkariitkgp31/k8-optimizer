import os
import math
from typing import List, Optional
from .models import WorkloadInput, OptimizationRecommendation
from .metrics import recommendations_total


class OptimizationConfig:
    # Utilization thresholds
    CPU_HIGH_OVER_THRESH = float(os.getenv("CPU_HIGH_OVER_THRESH", "0.35"))
    CPU_MOD_OVER_THRESH  = float(os.getenv("CPU_MOD_OVER_THRESH", "0.65"))
    CPU_UNDER_THRESH     = float(os.getenv("CPU_UNDER_THRESH", "0.85"))

    MEM_HIGH_OVER_THRESH = float(os.getenv("MEM_HIGH_OVER_THRESH", "0.40"))
    MEM_MOD_OVER_THRESH  = float(os.getenv("MEM_MOD_OVER_THRESH", "0.70"))
    MEM_UNDER_THRESH     = float(os.getenv("MEM_UNDER_THRESH", "0.85"))

    # Safety buffer multipliers
    CPU_HIGH_BUFFER  = float(os.getenv("CPU_HIGH_BUFFER", "1.5"))
    CPU_MOD_BUFFER   = float(os.getenv("CPU_MOD_BUFFER", "1.3"))
    CPU_UNDER_BUFFER = float(os.getenv("CPU_UNDER_BUFFER", "1.2"))

    MEM_HIGH_BUFFER  = float(os.getenv("MEM_HIGH_BUFFER", "1.5"))
    MEM_MOD_BUFFER   = float(os.getenv("MEM_MOD_BUFFER", "1.3"))
    MEM_UNDER_BUFFER = float(os.getenv("MEM_UNDER_BUFFER", "1.25"))

    # Floors and rounding steps
    MIN_CPU   = int(os.getenv("MIN_CPU", "50"))
    MIN_MEM   = int(os.getenv("MIN_MEM", "128"))
    CPU_ROUND = int(os.getenv("CPU_ROUND", "50"))
    MEM_ROUND = int(os.getenv("MEM_ROUND", "128"))

    # Churn prevention
    NOISE_GATE_PCT = float(os.getenv("NOISE_GATE_PCT", "0.15"))


def _round_up(val: float, step: int, floor: int) -> int:
    """Round val up to nearest step, enforcing a minimum floor."""
    if val <= 0:
        return floor
    rounded = math.ceil(val / step) * step
    return max(floor, int(rounded))


def _classify_action(original: float, recommended: float) -> str:
    """Classify the direction of a resource change for Prometheus labels."""
    if recommended > original:
        return "increase"
    elif recommended < original:
        return "decrease"
    return "no_change"


def optimize_single(
    workload: WorkloadInput, cfg: OptimizationConfig = None
) -> Optional[OptimizationRecommendation]:
    cfg = cfg or OptimizationConfig()

    cpu_req = workload.cpu_request
    cpu_use = workload.cpu_usage_avg
    mem_req = workload.memory_request
    mem_use = workload.memory_usage_avg

    # Rule 1 — Skip best-effort workloads (request = 0 means unbounded)
    if cpu_req == 0 or mem_req == 0:
        return None

    # Rule 2 — Utilization ratios
    cpu_util = cpu_use / cpu_req
    mem_util = mem_use / mem_req

    rec_cpu = cpu_req
    rec_mem = mem_req
    reasons = []

    # Rule 3 + 4 + 5 — CPU classification, buffer, floor, rounding
    if cpu_util < cfg.CPU_HIGH_OVER_THRESH:
        rec_cpu = _round_up(cpu_use * cfg.CPU_HIGH_BUFFER, cfg.CPU_ROUND, cfg.MIN_CPU)
        reasons.append(f"CPU overprovisioned: usage is {cpu_util:.0%} of request")
    elif cpu_util < cfg.CPU_MOD_OVER_THRESH:
        rec_cpu = _round_up(cpu_use * cfg.CPU_MOD_BUFFER, cfg.CPU_ROUND, cfg.MIN_CPU)
        reasons.append(f"CPU moderately overprovisioned: usage is {cpu_util:.0%} of request")
    elif cpu_util > cfg.CPU_UNDER_THRESH:
        rec_cpu = _round_up(cpu_use * cfg.CPU_UNDER_BUFFER, cfg.CPU_ROUND, cfg.MIN_CPU)
        reasons.append(f"CPU underprovisioned: usage is {cpu_util:.0%} of request")

    # Rule 3 + 4 + 5 — Memory classification, buffer, floor, rounding
    if mem_util < cfg.MEM_HIGH_OVER_THRESH:
        rec_mem = _round_up(mem_use * cfg.MEM_HIGH_BUFFER, cfg.MEM_ROUND, cfg.MIN_MEM)
        reasons.append(f"Memory overprovisioned: usage is {mem_util:.0%} of request")
    elif mem_util < cfg.MEM_MOD_OVER_THRESH:
        rec_mem = _round_up(mem_use * cfg.MEM_MOD_BUFFER, cfg.MEM_ROUND, cfg.MIN_MEM)
        reasons.append(f"Memory moderately overprovisioned: usage is {mem_util:.0%} of request")
    elif mem_util > cfg.MEM_UNDER_THRESH:
        rec_mem = _round_up(mem_use * cfg.MEM_UNDER_BUFFER, cfg.MEM_ROUND, cfg.MIN_MEM)
        reasons.append(f"Memory underprovisioned: usage is {mem_util:.0%} of request")

    # Rule 6 — Noise gate: suppress marginal reductions to prevent pod churn
    cpu_diff = abs(rec_cpu - cpu_req) / cpu_req
    mem_diff = abs(rec_mem - mem_req) / mem_req

    if cpu_diff < cfg.NOISE_GATE_PCT and mem_diff < cfg.NOISE_GATE_PCT:
        return None

    # Rule 7 — Output filter: skip if rounding produced no net change
    if rec_cpu == cpu_req and rec_mem == mem_req:
        return None

    # ------------------------------------------------------------------
    # PROMETHEUS: Emit custom business metrics
    # Both original and recommended values are in scope here.
    # This block is only reached for recommendations that will be returned.
    # ------------------------------------------------------------------
    cpu_action = _classify_action(cpu_req, rec_cpu)
    mem_action = _classify_action(mem_req, rec_mem)

    recommendations_total.labels(
        deployment=workload.deployment,
        resource_type="cpu",
        action=cpu_action,
    ).inc()

    recommendations_total.labels(
        deployment=workload.deployment,
        resource_type="memory",
        action=mem_action,
    ).inc()

    reason_str = "; ".join(reasons) if reasons else "Adjusted for optimal resource fit"

    return OptimizationRecommendation(
        deployment=workload.deployment,
        recommended_cpu=rec_cpu,
        recommended_memory=rec_mem,
        reason=reason_str,
    )


def optimize_all(workloads: List[WorkloadInput]) -> List[OptimizationRecommendation]:
    """Run optimize_single for each workload and return non-None results."""
    results: List[OptimizationRecommendation] = []
    for w in workloads:
        rec = optimize_single(w)
        if rec:
            results.append(rec)
    return results
