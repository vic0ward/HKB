# Regarding half/full duplex see comments below
import serial
import binascii
import time
import datetime
import sys
import logging
from serial.serialutil import SerialException
from threading import Thread
import datetime
import os.path
import smtplib
import threading
# import bcrypt
import numpy as np
from fcntl import ioctl

PT100_ref = {"gain": 0.196973, "offset": 22.126}
Temperature_ref = {"gain": 0.251749, "offset": 278.293}
Humidity_ref = {"gain": 0.127548, "offset": 69.426}

LOG_DIR = "./logs"

sleeping_time = 0.3

from serial.tools import list_ports

HKB_FTDI_SERIAL = "FT404Z59"

def find_ftdi(serial_number=HKB_FTDI_SERIAL):
    """Return the serial device belonging to the HKB FTDI adapter.

    Matching the USB serial number is important because other connected
    instruments (e.g. the Sensirion SensorBridge) may also enumerate as
    FTDI serial devices.
    """
    ports = list_ports.comports()

    for p in ports:
        if p.vid == 0x0403 and p.serial_number == serial_number:
            print(f"Found HKB FTDI device: {p.device}")
            print(f"  PID: {p.pid:04x}" if p.pid else "")
            print(f"  Serial: {p.serial_number}")
            return p.device

    available = [
        f"{p.device} (VID={p.vid}, PID={p.pid}, serial={p.serial_number!r}, "
        f"description={p.description!r})"
        for p in ports
    ]
    raise RuntimeError(
        f"HKB FTDI adapter with serial {serial_number!r} not found. "
        f"Available serial devices: {available}"
    )

def decodeADC(ADC_count, gain_offset):
    return (ADC_count - gain_offset['offset']) * gain_offset['gain']

def to_binary(num, length=8):
    return format(num, '#0{}b'.format(length + 2))

def get_command(_address, _command, _message):
    query = bytearray()
    query.append(0x00)
    query.append(_command)
    for m in _message:
        query.append(m)

    first = "%s%s" % (to_binary(_address, 4).replace('0b', ''), to_binary(len(query)+1, 4).replace('0b', ''))
    query[0] = int(first, 2)

    checksum = 0
    for i, v in enumerate(query):
        checksum += v

    checksum = 0xFF - checksum
    query.append(checksum)
    return query


