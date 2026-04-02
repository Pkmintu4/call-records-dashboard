import json
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.sentiment import Sentiment
from app.models.transcript import Transcript
from app.schemas.dashboard import CallDetail, CallItem, DailyOverallKPITrend, DistributionPoint, KeyValueCount, OverallKPIs, TrendPoint


router = APIRouter()


def _segment_from_kpi(kpi: dict[str, object]) -> str:
    intent_score = int(kpi.get("intent_score", 0) or 0)
    visit_intent = str(kpi.get("visit_intent", "maybe") or "maybe").lower()
    sentiment = str(kpi.get("sentiment", "neutral") or "neutral").lower()

    if intent_score >= 4 and visit_intent == "yes":
        return "high-intent"
    if sentiment == "negative" or (kpi.get("friction_points") and len(kpi.get("friction_points", [])) > 0):
        return "skeptical"
    if intent_score <= 2 and visit_intent in {"no", "maybe"}:
        return "cold"
    return "exploring"


def _build_detailed_call_insight(summary: str, kpi: dict[str, object], label: str, score: float) -> str:
    intent_score = int(kpi.get("intent_score", 0) or 0)
    visit_intent = str(kpi.get("visit_intent", "maybe") or "maybe").lower()
    admission_probability = int(float(kpi.get("admission_probability", 0) or 0))
    lead_source = str(kpi.get("lead_source", "unknown") or "unknown")

    concerns = [str(item).strip() for item in (kpi.get("parent_concerns") or []) if str(item).strip()]
    key_questions = [str(item).strip() for item in (kpi.get("key_questions_asked") or []) if str(item).strip()]
    friction_points = [str(item).strip() for item in (kpi.get("friction_points") or []) if str(item).strip()]
    competitors = [str(item).strip() for item in (kpi.get("competitor_schools_mentioned") or []) if str(item).strip()]

    concerns_text = ", ".join(concerns[:4]) if concerns else "no major concern was explicitly stated"
    questions_text = "; ".join(key_questions[:3]) if key_questions else "few explicit qualifying questions were asked"
    friction_text = "; ".join(friction_points[:3]) if friction_points else "no strong friction point was clearly recorded"
    competitor_text = ", ".join(competitors[:3]) if competitors else "no competitor school was directly mentioned"

    summary_text = summary.strip() or "Detailed summary unavailable"

    return (
        f"{summary_text} "
        f"Overall parent sentiment is {label} (score {score:.2f}) with intent score {intent_score}/5 and visit intent '{visit_intent}'. "
        f"Predicted admission probability is {admission_probability}%, indicating the current conversion readiness for this lead. "
        f"Lead source appears to be '{lead_source}', while key concerns include {concerns_text}. "
        f"The most relevant questions asked were: {questions_text}. "
        f"Observed friction points: {friction_text}. "
        f"Competitor context: {competitor_text}."
    )


def _boost_staff_metric(value: float, extra_boost: float = 0.0) -> float:
    """Apply aggressive uplift (profile 3) while preserving the 1-5 scale."""
    if value <= 0:
        return 0.0

    boosted = value + 0.55 + extra_boost + max(0.0, value - 2.5) * 0.18
    return round(max(1.0, min(5.0, boosted)), 2)


@router.get("/trend", response_model=list[TrendPoint])
def get_trend(db: Session = Depends(get_db)) -> list[TrendPoint]:
    rows = db.execute(
        select(Transcript.created_at, Sentiment.score)
        .join(Sentiment, Sentiment.transcript_id == Transcript.id)
        .order_by(Transcript.created_at.asc())
    ).all()

    bucket: dict[str, list[float]] = {}
    for created_at, score in rows:
        day = created_at.date().isoformat()
        bucket.setdefault(day, []).append(float(score))

    return [
        TrendPoint(day=day, avg_score=sum(scores) / len(scores))
        for day, scores in sorted(bucket.items(), key=lambda item: item[0])
    ]


@router.get("/distribution", response_model=list[DistributionPoint])
def get_distribution(db: Session = Depends(get_db)) -> list[DistributionPoint]:
    rows = db.execute(
        select(Sentiment.label, func.count(Sentiment.id).label("count")).group_by(Sentiment.label).order_by(Sentiment.label)
    ).all()
    return [DistributionPoint(label=row.label, count=int(row.count)) for row in rows]


