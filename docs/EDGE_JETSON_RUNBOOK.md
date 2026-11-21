# Jetson runbook: aei-microwave-link-exposure 0.3.1 edge check

Copy-paste steps to install 0.3.1 from the local wheel on an NVIDIA Jetson Orin Nano (ARM64), run `aei-mw-edge` offline on the
bundled sample data, measure it, and record the numbers. About 15 minutes. No `sudo` is needed on the Jetson.

Run blocks marked **Mac** on the Mac that holds the release candidate and blocks marked **Jetson** on the device.

## 1. Build the bundle (Mac)

```bash
B=~/velorona-edge-bundle-0.3.1
R=~/velorona-repos/_hardening/aei-microwave-link-exposure
rm -rf "$B" && mkdir -p "$B/wheels" "$B/examples" "$B/tests" "$B/scripts"
cp ~/velorona-repos/_hardening/release-candidates/aei-microwave-link-exposure-0.3.1/* "$B/wheels/"
cp -R "$R/examples/edge" "$B/examples/"
cp "$R/tests/test_edge.py" "$B/tests/"
cp "$R/scripts/edge_resource_check.py" "$B/scripts/"
# Optional, for the smoke test: pytest and its dependencies as pure-Python wheels for Python 3.10
# (exceptiongroup and tomli are named because pip resolves markers for the Mac's Python, not 3.10)
python3.11 -m pip download pytest exceptiongroup tomli --only-binary=:all: --python-version 3.10 --platform manylinux2014_aarch64 -d "$B/wheels"
ls -R "$B"
```

The bundle must keep this layout: `tests/test_edge.py` finds the sample data at `../examples/edge/`.

```
velorona-edge-bundle-0.3.1/
  wheels/      aei_microwave_link_exposure-0.3.1-py3-none-any.whl, .tar.gz, SHA256SUMS (+ pytest wheels)
  examples/edge/  links.json, telemetry.jsonl, telemetry.csv
  tests/       test_edge.py
  scripts/     edge_resource_check.py
```

Copy it to the Jetson (replace the address), e.g.:

```bash
scp -r ~/velorona-edge-bundle-0.3.1 <user>@<jetson-ip>:~/
```

## 2. Check the device and the files (Jetson)

```bash
cd ~/velorona-edge-bundle-0.3.1
uname -m                                   # expect: aarch64
cat /etc/nv_tegra_release                  # JetPack / L4T release, for the results table
python3 --version                          # needs 3.10 or newer (see failure point 1)
(cd wheels && sha256sum -c SHA256SUMS)     # expect: both files "OK"
```

## 3. Go offline (Jetson)

Unplug Ethernet and turn Wi-Fi off from the desktop menu. Confirm there is no route out:

```bash
python3 -c "import urllib.request; urllib.request.urlopen('https://pypi.org', timeout=3)" && echo "STILL ONLINE" || echo "offline: OK"
```

Every remaining step runs offline.

## 4. Install from the local wheel (Jetson)

```bash
cd ~/velorona-edge-bundle-0.3.1
python3 -m venv ~/venv-velorona-edge
. ~/venv-velorona-edge/bin/activate
pip install --no-index --find-links wheels "aei-microwave-link-exposure[edge]==0.3.1"
pip install --no-index --find-links wheels pytest            # optional, only if you bundled pytest
python -c "import aei_mw_exposure as m; print(m.__version__)"   # expect: 0.3.1
pip list                                                      # expect: no requests / urllib3 / numpy pulled in
```

## 5. Run the edge command on the sample data (Jetson)

```bash
cd ~/velorona-edge-bundle-0.3.1
aei-mw-edge --links examples/edge/links.json examples/edge/telemetry.jsonl > decisions.jsonl 2> events.jsonl; echo "exit=$?"
cat decisions.jsonl events.jsonl
aei-mw-edge --links examples/edge/links.json --final examples/edge/telemetry.csv
```

**Expected format.** `exit=0`. Each line of `decisions.jsonl` is one JSON object:

```
{"kind":"decision","link_id":<str>,"severity":"low"|"moderate"|"high","exposure_ratio":<number>,
 "predicted_attenuation_db":<number>,"fade_margin_db":<number>,"rain_rate_mm_h":<number>,"rain_source_site_id":<str>,
 "observed_at":{<site_id>:<timestamp>,<site_id>:<timestamp>},"flags":[<str>...]}
```

