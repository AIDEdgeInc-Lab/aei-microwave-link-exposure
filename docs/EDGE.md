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

None yet. Fill this table only with output from `scripts/edge_resource_check.py` run on the device.

| Device | JetPack / Python | Links × readings | Runtime (s) | Peak alloc (MiB) | Peak RSS (MiB) | Date |
|---|---|---|---|---|---|---|
| Jetson Orin Nano | TODO | 200 × 100 | TODO | TODO | TODO | TODO |
| Jetson Orin Nano | TODO | 2000 × 500 | TODO | TODO | TODO | TODO |