@router.get("/calls", response_model=list[CallItem])
def get_calls(limit: int = 10, db: Session = Depends(get_db)) -> list[CallItem]:
    rows = db.execute(
        select(Transcript, Sentiment)
        .join(Sentiment, Sentiment.transcript_id == Transcript.id)
        .order_by(Transcript.created_at.desc())
    ).all()

    normalized_limit = max(1, min(50, int(limit)))
    enriched_rows: list[tuple[int, Transcript, Sentiment, dict[str, object], str]] = []

    for transcript, sentiment in rows:
        try:
            kpis = json.loads(sentiment.kpi_json or "{}")
        except json.JSONDecodeError:
            kpis = {}

        if not isinstance(kpis, dict):
            kpis = {}

        admission_probability = int(float(kpis.get("admission_probability", 0) or 0))
        summary = sentiment.summary or sentiment.explanation
        detailed_insight = _build_detailed_call_insight(summary, kpis, sentiment.label, float(sentiment.score))
        enriched_rows.append((admission_probability, transcript, sentiment, kpis, detailed_insight))

    # Show top-N calls by conversion likelihood, then most recent for ties.
    enriched_rows.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)

    result: list[CallItem] = []
    for _, transcript, sentiment, kpis, detailed_insight in enriched_rows[:normalized_limit]:
        result.append(
            CallItem(
                transcript_id=transcript.id,
                file_name=transcript.file_name,
                created_at=transcript.created_at,
                score=sentiment.score,
                label=sentiment.label,
                summary=sentiment.summary or sentiment.explanation,
                detailed_insight=detailed_insight,
                admission_probability=int(float(kpis.get("admission_probability", 0) or 0)),
                intent_score=max(0, min(5, int(float(kpis.get("intent_score", 0) or 0)))),
                visit_intent=str(kpis.get("visit_intent", "maybe") or "maybe").lower(),
            )
        )

    return result


@router.get("/calls/{transcript_id}", response_model=CallDetail)
def get_call_detail(transcript_id: int, db: Session = Depends(get_db)) -> CallDetail:
    row = db.execute(
        select(Transcript, Sentiment)
        .join(Sentiment, Sentiment.transcript_id == Transcript.id)
        .where(Transcript.id == transcript_id)
    ).first()

    if not row:
        raise HTTPException(status_code=404, detail="Call not found")

    transcript, sentiment = row
    keywords = [token.strip() for token in sentiment.keywords.split(",") if token.strip()]
    try:
        kpis = json.loads(sentiment.kpi_json or "{}")
    except json.JSONDecodeError:
        kpis = {}

    if not isinstance(kpis, dict):
        kpis = {}

    return CallDetail(
        transcript_id=transcript.id,
        file_name=transcript.file_name,
        modified_time=transcript.modified_time,
        score=sentiment.score,
        label=sentiment.label,
        summary=sentiment.summary or sentiment.explanation,
        kpis=kpis,
        explanation=sentiment.explanation,
        keywords=keywords,
        content=transcript.content,
    )


@router.get("/overall-kpis", response_model=OverallKPIs)
def get_overall_kpis(db: Session = Depends(get_db)) -> OverallKPIs:
    rows = db.execute(select(Sentiment.kpi_json)).all()

    total_calls = 0
    segment_counter: Counter[str] = Counter()
    competitor_counter: Counter[str] = Counter()
    conversion_counter: Counter[str] = Counter()

    admission_probs: list[float] = []
    persuasion_scores: list[float] = []
    clarity_scores: list[float] = []
    politeness_scores: list[float] = []

    for (kpi_json,) in rows:
        try:
            kpi = json.loads(kpi_json or "{}")
        except json.JSONDecodeError:
            continue

        if not isinstance(kpi, dict):
            continue

        total_calls += 1

        segment = _segment_from_kpi(kpi)
        segment_counter[segment] += 1

        competitors = kpi.get("competitor_schools_mentioned") or []
        if isinstance(competitors, list):
            for competitor in competitors:
                competitor_name = str(competitor).strip()
                if competitor_name:
                    competitor_counter[competitor_name] += 1

        admission_probability = float(kpi.get("admission_probability", 0) or 0)
        admission_probs.append(max(0.0, min(100.0, admission_probability)))

        if admission_probability >= 70:
            conversion_counter["high"] += 1
        elif admission_probability >= 40:
            conversion_counter["medium"] += 1
        else:
            conversion_counter["low"] += 1

        persuasion_scores.append(float(kpi.get("persuasion_score", 0) or 0))
        clarity_scores.append(float(kpi.get("response_clarity", 0) or 0))
        politeness_scores.append(float(kpi.get("politeness_score", 0) or 0))

    def avg(values: list[float]) -> float:
        clean = [value for value in values if value > 0]
        return round(sum(clean) / len(clean), 2) if clean else 0.0

    boosted_persuasion = _boost_staff_metric(avg(persuasion_scores), extra_boost=0.05)
    boosted_clarity = _boost_staff_metric(avg(clarity_scores), extra_boost=0.08)
    boosted_politeness = _boost_staff_metric(avg(politeness_scores), extra_boost=0.42)
    staff_score = (
        round(
            min(
                5.0,
                max(
                    1.0,
                    (boosted_persuasion * 0.30) + (boosted_clarity * 0.25) + (boosted_politeness * 0.45) + 0.20,
                ),
            ),
            2,
        )
        if total_calls
        else 0.0
    )

    return OverallKPIs(
        total_calls=total_calls,
        parent_psychology_segments=[
            KeyValueCount(key=key, count=count)
            for key, count in segment_counter.most_common()
        ],
        competitor_intelligence=[
            KeyValueCount(key=key, count=count)
            for key, count in competitor_counter.most_common(10)
        ],
        avg_admission_probability=round(sum(admission_probs) / len(admission_probs), 2) if admission_probs else 0.0,
        conversion_prediction={
            "high": conversion_counter.get("high", 0),
            "medium": conversion_counter.get("medium", 0),
            "low": conversion_counter.get("low", 0),
        },
        staff_performance={
            "persuasion": boosted_persuasion,
            "response_clarity": boosted_clarity,
            "politeness": boosted_politeness,
            "staff_score": staff_score,
        },
    )


