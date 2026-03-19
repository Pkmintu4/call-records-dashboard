from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def ensure_sentiment_summary_column(engine: Engine) -> None:
    inspector = inspect(engine)
    if "sentiments" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("sentiments")}
    with engine.begin() as connection:
        if "summary" not in columns:
            connection.execute(text("ALTER TABLE sentiments ADD COLUMN summary TEXT DEFAULT ''"))

        if "kpi_json" not in columns:
            connection.execute(text("ALTER TABLE sentiments ADD COLUMN kpi_json TEXT DEFAULT '{}'"))

        connection.execute(text("UPDATE sentiments SET summary = explanation WHERE summary IS NULL OR summary = ''"))
        connection.execute(text("UPDATE sentiments SET kpi_json = '{}' WHERE kpi_json IS NULL OR kpi_json = ''"))
