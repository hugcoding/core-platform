"""Safety primitives for controlled personal-document moves."""
from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple, Union


DATA_ROOT = Path("/volume1/data")
PERSONAL_ROOT = DATA_ROOT / "Persoonlijk"
ALLOWED_ZONES = (PERSONAL_ROOT / "Actief", PERSONAL_ROOT / "Inactief")


class MigrationSafetyError(RuntimeError):
    """Raised when a move or rollback violates a safety precondition."""


def normalized_path(value: Union[str, Path]) -> Path:
    return Path(os.path.normpath(str(value)))


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def nearest_existing(path: Path) -> Path:
    current = path
    while not current.exists():
        if current.parent == current:
            return current
        current = current.parent
    return current


def validate_paths(
    source: Union[str, Path], target: Union[str, Path], *, source_may_be_missing: bool = False,
    allowed_zones: Optional[Tuple[Path, ...]] = None,
) -> Tuple[Path, Path]:
    source_path, target_path = normalized_path(source), normalized_path(target)
    if not is_within(source_path, DATA_ROOT) or not is_within(target_path, DATA_ROOT):
        raise MigrationSafetyError("source_and_target_must_be_within_volume1_data")
    zones = allowed_zones or ALLOWED_ZONES
    if not any(is_within(target_path, zone) for zone in zones):
        raise MigrationSafetyError("target_outside_allowed_zone")
    if source_path == target_path:
        raise MigrationSafetyError("source_equals_target")
    resolved_root = DATA_ROOT.resolve(strict=True)
    source_anchor = nearest_existing(source_path) if source_may_be_missing else source_path
    if not is_within(source_anchor.resolve(strict=True), resolved_root):
        raise MigrationSafetyError("source_resolves_outside_volume1_data")
    target_ancestor = nearest_existing(target_path.parent).resolve(strict=True)
    if not is_within(target_ancestor, resolved_root):
        raise MigrationSafetyError("target_resolves_outside_volume1_data")
    return source_path, target_path


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class Preconditions:
    source: Path
    target: Path
    size_bytes: int
    mtime_ns: int
    content_sha256: str


def inspect_preconditions(
    item: Mapping[str, Any], *, minimum_free_bytes: int = 0,
    allowed_zones: Optional[Tuple[Path, ...]] = None,
) -> Preconditions:
    source, target = validate_paths(
        item["source_path"], item["target_path"], allowed_zones=allowed_zones
    )
    if not source.is_file() or source.is_symlink():
        raise MigrationSafetyError("source_missing_or_not_regular_file")
    if target.exists() or target.is_symlink():
        raise MigrationSafetyError("target_collision")
    stat = source.stat()
    expected_size = int(item["size_bytes"])
    if stat.st_size != expected_size:
        raise MigrationSafetyError("source_size_changed")
    expected_hash = str(item["content_sha256"]).lower()
    if sha256_file(source) != expected_hash:
        raise MigrationSafetyError("source_hash_changed")
    usage = shutil.disk_usage(source.parent)
    if usage.free - expected_size < int(minimum_free_bytes):
        raise MigrationSafetyError("insufficient_free_space")
    return Preconditions(source, target, expected_size, stat.st_mtime_ns, expected_hash)


def move_verified(
    item: Mapping[str, Any], *, minimum_free_bytes: int = 0,
    allowed_zones: Optional[Tuple[Path, ...]] = None,
) -> Dict[str, Any]:
    checked = inspect_preconditions(
        item, minimum_free_bytes=minimum_free_bytes, allowed_zones=allowed_zones
    )
    checked.target.parent.mkdir(parents=True, exist_ok=True)
    if checked.source.stat().st_dev != checked.target.parent.stat().st_dev:
        raise MigrationSafetyError("cross_filesystem_move_not_supported")
    # A same-filesystem hard link is no-clobber: an existing target fails. The
    # source name is removed only after the target has been fully verified.
    os.link(str(checked.source), str(checked.target))
    if checked.target.stat().st_size != checked.size_bytes:
        raise MigrationSafetyError("target_size_verification_failed")
    if sha256_file(checked.target) != checked.content_sha256:
        raise MigrationSafetyError("target_hash_verification_failed")
    if checked.target.stat().st_mtime_ns != checked.mtime_ns:
        raise MigrationSafetyError("target_mtime_verification_failed")
    checked.source.unlink()
    return {
        "source_path": str(checked.source), "target_path": str(checked.target),
        "size_bytes": checked.size_bytes, "mtime_ns": checked.mtime_ns,
        "content_sha256": checked.content_sha256,
    }


