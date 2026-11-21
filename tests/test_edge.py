"""Edge runner: parity with calculate_exposure, refusal of bad telemetry, offline operation."""

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from aei_mw_exposure import WeatherObservation, calculate_exposure
from aei_mw_exposure.edge import ConfigError, _csv_records, _jsonl_records, load_links, main, run, MAX_LINE_CHARS

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "edge"
LINKS = str(EXAMPLES / "links.json")


def _run(text, fmt="jsonl", **kw):
    out, err = io.StringIO(), io.StringIO()
    reader = _csv_records if fmt == "csv" else _jsonl_records
    summary = run(load_links(LINKS), reader(io.StringIO(text)), out, err, **kw)
    decisions = [json.loads(line) for line in out.getvalue().splitlines()]
    events = [json.loads(line) for line in err.getvalue().splitlines()]
    return decisions, events, summary


def _obs(site, ts, rain):
    return json.dumps({"site_id": site, "timestamp": ts, "rain_rate_mm_h": rain}) + "\n"


def test_decisions_match_library_api_exactly():
    decisions, _, _ = _run(_obs("DEMO-A", "t1", 30.0) + _obs("DEMO-B", "t1", 7.5))
    assert len(decisions) == 1
    link = next(l for l in load_links(LINKS) if l.id == "DEMO-L1")
    ref = calculate_exposure(link, {
        "DEMO-A": WeatherObservation(latitude=43.65, longitude=-79.38, timestamp="t1", rain_rate_mm_h=30.0, source="x"),
        "DEMO-B": WeatherObservation(latitude=43.78, longitude=-79.23, timestamp="t1", rain_rate_mm_h=7.5, source="x"),
    })
    d = decisions[0]
    assert (d["severity"], d["exposure_ratio"], d["predicted_attenuation_db"], d["rain_source_site_id"]) == (
        ref.severity, ref.exposure_ratio, ref.attenuation.predicted_attenuation_db, ref.source_site_id)


def test_no_decision_until_both_ends_have_a_reading():
    decisions, events, summary = _run(_obs("DEMO-A", "t1", 5.0))
    assert decisions == []
    assert summary["links_without_both_readings"] == 2


@pytest.mark.parametrize("line,reason", [
    ('{"site_id": "DEMO-A", "timestamp": "t", "rain_rate_mm_h": NaN}', "invalid_json"),
    ('{"site_id": "DEMO-A", "timestamp": "t", "rain_rate_mm_h": Infinity}', "invalid_json"),
    ('{"site_id": "DEMO-A", "timestamp": "t", "rain_rate_mm_h": -1}', "invalid_value"),
    ('{"site_id": "DEMO-A", "timestamp": "t", "rain_rate_mm_h": true}', "invalid_value"),
    ('{"site_id": "DEMO-A", "timestamp": "t", "rain_rate_mm_h": "12"}', "invalid_value"),
    ('{"site_id": "DEMO-A", "timestamp": "t"}', "missing_field"),
    ('{"site_id": "SECRET-SITE", "timestamp": "t", "rain_rate_mm_h": 1}', "unknown_site"),
    ('[1, 2]', "not_an_object"),
    ('not json', "invalid_json"),
])
def test_bad_telemetry_is_rejected_never_scored(line, reason):
    good = _obs("DEMO-B", "t", 1.0)
    decisions, events, summary = _run(good + line + "\n")
    assert decisions == []  # the bad DEMO-A line must not complete DEMO-L1
    assert {"event": "rejected", "line": 2, "reason": reason} in events
    assert "SECRET-SITE" not in json.dumps(events)  # stderr never echoes raw identifiers or values
    assert summary["rejected"] == 1


def test_oversized_line_is_skipped_and_processing_continues():
    text = "x" * (MAX_LINE_CHARS + 10) + "\n" + _obs("DEMO-A", "t", 1.0) + _obs("DEMO-B", "t", 1.0)
    decisions, events, _ = _run(text)
    assert events[0] == {"event": "rejected", "line": 1, "reason": "line_too_long"}
    assert [d["link_id"] for d in decisions] == ["DEMO-L1"]  # DEMO-L2 still waits for a DEMO-C reading


def test_csv_and_jsonl_give_the_same_decisions():
    csv_text = (EXAMPLES / "telemetry.csv").read_text()
    jsonl_text = "".join(_obs(*row.split(",")[:2], float(row.split(",")[2])) for row in csv_text.splitlines()[1:])
    assert _run(csv_text, fmt="csv")[0] == _run(jsonl_text)[0]


