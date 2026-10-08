#!/usr/bin/env python3
"""SHT40 sensors connected through a Sensirion SensorBridge.

The SensorBridge is opened once. Each physical SensorBridge port gets its own
I2C proxy and SHT4x device. This supports, for example, one SHT40 at address
0x44 on port ONE and another SHT40 at the same address on port TWO.
"""

import logging
import time

from serial.tools import list_ports

from sensirion_i2c_driver import I2cConnection, CrcCalculator
from sensirion_shdlc_driver import ShdlcSerialPort, ShdlcConnection
from sensirion_shdlc_sensorbridge import (
    SensorBridgePort,
    SensorBridgeShdlcDevice,
    SensorBridgeI2cProxy,
)
from sensirion_driver_adapters.i2c_adapter.i2c_channel import I2cChannel
from sensirion_i2c_sht4x.device import Sht4xDevice


LOGGER = logging.getLogger("SHT40")


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


def numeric_value(value):
    """Convert Sensirion typed measurement values to float."""
    try:
        return float(value)
    except (TypeError, ValueError):
        pass

    if hasattr(value, "value"):
        return float(value.value)

    raise TypeError(f"Cannot convert Sensirion value {value!r} to float")


class SHT40SensorBridge:
    """Manage SHT40 sensors attached to different ports of one SensorBridge."""

    def __init__(
        self,
        serial_number,
        ports=(SensorBridgePort.ONE, SensorBridgePort.TWO),
        slave_address=0x44,
        i2c_frequency=100e3,
        supply_voltage=3.3,
    ):
        self.serial_number = serial_number
        self.ports = tuple(ports)
        self.slave_address = slave_address
        self.i2c_frequency = i2c_frequency
        self.supply_voltage = supply_voltage

        self.serial_port_name = find_serial_device(serial_number)
        self.serial_port = None
        self.bridge = None
        self.sensors = {}

    def open(self):
        """Open the SensorBridge and initialize one SHT40 on each port."""
        LOGGER.info(
            "Opening Sensirion SensorBridge %s on %s",
            self.serial_number,
            self.serial_port_name,
        )

        self.serial_port = ShdlcSerialPort(
            port=self.serial_port_name,
            baudrate=460800,
        )
        self.serial_port.__enter__()

        self.bridge = SensorBridgeShdlcDevice(
            ShdlcConnection(self.serial_port),
            slave_address=0,
        )

        for bridge_port in self.ports:
            self.bridge.set_i2c_frequency(
                bridge_port,
                frequency=self.i2c_frequency,
            )
            self.bridge.set_supply_voltage(
                bridge_port,
                voltage=self.supply_voltage,
            )
            self.bridge.switch_supply_on(bridge_port)

            i2c_transceiver = SensorBridgeI2cProxy(
                self.bridge,
                port=bridge_port,
            )
            channel = I2cChannel(
                I2cConnection(i2c_transceiver),
                slave_address=self.slave_address,
                crc=CrcCalculator(8, 0x31, 0xff, 0x0),
            )
            sensor = Sht4xDevice(channel)

            try:
                sensor.soft_reset()
                time.sleep(0.01)
            except BaseException:
                LOGGER.warning(
                    "SHT40 soft reset failed on SensorBridge port %s",
                    bridge_port,
                    exc_info=True,
                )

            LOGGER.info(
                "SHT40 on SensorBridge port %s: serial number %s",
                bridge_port,
                sensor.serial_number(),
            )
            self.sensors[bridge_port] = sensor

        return self

    def read(self, bridge_port):
        """Read temperature and relative humidity from one SensorBridge port."""
        if bridge_port not in self.sensors:
            raise RuntimeError(
                f"No SHT40 configured on SensorBridge port {bridge_port}"
            )

        temperature, humidity = (
            self.sensors[bridge_port].measure_lowest_precision()
        )
        return numeric_value(temperature), numeric_value(humidity)

    def read_all(self):
        """Read all configured SHT40 sensors, keyed by SensorBridge port."""
        return {bridge_port: self.read(bridge_port) for bridge_port in self.ports}

    def close(self):
        """Close the SensorBridge serial connection."""
        if self.serial_port is not None:
            try:
                self.serial_port.__exit__(None, None, None)
            finally:
                self.serial_port = None
                self.bridge = None
                self.sensors = {}
