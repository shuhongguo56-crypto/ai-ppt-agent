import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Event

import pytest

from app.domain.models import ProjectRecord
from app.domain.repositories import ProjectAlreadyExists, ProjectNotFound, VersionConflict
from app.persistence import sqlite as sqlite_module
from app.persistence.sqlite import SQLiteProjectRepository


def repository_at(path):
    repository = SQLiteProjectRepository(path)
    repository.initialize()
    return repository


@pytest.fixture
def repository_factory():
    repositories = []

    def create(path):
        repository = repository_at(path)
        repositories.append(repository)
        return repository

    yield create
    for repository in reversed(repositories):
        repository.close()


def test_project_survives_repository_reopen_with_aware_timestamp(
    tmp_path, repository_factory
) -> None:
    path = tmp_path / "state.db"
    first = repository_factory(path)
    brief = {"schemaVersion": "1.0.0", "topic": "CRISPR"}
    first.create(ProjectRecord.new("project-1", brief))
    brief["topic"] = "mutated"
    first.close()

    second = repository_factory(path)
    project = second.get("project-1")
    assert project is not None
    assert project.brief["topic"] == "CRISPR"
    assert project.created_at.utcoffset() is not None


def test_project_errors_are_domain_errors(tmp_path, repository_factory) -> None:
    repository = repository_factory(tmp_path / "state.db")
    project = ProjectRecord.new("project-1", {"schemaVersion": "1.0.0"})
    repository.create(project)
    with pytest.raises(ProjectAlreadyExists):
        repository.create(project)
    with pytest.raises(ProjectNotFound):
        repository.put_checkpoint(
            "missing", "brief", "draft", {"schemaVersion": "1.0.0"}, 0
        )


def test_checkpoint_versions_are_scoped_to_project_and_stage(
    tmp_path, repository_factory
) -> None:
    repository = repository_factory(tmp_path / "state.db")
    repository.create(ProjectRecord.new("project-1", {"schemaVersion": "1.0.0"}))
    brief = repository.put_checkpoint(
        "project-1", "brief", "draft", {"schemaVersion": "1.0.0"}, 0
    )
    outline = repository.put_checkpoint(
        "project-1", "outline", "draft", {"schemaVersion": "1.0.0"}, 0
    )
    assert brief.version == outline.version == 1

    with pytest.raises(VersionConflict) as captured:
        repository.put_checkpoint(
            "project-1", "brief", "confirmed", {"schemaVersion": "1.0.0"}, 0
        )
    assert captured.value.current_version == 1
    confirmed = repository.put_checkpoint(
        "project-1", "brief", "confirmed", {"schemaVersion": "1.0.0"}, 1
    )
    assert confirmed.version == 2


def test_checkpoint_survives_reopen_and_results_are_not_aliased(
    tmp_path, repository_factory
) -> None:
    path = tmp_path / "state.db"
    first = repository_factory(path)
    first.create(ProjectRecord.new("project-1", {"schemaVersion": "1.0.0"}))
    payload = {"schemaVersion": "1.0.0", "nested": {"value": 1}}
    written = first.put_checkpoint("project-1", "brief", "draft", payload, 0)
    payload["nested"]["value"] = 2
    written.payload["nested"]["value"] = 3
    first.close()

    second = repository_factory(path)
    latest = second.latest_checkpoint("project-1")
    assert latest is not None
    assert latest.payload["nested"]["value"] == 1
    assert latest.created_at.utcoffset() is not None


def test_latest_checkpoint_across_stages_is_deterministic(
    tmp_path, repository_factory
) -> None:
    repository = repository_factory(tmp_path / "state.db")
    repository.create(ProjectRecord.new("project-1", {"schemaVersion": "1.0.0"}))
    repository.put_checkpoint(
        "project-1", "brief", "draft", {"schemaVersion": "1.0.0", "n": 1}, 0
    )
    repository.put_checkpoint(
        "project-1", "outline", "draft", {"schemaVersion": "1.0.0", "n": 2}, 0
    )
    assert repository.latest_checkpoint("project-1").stage == "outline"