def resume_verified_move(
    item: Mapping[str, Any], *, allowed_zones: Optional[Tuple[Path, ...]] = None
) -> Dict[str, Any]:
    """Finish or verify a move interrupted between append-only events."""
    source, target = validate_paths(
        item["source_path"], item["target_path"], source_may_be_missing=True,
        allowed_zones=allowed_zones,
    )
    if not target.is_file() or target.is_symlink():
        raise MigrationSafetyError("interrupted_move_target_missing")
    expected_hash, expected_size = str(item["content_sha256"]).lower(), int(item["size_bytes"])
    mtime_ns = int(item["mtime_ns"])
    if target.stat().st_size != expected_size or sha256_file(target) != expected_hash:
        raise MigrationSafetyError("interrupted_move_target_changed")
    if target.stat().st_mtime_ns != mtime_ns:
        raise MigrationSafetyError("interrupted_move_mtime_changed")
    if source.exists():
        if not source.is_file() or not os.path.samefile(str(source), str(target)):
            raise MigrationSafetyError("interrupted_move_source_target_conflict")
        source.unlink()
    return {"source_path": str(source), "target_path": str(target),
            "size_bytes": expected_size, "mtime_ns": mtime_ns,
            "content_sha256": expected_hash, "resumed": True}


def rollback_verified(
    item: Mapping[str, Any], *, allowed_zones: Optional[Tuple[Path, ...]] = None
) -> Dict[str, Any]:
    source, target = validate_paths(
        item["source_path"], item["target_path"], source_may_be_missing=True,
        allowed_zones=allowed_zones,
    )
    expected_hash = str(item["content_sha256"]).lower()
    expected_size = int(item["size_bytes"])
    mtime_ns = int(item["mtime_ns"])
    if source.is_file() and not target.exists():
        if source.stat().st_size != expected_size or sha256_file(source) != expected_hash:
            raise MigrationSafetyError("rollback_existing_source_changed")
        return {"restored_path": str(source), "content_sha256": expected_hash,
                "mtime_ns": mtime_ns, "already_at_source": True}
    if source.exists() or source.is_symlink():
        if not target.is_file() or not os.path.samefile(str(source), str(target)):
            raise MigrationSafetyError("rollback_source_collision")
        if target.stat().st_size != expected_size or sha256_file(target) != expected_hash:
            raise MigrationSafetyError("rollback_target_content_changed")
        target.unlink()
        return {"restored_path": str(source), "content_sha256": expected_hash,
                "mtime_ns": mtime_ns, "recovered_interrupted_move": True}
    if not target.is_file() or target.is_symlink():
        raise MigrationSafetyError("rollback_target_missing")
    if target.stat().st_size != expected_size or sha256_file(target) != expected_hash:
        raise MigrationSafetyError("rollback_target_content_changed")
    source.parent.mkdir(parents=True, exist_ok=True)
    if source.parent.stat().st_dev != target.stat().st_dev:
        raise MigrationSafetyError("cross_filesystem_rollback_not_supported")
    os.link(str(target), str(source))
    if source.stat().st_size != expected_size or sha256_file(source) != expected_hash:
        raise MigrationSafetyError("rollback_verification_failed")
    if source.stat().st_mtime_ns != mtime_ns:
        raise MigrationSafetyError("rollback_mtime_verification_failed")
    target.unlink()
    return {"restored_path": str(source), "content_sha256": expected_hash, "mtime_ns": mtime_ns}
