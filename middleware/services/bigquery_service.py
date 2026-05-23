"""
BigQuery service — handles all database operations.
"""
import logging
from datetime import datetime, timezone
from google.cloud import bigquery
from config import GOOGLE_CLOUD_PROJECT, BIGQUERY_DATASET, BIGQUERY_TABLE

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = bigquery.Client(project=GOOGLE_CLOUD_PROJECT)
    return _client


def _table_id():
    return f"{GOOGLE_CLOUD_PROJECT}.{BIGQUERY_DATASET}.{BIGQUERY_TABLE}"


def ensure_dataset_and_table():
    """Create the dataset and table if they don't exist."""
    client = _get_client()

    # Dataset
    dataset_ref = bigquery.DatasetReference(GOOGLE_CLOUD_PROJECT, BIGQUERY_DATASET)
    try:
        client.get_dataset(dataset_ref)
    except Exception:
        dataset = bigquery.Dataset(dataset_ref)
        dataset.location = "EU"
        client.create_dataset(dataset)
        logger.info(f"Dataset {BIGQUERY_DATASET} created.")

    # Table schema
    schema = [
        bigquery.SchemaField("timestamp",        "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("temperature",       "FLOAT64",   mode="NULLABLE"),
        bigquery.SchemaField("humidity",          "FLOAT64",   mode="NULLABLE"),
        bigquery.SchemaField("tvoc",              "INT64",     mode="NULLABLE"),
        bigquery.SchemaField("eco2",              "INT64",     mode="NULLABLE"),
        bigquery.SchemaField("aq_label",          "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("location",          "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("outdoor_temp",      "FLOAT64",   mode="NULLABLE"),
        bigquery.SchemaField("outdoor_humidity",  "FLOAT64",   mode="NULLABLE"),
        bigquery.SchemaField("outdoor_desc",      "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("outdoor_condition", "STRING",    mode="NULLABLE"),
        bigquery.SchemaField("outdoor_wind",      "FLOAT64",   mode="NULLABLE"),
    ]

    table_ref = bigquery.TableReference(dataset_ref, BIGQUERY_TABLE)
    try:
        client.get_table(table_ref)
    except Exception:
        table = bigquery.Table(table_ref, schema=schema)
        # Partition by day for efficiency
        table.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="timestamp",
        )
        client.create_table(table)
        logger.info(f"Table {BIGQUERY_TABLE} created.")


def insert_reading(reading: dict) -> bool:
    """Insert a sensor reading into BigQuery."""
    client = _get_client()
    now_utc = datetime.now(timezone.utc).isoformat()

    row = {
        "timestamp":        reading.get("timestamp", now_utc),
        "temperature":      reading.get("temperature"),
        "humidity":         reading.get("humidity"),
        "tvoc":             reading.get("tvoc"),
        "eco2":             reading.get("eco2"),
        "aq_label":         reading.get("aq_label"),
        "location":         reading.get("location", "Lausanne,CH"),
        "outdoor_temp":     reading.get("outdoor_temp"),
        "outdoor_humidity": reading.get("outdoor_humidity"),
        "outdoor_desc":     reading.get("outdoor_desc"),
        "outdoor_condition":reading.get("outdoor_condition"),
        "outdoor_wind":     reading.get("outdoor_wind"),
    }

    errors = client.insert_rows_json(_table_id(), [row])
    if errors:
        logger.error(f"BigQuery insert errors: {errors}")
        return False
    return True


def get_latest_reading() -> dict | None:
    """Return the most recent sensor reading."""
    client = _get_client()
    query = f"""
        SELECT *
        FROM `{_table_id()}`
        WHERE temperature IS NOT NULL OR tvoc IS NOT NULL
        ORDER BY timestamp DESC
        LIMIT 1
    """
    try:
        rows = list(client.query(query).result())
        if rows:
            return dict(rows[0])
        return None
    except Exception as e:
        logger.error(f"BigQuery query error: {e}")
        return None


def get_history(hours: int = 24) -> list:
    """Return sensor readings for the last N hours."""
    client = _get_client()
    query = f"""
        SELECT
            timestamp,
            temperature,
            humidity,
            tvoc,
            eco2,
            aq_label,
            outdoor_temp,
            outdoor_desc
        FROM `{_table_id()}`
        WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours} HOUR)
          AND (temperature IS NOT NULL OR tvoc IS NOT NULL)
        ORDER BY timestamp ASC
    """
    try:
        rows = list(client.query(query).result())
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"BigQuery history query error: {e}")
        return []
