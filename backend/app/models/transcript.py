from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    drive_file_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    modified_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False, default="text")
    transcription_language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    transcription_status: Mapped[str] = mapped_column(String(32), nullable=False, default="completed")
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    sentiment = relationship("Sentiment", back_populates="transcript", uselist=False, cascade="all, delete-orphan")
