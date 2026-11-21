"""Offline edge runner: link list + weather telemetry -> exposure decisions as JSON Lines.

Built for small ARM64 devices (e.g. an NVIDIA Jetson Orin Nano) that run without internet access:

* standard library only, and nothing here imports ``aei_mw_exposure.providers`` or any networking module;
* streaming: telemetry is read one line at a time, and memory grows with the number of sites and links, not with the input;
* every decision is the library's own ``calculate_exposure`` result, so it is identical to calling the API directly.

Usage::

    aei-mw-edge --links links.json telemetry.jsonl          # or telemetry.csv, or "-" for stdin
    python -m aei_mw_exposure.edge --links links.json -     # same, without the console script

``links.json``::

    {"links": [{"id": "L1", "frequency_ghz": 18, "polarization": "V", "fade_margin_db": 32,
                "site_a": {"id": "A", "latitude": 43.65, "longitude": -79.38},
                "site_b": {"id": "B", "latitude": 43.78, "longitude": -79.23}}]}

Telemetry, one observation per line (JSON Lines) or per row (CSV with a header)::

    {"site_id": "A", "timestamp": "2026-11-21T10:00Z", "rain_rate_mm_h": 12.5}
    site_id,timestamp,rain_rate_mm_h[,temperature_c,wind_speed_kmh]

Each accepted observation updates that site's latest reading. Every link with readings at both ends then gets one decision line
on stdout. A line that cannot be used (bad JSON, a NaN or negative rain rate, an unknown site, ...) is never turned into a
decision: it is reported on stderr as ``{"event": "rejected", "line": N, "reason": ...}``, and processing continues. The reason
is a fixed category, never the line's content, so stderr logs do not repeat site identifiers or raw values. A summary line goes
to stderr at the end.

Exit status: 0 when the input was processed (even with rejected lines; see the summary), 2 when the links file or the input
cannot be used at all.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from typing import IO, Dict, Iterator, List, Optional, Tuple

from .exposure import DEFAULT_HIGH_THRESHOLD, DEFAULT_MODERATE_THRESHOLD, LinkExposure, calculate_exposure
from .microwave import MicrowaveLink, MicrowaveSite
from .provenance import Provenance
from .weather import WeatherObservation

MAX_LINE_CHARS = 64 * 1024
MAX_LINKS_FILE_BYTES = 16 * 1024 * 1024
TELEMETRY_FIELDS = ("site_id", "timestamp", "rain_rate_mm_h")
OPTIONAL_FIELDS = ("temperature_c", "wind_speed_kmh")
SOURCE_EDGE = "edge-telemetry"


class ConfigError(ValueError):
    """The links file cannot be used. Nothing is processed."""


class _Rejected(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _reject_constant(token: str):
    raise ValueError(f"non-finite JSON number {token}")


def _loads(text: str):
    # json accepts NaN / Infinity / -Infinity by default; telemetry must never carry them as numbers.
    return json.loads(text, parse_constant=_reject_constant)


def _finite(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ConfigError(f"{name} must be a finite number")
    return float(value)


def _text_id(value, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ConfigError(f"{name} must be a non-empty string of at most 256 characters")
    return value


# --- links -----------------------------------------------------------------------------------------------------------------

def load_links(path: str) -> List[MicrowaveLink]:
    """Read and validate the links file. Raises ``ConfigError`` with the position of the first problem."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read(MAX_LINKS_FILE_BYTES + 1)
    except OSError as exc:
        raise ConfigError(f"cannot read links file: {exc.strerror or exc}") from None
    if len(raw) > MAX_LINKS_FILE_BYTES:
        raise ConfigError(f"links file is larger than {MAX_LINKS_FILE_BYTES} bytes")
    try:
        doc = _loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ConfigError(f"links file is not valid UTF-8 JSON: {exc}") from None
    if not isinstance(doc, dict) or not isinstance(doc.get("links"), list) or not doc["links"]:
        raise ConfigError('links file must be an object with a non-empty "links" list')

    sites: Dict[str, MicrowaveSite] = {}
    links: List[MicrowaveLink] = []
    link_ids = set()
    for i, item in enumerate(doc["links"]):
        where = f"links[{i}]"
        if not isinstance(item, dict):
            raise ConfigError(f"{where} must be an object")
        link_id = _text_id(item.get("id"), f"{where}.id")
        if link_id in link_ids:
            raise ConfigError(f"{where}.id is a duplicate")
        link_ids.add(link_id)
        ends = []
        for end in ("site_a", "site_b"):
            s = item.get(end)
            if not isinstance(s, dict):
                raise ConfigError(f"{where}.{end} must be an object")
            sid = _text_id(s.get("id"), f"{where}.{end}.id")
            lat = _finite(s.get("latitude"), f"{where}.{end}.latitude")
            lon = _finite(s.get("longitude"), f"{where}.{end}.longitude")
            known = sites.get(sid)
            if known is not None:
                if (known.latitude, known.longitude) != (lat, lon):
                    raise ConfigError(f"{where}.{end}: site id is reused with different coordinates")
                ends.append(known)
                continue
            try:
                site = MicrowaveSite(id=sid, name=str(s.get("name") or sid), latitude=lat, longitude=lon,
                                     provenance=Provenance.USER_PROVIDED)
            except ValueError:
                # Position only: the library's message repeats the coordinate at full precision.
                raise ConfigError(f"{where}.{end}: latitude must be within [-90, 90] and longitude within [-180, 180]") from None
            sites[sid] = site
            ends.append(site)
        try:
            links.append(MicrowaveLink(
                id=link_id, site_a=ends[0], site_b=ends[1],
                frequency_ghz=_finite(item.get("frequency_ghz"), f"{where}.frequency_ghz"),
                polarization=item.get("polarization"),
                fade_margin_db=_finite(item.get("fade_margin_db"), f"{where}.fade_margin_db"),
                provenance=Provenance.USER_PROVIDED,
            ))
        except ValueError as exc:
            raise ConfigError(f"{where}: {exc}") from None
    return links


