from typing import List
from pydantic import BaseModel, Field, field_validator

class WorkloadInput(BaseModel):
    deployment: str = Field(..., min_length=1, description="Deployment name")
    cpu_request: float = Field(..., ge=0, description="CPU request in millicores")
    cpu_usage_avg: float = Field(..., ge=0, description="Average CPU usage in millicores")
    memory_request: float = Field(..., ge=0, description="Memory request in MiB")
    memory_usage_avg: float = Field(..., ge=0, description="Average memory usage in MiB")

class OptimizationRecommendation(BaseModel):
    deployment: str
    recommended_cpu: int
    recommended_memory: int
    reason: str

class OptimizationRequest(BaseModel):
    workloads: List[WorkloadInput]

    @field_validator("workloads", mode="before")
    @classmethod
    def workloads_must_not_be_empty(cls, v):
        if len(v) == 0:
            raise ValueError("workloads array cannot be empty")
        return v
