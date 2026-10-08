from pydantic import BaseModel


class RetentionBucket(BaseModel):
    period: str
    active_donors: int
    retained: int


class DonorRetentionOut(BaseModel):
    buckets: list[RetentionBucket]
    retention_rate: float


class DistributionEfficiencyOut(BaseModel):
    organization_id: int
    mean_days_paid_to_distributed: float | None
    distributed_count: int


class ProgramEffectivenessRow(BaseModel):
    program_id: int
    name: str
    raised_amount: int
    distributed_amount: int
    distribution_ratio: float


class AnalyticsSummaryOut(BaseModel):
    retention: DonorRetentionOut
    distribution_efficiency: DistributionEfficiencyOut
    program_effectiveness: list[ProgramEffectivenessRow]