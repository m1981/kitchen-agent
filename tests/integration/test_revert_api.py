"""
tests/test_revert_api.py
========================
Integration tests for the new revert endpoint:

  POST /api/files/revert/{revert_id}

TDD — Written BEFORE the implementation.

Covers:
  - 200: happy path — file content is restored
  - 200: happy path — created file is deleted on revert
  - 404: unknown revert_id returns 404
  - 404: calling revert twice returns 404 on second call
  - 400: malformed backup JSON returns 400
  - 422: revert_id with path traversal sequence is rejected
  - RevertResponse schema validation (success bool + message str)
"""

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """Returns a tmp directory acting as settings.data_dir."""
    (tmp_path / "materials.md").write_text(
        "# Materials\n\n18mm Birch Plywood.\n", encoding="utf-8"
    )
    return tmp_path


@pytest.fixture
def client(data_dir: Path, monkeypatch) -> TestClient:
    """TestClient with DATA_DIR patched to the tmp data_dir."""
    import src.config as config_module
    import src.main as main_module

    monkeypatch.setattr(config_module.settings, "data_dir", data_dir)

    return TestClient(main_module.app)


def _plant_backup(data_dir: Path, target: Path, original_content: str | None, existed: bool) -> str:
    """
    Manually plants a backup JSON in data_dir/.backups/ and returns the revert_id.
    Used to set up revert scenarios without going through the tool layer.
    """
    revert_id = str(uuid.uuid4())
    backup_dir = data_dir / ".backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "filepath": target.as_posix(),
        "existed": existed,
        "content": original_content,
    }
    (backup_dir / f"{revert_id}.json").write_text(json.dumps(state), encoding="utf-8")
    return revert_id


# ──────────────────────────────────────────────────────────────────────────────
# Happy path — edit revert
# ──────────────────────────────────────────────────────────────────────────────

class TestRevertEditHappyPath:

    def test_revert_restores_original_content(self, client: TestClient, data_dir: Path) -> None:
        """POSTing to /revert/{id} must restore the pre-edit file content."""
        target = data_dir / "materials.md"
        original = target.read_text(encoding="utf-8")

        revert_id = _plant_backup(data_dir, target, original_content=original, existed=True)

        # Simulate what the agent did — overwrite the file
        target.write_text("# Modified\n\nCheap MDF.\n", encoding="utf-8")

        resp = client.post(f"/api/files/revert/{revert_id}")

        assert resp.status_code == 200
        assert target.read_text(encoding="utf-8") == original

    def test_revert_returns_success_true(self, client: TestClient, data_dir: Path) -> None:
        target = data_dir / "materials.md"
        original = target.read_text(encoding="utf-8")
        revert_id = _plant_backup(data_dir, target, original_content=original, existed=True)
        target.write_text("modified", encoding="utf-8")

        resp = client.post(f"/api/files/revert/{revert_id}")

        body = resp.json()
        assert body["success"] is True

    def test_revert_response_has_message(self, client: TestClient, data_dir: Path) -> None:
        target = data_dir / "materials.md"
        original = target.read_text(encoding="utf-8")
        revert_id = _plant_backup(data_dir, target, original_content=original, existed=True)
        target.write_text("modified", encoding="utf-8")

        resp = client.post(f"/api/files/revert/{revert_id}")

        body = resp.json()
        assert isinstance(body["message"], str)
        assert len(body["message"]) > 0


# ──────────────────────────────────────────────────────────────────────────────
# Happy path — create revert (file deletion)
# ──────────────────────────────────────────────────────────────────────────────

class TestRevertCreateHappyPath:

    def test_revert_create_deletes_the_new_file(self, client: TestClient, data_dir: Path) -> None:
        """When the backup says existed=False, reverting must delete the file."""
        new_file = data_dir / "brand_new.md"
        new_file.write_text("# Brand new content", encoding="utf-8")

        revert_id = _plant_backup(data_dir, new_file, original_content=None, existed=False)

        resp = client.post(f"/api/files/revert/{revert_id}")

        assert resp.status_code == 200
        assert not new_file.exists()

    def test_revert_create_returns_success_true(self, client: TestClient, data_dir: Path) -> None:
        new_file = data_dir / "brand_new.md"
        new_file.write_text("content", encoding="utf-8")
        revert_id = _plant_backup(data_dir, new_file, original_content=None, existed=False)

        resp = client.post(f"/api/files/revert/{revert_id}")

        assert resp.json()["success"] is True


# ──────────────────────────────────────────────────────────────────────────────
# Backup cleanup — double-revert prevention
# ──────────────────────────────────────────────────────────────────────────────

class TestRevertIdempotency:

    def test_backup_json_deleted_after_successful_revert(
        self, client: TestClient, data_dir: Path
    ) -> None:
        """The backup JSON must be cleaned up after a successful revert."""
        target = data_dir / "materials.md"
        original = target.read_text(encoding="utf-8")
        revert_id = _plant_backup(data_dir, target, original_content=original, existed=True)
        target.write_text("modified", encoding="utf-8")

        client.post(f"/api/files/revert/{revert_id}")

        backup_file = data_dir / ".backups" / f"{revert_id}.json"
        assert not backup_file.exists()

    def test_second_revert_returns_404(self, client: TestClient, data_dir: Path) -> None:
        """Calling revert a second time with the same ID must return 404."""
        target = data_dir / "materials.md"
        original = target.read_text(encoding="utf-8")
        revert_id = _plant_backup(data_dir, target, original_content=original, existed=True)
        target.write_text("modified", encoding="utf-8")

        client.post(f"/api/files/revert/{revert_id}")  # first call → 200
        resp = client.post(f"/api/files/revert/{revert_id}")  # second call → 404

        assert resp.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# Error cases
# ──────────────────────────────────────────────────────────────────────────────

class TestRevertErrorCases:

    def test_unknown_revert_id_returns_404(self, client: TestClient) -> None:
        resp = client.post("/api/files/revert/totally-unknown-id")
        assert resp.status_code == 404

    def test_malformed_json_backup_returns_400(self, client: TestClient, data_dir: Path) -> None:
        """Corrupt backup JSON must yield a 400, not a 500."""
        backup_dir = data_dir / ".backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        bad_id = str(uuid.uuid4())
        (backup_dir / f"{bad_id}.json").write_text("{BROKEN JSON", encoding="utf-8")

        resp = client.post(f"/api/files/revert/{bad_id}")

        assert resp.status_code == 400

    def test_path_traversal_in_backup_content_is_blocked(
        self, client: TestClient, data_dir: Path
    ) -> None:
        """
        A backup file whose stored 'filepath' points outside data_dir must be rejected.
        This guards against a crafted / tampered backup file.
        """
        # Plant a backup that points outside data_dir
        backup_dir = data_dir / ".backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        evil_id = str(uuid.uuid4())
        evil_state = {
            "filepath": "/etc/passwd",
            "existed": True,
            "content": "evil content",
        }
        (backup_dir / f"{evil_id}.json").write_text(json.dumps(evil_state), encoding="utf-8")

        resp = client.post(f"/api/files/revert/{evil_id}")

        assert resp.status_code == 400
