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
