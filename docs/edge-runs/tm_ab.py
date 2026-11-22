"""Diagnostic only (not part of the package): time the edge runner on a synthetic 200x100 load, tracemalloc off vs on."""
import io, json, platform, random, sys, time, tracemalloc
from aei_mw_exposure import MicrowaveLink, MicrowaveSite, Provenance
from aei_mw_exposure.edge import _jsonl_records, run

class Discard:
    def write(self, t): return len(t)
    def flush(self): pass

rng = random.Random(7); n = 200; reads = 100
sites = [MicrowaveSite(id=f"S{i}", name=f"S{i}", latitude=45.0+i*0.01, longitude=-75.0, provenance=Provenance.DEMO) for i in range(n+1)]
links = [MicrowaveLink(id=f"L{i}", site_a=sites[i], site_b=sites[i+1], frequency_ghz=rng.choice([11,18,23,38]), polarization=rng.choice("HV"),
                       fade_margin_db=rng.uniform(20,40), provenance=Provenance.DEMO) for i in range(n)]
lines = "\n".join(json.dumps({"site_id": s.id, "timestamp": f"t{r}", "rain_rate_mm_h": round(rng.expovariate(0.2),2)}) for r in range(reads) for s in sites) + "\n"
def once(trace):
    if trace: tracemalloc.start()
    t0 = time.perf_counter(); run(links, _jsonl_records(io.StringIO(lines)), Discard(), Discard()); dt = time.perf_counter() - t0
    if trace: tracemalloc.stop()
    return dt
res = {}
for trace in (False, True, False, True):
    res.setdefault("tracemalloc_on" if trace else "tracemalloc_off", []).append(round(once(trace), 3))
print(json.dumps({"python": platform.python_version(), "compiler": platform.python_compiler(), "build": " ".join(platform.python_build()), **res}))
