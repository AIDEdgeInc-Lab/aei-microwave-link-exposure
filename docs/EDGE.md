# Running on edge devices

`aei-mw-edge` runs the library's exposure calculation next to the radios, with no internet connection. Every decision it writes is
exactly what `calculate_exposure` returns for the same inputs.

## Target

| | |
|---|---|
| Hardware | ARM64, e.g. NVIDIA Jetson Orin Nano class (any CPU works: the wheel is pure Python, `py3-none-any`) |
| Python | 3.10 or newer (JetPack 6 / Ubuntu 22.04 ships 3.10; JetPack 5 ships 3.8, which is not supported) |
| Dependencies | none (standard library only) |
| Network | none at runtime; `aei_mw_exposure.edge` imports no networking module, and the tests run it with sockets disabled |
| Memory | grows with the number of sites and links, not the length of the telemetry stream |

## Install (offline)

On a machine with internet access:

```bash
pip download "aei-microwave-link-exposure[edge]" --no-deps -d wheels/
sha256sum wheels/*.whl          # compare with the SHA256SUMS published with the release
```

Copy `wheels/` to the device, then:

```bash
pip install --no-index --find-links wheels/ "aei-microwave-link-exposure[edge]"
```

## Inputs

**Links** (`--links links.json`): an object with a non-empty `links` list. Each link has `id`, `frequency_ghz`, `polarization`
(`"H"` or `"V"`), `fade_margin_db`, and `site_a` / `site_b` objects with `id`, `latitude` and `longitude`. A site id that appears in
several links must have the same coordinates each time. Links and sites are recorded as `user_provided`. The file is refused as a
whole (exit 2) if anything in it is missing, non-finite or out of range; the message gives the position (`links[3].site_b.latitude`).

**Telemetry**: a file or `-` for stdin. JSON Lines by default, CSV when the name ends in `.csv` or with `--format csv`.

```json
{"site_id": "A", "timestamp": "2026-11-21T10:00Z", "rain_rate_mm_h": 12.5, "temperature_c": 4.0}
```

`site_id`, `timestamp` and `rain_rate_mm_h` are required; `temperature_c` and `wind_speed_kmh` are optional. The rain rate must be a
JSON number (not a string), finite and not negative.

## Output

stdout, one JSON object per line. Each accepted observation produces a decision for every link that now has a reading at both ends
(with `--final`, only the last decision per link, after the whole input):

```json
{"kind":"decision","link_id":"L1","severity":"high","exposure_ratio":1.002,"predicted_attenuation_db":32.05,
 "fade_margin_db":32.0,"rain_rate_mm_h":45.0,"rain_source_site_id":"A",
 "observed_at":{"A":"2026-11-21T10:05Z","B":"2026-11-21T10:00Z"},"flags":["high_exposure","endpoint_timestamps_differ"]}
```

Flags: `high_exposure`, `moderate_exposure`, and `endpoint_timestamps_differ` (the two ends' latest readings are not from the same
time, so one of them may be older).

stderr, one JSON object per line:

- `{"event":"rejected","line":N,"reason":R}` for a line that was not used. `R` is one of `invalid_json` (including `NaN` and
  `Infinity`), `invalid_csv`, `not_an_object`, `missing_field`, `unknown_site`, `invalid_timestamp`, `invalid_value`,
  `wrong_column_count`, `line_too_long` (over 64 KiB). A rejected reading never updates a site and never produces a decision. The
  line's content is not repeated, so logs carry no raw identifiers or values.
- `{"event":"summary",...}` at the end: observations, decisions, rejected, links, and links still waiting for both readings.

Exit status: 0 when the input was processed (check `rejected` in the summary), 2 when the links file, the CSV header, the thresholds
or the input file cannot be used.

## Resource check on the device

```bash
python scripts/edge_resource_check.py                       # 200 links, 100 readings per site
python scripts/edge_resource_check.py --links 2000 --readings 500
python -m pytest tests/test_edge.py                         # smoke test, needs pytest
```

The script uses a synthetic, seeded load and prints runtime, peak Python allocation and peak process RSS as JSON.

## Measured results

Only values produced by `scripts/edge_resource_check.py` on the device. Raw output: [edge-runs/jetson-2026-11-22.txt](edge-runs/jetson-2026-11-22.txt).

**Run of 2026-11-22: the runbook's install step failed on this board.** The board is L4T R35.5 (JetPack 5) with Python 3.8.10.
`python3 -m venv` fails (no `ensurepip`), and `pip install` refuses the package (`requires a different Python: 3.8.10 not in
'>=3.10'`). The numbers below come from the runbook's fallback (unpacked wheel on `PYTHONPATH`) on Python 3.8.10, which this
package does **not** support. They describe this code on this hardware, not a supported installation. The pytest smoke test could
not run (pytest 9 needs Python 3.10).

| Device | JetPack / Python | Links × readings | Runtime (s) | Peak alloc (MiB) | Peak RSS (MiB) | Date | Script |
|---|---|---|---|---|---|---|---|
| Jetson Orin Nano class, 7.4 GiB | L4T R35.5 (JetPack 5) / 3.8.10 (unsupported, fallback) | 200 × 100 | 6.845 | 0.12 | 20.8 | 2026-11-22 | `f151ad1` |
| Jetson Orin Nano class, 7.4 GiB | L4T R35.5 (JetPack 5) / 3.8.10 (unsupported, fallback) | 2000 × 500 | 344.994 | 0.92 | 456.0 | 2026-11-22 | `f151ad1` |

The same runs with the first version of the script (which kept every decision line in an in-memory buffer, so its peak alloc
measures that buffer, not the runner): 200 × 100: 7.1 s, 12.15 MiB alloc, 33.6 MiB RSS; 2000 × 500: 368.243 s, 513.29 MiB alloc,
788.4 MiB RSS. Peak RSS in every row includes the synthetic input, which the script builds in memory before the run.

Still TODO: a run on a supported install (JetPack 6, or any Python 3.10+ on the device).