def test_csv_nan_is_rejected():
    decisions, events, _ = _run("site_id,timestamp,rain_rate_mm_h\nDEMO-A,t,nan\nDEMO-B,t,1\n", fmt="csv")
    assert decisions == [] and events[0]["reason"] == "invalid_value"


def test_final_only_writes_last_decision_per_link():
    text = _obs("DEMO-A", "t1", 1.0) + _obs("DEMO-B", "t1", 1.0) + _obs("DEMO-A", "t2", 60.0)
    decisions, _, _ = _run(text, final_only=True)
    assert [d["link_id"] for d in decisions] == ["DEMO-L1"]
    assert decisions[0]["severity"] == "high" and "endpoint_timestamps_differ" in decisions[0]["flags"]


@pytest.mark.parametrize("doc,msg", [
    ({}, "non-empty"),
    ({"links": [{"id": "L"}]}, "site_a"),
    ({"links": [{"id": "L", "frequency_ghz": float("nan"), "polarization": "V", "fade_margin_db": 1,
                 "site_a": {"id": "A", "latitude": 0, "longitude": 0},
                 "site_b": {"id": "B", "latitude": 0.1, "longitude": 0}}]}, "non-finite"),
    ({"links": [{"id": "L", "frequency_ghz": 18, "polarization": "X", "fade_margin_db": 1,
                 "site_a": {"id": "A", "latitude": 0, "longitude": 0},
                 "site_b": {"id": "B", "latitude": 0.1, "longitude": 0}}]}, "polarization"),
    ({"links": [{"id": "L", "frequency_ghz": 18, "polarization": "V", "fade_margin_db": 1,
                 "site_a": {"id": "A", "latitude": 95, "longitude": 0},
                 "site_b": {"id": "B", "latitude": 0.1, "longitude": 0}}]}, "latitude"),
])
def test_bad_links_file_is_refused(tmp_path, doc, msg):
    p = tmp_path / "links.json"
    p.write_text(json.dumps(doc))  # json.dumps writes NaN, which load_links must refuse
    with pytest.raises(ConfigError, match=msg):
        load_links(str(p))


def test_links_error_never_repeats_a_full_precision_coordinate(tmp_path):
    p = tmp_path / "links.json"
    p.write_text(json.dumps({"links": [{"id": "L", "frequency_ghz": 18, "polarization": "V", "fade_margin_db": 1,
                                        "site_a": {"id": "A", "latitude": 95.1234567, "longitude": -79.3832111},
                                        "site_b": {"id": "B", "latitude": 0.1, "longitude": 0}}]}))
    with pytest.raises(ConfigError) as info:
        load_links(str(p))
    assert "links[0].site_a" in str(info.value)
    assert "95.1234567" not in str(info.value) and "79.3832111" not in str(info.value)


def test_main_exit_codes(tmp_path, capsys):
    assert main(["--links", LINKS, str(EXAMPLES / "telemetry.jsonl")]) == 0
    assert main(["--links", str(tmp_path / "missing.json"), str(EXAMPLES / "telemetry.jsonl")]) == 2
    assert main(["--links", LINKS, "--moderate-threshold", "0.9", "--high-threshold", "0.5", "-"]) == 2


def test_edge_import_pulls_in_no_networking(tmp_path):
    code = ("import sys, aei_mw_exposure.edge; "
            "bad = [m for m in sys.modules if m.split('.')[0] in ('socket', 'ssl', 'http', 'urllib', 'urllib3', 'requests') "
            "or m.startswith('aei_mw_exposure.providers') or m.startswith('aei_mw_exposure.infrastructure')]; "
            "print(bad); sys.exit(1 if bad else 0)")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_cli_runs_with_network_blocked(tmp_path):
    # Any attempt to open a socket during the run fails the test.
    code = ("import socket, sys\n"
            "def _no(*a, **k): raise RuntimeError('network used')\n"
            "socket.socket = _no; socket.create_connection = _no; socket.getaddrinfo = _no\n"
            "from aei_mw_exposure.edge import main\n"
            f"sys.exit(main(['--links', {LINKS!r}, {str(EXAMPLES / 'telemetry.jsonl')!r}]))\n")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert '"kind":"decision"' in r.stdout
