"""Rain attenuation for terrestrial microwave links.

Method: ITU-R P.838-3 ("Specific attenuation model for rain for use in
prediction methods") for the specific attenuation gamma_R = k * R^alpha,
combined with the ITU-R P.530 effective-path-length factor for terrestrial
line-of-sight links.

WHAT THIS IS
------------
A physics-based ESTIMATE of how much a given rain rate would attenuate a
given microwave hop, given its length, frequency and polarization. It is
standard, published, and independent of any vendor or operator data.

WHAT THIS IS NOT
-----------------
- Not an outage predictor. Whether a link actually drops depends on its
  real fade margin, hardware, and factors this model does not see
  (multipath, interference, hardware faults, transmit-power control state,
  ...). None of that is modelled here.
- Not a real-time storm-cell model. A real rain cell has spatial structure;
  this treats the rain rate at the link's location as uniform along the
  path, then shrinks the path with the P.530 distance factor to partially
  correct for that. That correction is itself a long-term statistical-
  design approximation being reused here for an instantaneous rain rate --
  a simplification, stated once, here, rather than hidden.

Coefficients: the constants of Tables 1-4 of Recommendation ITU-R P.838-3 and its
equations (2)-(5), evaluated directly (no lookup table, no interpolation). From
0.2.0 on; releases up to 0.1.5 used a transcribed table that did not match the
Recommendation for most frequencies (see CHANGELOG).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

Polarization = Literal["H", "V"]

# BEGIN GENERATED P838 CONSTANTS (scripts/gen_p838_constants.py in the Velorona Map repo; do not edit by hand)
# Recommendation ITU-R P.838-3 (03/2005), English edition, Tables 1-4: https://www.itu.int/dms_pubrec/itu-r/rec/p/R-REC-P.838-3-200503-I!!PDF-E.pdf (retrieved 2026-10-09T01:30:36Z, pdf sha256 3ab7482993e51fc63c5127a72e9e8930614e73652ac614882760817e7c1469cb)
# name -> (a_j, b_j, c_j, m, c). log10 k (kH, kV) uses 4 terms, alpha (aH, aV) uses 5: Recommendation eq. (2) and (3).
_P838_CONSTANTS = {
    "kH": ((-5.3398, -0.35351, -0.23789, -0.94158), (-0.10008, 1.2697, 0.86036, 0.64552), (1.13098, 0.454, 0.15354, 0.16817), -0.18961, 0.71147),
    "kV": ((-3.80595, -3.44965, -0.39902, 0.50167), (0.56934, -0.22911, 0.73042, 1.07319), (0.81061, 0.51059, 0.11899, 0.27195), -0.16398, 0.63297),
    "alphaH": ((-0.14318, 0.29591, 0.32177, -5.3761, 16.1721), (1.82442, 0.77564, 0.63773, -0.9623, -3.2998), (-0.55187, 0.19822, 0.13164, 1.47828, 3.4399), 0.67849, -1.95537),
    "alphaV": ((-0.07771, 0.56727, -0.20238, -48.2991, 48.5833), (2.3384, 0.95545, 1.1452, 0.791669, 0.791459), (-0.76284, 0.54039, 0.26809, 0.116226, 0.116479), -0.053739, 0.83433),
}
# END GENERATED P838 CONSTANTS

# Range this library accepts. The Recommendation itself is defined for 1-1000 GHz; the 1-100 GHz limit is the library's existing, narrower scope and is unchanged.
MIN_FREQ_GHZ = 1.0
MAX_FREQ_GHZ = 100.0


def _p838_term(name: str, log_f: float) -> float:
    a, b, c, m, c0 = _P838_CONSTANTS[name]
    return sum(aj * math.exp(-(((log_f - bj) / cj) ** 2)) for aj, bj, cj in zip(a, b, c)) + m * log_f + c0


def rain_coefficients(freq_ghz: float, polarization: Polarization = "V") -> tuple[float, float]:
    """(k, alpha) from the Recommendation's equations (2) and (3) -- a continuous function of frequency, no table and no interpolation.

    Terrestrial link: path elevation theta = 0 and polarization tilt tau = 0 (H) or 90 degrees (V), so equations (4) and (5) reduce to
    k = kH / kV and alpha = alphaH / alphaV (cos^2(theta) = 1, cos(2 tau) = +1 / -1).

    Raises ``ValueError`` outside the supported 1-100 GHz range rather than extrapolating.
    """
    if not (MIN_FREQ_GHZ <= freq_ghz <= MAX_FREQ_GHZ):
        raise ValueError(
            f"freq_ghz={freq_ghz} outside supported range [{MIN_FREQ_GHZ}, {MAX_FREQ_GHZ}] GHz"
        )
    log_f = math.log10(freq_ghz)
    suffix = "V" if polarization == "V" else "H"
    k = 10 ** _p838_term("k" + suffix, log_f)
    alpha = _p838_term("alpha" + suffix, log_f)
    return float(k), float(alpha)


def specific_attenuation_db_km(
    rain_rate_mm_h: float, freq_ghz: float, polarization: Polarization = "V"
) -> float:
    """gamma_R = k * R^alpha  [dB/km]  (ITU-R P.838-3)."""
    if rain_rate_mm_h <= 0:
        return 0.0
    k, alpha = rain_coefficients(freq_ghz, polarization)
    return k * (rain_rate_mm_h**alpha)


def effective_path_length_km(path_length_km: float, rain_rate_mm_h: float) -> float:
    """P.530 distance factor: d_eff = d / (1 + d/d0), d0 = 35*exp(-0.015*R).

    Rain cells are smaller than long hops; this shrinks the effective wet
    path so long hops aren't systematically over-penalized. Rain rate is
    capped at 100 mm/h, matching the Recommendation's exponent domain.
    """
    if path_length_km <= 0:
        return 0.0
    r = min(rain_rate_mm_h, 100.0)
    d0 = 35.0 * math.exp(-0.015 * r)
    return path_length_km / (1.0 + path_length_km / d0)


@dataclass(frozen=True)
class AttenuationEstimate:
    """Every quantity that went into the final number -- nothing hidden."""

    rain_rate_mm_h: float
    freq_ghz: float
    polarization: Polarization
    path_length_km: float
    k: float
    alpha: float
    specific_attenuation_db_km: float
    effective_path_length_km: float
    predicted_attenuation_db: float
    method: str
    assumption: str


def estimate_rain_attenuation(
    path_length_km: float,
    rain_rate_mm_h: float,
    freq_ghz: float,
    polarization: Polarization = "V",
) -> AttenuationEstimate:
    """Full transparent estimate: input -> formula -> output -> assumption."""
    if path_length_km < 0:
        raise ValueError(f"path_length_km cannot be negative: {path_length_km}")
    if rain_rate_mm_h < 0:
        raise ValueError(f"rain_rate_mm_h cannot be negative: {rain_rate_mm_h}")

    k, alpha = rain_coefficients(freq_ghz, polarization) if rain_rate_mm_h > 0 else (0.0, 0.0)
    gamma = specific_attenuation_db_km(rain_rate_mm_h, freq_ghz, polarization)
    d_eff = effective_path_length_km(path_length_km, rain_rate_mm_h)
    attenuation = gamma * d_eff

    return AttenuationEstimate(
        rain_rate_mm_h=rain_rate_mm_h,
        freq_ghz=freq_ghz,
        polarization=polarization,
        path_length_km=path_length_km,
        k=round(k, 6),
        alpha=round(alpha, 4),
        specific_attenuation_db_km=round(gamma, 4),
        effective_path_length_km=round(d_eff, 2),
        predicted_attenuation_db=round(attenuation, 2),
        method="ITU-R P.838-3 specific attenuation x ITU-R P.530 effective path length",
        assumption=(
            # freq_ghz is reproduced exactly, not rounded: it is the caller's
            # own input, and this string is quoted verbatim as the method
            # disclosure by downstream evidence exports. At :.0f a 7.25 GHz
            # input read back as "7 GHz", contradicting the same value shown
            # elsewhere in the same record. !r is shortest round-trip, so it
            # cannot truncate the way a %g six-significant-figure format can.
            f"gamma_R = k*R^alpha at R={rain_rate_mm_h:.1f} mm/h, {freq_ghz!r} GHz, "
            f"{polarization} pol (k={k:.6g}, alpha={alpha:.4g}) -> {gamma:.4f} dB/km. "
            f"d_eff = {path_length_km:.1f} km / (1 + {path_length_km:.1f}/d0) = {d_eff:.2f} km "
            f"(rain assumed uniform along the effective path, not the full "
            f"geometric path; instantaneous rain rate used with a long-term "
            f"design-rule distance factor -- a stated simplification, not a "
            f"validated instantaneous model)."
        ),
    )
