import json
import math
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List

import requests
import yaml


REQUEST_TIMEOUT = 60
HISTORY_DAYS = 60
MIN_ACTIVE_WATTS = 20
MAX_ACTIVE_WATTS = 500
PERCENTILE = 0.95
MIN_POSITIVE_SAMPLE = 0.0
MIN_SAMPLE_COUNT = 10
SECRETS_PATH = Path("/config/secrets.yaml")
RECORDER_DB_PATH = Path("/config/home-assistant_v2.db")
RESTORE_STATE_PATH = Path("/config/.storage/core.restore_state")
THRESHOLD_PREFIX = "sensor.energy_threshold_"
SYNC_STATUS_ENTITY_ID = "sensor.energy_thresholds_last_sync"


def load_secrets() -> dict:
    with SECRETS_PATH.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def percentile(values: List[float], ratio: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * ratio
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    weight = index - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def threshold_entity_id(target_key: str) -> str:
    return f"{THRESHOLD_PREFIX}{target_key}"


def friendly_name(display_name: str) -> str:
    return f"Energy Threshold {display_name}"


def parse_targets(raw_value: str) -> List[dict]:
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid targets JSON: {exc}") from exc

    targets = []
    seen_keys = set()
    if not isinstance(payload, list):
        raise ValueError("Targets payload must be a list")

    for item in payload:
        if not isinstance(item, dict):
            continue
        target_key = str(item.get("key", "")).strip()
        source_sensor = str(item.get("sensor", "")).strip()
        display_name = str(item.get("name", "")).strip() or source_sensor
        if not target_key or not source_sensor or target_key in seen_keys:
            continue
        targets.append(
            {
                "key": target_key,
                "sensor": source_sensor,
                "name": display_name,
            }
        )
        seen_keys.add(target_key)
    return targets


def iter_numeric_samples(history_payload: Iterable[dict]) -> List[float]:
    samples = []
    for item in history_payload:
        state = item.get("state")
        try:
            numeric_state = float(state)
        except (TypeError, ValueError):
            continue
        if math.isfinite(numeric_state) and numeric_state > MIN_POSITIVE_SAMPLE:
            samples.append(numeric_state)
    return samples


def preview_states(history_payload: Iterable[dict], limit: int = 5) -> List[str]:
    preview = []
    for item in history_payload:
        state = item.get("state")
        if state is None:
            continue
        preview.append(str(state))
        if len(preview) >= limit:
            break
    return preview


def clamp_threshold(value: float) -> int:
    rounded = int(round(value))
    return max(MIN_ACTIVE_WATTS, min(MAX_ACTIVE_WATTS, rounded))


def fetch_history(session: requests.Session, ha_url: str, source_entity_id: str) -> List[dict]:
    start_at = (datetime.now(timezone.utc) - timedelta(days=HISTORY_DAYS)).isoformat()
    response = session.get(
        f"{ha_url}/api/history/period/{start_at}",
        params={
            "filter_entity_id": source_entity_id,
            "minimal_response": "1",
            "no_attributes": "1",
            "significant_changes_only": "0",
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload:
        return []
    return payload[0]


def fetch_history_from_sqlite(source_entity_id: str) -> List[dict]:
    if not RECORDER_DB_PATH.exists():
        return []

    start_ts = (datetime.now(timezone.utc) - timedelta(days=HISTORY_DAYS)).timestamp()

    with sqlite3.connect(str(RECORDER_DB_PATH)) as connection:
        cursor = connection.cursor()
        cursor.execute("PRAGMA table_info(states)")
        state_columns = {row[1] for row in cursor.fetchall()}

        if "metadata_id" in state_columns:
            query = """
                SELECT s.state
                FROM states AS s
                JOIN states_meta AS sm ON sm.metadata_id = s.metadata_id
                WHERE sm.entity_id = ?
                  AND s.last_updated_ts >= ?
                ORDER BY s.last_updated_ts ASC
            """
            cursor.execute(query, (source_entity_id, start_ts))
        elif "entity_id" in state_columns and "last_updated_ts" in state_columns:
            query = """
                SELECT state
                FROM states
                WHERE entity_id = ?
                  AND last_updated_ts >= ?
                ORDER BY last_updated_ts ASC
            """
            cursor.execute(query, (source_entity_id, start_ts))
        else:
            return []

        return [{"state": row[0]} for row in cursor.fetchall()]


def fetch_states(session: requests.Session, ha_url: str) -> List[dict]:
    response = session.get(f"{ha_url}/api/states", timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def delete_state(session: requests.Session, ha_url: str, entity_id: str) -> None:
    response = session.delete(f"{ha_url}/api/states/{entity_id}", timeout=REQUEST_TIMEOUT)
    response.raise_for_status()


def cleanup_stale_thresholds(
    session: requests.Session,
    ha_url: str,
    expected_entity_ids: List[str],
) -> List[str]:
    deleted = []
    expected = set(expected_entity_ids)
    states = fetch_states(session, ha_url)
    for state in states:
        entity_id = state.get("entity_id")
        if not entity_id or not entity_id.startswith(THRESHOLD_PREFIX):
            continue
        if entity_id == SYNC_STATUS_ENTITY_ID:
            continue
        if entity_id in expected:
            continue
        delete_state(session, ha_url, entity_id)
        deleted.append(entity_id)
    return deleted


def cleanup_restore_state(expected_entity_ids: List[str]) -> List[str]:
    if not RESTORE_STATE_PATH.exists():
        return []

    with RESTORE_STATE_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    data = payload.get("data")
    if not isinstance(data, list):
        return []

    expected = set(expected_entity_ids)
    kept = []
    deleted = []

    for item in data:
        if not isinstance(item, dict):
            kept.append(item)
            continue

        state_obj = item.get("state")
        entity_id = None
        if isinstance(state_obj, dict):
            entity_id = state_obj.get("entity_id")

        if (
            isinstance(entity_id, str)
            and entity_id.startswith(THRESHOLD_PREFIX)
            and entity_id != SYNC_STATUS_ENTITY_ID
            and entity_id not in expected
        ):
            deleted.append(entity_id)
            continue

        kept.append(item)

    if not deleted:
        return []

    payload["data"] = kept
    temp_path = RESTORE_STATE_PATH.with_suffix(".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, separators=(",", ":"))
    temp_path.replace(RESTORE_STATE_PATH)

    return deleted


def publish_threshold(
    session: requests.Session,
    ha_url: str,
    target_key: str,
    source_entity_id: str,
    display_name: str,
    threshold_value: int,
    history_source: str,
    history_rows: int,
    samples_count: int,
    p95_value: float,
    max_sample: float,
    states_preview: List[str],
    threshold_mode: str,
) -> None:
    entity_id = threshold_entity_id(target_key)
    response = session.post(
        f"{ha_url}/api/states/{entity_id}",
        json={
            "state": threshold_value,
            "attributes": {
                "friendly_name": friendly_name(display_name),
                "unit_of_measurement": "W",
                "icon": "mdi:tune-variant",
                "threshold_key": target_key,
                "source_sensor": source_entity_id,
                "display_name": display_name,
                "history_days": HISTORY_DAYS,
                "history_source": history_source,
                "history_rows": history_rows,
                "sample_count": samples_count,
                "percentile": int(PERCENTILE * 100),
                "percentile_value": round(p95_value, 1),
                "max_sample": round(max_sample, 1),
                "states_preview": states_preview,
                "threshold_formula": "clamp(p95_positive_samples * 0.1, 20W, 500W)",
                "threshold_mode": threshold_mode,
                "last_synced": datetime.now(timezone.utc).isoformat(),
            },
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()


def publish_sync_status(
    session: requests.Session,
    ha_url: str,
    synced_entities: List[str],
    deleted_entities: List[str],
    restore_deleted_entities: List[str],
) -> None:
    response = session.post(
        f"{ha_url}/api/states/{SYNC_STATUS_ENTITY_ID}",
        json={
            "state": datetime.now(timezone.utc).isoformat(),
            "attributes": {
                "friendly_name": "Energy Thresholds Last Sync",
                "icon": "mdi:update",
                "synced_entities": synced_entities,
                "deleted_entities": deleted_entities,
                "restore_deleted_entities": restore_deleted_entities,
                "count": len(synced_entities),
            },
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()


def main() -> int:
    if len(sys.argv) < 2:
        print("Missing targets JSON argument")
        return 1

    try:
        targets = parse_targets(sys.argv[1])
    except ValueError as exc:
        print(str(exc))
        return 1

    secrets = load_secrets()
    ha_token = secrets.get("ha_api_token")
    if not ha_token:
        print("Missing secret 'ha_api_token' in /config/secrets.yaml")
        return 1

    ha_url = secrets.get("homeassistant_url", "http://127.0.0.1:8123").rstrip("/")
    if not targets:
        print("No source sensors provided")
        return 0

    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {ha_token}",
            "Content-Type": "application/json",
        }
    )

    synced_entities = []
    failures = 0
    expected_entity_ids = [threshold_entity_id(target["key"]) for target in targets]

    for target in targets:
        target_key = target["key"]
        source_entity_id = target["sensor"]
        display_name = target["name"]
        try:
            history_payload = fetch_history(session, ha_url, source_entity_id)
            history_source = "api"
            if not history_payload:
                history_payload = fetch_history_from_sqlite(source_entity_id)
                history_source = "sqlite" if history_payload else "none"
            samples = iter_numeric_samples(history_payload)
            states_preview = preview_states(history_payload)
            p95_value = percentile(samples, PERCENTILE) if samples else 0.0
            max_sample = max(samples) if samples else 0.0
            if len(samples) >= MIN_SAMPLE_COUNT and p95_value > 0:
                threshold_value = clamp_threshold(p95_value * 0.1)
                threshold_mode = "derived"
            else:
                threshold_value = MIN_ACTIVE_WATTS
                threshold_mode = "fallback"
            publish_threshold(
                session=session,
                ha_url=ha_url,
                target_key=target_key,
                source_entity_id=source_entity_id,
                display_name=display_name,
                threshold_value=threshold_value,
                history_source=history_source,
                history_rows=len(history_payload),
                samples_count=len(samples),
                p95_value=p95_value,
                max_sample=max_sample,
                states_preview=states_preview,
                threshold_mode=threshold_mode,
            )
            synced_entities.append(threshold_entity_id(target_key))
            print(
                f"{target_key} <- {source_entity_id}: threshold={threshold_value}W "
                f"source={history_source} mode={threshold_mode} rows={len(history_payload)} "
                f"samples={len(samples)} max={round(max_sample, 1)} "
                f"p95={round(p95_value, 1)} preview={states_preview}"
            )
        except requests.RequestException as exc:
            failures += 1
            print(f"{target_key} <- {source_entity_id}: request error: {exc}")
        except Exception as exc:
            failures += 1
            print(f"{target_key} <- {source_entity_id}: unexpected error: {exc}")

    deleted_entities = []
    restore_deleted_entities = []
    try:
        deleted_entities = cleanup_stale_thresholds(session, ha_url, expected_entity_ids)
        if deleted_entities:
            print(f"Deleted stale threshold entities: {', '.join(deleted_entities)}")
    except requests.RequestException as exc:
        failures += 1
        print(f"threshold cleanup error: {exc}")

    try:
        restore_deleted_entities = cleanup_restore_state(expected_entity_ids)
        if restore_deleted_entities:
            print(f"Deleted stale restore_state entries: {', '.join(restore_deleted_entities)}")
    except Exception as exc:
        failures += 1
        print(f"restore_state cleanup error: {exc}")

    try:
        publish_sync_status(
            session,
            ha_url,
            synced_entities,
            deleted_entities,
            restore_deleted_entities,
        )
    except requests.RequestException as exc:
        failures += 1
        print(f"sync status publish error: {exc}")

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
