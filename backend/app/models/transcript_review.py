from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TranscriptReview(Base):
    __tablename__ = "transcript_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    transcript_id: Mapped[int] = mapped_column(ForeignKey("transcripts.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    review_status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending", index=True)
    reviewer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    corrected_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    correction_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    transcript = relationship("Transcript", back_populates="review")
