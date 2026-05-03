from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class FollowupResolution(Base):
    __tablename__ = "followup_resolutions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    transcript_id: Mapped[int] = mapped_column(ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False, index=True)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    transcript = relationship("Transcript", backref="followup_resolutions")
