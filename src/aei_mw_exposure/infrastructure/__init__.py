"""Real public infrastructure data -> normalized ``MicrowaveSite`` objects.

Every module here follows the same shape: a pure ``parse_*`` function that
turns one raw government record into a ``MicrowaveSite`` (testable with a
fixture, no network), and a ``fetch_*`` function that gets those raw
records from the live public service (isolated behind a local ``requests``
import so the parser is usable without that dependency).

**These adapters only ever produce sites, never links.** No public
Canadian source used here establishes which real site talks to which --
see each module's docstring for exactly what its source does and does not
confirm. Inferring a link from proximity, azimuth, or frequency is
deliberately not implemented here; do not add it.
"""