def test_latest_checkpoint_follows_database_insertion_order(
    tmp_path, repository_factory
) -> None:
    path = tmp_path / "state.db"
    repository = repository_factory(path)
    repository.create(ProjectRecord.new("project-1", {"schemaVersion": "1.0.0"}))

    lock_holder = sqlite3.connect(path, isolation_level=None, timeout=30)
    lock_holder.execute("PRAGMA foreign_keys = ON")
    lock_holder.execute("BEGIN IMMEDIATE")
    begin_attempted = Event()
    real_connection = repository._connection

    class BeginObserver:
        def execute(self, sql, parameters=()):
            if sql == "BEGIN IMMEDIATE":
                begin_attempted.set()
            return real_connection.execute(sql, parameters)

        def __getattr__(self, name):
            return getattr(real_connection, name)

    repository._connection = BeginObserver()
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        waiting_writer = pool.submit(
            repository.put_checkpoint,
            "project-1",
            "brief",
            "inserted-last",
            {"schemaVersion": "1.0.0"},
            0,
        )
        try:
            assert begin_attempted.wait(timeout=5)
            lock_holder.execute(
                """
                INSERT INTO workflow_checkpoints(
                  project_id, stage, status, version, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "project-1",
                    "outline",
                    "inserted-first",
                    1,
                    '{"schemaVersion":"1.0.0"}',
                    "9999-12-31T23:59:59+00:00",
                ),
            )
            lock_holder.execute("COMMIT")
        finally:
            if lock_holder.in_transaction:
                lock_holder.execute("ROLLBACK")
            lock_holder.close()
        waiting_writer.result(timeout=5)
    finally:
        pool.shutdown(wait=True, cancel_futures=True)

    latest = repository.latest_checkpoint("project-1")
    assert latest is not None
    assert latest.status == "inserted-last"


def test_initialize_closes_connection_when_schema_setup_fails(
    tmp_path, monkeypatch
) -> None:
    class FailingConnection:
        row_factory = None
        closed = False

        def execute(self, _sql):
            raise sqlite3.OperationalError("schema setup failed")

        def close(self):
            self.closed = True

    connection = FailingConnection()
    monkeypatch.setattr(sqlite3, "connect", lambda *args, **kwargs: connection)
    repository = SQLiteProjectRepository(tmp_path / "state.db")

    with pytest.raises(sqlite3.OperationalError, match="schema setup failed"):
        repository.initialize()

    assert connection.closed is True


def test_initialize_rejects_checkpoint_schema_without_insertion_id(tmp_path) -> None:
    path = tmp_path / "state.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE projects (
          project_id TEXT PRIMARY KEY,
          brief_json TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE workflow_checkpoints (
          project_id TEXT NOT NULL REFERENCES projects(project_id),
          stage TEXT NOT NULL,
          status TEXT NOT NULL,
          version INTEGER NOT NULL,
          payload_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          PRIMARY KEY (project_id, stage, version)
        );
        """
    )
    connection.close()

    repository = SQLiteProjectRepository(path)
    with pytest.raises(RuntimeError, match="incompatible workflow_checkpoints schema"):
        repository.initialize()


@pytest.mark.parametrize(
    "projects_sql",
    [
        "CREATE TABLE projects (project_id INTEGER PRIMARY KEY, brief_json TEXT NOT NULL, created_at TEXT NOT NULL)",
        "CREATE TABLE projects (project_id TEXT PRIMARY KEY, brief_json TEXT, created_at TEXT NOT NULL)",
        "CREATE TABLE projects (project_id TEXT PRIMARY KEY, brief_json TEXT NOT NULL, created_at TEXT NOT NULL, legacy TEXT)",
    ],
)
def test_initialize_rejects_incompatible_projects_schema(tmp_path, projects_sql) -> None:
    path = tmp_path / "state.db"
    connection = sqlite3.connect(path)
    connection.execute(projects_sql)
    connection.close()
    repository = SQLiteProjectRepository(path)

    with pytest.raises(RuntimeError, match="incompatible projects schema"):
        repository.initialize()

    assert repository._connection is None


def test_checkpoint_timestamp_is_captured_after_write_lock(
    tmp_path, repository_factory, monkeypatch
) -> None:
    repository = repository_factory(tmp_path / "state.db")
    repository.create(ProjectRecord.new("project-1", {"schemaVersion": "1.0.0"}))
    write_lock_acquired = Event()
    real_connection = repository._connection

    class LockObserver:
        def execute(self, sql, parameters=()):
            result = real_connection.execute(sql, parameters)
            if sql == "BEGIN IMMEDIATE":
                write_lock_acquired.set()
            return result

        def __getattr__(self, name):
            return getattr(real_connection, name)

    class GuardedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            assert write_lock_acquired.is_set()
            return super().now(tz)

    repository._connection = LockObserver()
    monkeypatch.setattr(sqlite_module, "datetime", GuardedDatetime)

    repository.put_checkpoint(
        "project-1", "brief", "draft", {"schemaVersion": "1.0.0"}, 0
    )


def test_same_expected_version_allows_exactly_one_concurrent_writer(tmp_path) -> None:
    path = tmp_path / "state.db"
    setup = repository_at(path)
    setup.create(ProjectRecord.new("project-1", {"schemaVersion": "1.0.0"}))
    setup.close()

    def write(status: str):
        repository = repository_at(path)
        try:
            return repository.put_checkpoint(
                "project-1", "brief", status, {"schemaVersion": "1.0.0"}, 0
            )
        except VersionConflict as exc:
            return exc
        finally:
            repository.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, ["draft", "confirmed"]))
    assert sum(not isinstance(result, VersionConflict) for result in results) == 1
    conflicts = [result for result in results if isinstance(result, VersionConflict)]
    assert len(conflicts) == 1
    assert conflicts[0].current_version == 1