# --- telemetry -------------------------------------------------------------------------------------------------------------

def _bounded_lines(stream: IO[str]) -> Iterator[Tuple[int, Optional[str]]]:
    """(line number, text) pairs; text is None for a line longer than MAX_LINE_CHARS, which is skipped without being held."""
    n = 0
    while True:
        chunk = stream.readline(MAX_LINE_CHARS + 1)
        if not chunk:
            return
        n += 1
        if len(chunk) > MAX_LINE_CHARS and not chunk.endswith("\n"):
            while True:  # drain the rest of the oversized line
                rest = stream.readline(MAX_LINE_CHARS)
                if not rest or rest.endswith("\n"):
                    break
            yield n, None
            continue
        yield n, chunk.rstrip("\r\n")


def _jsonl_records(stream: IO[str]) -> Iterator[Tuple[int, object]]:
    for n, text in _bounded_lines(stream):
        if text is None:
            yield n, _Rejected("line_too_long")
        elif not text.strip():
            continue
        else:
            try:
                yield n, _loads(text)
            except ValueError:
                yield n, _Rejected("invalid_json")


def _csv_records(stream: IO[str]) -> Iterator[Tuple[int, object]]:
    lines = _bounded_lines(stream)
    header = None
    for n, text in lines:
        if text is None:
            yield n, _Rejected("line_too_long")
            continue
        if not text.strip():
            continue
        try:
            row = next(csv.reader([text]))
        except csv.Error:
            yield n, _Rejected("invalid_csv")
            continue
        if header is None:
            header = [h.strip() for h in row]
            missing = [f for f in TELEMETRY_FIELDS if f not in header]
            if missing:
                raise ConfigError(f"CSV header is missing column(s): {', '.join(missing)}")
            continue
        if len(row) != len(header):
            yield n, _Rejected("wrong_column_count")
            continue
        rec = dict(zip(header, row))
        try:
            for f in ("rain_rate_mm_h",) + OPTIONAL_FIELDS:
                v = rec.get(f)
                if v is None or (f in OPTIONAL_FIELDS and v.strip() == ""):
                    rec.pop(f, None)
                else:
                    rec[f] = float(v)
        except ValueError:
            yield n, _Rejected("invalid_value")
            continue
        yield n, rec


def _observation(rec, sites: Dict[str, MicrowaveSite]) -> WeatherObservation:
    if not isinstance(rec, dict):
        raise _Rejected("not_an_object")
    if any(f not in rec for f in TELEMETRY_FIELDS):
        raise _Rejected("missing_field")
    site = sites.get(rec["site_id"]) if isinstance(rec["site_id"], str) else None
    if site is None:
        raise _Rejected("unknown_site")
    ts = rec["timestamp"]
    if not isinstance(ts, str) or not ts.strip() or len(ts) > 64:
        raise _Rejected("invalid_timestamp")
    extra = {f: rec[f] for f in OPTIONAL_FIELDS if rec.get(f) is not None}
    try:
        return WeatherObservation(latitude=site.latitude, longitude=site.longitude, timestamp=ts,
                                  rain_rate_mm_h=rec["rain_rate_mm_h"], source=SOURCE_EDGE, site_id=site.id, **extra)
    except (TypeError, ValueError):
        raise _Rejected("invalid_value") from None


# --- decisions -------------------------------------------------------------------------------------------------------------

