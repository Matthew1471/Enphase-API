#!/usr/bin/env python
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

import argparse # We support command line arguments.
import datetime # We interpret and manipulate dates and times of readings.
import json     # This script makes heavy use of JSON parsing.
import os.path  # We check whether a file exists.
import queue    # We use a queue as the response is buffered with no timestamps.

import mysql.connector # Third party library; "pip install mysql-connector-python"

# All the shared Enphase® functions are in these packages.
from enphase_api.cloud.authentication import Authentication
from enphase_api.local.gateway import Gateway


# SQL statements.
add_meter_reading = ('INSERT INTO `MeterReading` (Timestamp, '
                      'Production_Phase_A_ID, Production_Phase_B_ID, Production_Phase_C_ID, '
                      'NetConsumption_Phase_A_ID, NetConsumption_Phase_B_ID, NetConsumption_Phase_C_ID, '
                      'TotalConsumption_Phase_A_ID, TotalConsumption_Phase_B_ID, TotalConsumption_Phase_C_ID'
                      ') VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)')
add_meter_reading_result = ('INSERT INTO `MeterReading_Result` (p, q, s, v, i, pf, f) VALUES (%s, %s, %s, %s, %s, %s, %s)')

def add_results_to_database(database_connection, database_cursor_meter_reading, database_cursor_meter_reading_result, timestamp, json_object):
    # Take each of the meter types.
    for meter_reading_type, meter_reading_type_result in json_object.items():
        # Initialise to empty by default so they convert to a database NULL if not later set.
        ph_a = None
        ph_b = None
        ph_c = None

        # Take each of the phase readings.
        for meter_phase, meter_reading_result in meter_reading_type_result.items():
            # Skip empty phases.
            if all(value == 0 for value in meter_reading_result.values()): continue

            # Add to the database the meter reading(s) (specifying a dictionary prevented the query from being prepared).
            database_cursor_meter_reading_result.execute(add_meter_reading_result, (meter_reading_result['p'], meter_reading_result['q'], meter_reading_result['s'], meter_reading_result['v'], meter_reading_result['i'], meter_reading_result['pf'], meter_reading_result['f']))

            # Get the result ID for this phase insert.
            if meter_phase == 'ph-a':
                ph_a = database_cursor_meter_reading_result.lastrowid
            elif meter_phase == 'ph-b':
                ph_b = database_cursor_meter_reading_result.lastrowid
            elif meter_phase == 'ph-c':
                ph_c = database_cursor_meter_reading_result.lastrowid
            else:
                raise ValueError('Unexpected phase "' + meter_phase + '" in JSON.')

        # Store the meter reading record IDs for this meter type.
        if meter_reading_type == 'production':
            production_phase_list_id = (ph_a, ph_b, ph_c)
        elif meter_reading_type == 'net-consumption':
            net_consumption_phase_list_id = (ph_a, ph_b, ph_c)
        elif meter_reading_type == 'total-consumption':
            total_consumption_phase_list_id = (ph_a, ph_b, ph_c)
        else:
            raise ValueError('Unexpected reading type "' + meter_reading_type + '" in JSON.')

    # Add the meter reading.
    database_cursor_meter_reading.execute(add_meter_reading, (timestamp,) + production_phase_list_id + net_consumption_phase_list_id + total_consumption_phase_list_id)

    # Make sure data is committed to the database.
    database_connection.commit()

