#!/bin/bash

ID=$(lsusb | grep 05d1 | awk '{print $6}')
for i in $ID:
do
    dev=$(echo $i | tr ':' ' ')
    echo "Activating adapter $dev"
    modprobe ftdi_sio
    echo "$dev" | tr ':' ' ' > /sys/bus/usb-serial/drivers/ftdi_sio/new_id
    chmod 777 /dev/ttyUSB*
done
