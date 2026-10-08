#!/usr/bin/env python3
"""
Unified monitoring loop for the House Keeping Board and calibration devices.

Devices
-------
HKB:
    RS-422/485 through FTDI adapter, USB serial FT404Z59.
Sensirion SHT40:
    Connected through SensorBridge, USB serial EKS24YNNUB.
Agilent 34410A:
    Connected over LAN.

The HKB class keeps its own low-level command worker.  This module owns the
higher-level acquisition cycle so all instruments are sampled and logged
together.
"""

import argparse
import csv
import logging
import math
import os
import signal
import threading
import time
from datetime import datetime
from pathlib import Path

from serial.tools import list_ports

from HKB import HKB
from DMM import Agilent34410A

from SHT40 import SHT40SensorBridge, SensorBridgePort



HKB_SERIAL = "FT404Z59"
SENSORBRIDGE_SERIAL = "EKS24YNNUB"
DMM_HOST = "10.195.50.148"
ACQUISITION_PERIOD = 5.0
LOG_DIR = Path("./logs")

LOGGER = logging.getLogger("Monitoring")


def find_serial_device(serial_number):
    """Find a serial device by its USB serial number."""
    ports = list_ports.comports()
    for port in ports:
        if port.serial_number == serial_number:
            return port.device

    devices = [
        f"{p.device}: serial={p.serial_number!r}, "
        f"VID:PID={p.vid!s}:{p.pid!s}, description={p.description!r}"
        for p in ports
    ]
    raise RuntimeError(
        f"USB serial device {serial_number!r} not found.\n"
        + "\n".join(devices)
    )


