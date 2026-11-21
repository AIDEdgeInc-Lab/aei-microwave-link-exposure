"""Measure the edge runner's runtime and peak memory on this device. Prints one JSON object; records nothing anywhere else.

    python scripts/edge_resource_check.py                    # 200 links, 100 readings per site
    python scripts/edge_resource_check.py --links 2000 --readings 500

The load is SYNTHETIC (seeded random rain rates on a made-up chain of sites) and labelled as such in the output. It measures
this library's cost on this hardware; it says nothing about any real network. Copy the JSON into docs/EDGE.md as measured.
"""

from __future__ import annotations

import argparse
import io
import json
import platform
import random
import resource
import sys
import time
import tracemalloc

from aei_mw_exposure import MicrowaveLink, MicrowaveSite, Provenance, __version__
from aei_mw_exposure.edge import _jsonl_records, run


def _peak_rss_mib() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(peak / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)  # bytes on macOS, KiB on Linux


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--links", type=int, default=200)
    p.add_argument("--readings", type=int, default=100, help="readings per site")
    p.add_argument("--seed", type=int, default=7)
    args = p.parse_args()

    rss_before = _peak_rss_mib()
    rng = random.Random(args.seed)
    sites = [MicrowaveSite(id=f"S{i}", name=f"S{i}", latitude=45.0 + i * 0.01, longitude=-75.0,
                           provenance=Provenance.DEMO) for i in range(args.links + 1)]
    links = [MicrowaveLink(id=f"L{i}", site_a=sites[i], site_b=sites[i + 1], frequency_ghz=rng.choice([11, 18, 23, 38]),
                           polarization=rng.choice("HV"), fade_margin_db=rng.uniform(20, 40), provenance=Provenance.DEMO)
             for i in range(args.links)]
    lines = [json.dumps({"site_id": s.id, "timestamp": f"t{r}", "rain_rate_mm_h": round(rng.expovariate(0.2), 2)})
             for r in range(args.readings) for s in sites]
    telemetry = io.StringIO("\n".join(lines) + "\n")
    del lines

    out, err = io.StringIO(), io.StringIO()
    tracemalloc.start()
    t0 = time.perf_counter()
    summary = run(links, _jsonl_records(telemetry), out, err)
    elapsed = time.perf_counter() - t0
    _, traced_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print(json.dumps({
        "load": "synthetic",
        "library_version": __version__,
        "python": platform.python_version(),
        "machine": platform.machine(),
        "platform": platform.platform(),
        "links": args.links,
        "readings_per_site": args.readings,
        "observations": summary["observations"],
        "decisions": summary["decisions"],
        "rejected": summary["rejected"],
        "runtime_s": round(elapsed, 3),
        "observations_per_s": round(summary["observations"] / elapsed) if elapsed else None,
        "peak_python_alloc_mib_during_run": round(traced_peak / (1024 * 1024), 2),
        "peak_rss_mib_process": _peak_rss_mib(),
        "peak_rss_mib_before_run": rss_before,
        "note": "tracemalloc slows the run; runtime_s is an upper bound. RSS includes the interpreter and the synthetic input.",
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
