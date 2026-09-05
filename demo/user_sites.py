"""Parse a user-uploaded CSV of infrastructure locations into
``MicrowaveSite`` objects.

This is application-boundary code, not part of the reusable
``aei_mw_exposure`` core: CSV upload is an Explorer concern. Uses only the
Python standard library (``csv``, ``io``) -- no pandas, no Streamlit
import here, so this module is independently testable and reusable
outside the Explorer.

WHAT THIS DOES NOT DO
----------------------
It does not verify an uploaded site against any public record. A site
parsed here carries ``Provenance.USER_PROVIDED`` -- never ``REAL`` (that
label is reserved for cited public sources like Ontario GeoHub/ISED) and
never ``DEMO`` (a user's own infrastructure is presumably real, just
unverified here -- it is not synthetic or illustrative).

It does not require, parse, or infer any microwave-specific field
(frequency, fade margin, endpoint pairing, ...). A row is a location,
nothing more -- see ``REQUIRED_COLUMNS``.
"""

from __future__ import annotations

import csv
import io
from typing import List, Tuple

from aei_mw_exposure import MicrowaveSite, Provenance

REQUIRED_COLUMNS: Tuple[str, ...] = ("site_id", "name", "latitude", "longitude")
SOURCE_LABEL = "User-uploaded CSV (not independently verified against a public record)"

# A defensive cap, not a UX feature -- same convention as
# MAX_REAL_MARKERS_PER_SOURCE in app.py: keeps one accidental large upload
# from triggering an unreasonable number of per-site ECCC/model lookups.
MAX_USER_SITES = 50


def parse_user_sites_csv(csv_text: str) -> Tuple[List[MicrowaveSite], List[str]]:
    """Parse CSV text into ``(sites, row_errors)``.

    Raises ``ValueError`` for file-level problems (empty file, no header,
    missing required columns) that make the whole upload unusable.
    Row-level problems (bad coordinates, duplicate/empty site_id) are
    skipped and named in ``row_errors`` -- processing continues for the
    rest of the file, matching this project's existing
    ``load_towers``/``load_sites`` convention of never silently dropping a
    problem without naming it.
    """
    if not csv_text.strip():
        raise ValueError("The uploaded file is empty.")

    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        raise ValueError("The uploaded file has no header row.")

    missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
    if missing:
        raise ValueError(
            f"Missing required column(s): {', '.join(missing)}. "
            f"Required columns are: {', '.join(REQUIRED_COLUMNS)}."
        )

    sites: List[MicrowaveSite] = []
    row_errors: List[str] = []
    seen_ids = set()

    for row_number, row in enumerate(reader, start=2):  # row 1 is the header
        site_id = (row.get("site_id") or "").strip()
        name = (row.get("name") or "").strip()
        lat_raw = (row.get("latitude") or "").strip()
        lon_raw = (row.get("longitude") or "").strip()

        if not site_id:
            row_errors.append(f"Row {row_number}: empty site_id -- skipped.")
            continue
        if site_id in seen_ids:
            row_errors.append(f"Row {row_number}: duplicate site_id '{site_id}' -- skipped.")
            continue

        try:
            latitude = float(lat_raw)
            longitude = float(lon_raw)
        except ValueError:
            row_errors.append(
                f"Row {row_number} ('{site_id}'): latitude/longitude must be numeric "
                f"(got '{lat_raw}', '{lon_raw}') -- skipped."
            )
            continue

        try:
            site = MicrowaveSite(
                id=site_id,
                name=name or site_id,
                latitude=latitude,
                longitude=longitude,
                provenance=Provenance.USER_PROVIDED,
                source=SOURCE_LABEL,
            )
        except ValueError as exc:
            row_errors.append(f"Row {row_number} ('{site_id}'): {exc} -- skipped.")
            continue

        seen_ids.add(site_id)
        sites.append(site)

        if len(sites) >= MAX_USER_SITES:
            remaining = sum(1 for _ in reader)
            if remaining:
                row_errors.append(
                    f"Stopped after {MAX_USER_SITES} sites (this tool's per-upload limit); "
                    f"{remaining} more row(s) were not processed."
                )
            break

    return sites, row_errors
