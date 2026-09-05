"""Where did this object's data actually come from?

Every infrastructure object in this library must be able to answer that
question honestly. A boolean "is this demo data" isn't expressive enough
once real public records enter the picture: a real tower's *location* is a
fact, the *distance* between two real towers is arithmetic on that fact,
and a *microwave link* between them is neither -- it's a claim public data
does not make. Five buckets, not two.
"""

from __future__ import annotations

from enum import Enum


class Provenance(str, Enum):
    """Subclasses ``str`` so it compares/serializes as a plain string
    (e.g. for JSON export) while still being a closed, typo-proof set."""

    REAL = "real"
    """Sourced directly from a cited public record (a government dataset,
    a live public API). Not modified beyond normalization into this
    library's types."""

    DERIVED = "derived"
    """Computed from REAL inputs using a stated method (e.g. haversine
    distance between two real coordinates, or an exposure calculation on
    a confirmed link). Traceable back to real inputs, but itself a
    calculation, not a record."""

    DEMO = "demo"
    """Synthetic / illustrative. Must never be presented as if it were a
    real record, however realistic the coordinates look."""

    NOT_AVAILABLE = "not_available"
    """The information would be needed here, but no public source
    establishes it. Used as a marker value, not attached to a fabricated
    object -- e.g. "confirmed microwave link topology: NOT_AVAILABLE" is a
    statement about missing data, not a link that exists with unknown
    properties."""

    USER_PROVIDED = "user_provided"
    """Asserted by the person using this tool (e.g. an uploaded site
    list), not independently verified against any public record. Distinct
    from REAL (that label is reserved for cited public sources) and from
    DEMO (a user's own infrastructure is presumably real, just unverified
    here -- never call it synthetic or illustrative)."""
