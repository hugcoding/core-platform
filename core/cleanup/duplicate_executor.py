"""Safety checks for reversible exact-duplicate quarantine moves."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping

from core.migration.personal_executor import (
    MigrationSafetyError,
    Preconditions,
    inspect_preconditions as inspect_move_preconditions,
    move_verified as move_file_verified,
    resume_verified_move as resume_file_verified,
    rollback_verified as rollback_file_verified,
    sha256_file,
)


QUARANTINE_ROOT = Path("/volume1/data/.core/quarantaine/duplicaten")
QUARANTINE_ZONES = (QUARANTINE_ROOT,)


def verify_leader(item: Mapping[str, Any]) -> Dict[str, Any]:
    leader = Path(str(item["leader_path"]))
    source = Path(str(item["source_path"]))
    expected_hash = str(item["content_sha256"]).lower()
    expected_size = int(item["size_bytes"])
    if leader == source:
        raise MigrationSafetyError("leader_equals_redundant_copy")
    if not leader.is_file() or leader.is_symlink():
        raise MigrationSafetyError("leader_missing_or_not_regular_file")
    if leader.stat().st_size != expected_size:
        raise MigrationSafetyError("leader_size_changed")
    if sha256_file(leader) != expected_hash:
        raise MigrationSafetyError("leader_hash_changed")
    return {"leader_path": str(leader), "leader_hash_verified": True}


def inspect_preconditions(item: Mapping[str, Any]) -> Preconditions:
    verify_leader(item)
    return inspect_move_preconditions(item, allowed_zones=QUARANTINE_ZONES)


def move_verified(item: Mapping[str, Any]) -> Dict[str, Any]:
    leader = verify_leader(item)
    result = move_file_verified(item, allowed_zones=QUARANTINE_ZONES)
    result.update(leader)
    return result


def resume_verified_move(item: Mapping[str, Any]) -> Dict[str, Any]:
    leader = verify_leader(item)
    result = resume_file_verified(item, allowed_zones=QUARANTINE_ZONES)
    result.update(leader)
    return result


def rollback_verified(item: Mapping[str, Any]) -> Dict[str, Any]:
    result = rollback_file_verified(item, allowed_zones=QUARANTINE_ZONES)
    result["leader_still_verified"] = verify_leader(item)["leader_hash_verified"]
    return result
