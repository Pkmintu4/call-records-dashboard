from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Sentiment(Base):
    __tablename__ = "sentiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    transcript_id: Mapped[int] = mapped_column(ForeignKey("transcripts.id", ondelete="CASCADE"), unique=True, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    label: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    intent_category: Mapped[str] = mapped_column(String(32), nullable=False, default="Inquiry", index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    kpi_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    keywords: Mapped[str] = mapped_column(Text, nullable=False)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    transcript = relationship("Transcript", back_populates="sentiment")
