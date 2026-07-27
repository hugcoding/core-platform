"""CSV conventions for Dutch-locale CORE exports."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, TextIO


CSV_DELIMITER = ";"


def dict_reader(handle: TextIO) -> csv.DictReader:
    sample = handle.read(4096)
    handle.seek(0)
    delimiter = CSV_DELIMITER if sample.count(";") > sample.count(",") else ","
    return csv.DictReader(handle, delimiter=delimiter)


def write_dict_rows(
    path: Path,
    rows: Iterable[dict[str, object]],
    fieldnames: list[str],
) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            delimiter=CSV_DELIMITER,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
