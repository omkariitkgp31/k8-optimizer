from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app.main import app
from app.metrics import recommendations_total

def _get_metric_value(metric, **labels):
    try:
        return metric.labels(**labels)._value.get()
    except KeyError:
        return 0.0

client = TestClient(app)

def test_api_service_significantly_overprovisioned():
    response = client.post("/optimize", json={
        "workloads": [
            {
                "deployment": "api-service",
                "cpu_request": 1000,
                "cpu_usage_avg": 180,
                "memory_request": 2048,
                "memory_usage_avg": 700
            }
        ]
    })
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["deployment"] == "api-service"
    assert data[0]["recommended_cpu"] == 300
    assert data[0]["recommended_memory"] == 1152

def test_worker_service_properly_sized():
    response = client.post("/optimize", json={
        "workloads": [
            {
                "deployment": "worker-service",
                "cpu_request": 500,
                "cpu_usage_avg": 450,
                "memory_request": 1024,
                "memory_usage_avg": 900
            }
        ]
    })
    assert response.status_code == 200
    assert len(response.json()) == 0

def test_best_effort_skipped():
    response = client.post("/optimize", json={
        "workloads": [
            {
                "deployment": "best-effort-pod",
                "cpu_request": 0,
                "cpu_usage_avg": 100,
                "memory_request": 512,
                "memory_usage_avg": 200
            }
        ]
    })
    assert response.status_code == 200
    assert len(response.json()) == 0

def test_underprovisioned_increase():
    response = client.post("/optimize", json={
        "workloads": [
            {
                "deployment": "under-service",
                "cpu_request": 100,
                "cpu_usage_avg": 95,
                "memory_request": 256,
                "memory_usage_avg": 240
            }
        ]
    })
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["recommended_cpu"] > 100

def test_noise_gate_ignores_tiny_changes():
    response = client.post("/optimize", json={
        "workloads": [
            {
                "deployment": "noise-service",
                "cpu_request": 900,
                "cpu_usage_avg": 580,
                "memory_request": 1280,
                "memory_usage_avg": 880
            }
        ]
    })
    assert response.status_code == 200
    assert len(response.json()) == 0

def test_invalid_negative_input():
    response = client.post("/optimize", json={
        "workloads": [
            {
                "deployment": "api-service",
                "cpu_request": -100,
                "cpu_usage_avg": 180,
                "memory_request": 2048,
                "memory_usage_avg": 700
            }
        ]
    })
    assert response.status_code == 422

def test_empty_deployment_name():
    response = client.post("/optimize", json={
        "workloads": [
            {
                "deployment": "",
                "cpu_request": 1000,
                "cpu_usage_avg": 180,
                "memory_request": 2048,
                "memory_usage_avg": 700
            }
        ]
    })
    assert response.status_code == 422

def test_metrics_counter_increments():
    # 1. Read the BEFORE state for the specific labels we expect
    labels_cpu = {"deployment": "metrics-test-app", "resource_type": "cpu", "action": "decrease"}
    labels_mem = {"deployment": "metrics-test-app", "resource_type": "memory", "action": "decrease"}
    
    before_cpu = _get_metric_value(recommendations_total, **labels_cpu)
    before_mem = _get_metric_value(recommendations_total, **labels_mem)
    
    # 2. Trigger the action (API call that causes a decrease)
    response = client.post("/optimize", json={
        "workloads": [
            {
                "deployment": "metrics-test-app",
                "cpu_request": 2000,
                "cpu_usage_avg": 200,
                "memory_request": 4096,
                "memory_usage_avg": 1000
            }
        ]
    })
    
    assert response.status_code == 200
    
    # 3. Read the AFTER state
    after_cpu = _get_metric_value(recommendations_total, **labels_cpu)
    after_mem = _get_metric_value(recommendations_total, **labels_mem)
    
    # 4. Assert the DELTA is exactly 1.0
    assert after_cpu - before_cpu == 1.0, "CPU decrease counter did not increment by 1"
    assert after_mem - before_mem == 1.0, "Memory decrease counter did not increment by 1"
