import json
import sqlite3
import threading
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.domain.models import CheckpointRecord, ProjectRecord
from app.domain.repositories import (
    ProjectAlreadyExists,
    ProjectNotFound,
    VersionConflict,
)


def _canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


class SQLiteProjectRepository:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._connection: sqlite3.Connection | None = None
        self._lock = threading.RLock()

    def initialize(self) -> None:
        with self._lock:
            if self._connection is not None:
                return
            self._path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(
                self._path,
                check_same_thread=False,
                isolation_level=None,
                timeout=30,
            )
            try:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys = ON")
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS projects (
                      project_id TEXT PRIMARY KEY,
                      brief_json TEXT NOT NULL,
                      created_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS workflow_checkpoints (
                      checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
                      project_id TEXT NOT NULL REFERENCES projects(project_id),
                      stage TEXT NOT NULL,
                      status TEXT NOT NULL,
                      version INTEGER NOT NULL,
                      payload_json TEXT NOT NULL,
                      created_at TEXT NOT NULL,
                      UNIQUE (project_id, stage, version)
                    );
                    """
                )
                self._validate_projects_schema(connection)
                self._validate_checkpoint_schema(connection)
            except Exception:
                connection.close()
                raise
            self._connection = connection

    @staticmethod
    def _validate_projects_schema(connection: sqlite3.Connection) -> None:
        columns = {
            row["name"]: row for row in connection.execute("PRAGMA table_info(projects)")
        }
        required = {"project_id", "brief_json", "created_at"}
        project_id = columns.get("project_id")
        has_text_primary_key = (
            project_id is not None
            and project_id["type"].upper() == "TEXT"
            and project_id["pk"] == 1
        )
        has_required_values = all(
            columns.get(name) is not None and columns[name]["notnull"] == 1
            for name in ("brief_json", "created_at")
        )
        if set(columns) != required or not has_text_primary_key or not has_required_values:
            raise RuntimeError("incompatible projects schema; recreate the local database")

    @staticmethod
    def _validate_checkpoint_schema(connection: sqlite3.Connection) -> None:
        columns = {
            row["name"]: row
            for row in connection.execute("PRAGMA table_info(workflow_checkpoints)")
        }
        required = {
            "checkpoint_id",
            "project_id",
            "stage",
            "status",
            "version",
            "payload_json",
            "created_at",
        }
        has_integer_primary_key = (
            columns.get("checkpoint_id") is not None
            and columns["checkpoint_id"]["type"].upper() == "INTEGER"
            and columns["checkpoint_id"]["pk"] == 1
        )
        has_version_constraint = False
        for index in connection.execute("PRAGMA index_list(workflow_checkpoints)"):
            if not index["unique"]:
                continue
            index_name = index["name"].replace('"', '""')
            names = [
                row["name"]
                for row in connection.execute(f'PRAGMA index_info("{index_name}")')
            ]
            if names == ["project_id", "stage", "version"]:
                has_version_constraint = True
                break
        if set(columns) != required or not has_integer_primary_key or not has_version_constraint:
            raise RuntimeError(
                "incompatible workflow_checkpoints schema; recreate the local database"
            )

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def _connected(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("repository is not initialized")
        return self._connection

    def create(self, project: ProjectRecord) -> None:
        try:
            with self._lock:
                self._connected().execute(
                    "INSERT INTO projects(project_id, brief_json, created_at) VALUES (?, ?, ?)",
                    (
                        project.project_id,
                        _canonical_json(project.brief),
                        project.created_at.astimezone(UTC).isoformat(),
                    ),
                )
        except sqlite3.IntegrityError:
            raise ProjectAlreadyExists from None

    def get(self, project_id: str) -> ProjectRecord | None:
        with self._lock:
            row = self._connected().execute(
                "SELECT project_id, brief_json, created_at FROM projects WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        if row is None:
            return None
        return ProjectRecord(
            project_id=row["project_id"],
            brief=json.loads(row["brief_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def latest_checkpoint(self, project_id: str) -> CheckpointRecord | None:
        with self._lock:
            row = self._connected().execute(
                """
                SELECT project_id, stage, status, version, payload_json, created_at
                FROM workflow_checkpoints
                WHERE project_id = ?
                ORDER BY checkpoint_id DESC
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
        return None if row is None else self._checkpoint(row)

    def put_checkpoint(
        self,
        project_id: str,
        stage: str,
        status: str,
        payload: dict[str, Any],
        expected_version: int,
    ) -> CheckpointRecord:
        payload_json = _canonical_json(payload)
        with self._lock:
            connection = self._connected()
            connection.execute("BEGIN IMMEDIATE")
            try:
                now = datetime.now(UTC)
                project = connection.execute(
                    "SELECT 1 FROM projects WHERE project_id = ?", (project_id,)
                ).fetchone()
                if project is None:
                    raise ProjectNotFound
                row = connection.execute(
                    """
                    SELECT COALESCE(MAX(version), 0) AS version
                    FROM workflow_checkpoints
                    WHERE project_id = ? AND stage = ?
                    """,
                    (project_id, stage),
                ).fetchone()
                current = int(row["version"])
                if current != expected_version:
                    raise VersionConflict(current_version=current)
                version = current + 1
                connection.execute(
                    """
                    INSERT INTO workflow_checkpoints(
                      project_id, stage, status, version, payload_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        stage,
                        status,
                        version,
                        payload_json,
                        now.isoformat(),
                    ),
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return CheckpointRecord(
            project_id=project_id,
            stage=stage,
            status=status,
            version=version,
            payload=deepcopy(json.loads(payload_json)),
            created_at=now,
        )

    @staticmethod
    def _checkpoint(row: sqlite3.Row) -> CheckpointRecord:
        return CheckpointRecord(
            project_id=row["project_id"],
            stage=row["stage"],
            status=row["status"],
            version=row["version"],
            payload=json.loads(row["payload_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