def main():
    # Create an instance of argparse to handle any command line arguments.
    parser = argparse.ArgumentParser(prefix_chars='/-', add_help=False, description='A program that connects to an Enphase® Gateway and stores the meter values in a database.')

    # Arguments to control the database connection.
    database_group = parser.add_argument_group('Database')
    database_group.add_argument('/DBHost', '-DBHost', '--DBHost', dest='database_host', default='127.0.0.1', help='The database server host (defaults to "127.0.0.1").')
    database_group.add_argument('/DBUsername', '-DBUsername', '--DBUsername', dest='database_username', default='root', help='The database username (defaults to "root").')
    database_group.add_argument('/DBPassword', '-DBPassword', '--DBPassword', dest='database_password', default='', help='The database password (defaults to blank).')
    database_group.add_argument('/DBDatabase', '-DBDatabase', '--DBDatabase', dest='database_database', default='Enphase', help='The database schema (defaults to "Enphase").')

    # Arguments to control how the program generally behaves.
    general_group = parser.add_argument_group('General')
    general_group.add_argument('/Host', '-Host', '--Host', dest='host', help='The Enphase® Gateway URL (defaults to config or https://envoy.local).')

    # We want this to appear last in the argument usage list.
    general_group.add_argument('/?', '/Help', '/help', '-h','--help','-help', action='help', help='Show this help message and exit.')

    # Handle any command line arguments.
    args = parser.parse_args()

    # Load credentials.
    with open('configuration\\credentials_token.json', mode='r', encoding='utf-8') as json_file:
        credentials = json.load(json_file)

    # Do we have a valid JSON Web Token (JWT) to be able to use the service?
    if not (credentials.get('Token') or Authentication.check_token_valid(credentials['Token'], credentials['GatewaySerialNumber'])):
        # It is not valid so clear it.
        raise ValueError('No or expired token.')

    # Download and store the certificate from the gateway so all future requests are secure.
    if not os.path.exists('configuration\\gateway.cer'): Gateway.trust_gateway()

    # Did the user override the config or library default hostname to the Gateway?
    if args.host:
        # Get an instance of the Gateway API wrapper object (using the argument hostname).
        gateway = Gateway(args.host)
    elif credentials.get('Host'):
        # Get an instance of the Gateway API wrapper object (using the hostname specified in the config).
        gateway = Gateway(credentials['Host'])
    else:
        # Get an instance of the Gateway API wrapper object (using the library default hostname).
        gateway = Gateway()

    # Are we able to login to the gateway?
    if gateway.login(credentials['Token']):
        # Connect to the MySQL/MariaDB database.
        database_connection = mysql.connector.connect(user=args.database_username, password=args.database_password, host=args.database_host, database=args.database_database)

        # Get a reference to a database cursor.
        database_cursor_meter_reading = database_connection.cursor(prepared=True)
        database_cursor_meter_reading_result = database_connection.cursor(prepared=True)

        try:
            # On a single phase system this returns every 21 - 23 seconds, returning 21 - 23 results in multiple >= 712 bytes and <= 737 bytes chunks (potentially a 16 KB = 16,384 byte pre-TLS pre-HTTP server-side buffer?) across 12 TCP/IP packets, so each result could be a per-second poll interval?
            with gateway.api_call_stream('/stream/meter') as stream:
                # We use a queue as it is FIFO.
                queued_chunks = queue.Queue()

                # Statistics
                stats_count = 0
                stats_length = 0
                stats_min = None
                stats_max = None
                stats_delay = None

                # We calculate each meeter reading time based off when the chunk batches come in (we initially add on a bit of latency).
                chunk_first_received = None

                # Chunks are received when the gateway flushes its buffer.
                for chunk in stream.iter_content(chunk_size=1024, decode_unicode=True):
                    # Take a reference of the received date/time.
                    now = datetime.datetime.now()

                    # This is to be expected with Server-Sent Events (SSE).
                    if chunk.startswith('data: '):
                        if (chunk_first_received):
                            # Was the previous chunk first recieved over 10 seconds ago (we add on an allowance of 10 seconds for network latency)?
                            if (chunk_first_received and chunk_first_received + datetime.timedelta(seconds=10) < now):
                                # Preserve the count of seconds to add on to the oldest reading.
                                counter = 0

                                # Flush the queue now we know how many were received in this batch.
                                while not queued_chunks.empty():
                                    # Get the first chunk from the queue.
                                    json_object = queued_chunks.get()

                                    # We calculate the timestamp of the meter reading off the time the chunks were received (and add a network delay).
                                    if stats_delay:
                                        timestamp = chunk_first_received + datetime.timedelta(seconds=counter + stats_delay.total_seconds())
                                    else:
                                        timestamp = chunk_first_received + datetime.timedelta(seconds=counter)

                                    # Add this record to the database.
                                    add_results_to_database(database_connection=database_connection, database_cursor_meter_reading=database_cursor_meter_reading, database_cursor_meter_reading_result=database_cursor_meter_reading_result, timestamp=timestamp, json_object=json_object)

                                    # Output the reading time of the chunk and a value for debugging.
                                    print(str(timestamp) + ' - ' + str(json_object['net-consumption']['ph-a']['p']) + ' W')

                                    # The queue has no reliable method for determining queue size.
                                    counter+=1

                                # Print statistics.
                                print(str(datetime.datetime.now()) + ' - Length:' + str(stats_length) + ',Count:' + str(stats_count) + ',Min:' + str(stats_min) + ',Max:' + str(stats_max) + ',Latency:' + str(stats_delay.total_seconds()))

                                # Clear statistics.
                                stats_count = 0
                                stats_length = 0
                                stats_min = None
                                stats_max = None
                                stats_delay = None

                                # Update the chunk first received time if it is significantly different.
                                chunk_first_received = now
                            else:

                                # Calculate the delay between this and the previous packet.
                                delay = now - chunk_last_received

                                if stats_delay:
                                    stats_delay += delay
                                else:
                                    stats_delay = delay
                        else:
                            # Update the chunk first received time.
                            chunk_first_received = now

                        # Add this to the queue (turning the chunk into a dict) as we will need to sort out the timestamps once all the chunks have been flushed.
                        queued_chunks.put(json.loads(chunk[6:]))

                        # Gather statistics.
                        stats_count += 1
                        stats_length += len(chunk) + 4 + len(hex(len(chunk)))
                        if not stats_min or len(chunk) < stats_min: stats_min = len(chunk)
                        if not stats_max or len(chunk) > stats_max: stats_max = len(chunk)

                        # Update the last received time.
                        chunk_last_received = now
                    else:
                        raise ValueError('Bad line returned from meter stream (' + chunk + ').')
        finally:
            # Close the database connection.
            database_connection.close()
    else:
        # Let the user know why the program is exiting.
        raise ValueError('Unable to login to the gateway (bad, expired or missing token in credentials_token.json).')

# Launch the main method if invoked directly.
if __name__ == '__main__':
    main()