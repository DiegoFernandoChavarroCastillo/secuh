"""Vuelca el histórico a CSV o Parquet para analizarlo con pandas.

Lee la base de datos directamente, sin pasar por la API: no necesita que el
servidor esté corriendo ni credenciales de sesión, solo acceso a la base. Usa
las mismas columnas que la descarga del panel (``secuh.db.export``), así que
los dos caminos producen exactamente el mismo dataset.

Uso::

    cd backend
    uv run python scripts/export_dataset.py --out ../data/analisis
    uv run python scripts/export_dataset.py --format csv --from 2026-08-01

Parquet conserva los tipos (fechas como fechas, números como números) y ocupa
bastante menos; CSV se abre en cualquier sitio. Por defecto salen los dos.

Parquet necesita el grupo opcional de dependencias::

    uv sync --group analysis
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from secuh.db.export import (
    EVENT_COLUMNS,
    OBJECT_COLUMNS,
    csv_safe,
    event_rows,
    object_rows,
)
from secuh.settings import ServerSettings


def write_csv(path: Path, header: tuple[str, ...], rows: Iterator[tuple[object, ...]]) -> int:
    """Escribe el CSV en streaming y devuelve cuántas filas salieron."""
    count = 0
    # newline="" es obligatorio con el módulo csv: sin él, en Windows cada fila
    # acabaría con un salto de línea doble.
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for row in rows:
            writer.writerow([csv_safe(value) for value in row])
            count += 1
    return count


def write_parquet(path: Path, header: tuple[str, ...], rows: Iterator[tuple[object, ...]]) -> int:
    """Escribe el Parquet. A diferencia del CSV, materializa en memoria."""
    try:
        import pandas as pd
    except ImportError:
        raise SystemExit(
            "Parquet necesita pandas y pyarrow. Instálalos con:\n"
            "    uv sync --group analysis\n"
            "O exporta solo CSV con: --format csv"
        ) from None

    frame = pd.DataFrame(list(rows), columns=list(header))
    # Los timestamps salen como texto ISO 8601 con zona; convertirlos aquí
    # evita que cada análisis tenga que acordarse de hacerlo.
    if "timestamp_utc" in frame.columns:
        frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
    frame.to_parquet(path, index=False)
    return len(frame)


def parse_date(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"fecha no válida: {value!r} (se espera ISO 8601, p. ej. 2026-08-01)"
        ) from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--out", type=Path, default=Path("export"), help="carpeta de destino (se crea si no existe)"
    )
    parser.add_argument("--format", choices=("csv", "parquet", "both"), default="both")
    parser.add_argument("--camera-id", type=UUID, default=None, help="filtrar por una cámara")
    parser.add_argument("--label", default=None, help="solo eventos con esta clase en la escena")
    parser.add_argument("--from", dest="since", type=parse_date, default=None)
    parser.add_argument("--to", dest="until", type=parse_date, default=None)
    parser.add_argument(
        "--database-url",
        default=None,
        help="por defecto, la de SECUH_DATABASE_URL / settings",
    )
    args = parser.parse_args(argv)

    settings = ServerSettings()
    database_url = args.database_url or settings.database_url
    args.out.mkdir(parents=True, exist_ok=True)

    filters: dict[str, Any] = {
        "camera_id": args.camera_id,
        "label": args.label,
        "since": args.since,
        "until": args.until,
    }
    engine = create_engine(database_url)
    formats = ("csv", "parquet") if args.format == "both" else (args.format,)

    with Session(engine) as session:
        for name, header, builder in (
            ("eventos", EVENT_COLUMNS, event_rows),
            ("objetos", OBJECT_COLUMNS, object_rows),
        ):
            for fmt in formats:
                path = args.out / f"secuh-{name}.{fmt}"
                writer = write_csv if fmt == "csv" else write_parquet
                # El generador se consume una vez por formato: hay que pedirlo
                # de nuevo, no reutilizar el iterador agotado.
                count = writer(path, header, builder(session, **filters))
                print(f"{path}  ({count} filas)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
