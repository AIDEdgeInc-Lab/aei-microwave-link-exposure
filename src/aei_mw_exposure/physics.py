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

Table source: ITU-R P.838-3 regression coefficients, transcribed from the
published recommendation. Re-verify against the official text before this
number is used for anything beyond an illustrative estimate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

Polarization = Literal["H", "V"]

# freq_ghz -> (k_H, alpha_H, k_V, alpha_V)
_P838_TABLE: dict[float, tuple[float, float, float, float]] = {
    1.0: (0.0000259, 0.9691, 0.0000308, 0.8592),
    2.0: (0.0000847, 1.0664, 0.0000998, 0.9490),
    4.0: (0.0001071, 1.6009, 0.0002461, 1.2476),
    6.0: (0.0001750, 1.5900, 0.0001425, 1.4745),
    7.0: (0.0003010, 1.5900, 0.0002277, 1.5037),
    8.0: (0.0004540, 1.5617, 0.0003380, 1.5213),
    10.0: (0.0010100, 1.2760, 0.0008870, 1.2640),
    12.0: (0.0188000, 1.2170, 0.0168000, 1.2000),
    15.0: (0.0367000, 1.1540, 0.0335000, 1.1280),
    18.0: (0.0555000, 1.1270, 0.0500000, 1.1100),
    20.0: (0.0751000, 1.0990, 0.0691000, 1.0650),
    23.0: (0.1035000, 1.0650, 0.0952000, 1.0330),
    25.0: (0.1240000, 1.0610, 0.1130000, 1.0300),
    30.0: (0.1870000, 1.0210, 0.1670000, 1.0000),
    35.0: (0.2630000, 0.9790, 0.2330000, 0.9630),
    38.0: (0.3055000, 0.9550, 0.2712000, 0.9410),
    40.0: (0.3500000, 0.9390, 0.3100000, 0.9290),
    45.0: (0.4420000, 0.9030, 0.3930000, 0.8970),
    50.0: (0.5360000, 0.8730, 0.4790000, 0.8680),
    60.0: (0.7070000, 0.8260, 0.6420000, 0.8240),
    70.0: (0.8510000, 0.7930, 0.7840000, 0.7930),
    80.0: (0.9750000, 0.7690, 0.9060000, 0.7690),
    90.0: (1.0600000, 0.7530, 0.9990000, 0.7540),
    100.0: (1.1200000, 0.7430, 1.0600000, 0.7440),
}
# NOTE: 18, 23, 38 GHz rows are log-log interpolated from the official
# tabulated points (12/20/25/35/40 GHz) to cover common microwave backhaul
# bands not directly tabulated in P.838-3. They are convenience values for
# this library's demo bands, not a substitute for the published table.

_FREQS = sorted(_P838_TABLE.keys())
MIN_FREQ_GHZ = _FREQS[0]
MAX_FREQ_GHZ = _FREQS[-1]


def rain_coefficients(freq_ghz: float, polarization: Polarization = "V") -> tuple[float, float]:
    """(k, alpha) for a frequency, log-log interpolated across the table.

    Raises ``ValueError`` outside the tabulated 1-100 GHz range rather than
    extrapolating -- extrapolating this regression is not defensible.
    """
    if not (MIN_FREQ_GHZ <= freq_ghz <= MAX_FREQ_GHZ):
        raise ValueError(
            f"freq_ghz={freq_ghz} outside supported range [{MIN_FREQ_GHZ}, {MAX_FREQ_GHZ}] GHz"
        )
    k_idx, a_idx = (2, 3) if polarization == "V" else (0, 1)
    ks = [_P838_TABLE[f][k_idx] for f in _FREQS]
    als = [_P838_TABLE[f][a_idx] for f in _FREQS]
    log_f = [math.log10(f) for f in _FREQS]
    x = math.log10(freq_ghz)
    k = 10 ** _interp(x, log_f, [math.log10(v) for v in ks])
    alpha = _interp(x, log_f, als)
    return float(k), float(alpha)


def _interp(x: float, xs: list[float], ys: list[float]) -> float:
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(1, len(xs)):
        if x <= xs[i]:
            x0, x1 = xs[i - 1], xs[i]
            y0, y1 = ys[i - 1], ys[i]
            t = (x - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return ys[-1]


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
            f"gamma_R = k*R^alpha at R={rain_rate_mm_h:.1f} mm/h, {freq_ghz:.0f} GHz, "
            f"{polarization} pol (k={k:.6g}, alpha={alpha:.4g}) -> {gamma:.4f} dB/km. "
            f"d_eff = {path_length_km:.1f} km / (1 + {path_length_km:.1f}/d0) = {d_eff:.2f} km "
            f"(rain assumed uniform along the effective path, not the full "
            f"geometric path; instantaneous rain rate used with a long-term "
            f"design-rule distance factor -- a stated simplification, not a "
            f"validated instantaneous model)."
        ),
    )
