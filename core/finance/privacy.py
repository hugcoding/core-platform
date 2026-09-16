"""Shared fail-closed source boundary; no content inspection is needed."""
import os
from pathlib import Path


def source_root():
    return Path(os.getenv('CORE_FINANCE_ROOT', '/volume1/data/import/finance'))


def protected_path(value):
    if not value:
        return False
    root = source_root()
    path = Path(str(value))
    # Check both the lexical and resolved path (including aliases/symlinks).
    return path.is_relative_to(root) or path.resolve().is_relative_to(root.resolve())


def deny_generic_access(value):
    if protected_path(value):
        raise PermissionError('finance_source_protected')
