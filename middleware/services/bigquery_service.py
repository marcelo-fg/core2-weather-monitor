"""
BigQuery service — handles all database operations.
"""
import logging
import time
from datetime import datetime, timezone
from google.cloud import bigquery
from config import GOOGLE_CLOUD_PROJECT, BIGQUERY_DATASET, BIGQUERY_TABLE

logger = logging.getLogger(__name__)

_client = None

# Small TTL cache of the most recent reading. The M5 uploads roughly every
# 5 minutes, so re-querying BigQuery on every voice request is wasteful.
_LATEST_CACHE = {"ts": 0.0, "value": None}
_LATEST_TTL = 30

# TTL cache of the aggregated history summary used by the voice assistant.
# Historical aggregates change slowly, so a 5-minute window is plenty.
_HISTORY_SUMMARY_CACHE = {"ts": 0.0, "value": None}
_HISTORY_SUMMARY_TTL = 300


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
    """Return the most recent sensor reading (cached for 30 seconds)."""
    if (time.time() - _LATEST_CACHE["ts"]) < _LATEST_TTL:
        return _LATEST_CACHE["value"]

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
        result = dict(rows[0]) if rows else None
        _LATEST_CACHE["ts"] = time.time()
        _LATEST_CACHE["value"] = result
        return result
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


# Metrics reported in the history summary. ``decimals`` controls rounding for
# the average; min/max are kept as integers for the inherently-integer ones.
_HISTORY_METRICS = (
    ("temperature", 1),
    ("humidity",    0),
    ("tvoc",        0),
    ("eco2",        0),
)


def _summarize_rows(rows: list, include_peak_hours: bool = False) -> dict:
    """Compute min/max/avg for each indoor metric over the given rows.

    When ``include_peak_hours`` is True, also returns the hour-of-day strings
    at which the indoor temperature reached its min and max in the window.
    """
    if not rows:
        return {}
    out = {"readings": len(rows)}
    for key, decimals in _HISTORY_METRICS:
        values = [r.get(key) for r in rows if r.get(key) is not None]
        if not values:
            continue
        mn, mx, avg = min(values), max(values), sum(values) / len(values)
        if decimals == 0:
            out[key + "_min"] = int(mn)
            out[key + "_max"] = int(mx)
            out[key + "_avg"] = int(round(avg))
        else:
            out[key + "_min"] = round(mn, decimals)
            out[key + "_max"] = round(mx, decimals)
            out[key + "_avg"] = round(avg, decimals)
    if include_peak_hours:
        temp_rows = [r for r in rows
                     if r.get("temperature") is not None and r.get("timestamp") is not None]
        if temp_rows:
            warm = max(temp_rows, key=lambda r: r["temperature"])
            cool = min(temp_rows, key=lambda r: r["temperature"])
            try:
                out["warmest_at"] = warm["timestamp"].strftime("%H:%M")
                out["coolest_at"] = cool["timestamp"].strftime("%H:%M")
            except Exception:
                pass
    return out


def get_history_summary() -> dict:
    """Return aggregated indoor stats for the last 24 hours and last 7 days.

    Used by the voice assistant to answer questions about past data.
    Cached in memory for 5 minutes — aggregates change slowly.
    """
    if (time.time() - _HISTORY_SUMMARY_CACHE["ts"]) < _HISTORY_SUMMARY_TTL:
        return _HISTORY_SUMMARY_CACHE["value"] or {}

    summary = {}
    try:
        rows_24h = get_history(24)
        if rows_24h:
            summary["h24"] = _summarize_rows(rows_24h, include_peak_hours=True)
        rows_7d = get_history(168)
        if rows_7d:
            summary["h168"] = _summarize_rows(rows_7d, include_peak_hours=False)
    except Exception as e:
        logger.error(f"BigQuery history summary error: {e}")
        return {}

    _HISTORY_SUMMARY_CACHE["ts"] = time.time()
    _HISTORY_SUMMARY_CACHE["value"] = summary
    return summary
