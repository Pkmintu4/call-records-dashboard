import threading

# Prevent concurrent ingest runs (manual + auto) from writing simultaneously.
INGEST_LOCK = threading.Lock()
