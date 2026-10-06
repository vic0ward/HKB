"""Driver for an Agilent/Keysight 34410A used as a 4-wire Pt100 thermometer."""

from __future__ import annotations

import math
from statistics import fmean

import pyvisa


class Agilent34410A:
    """Minimal 34410A interface for 4-wire resistance and Pt100 temperature."""

    # IEC 60751 coefficients for alpha = 0.00385 / degC Pt100/Pt1000 sensors.
    A = 3.9083e-3
    B = -5.775e-7
    C = -4.183e-12

    def __init__(
        self,
        hostname: str | None = "10.195.50.148",
        resource: str | None = None,
        *,
        nplc: float = 10.0,
        timeout_ms: int = 5000,
    ) -> None:
        self.rm = pyvisa.ResourceManager()
        if resource is None:
            if hostname is None:
                raise ValueError("Provide either hostname or VISA resource string")
            resource = f"TCPIP0::{hostname}::inst0::INSTR"

        self.resource = resource
        self.inst = self.rm.open_resource(resource)
        self.inst.timeout = timeout_ms
        self.inst.write_termination = "\n"
        self.inst.read_termination = "\n"
        self.configure_4wire_resistance(nplc=nplc)

    def identify(self) -> str:
        return self.inst.query("*IDN?").strip()

    def configure_4wire_resistance(self, *, nplc: float = 10.0) -> None:
        """Configure four-wire resistance with autorange and selected integration time."""
        self.inst.write("CONF:FRES")
        self.inst.write("FRES:RANG:AUTO ON")
        self.inst.write(f"FRES:NPLC {nplc:g}")

    def read_resistance_4w(self, *, averages: int = 1) -> float:
        """Read four-wire resistance in ohms; optionally average repeated readings."""
        if averages < 1:
            raise ValueError("averages must be >= 1")
        readings = [float(self.inst.query("READ?")) for _ in range(averages)]
        return fmean(readings)

    @classmethod
    def rtd_resistance_to_temperature(cls, resistance_ohm: float, *, r0_ohm: float = 100.0) -> float:
        """Convert IEC 60751 RTD resistance to degC using Callendar-Van Dusen.

        r0_ohm=100 selects a Pt100; r0_ohm=1000 selects a Pt1000.
        Valid for the standard IEC 60751 range (-200 to +850 degC).
        """
        if resistance_ohm <= 0 or r0_ohm <= 0:
            raise ValueError("Resistance and R0 must be positive")

        ratio = resistance_ohm / r0_ohm

        # For T >= 0 C: R/R0 = 1 + A*T + B*T^2, solved analytically.
        if resistance_ohm >= r0_ohm:
            discriminant = cls.A**2 - 4.0 * cls.B * (1.0 - ratio)
            if discriminant < 0:
                raise ValueError("Resistance is outside the IEC 60751 conversion range")
            temperature = (-cls.A + math.sqrt(discriminant)) / (2.0 * cls.B)
            if temperature > 850.0:
                raise ValueError("Resistance corresponds to a temperature above 850 degC")
            return temperature

        # For T < 0 C the C term makes the equation quartic. Bisection is robust.
        def normalized_resistance(t: float) -> float:
            return 1.0 + cls.A*t + cls.B*t*t + cls.C*(t - 100.0)*t**3

        lo, hi = -200.0, 0.0
        if ratio < normalized_resistance(lo):
            raise ValueError("Resistance corresponds to a temperature below -200 degC")

        for _ in range(60):
            mid = (lo + hi) / 2.0
            if normalized_resistance(mid) < ratio:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2.0

    def read_temperature_4w(self, *, r0_ohm: float = 100.0, averages: int = 10) -> float:
        """Read 4-wire resistance and convert it to RTD temperature in degC."""
        resistance = self.read_resistance_4w(averages=averages)
        return self.rtd_resistance_to_temperature(resistance, r0_ohm=r0_ohm)

    def close(self) -> None:
        self.inst.close()
        self.rm.close()

    def __enter__(self) -> "Agilent34410A":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