`events.jsonl` holds `{"event":"rejected","line":<n>,"reason":<code>}` lines and ends with one
`{"event":"summary","observations":<n>,"decisions":<n>,"rejected":<n>,"links":<n>,"links_without_both_readings":<n>}`.

The sample is fixed, so the counts are too. On the Mac, the same files give 3 decisions and 1 rejected line (line 5, a `NaN`,
reason `invalid_json`) for the JSONL file, and 2 decisions with `--final` for the CSV. Different counts on the Jetson mean
something is wrong: stop and send both files.

## 6. Smoke test (Jetson, optional, needs pytest)

```bash
cd ~/velorona-edge-bundle-0.3.1
python -m pytest -q tests/test_edge.py        # expect: "24 passed"
```

## 7. Resource check (Jetson)

```bash
cd ~/velorona-edge-bundle-0.3.1
python scripts/edge_resource_check.py | tee rc-200x100.json
python scripts/edge_resource_check.py --links 2000 --readings 500 | tee rc-2000x500.json
```

**Expected format** (one JSON object; values depend on the device):

```
{"load":"synthetic","library_version":"0.3.1","python":<str>,"machine":"aarch64","platform":<str>,
 "links":<n>,"readings_per_site":<n>,"observations":<n>,"decisions":<n>,"rejected":0,
 "runtime_s":<number>,"observations_per_s":<number>,"peak_python_alloc_mib_during_run":<number>,
 "peak_rss_mib_process":<number>,"peak_rss_mib_before_run":<number>,"note":<str>}
```

`"rejected"` must be 0 and `"machine"` must be `aarch64`. Otherwise the run does not count.

## 8. Record the numbers

Copy the two JSON files back (`scp <user>@<jetson-ip>:~/velorona-edge-bundle-0.3.1/rc-*.json .`). Then fill the
**Measured results** table at the end of `docs/EDGE.md` on branch `chore/lib-hardening-edge`:

| Table column | Take it from |
|---|---|
| Device | "Jetson Orin Nano" (+ RAM size, e.g. 8 GB) |
| JetPack / Python | `/etc/nv_tegra_release` (step 2) / `"python"` |
| Links × readings | `"links"` × `"readings_per_site"` |
| Runtime (s) | `"runtime_s"` |
| Peak alloc (MiB) | `"peak_python_alloc_mib_during_run"` |
| Peak RSS (MiB) | `"peak_rss_mib_process"` |
| Date | the day you ran it |

Commit the two JSON files next to it (e.g. `docs/edge-results/`) so the table can be checked against the raw output.

## Most likely failure points

1. **Python older than 3.10.** `pip install` says `requires a different Python: 3.8.x not in '>=3.10'`. JetPack 5 (L4T R35)
   ships Python 3.8; JetPack 6 (L4T R36) ships 3.10. Fix: use a JetPack 6 image. If `python3 -m venv` fails with "ensurepip is
   not available" (the `python3.10-venv` package is missing and cannot be installed offline), skip the venv and run from the
   unpacked wheel. This needs no pip, since the wheel is a zip of pure Python:
   ```bash
   python3 -m zipfile -e wheels/aei_microwave_link_exposure-0.3.1-py3-none-any.whl ~/edge-site
   PYTHONPATH=~/edge-site python3 -m aei_mw_exposure.edge --links examples/edge/links.json examples/edge/telemetry.jsonl
   PYTHONPATH=~/edge-site python3 scripts/edge_resource_check.py
   ```
2. **"No matching distribution" / "missing wheel for ARM".** The package wheel is `py3-none-any`, so it is not tied to any CPU
   and has no compiled parts. This error means pip is looking for something that is not in `wheels/`. Usually that is pytest or
   one of its dependencies (bundle them in step 1, or skip step 6), or a version typo in the install command. Check with
   `ls wheels/`. Do not drop `--no-index`: the device is offline on purpose.
3. **File permissions.** `Permission denied` on `scripts/...` or `aei-mw-edge`: run scripts with `python scripts/...` rather than
   executing them, and check `ls -l`. If the bundle was copied to a USB stick or SD card mounted `noexec`, or as another user,
   copy it into your home folder: `cp -r /media/<user>/<stick>/velorona-edge-bundle-0.3.1 ~/ && cd ~/velorona-edge-bundle-0.3.1`.
   Never use `sudo pip`; the venv (or `PYTHONPATH`) needs no root.
