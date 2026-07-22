# Atmospheric influence

Relative influence is screened with bearing/wind alignment, exponential distance decay `exp(-d/35)`, temporal decay `exp(-ln(2)t/12)`, wind speed, and rain attenuation `1/(1+rain)`. Low wind raises a meteorological accumulation indicator. Outputs are normalised screening scores only: no emissions rates, stack parameters, boundary-layer model, or regulatory concentration estimate is implied.
