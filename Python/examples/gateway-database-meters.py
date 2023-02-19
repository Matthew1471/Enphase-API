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

            try:
                # Add to the database the meter reading(s) (specifying a dictionary instead of a tuple prevented the query from being prepared - possibly a MySQL Connector bug).
                database_cursor_meter_reading_result.execute(add_meter_reading_result, (meter_reading_result['p'], meter_reading_result['q'], meter_reading_result['s'], meter_reading_result['v'], meter_reading_result['i'], meter_reading_result['pf'], meter_reading_result['f']))
            except mysql.connector.errors.DataError:
                print(json_object)
                raise

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
    with open('configuration/credentials_token.json', mode='r', encoding='utf-8') as json_file:
        credentials = json.load(json_file)

    # Do we have a valid JSON Web Token (JWT) to be able to use the service?
    if not (credentials.get('Token') or Authentication.check_token_valid(credentials['Token'], credentials['GatewaySerialNumber'])):
        # It is not valid so clear it.
        raise ValueError('No or expired token.')

    # Download and store the certificate from the gateway so all future requests are secure.
    if not os.path.exists('configuration/gateway.cer'): Gateway.trust_gateway()

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

        # Get references to 2 database cursors (that will PREPARE duplicate SQL statements).
        database_cursor_meter_reading = database_connection.cursor(prepared=True)
        database_cursor_meter_reading_result = database_connection.cursor(prepared=True)

        try:
            # On a single phase system this returns every 21 - 23 seconds, returning 21 - 23 results in multiple >= 701 bytes and <= 723 bytes chunks (potentially a 16 KB = 16,384 byte pre-TLS pre-HTTP server-side buffer?) across 12 TCP/IP packets, so each result could be a per-second poll interval?
            with gateway.api_call_stream('/stream/meter') as stream:
                # We use a queue as it is FIFO.
                queued_chunks = queue.Queue()

                # Statistics
                stats_count = 0
                stats_length = 0
                stats_min = None
                stats_max = None

                # We calculate each meter reading time based off when the chunk batches come in.
                chunk_first_received = None
                chunk_delay = None

                # The start and end strings for each chunk.
                start_needle = 'data: '
                end_needle = '}\r\n\r\n'

                # We allow partial chunks.
                partial_chunk = None

                # Chunks are received when the gateway flushes its buffer.
                for chunk in stream.iter_content(chunk_size=1024, decode_unicode=True):
                    # Take a reference of the chunk received date/time.
                    now = datetime.datetime.now()

                    # Have we received a chunk already?
                    if (chunk_first_received):
                        # Was the previous chunk first recieved over 10 seconds ago so the buffer has just been flushed (we add on an allowance of 10 seconds for network latency)?
                        if (chunk_first_received + datetime.timedelta(seconds=10) < now):
                            # Preserve the count of seconds to add on to the oldest reading.
                            counter = 0

                            # Flush the queue now we know how many were received in this batch.
                            while not queued_chunks.empty():
                                # Get the first chunk from the queue.
                                json_object = queued_chunks.get()

                                # We calculate the timestamp of the meter reading off the time the chunks were received (and add a network delay).
                                if chunk_delay:
                                    timestamp = chunk_first_received + datetime.timedelta(seconds=counter + chunk_delay.total_seconds())
                                else:
                                    timestamp = chunk_first_received + datetime.timedelta(seconds=counter)

                                # Add this record to the database.
                                add_results_to_database(database_connection=database_connection, database_cursor_meter_reading=database_cursor_meter_reading, database_cursor_meter_reading_result=database_cursor_meter_reading_result, timestamp=timestamp, json_object=json_object)

                                # Output the reading time of the chunk and a value for timestamp debugging.
                                #print(str(timestamp) + ' - ' + str(json_object['net-consumption']['ph-a']['p']) + ' W')

                                # The queue has no reliable method for determining queue size.
                                counter+=1

                            # Print statistics.
                            print(str(datetime.datetime.now()) + ' - Length:' + str(stats_length) + ',Count:' + str(stats_count) + ',Min:' + str(stats_min) + ',Max:' + str(stats_max) + ',Latency:' + str(chunk_delay.total_seconds()))

                            # Clear chunk latency calculations.
                            chunk_delay = None

                            # Clear statistics.
                            stats_count = 0
                            stats_length = 0
                            stats_min = None
                            stats_max = None

                            # Update the chunk first received time.
                            chunk_first_received = now
                        # We have received a chunk recently, so calculate the delay between them.
                        else:
                            # Calculate the delay between this and the previous packet.
                            delay = now - chunk_last_received

                            if chunk_delay:
                                chunk_delay += delay
                            else:
                                chunk_delay = delay
                    # This is the first chunk we have received since the last buffer flush.
                    else:
                        # Update the chunk first received time.
                        chunk_first_received = now

                    # Add on any previous partially complete chunks.
                    if partial_chunk: chunk = partial_chunk + chunk

                    # Where in the chunk to start reading from.
                    start_position = 0

                    # Repeat while there is an end-position.
                    while start_position < len(chunk):
                        # This is to be expected with Server-Sent Events (SSE).
                        if chunk.startswith(start_needle, start_position):
                            # Can the end_needle be found?
                            end_position = chunk.find(end_needle, start_position)

                            # Was the end_position found?
                            if end_position != -1:
                                # Start after the 'data: '.
                                start_position += len(start_needle)

                                # Add this to the queue (turning the chunk into a dict) as we will need to sort out the timestamps once all the chunks have been flushed.
                                queued_chunks.put(json.loads(chunk[start_position:end_position+1]))

                                # Gather statistics.
                                part_length = (end_position + 1) - start_position
                                stats_count += 1
                                stats_length += part_length
                                if not stats_min or part_length < stats_min: stats_min = part_length
                                if not stats_max or part_length > stats_max: stats_max = part_length

                                # The next start_position is after this current substring.
                                start_position = end_position + len(end_needle)
                            # Can happen when the connection is closed and the remaining data is flushed.
                            else:
                                # Store a reference to this ready to be consumed by the next chunk.
                                partial_chunk = chunk[start_position:]

                                # Notify the user.
                                print(str(datetime.datetime.now()) + ' - Incomplete chunk : "' + partial_chunk + '"')

                                # This completes the chunk iteration loop as this now consumes from the start to the end as there was no end_position.
                                break
                        else:
                            # This is fatal, this is not going to be a valid chunk irrespective of how much appending of future chunks we perform.
                            raise ValueError('Bad line returned from meter stream:\r\n "' + chunk[start_position:] + '"')

                    # Update the last received time.
                    chunk_last_received = now
        finally:
            # Close the database connection.
            database_connection.close()
    else:
        # Let the user know why the program is exiting.
        raise ValueError('Unable to login to the gateway (bad, expired or missing token in credentials_token.json).')

# Launch the main method if invoked directly.
if __name__ == '__main__':
    main()