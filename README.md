# HKB – Housekeeping Board Monitoring

Python software for communicating with and monitoring the Housekeeping Board (HKB) and associated environmental sensors.

The software provides interfaces for:

- communication with the HKB;
- monitoring housekeeping parameters;
- reading a Pt100 temperature sensor with an Agilent/Keysight 34410A digital multimeter;
- reading temperature and humidity from a Sensirion SHT4x sensor through a Sensirion SensorBridge;
- continuous monitoring and data logging.

## Hardware

The current monitoring setup supports:

- Housekeeping Board (HKB)
- Sensirion SHT4x temperature/humidity sensor
- Sensirion SensorBridge
- Agilent/Keysight 34410A digital multimeter
- Pt100 temperature sensor connected to the DMM in 4-wire configuration

## Installation

### 1. Clone the repository

```bash
git clone git@github.com:vic0ward/HKB.git
cd HKB
<<<<<<< HEAD
=======
```

### 2. Create a Python environment

Using Conda:

```bash
conda create -n hkb python=3.11
conda activate hkb
```

Alternatively, a standard Python virtual environment can be used:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install the dependencies

Install all required Python packages with:

```bash
pip install -r requirements.txt
```

This installs the serial/VISA communication packages as well as the Sensirion libraries required for the SHT4x and SensorBridge.

## Sensirion libraries

The SHT4x temperature and humidity sensor is accessed through a Sensirion SensorBridge.

The corresponding Sensirion Python libraries are therefore required:

- `sensirion-shdlc-driver`
- `sensirion-shdlc-sensorbridge`
- `sensirion-i2c-driver`
- `sensirion-i2c-sht4x`

These packages are maintained by Sensirion and are installed separately through `pip`; their source code is not redistributed as part of this repository.

The Sensirion Python drivers are distributed under their respective open-source licenses. In particular, the SHT4x Python driver uses the BSD 3-Clause License. Please refer to the individual Sensirion packages for their current copyright and licensing information.

## DMM communication

The Pt100 is read using an Agilent/Keysight 34410A digital multimeter in 4-wire resistance mode.

Communication with the instrument uses PyVISA.

The Python dependencies are:

- `pyvisa`
- `pyvisa-py`

A system VISA implementation such as NI-VISA can also be used instead of the pure-Python `pyvisa-py` backend.

## Software structure

### `HKB.py`

Interface to the Housekeeping Board and its monitored parameters.

### `DMM.py`

Interface to the Agilent/Keysight 34410A digital multimeter.

The driver provides 4-wire resistance measurements and conversion of Pt100 resistance measurements to temperature.

### `Monitoring.py`

Main monitoring program.

It combines measurements from:

- the Housekeeping Board;
- the Pt100 connected to the DMM;
- the Sensirion SHT4x sensor.

The acquired values are periodically recorded for monitoring and analysis.

## Running

Connect the required hardware and run:

```bash
python Monitoring.py
```

Communication parameters such as serial ports and instrument IP addresses may need to be adapted to the local setup.

## License

This project is distributed under the BSD 3-Clause License.

See [`LICENSE`](LICENSE) for details.

Third-party dependencies remain subject to their respective licenses.
>>>>>>> d7fe656 (Add README and Python dependencies)
