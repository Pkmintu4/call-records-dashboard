from datetime import datetime

from pydantic import BaseModel


class TrendPoint(BaseModel):
    day: str
    avg_score: float


class DistributionPoint(BaseModel):
    label: str
    count: int


class CallItem(BaseModel):
    transcript_id: int
    file_name: str
    created_at: datetime
    score: float
    label: str
    summary: str
    detailed_insight: str
    admission_probability: int
    intent_score: int
    visit_intent: str


class CallDetail(BaseModel):
    transcript_id: int
    file_name: str
    modified_time: datetime | None
    score: float
    label: str
    summary: str
    kpis: dict[str, object]
    explanation: str
    keywords: list[str]
    content: str


class KeyValueCount(BaseModel):
    key: str
    count: int


class OverallKPIs(BaseModel):
    total_calls: int
    parent_psychology_segments: list[KeyValueCount]
    competitor_intelligence: list[KeyValueCount]
    avg_admission_probability: float
    conversion_prediction: dict[str, int]
    staff_performance: dict[str, float]


class DailyOverallKPITrend(BaseModel):
    day: str
    avg_admission_probability: float
    avg_persuasion: float
    avg_clarity: float
    avg_politeness: float