def decision_record(result: LinkExposure, obs_a: WeatherObservation, obs_b: WeatherObservation) -> dict:
    """The JSON-ready decision for one link. Every number comes straight from ``calculate_exposure``."""
    flags = []
    if result.severity == "high":
        flags.append("high_exposure")
    elif result.severity == "moderate":
        flags.append("moderate_exposure")
    if obs_a.timestamp != obs_b.timestamp:
        flags.append("endpoint_timestamps_differ")
    return {
        "kind": "decision",
        "link_id": result.link.id,
        "severity": result.severity,
        "exposure_ratio": result.exposure_ratio,
        "predicted_attenuation_db": result.attenuation.predicted_attenuation_db,
        "fade_margin_db": result.link.fade_margin_db,
        "rain_rate_mm_h": result.rain_rate_mm_h,
        "rain_source_site_id": result.source_site_id,
        "observed_at": {result.link.site_a.id: obs_a.timestamp, result.link.site_b.id: obs_b.timestamp},
        "flags": flags,
    }


def run(links: List[MicrowaveLink], records: Iterator[Tuple[int, object]], out: IO[str], err: IO[str],
        moderate_threshold: float = DEFAULT_MODERATE_THRESHOLD, high_threshold: float = DEFAULT_HIGH_THRESHOLD,
        final_only: bool = False) -> dict:
    """Process telemetry records and write decisions. Returns the summary counts."""
    sites: Dict[str, MicrowaveSite] = {}
    links_by_site: Dict[str, List[MicrowaveLink]] = {}
    for link in links:
        for s in (link.site_a, link.site_b):
            sites[s.id] = s
            links_by_site.setdefault(s.id, []).append(link)
    latest: Dict[str, WeatherObservation] = {}
    last_decision: Dict[str, dict] = {}
    counts = {"observations": 0, "decisions": 0, "rejected": 0}

    def emit(stream: IO[str], obj: dict) -> None:
        stream.write(json.dumps(obj, allow_nan=False, separators=(",", ":")) + "\n")
        stream.flush()

    for n, rec in records:
        try:
            if isinstance(rec, _Rejected):
                raise rec
            obs = _observation(rec, sites)
        except _Rejected as rej:
            counts["rejected"] += 1
            emit(err, {"event": "rejected", "line": n, "reason": rej.reason})
            continue
        counts["observations"] += 1
        latest[obs.site_id] = obs
        for link in links_by_site[obs.site_id]:
            a, b = latest.get(link.site_a.id), latest.get(link.site_b.id)
            if a is None or b is None:
                continue
            result = calculate_exposure(link, {link.site_a.id: a, link.site_b.id: b},
                                        moderate_threshold=moderate_threshold, high_threshold=high_threshold)
            record = decision_record(result, a, b)
            if final_only:
                last_decision[link.id] = record
            else:
                counts["decisions"] += 1
                emit(out, record)
    if final_only:
        for link in links:
            if link.id in last_decision:
                counts["decisions"] += 1
                emit(out, last_decision[link.id])
    waiting = sum(1 for link in links if link.site_a.id not in latest or link.site_b.id not in latest)
    summary = dict(counts, links=len(links), links_without_both_readings=waiting)
    emit(err, dict({"event": "summary"}, **summary))
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="aei-mw-edge", description=__doc__.split("\n\n")[0])
    p.add_argument("telemetry", help='telemetry file (.jsonl/.json or .csv), or "-" for stdin')
    p.add_argument("--links", required=True, help="links JSON file")
    p.add_argument("--format", choices=("jsonl", "csv"), help="telemetry format (default: from the file extension, jsonl for stdin)")
    p.add_argument("--moderate-threshold", type=float, default=DEFAULT_MODERATE_THRESHOLD)
    p.add_argument("--high-threshold", type=float, default=DEFAULT_HIGH_THRESHOLD)
    p.add_argument("--final", action="store_true", help="write only the last decision per link, after the whole input")
    args = p.parse_args(argv)

    for name in ("moderate_threshold", "high_threshold"):
        v = getattr(args, name)
        if not math.isfinite(v) or v < 0:
            print(f"aei-mw-edge: --{name.replace('_', '-')} must be a finite, non-negative number", file=sys.stderr)
            return 2
    if args.moderate_threshold > args.high_threshold:
        print("aei-mw-edge: --moderate-threshold must not exceed --high-threshold", file=sys.stderr)
        return 2

    fmt = args.format or ("csv" if args.telemetry.lower().endswith(".csv") else "jsonl")
    try:
        links = load_links(args.links)
        if args.telemetry == "-":
            stream, close = sys.stdin, False
        else:
            stream, close = open(args.telemetry, "r", encoding="utf-8", errors="replace", newline=""), True
        try:
            records = _csv_records(stream) if fmt == "csv" else _jsonl_records(stream)
            run(links, records, sys.stdout, sys.stderr, args.moderate_threshold, args.high_threshold, args.final)
        finally:
            if close:
                stream.close()
    except ConfigError as exc:
        print(f"aei-mw-edge: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"aei-mw-edge: cannot read telemetry: {exc.strerror or exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