@router.get("/overall-kpis-trend", response_model=list[DailyOverallKPITrend])
def get_overall_kpis_trend(db: Session = Depends(get_db)) -> list[DailyOverallKPITrend]:
    rows = db.execute(
        select(Transcript.created_at, Sentiment.kpi_json)
        .join(Sentiment, Sentiment.transcript_id == Transcript.id)
        .order_by(Transcript.created_at.asc())
    ).all()

    bucket: dict[str, dict[str, list[float]]] = {}

    for created_at, kpi_json in rows:
        day = created_at.date().isoformat()
        if day not in bucket:
            bucket[day] = {
                "admission": [],
                "persuasion": [],
                "clarity": [],
                "politeness": [],
            }

        try:
            kpi = json.loads(kpi_json or "{}")
        except json.JSONDecodeError:
            continue

        if not isinstance(kpi, dict):
            continue

        bucket[day]["admission"].append(float(kpi.get("admission_probability", 0) or 0))
        bucket[day]["persuasion"].append(float(kpi.get("persuasion_score", 0) or 0))
        bucket[day]["clarity"].append(float(kpi.get("response_clarity", 0) or 0))
        bucket[day]["politeness"].append(float(kpi.get("politeness_score", 0) or 0))

    def avg(values: list[float]) -> float:
        clean = [value for value in values if value > 0]
        return round(sum(clean) / len(clean), 2) if clean else 0.0

    return [
        DailyOverallKPITrend(
            day=day,
            avg_admission_probability=avg(values["admission"]),
            avg_persuasion=_boost_staff_metric(avg(values["persuasion"]), extra_boost=0.05),
            avg_clarity=_boost_staff_metric(avg(values["clarity"]), extra_boost=0.08),
            avg_politeness=_boost_staff_metric(avg(values["politeness"]), extra_boost=0.42),
        )
        for day, values in sorted(bucket.items(), key=lambda item: item[0])
    ]


@router.get("/segment-sentiment-breakdown")
def get_segment_sentiment_breakdown(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    """Return sentiment distribution (positive/neutral/negative) for each parent psychology segment."""
    rows = db.execute(
        select(Sentiment.kpi_json, Sentiment.label)
        .join(Transcript, Sentiment.transcript_id == Transcript.id)
        .order_by(Transcript.created_at.desc())
    ).all()

    # Group by segment
    segment_sentiments: dict[str, Counter[str]] = {}

    for kpi_json, label in rows:
        try:
            kpi = json.loads(kpi_json or "{}")
        except json.JSONDecodeError:
            continue

        if not isinstance(kpi, dict):
            continue

        segment = _segment_from_kpi(kpi)
        if segment not in segment_sentiments:
            segment_sentiments[segment] = Counter()

        # Count by sentiment label
        segment_sentiments[segment][label] += 1

    # Build result with consistent ordering
    segment_order = ["high-intent", "exploring", "skeptical", "cold"]
    result = []

    for segment in segment_order:
        if segment not in segment_sentiments:
            continue

        counts = segment_sentiments[segment]
        total = sum(counts.values())

        result.append({
            "segment": segment.replace("-", " ").title(),
            "positive": counts.get("positive", 0),
            "neutral": counts.get("neutral", 0),
            "negative": counts.get("negative", 0),
            "total": total,
        })

    return result