class Monitoring:
    def __init__(
        self,
        hkb_serial=HKB_SERIAL,
        sensorbridge_serial=SENSORBRIDGE_SERIAL,
        dmm_host=DMM_HOST,
        period=ACQUISITION_PERIOD,
        log_dir=LOG_DIR,
        enable_dmm=True,
    ):
        self.period = period
        self.log_dir = Path(log_dir)
        self.stop_event = threading.Event()

        hkb_port = find_serial_device(hkb_serial)
        LOGGER.info("HKB %s found on %s", hkb_serial, hkb_port)
        self.hkb = HKB(port=hkb_port)

        self.sht40 = SHT40SensorBridge(
            sensorbridge_serial,
            ports=(SensorBridgePort.ONE, SensorBridgePort.TWO),
        ).open()

        self.dmm = None
        if enable_dmm:
            LOGGER.info("Opening Agilent 34410A at %s", dmm_host)
            self.dmm = Agilent34410A(hostname=dmm_host)

        self._log_date = None
        self._log_file = None
        self._writer = None

    def _open_log(self):
        today = datetime.now().strftime("%Y-%m-%d")
        if self._log_date == today and self._log_file is not None:
            return

        if self._log_file is not None:
            self._log_file.close()

        self.log_dir.mkdir(parents=True, exist_ok=True)
        filename = self.log_dir / f"monitoring_{today}.csv"
        new_file = not filename.exists()

        self._log_file = open(filename, "a", newline="")
        self._writer = csv.writer(self._log_file)

        if new_file:
            self._writer.writerow([
                "timestamp",
                "H0", "H1", "H2", "H3",
                "T0", "T1", "T2", "T3",
                "PT100_0", "PT100_1", "PT100_2", "PT100_3",
                #"P0", "P1",
                #"FANS0", "FANS1",
                #"PLEDS",
                "SHT40_1_T", "SHT40_1_RH",
                "SHT40_2_T", "SHT40_2_RH",
                "DMM",
            ])
            self._log_file.flush()

        self._log_date = today
        LOGGER.info("Logging unified measurements to %s", filename)

    @staticmethod
    def _values(data, count):
        values = data.get("values", []) if data else []
        return list(values[:count]) + [math.nan] * max(0, count - len(values))

    def acquire(self):
        """Perform one complete acquisition cycle."""
        LOGGER.info("Reading HKB")
        self.hkb.get_pleds()
        self.hkb.get_fans()
        self.hkb.get_pressure()
        self.hkb.get_PT100()
        self.hkb.get_humidities_temperatures()

        sht1_t = math.nan
        sht1_rh = math.nan
        sht2_t = math.nan
        sht2_rh = math.nan

        try:
            sht1_t, sht1_rh = self.sht40.read(SensorBridgePort.ONE)
            LOGGER.info(
                "SHT40 port ONE: %.3f degC, %.3f %%RH", sht1_t, sht1_rh
            )
        except Exception:
            LOGGER.exception("SHT40 readout failed on port ONE")

        try:
            sht2_t, sht2_rh = self.sht40.read(SensorBridgePort.TWO)
            LOGGER.info(
                "SHT40 port TWO: %.3f degC, %.3f %%RH", sht2_t, sht2_rh
            )
        except Exception:
            LOGGER.exception("SHT40 readout failed on port TWO")

        dmm_value = math.nan
        if self.dmm is not None:
            try:
                dmm_value = self.dmm.read_temperature_4w(
                    r0_ohm=100.0, averages=10
                )
                LOGGER.info("DMM PT100: %.3f degC", dmm_value)
            except Exception:
                LOGGER.exception("Agilent 34410A readout failed")

        return {
            "timestamp": time.time(),
            "H": self._values(self.hkb.H, 4),
            "T": self._values(self.hkb.T, 4),
            "PT100": self._values(self.hkb.PT100, 4),
            #"P": self._values(self.hkb.P, 2),
            #"FANS": self._values(self.hkb.FANS, 2),
            #"PLEDS": self._values(self.hkb.PLEDS, 1),
            "SHT40_1_T": sht1_t,
            "SHT40_1_RH": sht1_rh,
            "SHT40_2_T": sht2_t,
            "SHT40_2_RH": sht2_rh,
            "DMM": dmm_value,
        }

    def log(self, data):
        self._open_log()
        self._writer.writerow(
            [f"{data['timestamp']:.5f}"]
            + data["H"]
            + data["T"]
            + data["PT100"]
            #+ data["P"]
            #+ data["FANS"]
            #+ data["PLEDS"]
            + [
                data["SHT40_1_T"], data["SHT40_1_RH"],
                data["SHT40_2_T"], data["SHT40_2_RH"],
                data["DMM"],
            ]
        )
        self._log_file.flush()

    def run(self):
        self.hkb.send_abort()
        self.hkb.set_pleds(0)

        LOGGER.info("Starting monitoring loop (period %.1f s)", self.period)

        try:
            while not self.stop_event.is_set():
                cycle_start = time.monotonic()

                try:
                    data = self.acquire()
                    self.log(data)
                except Exception:
                    # A failed cycle should not kill long-running monitoring.
                    LOGGER.exception("Acquisition cycle failed")

                elapsed = time.monotonic() - cycle_start
                wait = max(0.0, self.period - elapsed)
                self.stop_event.wait(wait)
        finally:
            self.close()

    def stop(self):
        self.stop_event.set()

    def close(self):
        LOGGER.info("Stopping monitoring")

        if self._log_file is not None:
            self._log_file.close()
            self._log_file = None

        try:
            self.sht40.close()
        except Exception:
            LOGGER.exception("Error closing SensorBridge")

        try:
            self.hkb.stop()
        except Exception:
            LOGGER.exception("Error stopping HKB")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", type=float, default=ACQUISITION_PERIOD)
    parser.add_argument("--hkb-serial", default=HKB_SERIAL)
    parser.add_argument("--sensorbridge-serial", default=SENSORBRIDGE_SERIAL)
    parser.add_argument("--dmm-host", default=DMM_HOST)
    parser.add_argument("--no-dmm", action="store_true")
    parser.add_argument("--log-dir", default=str(LOG_DIR))
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    monitor = Monitoring(
        hkb_serial=args.hkb_serial,
        sensorbridge_serial=args.sensorbridge_serial,
        dmm_host=args.dmm_host,
        period=args.period,
        log_dir=args.log_dir,
        enable_dmm=not args.no_dmm,
    )

    def request_stop(signum, frame):
        LOGGER.info("Received signal %s", signum)
        monitor.stop()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    monitor.run()


if __name__ == "__main__":
    main()