class HKB:

    logLevel = logging.DEBUG

    queue = []
    replies = {}
    log_start = ""
    led_status = 1

    def openLogFiles(self):
        now = datetime.datetime.now().strftime("%Y-%m-%d")
        if now == self.log_start:
            return#### ====> Setting led status


        try:
            self.log_start = now
            self.filename = "%s/HKB_%s.log" % (LOG_DIR, now)
            self.dp_filename = "%s/HKB_DewPoint_%s.log" % (LOG_DIR, now)
            self.log.debug("Openning log file '%s'..." % self.filename)
            exists = os.path.exists(self.filename)
            self.target = open(self.filename, 'a')
            if exists == False:
                self.target.write('#### Log file from HKB\n' \
                                  '# timestamp : timestamps in seconds\n' \
                                  '# H0 : Humidity of temperature+humidity sensor ch0\n' \
                                  '# H1 : Humidity of temperature+humidity sensor ch1\n' \
                                  '# H2 : Humidity of temperature+humidity sensor ch2\n' \
                                  '# H3 : Humidity of temperature+humidity sensor ch3\n' \
                                  '# T0 : Temperature of temperature+humidity sensor ch0\n' \
                                  '# T1 : Temperature of temperature+humidity sensor ch1\n' \
                                  '# T2 : Temperature of temperature+humidity sensor ch2\n' \
                                  '# T3 : Temperature of temperature+humidity sensor ch3\n' \
                                  '# PT100_0 : Temperature of PT100 sensor ch0\n' \
                                  '# PT100_1 : Temperature of PT100 sensor ch1\n' \
                                  '# PT100_2 : Temperature of PT100 sensor ch2\n' \
                                  '# PT100_3 : Temperature of PT100 sensor ch3\n' \
                                  '# P0 : Pressure from pressure sensor ch0\n' \
                                  '# P1 : Pressure from pressure sensor ch1\n' \
                                  '# PLEDS : Status of pointing LEDs (1: ON, 2: OFF)\n' \
                                  '# HEADER\n' \
                                  '# timestamp H0 H1 H2 H3 T0 T1 T2 T3 PT100_0 PT100_1 PT100_2 PT100_3 P0 P1 PLEDS\n' \
                                  '# DATA\n')
                self.target.flush()
        except:
            self.log.critical("Failed to open the file for logs: %s" % self.filename)
            sys.exit(-1)

        try:
            self.log.debug("Opening dew point log file '%s'..." % self.dp_filename)
            exists = os.path.exists(self.dp_filename)
            self.dp_target = open(self.dp_filename, 'a')
            if exists == False:
                self.dp_target.write('#### Log file from HKB\n#timestamp DP0 DP1 DP2 DP3\n')
                self.dp_target.flush()
        except:
            self.log.critical("Failed to open the file for logs: %s" % self.dp_filename)
            sys.exit(-1)

    def __init__(self, port=None, address=1):

        if port is None:
            port = find_ftdi()

        self.port = port
        self.address = address

        self.H = {'values': [], 'updated': []}
        self.T = {'values': [], 'updated': []}
        self.P = {'values': [], 'updated': []}
        self.PT100 = {'values': [], 'updated': []}
        self.PLEDS = {'values': [], 'updated': []}
        self.DP = {'values': [], 'updated': []}
        self.FANS = {'values': [], 'updated': []}
        self.PS_STATUS = {}


        self.operate = True
        self.command_id = -1
        logging.basicConfig(level=self.logLevel, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        self.log = logging.getLogger("InterfaceHKB")
        self.log.debug("Using HKB address %d" % self.address)
        self.log.debug("Accessing the serial port %s" % self.port)

        try:
            #
            # RS-422/485 Full/Half Duplex
            #
            # For RS-422/485 ports, the half/full duplex mode is selected by configuring the DTR output. If
            # DTR is set (which seems to be the default), the port is in full-duplex mode, and if DTR is not
            # set, the port is in half-duplex mode. You can control DTR from your application using ioctl() calls.

            self.ser = serial.Serial(self.port, baudrate=9600, bytesize=serial.EIGHTBITS, stopbits=serial.STOPBITS_ONE, parity=serial.PARITY_NONE, timeout=1, xonxoff=0)
            #self.ser.dtr = False
            #self.ser.rts = False
            #if (self.ser.isOpen() == True):
            #    self.ser.close()
            #self.ser.open()
            #self.ser.reset_input_buffer

        except SerialException as e:
            self.log.critical("Serial port exception occured: %s" % e)
            sys.exit(-1)
            pass

        thread = Thread(target=self.loop)
        thread.start()

    def send_command(self, command, message):
        query_len = 0
        reply_len = 0
        total_tries = 0
        while True:
            query = None
            if (total_tries == 5):
                self.log.critical("Command processing %d failed after %d tries" % (command, total_tries))
                return None
            if (query_len == reply_len or reply_len == 0) and (total_tries > 0):
                self.log.warning('Performing reset of the HKB...')
                query = get_command(self.address, 0, [])
            else:
                query = get_command(self.address, command, message)

            self.log.debug("Sending query %s" % binascii.b2a_hex(query))
            total_tries += 1
            x = self.ser.write(query)
            self.ser.flush()
            retries = 0
            s = None
            time.sleep(sleeping_time)
            while True:
                if self.ser.inWaiting() == 0:
                    time.sleep(sleeping_time)
                else:
                    s = self.ser.read(self.ser.inWaiting())
                    break
                if (retries == 10):
                    self.log.critical("Reply timeout...")
                    break
                retries += 1
            query_len = len(query)
            if s is None:
                s = bytearray([])
            reply_len = len(s)
            if reply_len > 0:
                return s

    def print_replies(self):
        for command_id in self.replies:
            item = self.replies[command_id]
            print("id=%d command=%d message=%s query=%s reply=%s added=%f started=%f duration=%f" % (
            item['id'], item['command'], binascii.b2a_hex(item['message']), binascii.b2a_hex(item['query']),
            binascii.b2a_hex(item['reply']), item['added'], item['started'], item['duration']))

    def add_command(self, command, message):
        self.command_id += 1
        self.queue.append({"command": command, "message": message, "added": time.time(), "id": self.command_id})
        return self.command_id

    def get_reply(self, command_id):
        if command_id in self.replies:
            ret = self.replies[command_id]
            del self.replies[command_id]
            return ret
        else:
            return None

    def loop(self):
        self.log.debug("Starting main loop...")
        self.log.warning('Performing reset of the HKB...')
        query = get_command(self.address, 0, [])
        while self.operate:
            if len(self.queue) > 0:
                item = self.queue[0]
                command = item['command']
                self.log.info("Executing command #%d, message %s..." % (command, binascii.b2a_hex(item['message'])))
                message = item['message']
                command_id = item['id']
                added = item['added']
                t1 = time.time()
                ret = self.send_command(command, message)
                self.log.debug("Received reply %s" % ('None' if ret is None else binascii.b2a_hex(ret)))
                t2 = time.time()
                self.log.info("Executing done in %f sec..." % (t2 - t1))
                self.replies[command_id] = {"command": command, "message": message, "reply": ret, "duration": t2 - t1,
                                            "id": command_id, "added": added, "started": t1,
                                            "query": get_command(self.address, command, message)}
                self.queue.pop(0)
            else:
                time.sleep(sleeping_time)
        self.log.warn("Stopping main loop...")

    def obtain_reply(self, command, message, frames_count):
        i = self.add_command(command, message)
        data = None
        while True:
            data = self.get_reply(i)
            if data is not None:
                break
            time.sleep(sleeping_time)
        if data['reply'] is None:
            self.log.critical("Failed to get any reply, exiting...")
            sys.exit(-1)
        data = binascii.b2a_hex(data['reply'])
        frames = []
        for frame in range(0, frames_count):
            frames.append(data[frame * 14:frame * 14 + 14])
        return frames

    def send_abort(self):
        frames = self.obtain_reply(0, bytearray(), 1)
    
    def get_humidities_temperatures(self):
        frames = self.obtain_reply(9, bytearray([5]), 4)
        if frames is None: return
        tempH = []
        for frame in frames[0:2]:
            tempH.append(decodeADC(int(frame[4:8], 16), Humidity_ref))
            tempH.append(decodeADC(int(frame[8:12], 16), Humidity_ref))

        tempT = []
        for frame in frames[2:4]:
            tempT.append(decodeADC(int(frame[4:8], 16), Temperature_ref))
            tempT.append(decodeADC(int(frame[8:12], 16), Temperature_ref))

        self.H['values'] = tempH
        self.H['updated'] = time.time()

        self.T['values'] = tempT
        self.T['updated'] = time.time()

        tempDP = []

        tempDP.append(self.DewPoint(self.T['values'][0], self.H['values'][0]))
        tempDP.append(self.DewPoint(self.T['values'][1], self.H['values'][1]))
        tempDP.append(self.DewPoint(self.T['values'][2], self.H['values'][2]))
        tempDP.append(self.DewPoint(self.T['values'][3], self.H['values'][3]))        

        self.DP['values'] = tempDP
        self.DP['updated'] = time.time()
    
        time.sleep(sleeping_time)

    def get_PT100(self):
        frames = self.obtain_reply(9, bytearray([0]), 2)
        if frames is None:
            return
        tempPT100 = []
        for frame in frames[0:2]:
            tempPT100.append(decodeADC(int(frame[4:8], 16), PT100_ref))
            tempPT100.append(decodeADC(int(frame[8:12], 16), PT100_ref))

        self.PT100['values'] = tempPT100
        self.PT100['updated'] = time.time()
        
        time.sleep(sleeping_time)

    def get_pressure(self):
        frames = self.obtain_reply(9, bytearray([6]), 1)
        if frames is None: return
        tempP = []
        for frame in frames[0:1]:
            rp = int(frame[4:8], 16)
            tempP.append(((rp >> 4)+(rp & 0b1)*2**-4+((rp & 0b10) >> 1)*2**-3 +
                      ((rp & 0b100) >> 2)*2**-2+((rp & 0b1000) >> 3)*2**-1)*10)
            rp = int(frame[8:12], 16)
            tempP.append(((rp >> 4)+(rp & 0b1)*2**-4+((rp & 0b10) >> 1)*2**-3 +
                      ((rp & 0b100) >> 2)*2**-2+((rp & 0b1000) >> 3)*2**-1)*10)
        self.P['values'] = tempP
        self.P['updated'] = time.time()
        time.sleep(sleeping_time)

    def get_fans(self):
        frames = self.obtain_reply(9, bytearray([8]), 2)
        if frames is None: 
            print('No frames for fans')
            return

        tempFANS = []
        for frame in frames[0:1]:
            tempFANS.append(bin(int(frame[6:8], 16)))
            tempFANS.append(bin(int(frame[4:6], 16)))

        self.FANS['values'] = tempFANS
        self.FANS['updated'] = time.time()

        self.PS_STATUS['FA_CR0'] = int(self.FANS['values'][0], 16) & 0b1
        self.PS_STATUS['FB_CR0'] = int(self.FANS['values'][0], 16) & 0b1 << 1 >> 1
        self.PS_STATUS['FA_CR1'] = int(self.FANS['values'][0], 16) & 0b1 << 2 >> 2
        self.PS_STATUS['FB_CR1'] = int(self.FANS['values'][0], 16) & 0b1 << 3 >> 3
        self.PS_STATUS['FA_CR2'] = int(self.FANS['values'][0], 16) & 0b1 << 4 >> 4
        self.PS_STATUS['FB_CR2'] = int(self.FANS['values'][0], 16) & 0b1 << 5 >> 5

        self.PS_STATUS['PS_CR0'] = int(self.FANS['values'][0], 16) & 0b1 << 6 >> 6
        self.PS_STATUS['PS_CR1'] = int(self.FANS['values'][0], 16) & 0b1 << 7 >> 7
        self.PS_STATUS['PS_CR2'] = int(self.FANS['values'][1], 16) & 0b1
        self.PS_STATUS['PS_PDP'] = int(self.FANS['values'][1], 16) & 0b1

        time.sleep(sleeping_time)

    def get_pleds(self):
        frames = self.obtain_reply(9, bytearray([9]), 1)
        if frames is None: 
            print('No frames')
            return
        tempPLEDS = []
        for frame in frames[0:1]:
            tempPLEDS.append(int(frame[4:6], 16))

        self.PLEDS['values'] = tempPLEDS
        self.PLEDS['updated'] = time.time()
        time.sleep(sleeping_time)

    def set_led_status(self, status):
        self.led_status = status
        time.sleep(sleeping_time)

    def set_pleds(self, status):
        self.send_command(10, bytearray([status]))
        time.sleep(sleeping_time)


    def log_data(self):
        self.openLogFiles()

        self.target.write("%.5f" % time.time())
        self.target.write(" ")
        self.target.write(" ".join(map(str, self.H['values'])))
        self.target.write(" ")
        self.target.write(" ".join(map(str, self.T['values'])))
        self.target.write(" ")
        self.target.write(" ".join(map(str, self.PT100['values'])))
        self.target.write(" ")
        self.target.write(" ".join(map(str, self.P['values'])))
        self.target.write(" ")
        self.target.write(" ".join(map(str, self.FANS['values'])))
        self.target.write(" ")
        self.target.write(" ".join(map(str, self.PLEDS['values'])))
        self.target.write("\n")
        self.target.flush()

        dp = []
        dp.append(self.DewPoint(self.T['values'][0], self.H['values'][0]))
        dp.append(self.DewPoint(self.T['values'][1], self.H['values'][1]))
        dp.append(self.DewPoint(self.T['values'][2], self.H['values'][2]))
        dp.append(self.DewPoint(self.T['values'][3], self.H['values'][3]))

        self.DP["values"] = dp
        self.DP["updated"] = time.time()

        self.dp_target.write("%.5f" % time.time())
        self.dp_target.write(" ")
        self.dp_target.write(" ".join(map(str, dp)))
        self.dp_target.write("\n")
        self.dp_target.flush()

    def DewPoint(self, T, H):
        DP = ((H / 100) ** (1.0 / 8)) * (112 + 0.9 * T) + 0.1 * T - 112
        return DP

    def stop(self):
        self.operate = False
        if hasattr(self, 'target'):
            self.target.close()

def run_thread(hbk):
    try:
        cnt = 0
        hkb.set_pleds(0)	
        while True:
            print('#### ====> Getting led status')
            hkb.get_pleds()
#            print('#### ====> Setting led status')
#            hkb.set_pleds(int(cnt%2))
            print('#### ====> Getting fans')
            hkb.get_fans()
            print('#### ====> Getting pressure')
            hkb.get_pressure()
            print('#### ====> Getting PT100')
            hkb.get_PT100()
            print('#### ====> Getting humidities and temperatures')
            hkb.get_humidities_temperatures()
            print('#### ====> Logging data')
            hkb.log_data()
            time.sleep(5)
            cnt += 1
    except:
        hkb.stop()

def run_single_thread(hbk):
    try:
        hkb.get_PT100()	
        hkb.get_pleds()
        hkb.get_fans()
        hkb.get_fan_ps_status()
        hkb.get_humidities_temperatures()
        hkb.get_pressure()
        hkb.log_data()
        hkb.stop()
        #dmm.
    except:
        hkb.stop()
