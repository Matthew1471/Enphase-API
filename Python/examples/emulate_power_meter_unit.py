#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# This file is part of Enphase-API <https://github.com/Matthew1471/Enphase-API>
# Copyright (C) 2023 Matthew1471!
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
This example responds to the Enphase® IQ Gateway probing for a Power Meter Unit (PMU)
so that alternative meter readings can be provided for those where an IQ Gateway is not configured
with a meter (such as IQ Gateway Standard).
"""

# We output the current date/time for debugging.
import datetime

# We use IP sockets to receive and send data.
import socket


# Meter details.
METER_IP_ADDRESS = '192.168.0.100'
METER_SOFTWARE_VERSION = '1.0.0'
METER_MAC_ADDRESS = 'aa:bb:cc:dd:ee:ff'

def respond_to_power_meter_unit_probes():
    # Create a UDP socket.
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

    # Allow port number re-use.
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # Bind to all available interfaces and port 12345.
    sock.bind(('0.0.0.0', 12345))

    # Notify the user.
    print(f'{datetime.datetime.now()} - Waiting for Power Meter Unit (PMU) probes from an IQ Gateway.', flush=True)

    # Repeat indefinitely.
    while True:
        # Wait to receive 8 bytes of data and the sender's address.
        data, address = sock.recvfrom(8)

        # Was this a Power Meter Unit (PMU) "SendData" probe?
        if data.decode('utf-8') == 'SendData':
            # Format the address in the conventional IP:PORT format.
            formatted_address = f'{address[0]}:{address[1]}'

            # Notify the user.
            print(f'{datetime.datetime.now()} - Responding to a Power Meter Unit (PMU) probe from {formatted_address}.', flush=True)

            # Send a response back.
            sock.sendto(bytes(f'IP: {METER_IP_ADDRESS} Ver: {METER_SOFTWARE_VERSION} MAC: {METER_MAC_ADDRESS}', 'utf-8'), address)

# Launch the respond_to_power_meter_unit_probes function if invoked directly.
if __name__ == '__main__':
    respond_to_power_meter_unit_probes()