from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def ensure_sentiment_summary_column(engine: Engine) -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    with engine.begin() as connection:
        if "sentiments" in table_names:
            sentiment_columns = {column["name"] for column in inspector.get_columns("sentiments")}
            if "summary" not in sentiment_columns:
                connection.execute(text("ALTER TABLE sentiments ADD COLUMN summary TEXT DEFAULT ''"))

            if "kpi_json" not in sentiment_columns:
                connection.execute(text("ALTER TABLE sentiments ADD COLUMN kpi_json TEXT DEFAULT '{}'"))

            if "intent_category" not in sentiment_columns:
                connection.execute(text("ALTER TABLE sentiments ADD COLUMN intent_category VARCHAR(32) DEFAULT 'Inquiry'"))

            connection.execute(text("UPDATE sentiments SET summary = explanation WHERE summary IS NULL OR summary = ''"))
            connection.execute(text("UPDATE sentiments SET kpi_json = '{}' WHERE kpi_json IS NULL OR kpi_json = ''"))
            connection.execute(text("UPDATE sentiments SET intent_category = 'Inquiry' WHERE intent_category IS NULL OR intent_category = ''"))

        if "transcripts" in table_names:
            transcript_columns = {column["name"] for column in inspector.get_columns("transcripts")}
            if "source_type" not in transcript_columns:
                connection.execute(text("ALTER TABLE transcripts ADD COLUMN source_type VARCHAR(16) DEFAULT 'text'"))

            if "transcription_language" not in transcript_columns:
                connection.execute(text("ALTER TABLE transcripts ADD COLUMN transcription_language VARCHAR(16)"))

            if "transcription_status" not in transcript_columns:
                connection.execute(text("ALTER TABLE transcripts ADD COLUMN transcription_status VARCHAR(32) DEFAULT 'completed'"))

            if "duration_seconds" not in transcript_columns:
                connection.execute(text("ALTER TABLE transcripts ADD COLUMN duration_seconds FLOAT"))

            connection.execute(text("UPDATE transcripts SET source_type = 'text' WHERE source_type IS NULL OR source_type = ''"))
            connection.execute(text("UPDATE transcripts SET transcription_status = 'completed' WHERE transcription_status IS NULL OR transcription_status = ''"))
