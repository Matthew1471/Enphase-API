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

import datetime # We use the current date/time for the reading times.
import json     # This script makes heavy use of JSON parsing.
import os.path  # We check whether a file exists.

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
                print(json_object, flush=True)
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
    # Load credentials.
    with open('configuration/credentials.json', mode='r', encoding='utf-8') as json_file:
        credentials = json.load(json_file)

    # Do we have a valid JSON Web Token (JWT) to be able to use the service?
    if credentials.get('token'):
        # Check if the JWT is valid.
        if (credentials.get('gatewaySerialNumber') and not Authentication.check_token_valid(credentials['token'], credentials['gatewaySerialNumber'])) and not Authentication.check_token_valid(credentials['token']):
            # It is not valid so clear it.
            credentials['token'] = None

    # Do we still not have a Token?
    if not credentials.get('token'):
        # Do we have a way to obtain a token?
        if credentials.get('enphaseUsername') and credentials.get('enphasePassword'):
            # Create a Authentication object.
            authentication = Authentication()

            # Authenticate with Entrez (French for "Access").
            if not authentication.authenticate(credentials['enphaseUsername'], credentials['enphasePassword']):
                raise ValueError('Failed to login to Enphase Authentication server ("Entrez")')

            # Does the user want to target a specific gateway or all uncommissioned ones?
            if credentials.get('gatewaySerialNumber'):
                # Get a new gateway specific token (installer = short-life, owner = long-life).
                credentials['token'] = authentication.get_token_for_commissioned_gateway(credentials['gatewaySerialNumber'])
            else:
                # Get a new uncommissioned gateway specific token.
                credentials['token'] = authentication.get_token_for_uncommissioned_gateway()

            # Update the file to include the modified token.
            with open('configuration/credentials.json', mode='w', encoding='utf-8') as json_file:
                json.dump(credentials, json_file, indent=4)
        else:
            # Let the user know why the program is exiting.
            raise ValueError('Unable to login to the gateway (bad, expired or missing token in credentials.json).')

    # Did the user override the library default hostname to the Gateway?
    if credentials.get('host'):
        # Download and store the certificate from the gateway so all future requests are secure.
        if not os.path.exists('configuration/gateway.cer'): Gateway.trust_gateway(credentials['host'])

        # Get an instance of the Gateway API wrapper object (using the config specified hostname).
        gateway = Gateway(credentials['host'])
    else:
        # Download and store the certificate from the gateway so all future requests are secure.
        if not os.path.exists('configuration/gateway.cer'): Gateway.trust_gateway()

        # Get an instance of the Gateway API wrapper object (using the library default hostname).
        gateway = Gateway()

    # Are we not able to login to the gateway?
    if not gateway.login(credentials['token']):
        # Let the user know why the program is exiting.
        raise ValueError('Unable to login to the gateway (bad, expired or missing token in credentials.json).')

    # Gather the database details from the credentials file.
    database_host = credentials.get('database_host', 'localhost')
    database_username = credentials.get('database_username', 'root')
    database_password = credentials.get('database_password', '')
    database_database = credentials.get('database_database', 'Enphase')

    # Connect to the MySQL/MariaDB database.
    database_connection = mysql.connector.connect(host=database_host, user=database_username, password=database_password, database=database_database)

    # Get references to 2 database cursors (that will PREPARE duplicate SQL statements).
    database_cursor_meter_reading = database_connection.cursor(prepared=True)
    database_cursor_meter_reading_result = database_connection.cursor(prepared=True)

    try:
        # Request the data from the meter stream.
        with gateway.api_call_stream('/stream/meter') as stream:
            # The start and end strings for each chunk.
            start_needle = 'data: '
            end_needle = '}\r\n\r\n'

            # We allow partial chunks.
            partial_chunk = None

            # Chunks are received when the gateway flushes its buffer.
            for chunk in stream.iter_content(chunk_size=1024, decode_unicode=True):
                # Add on any previous partially complete chunks.
                if partial_chunk:
                    # Append the previous partial_chunk to this chunk.
                    chunk = partial_chunk + chunk

                    # Notify the user.
                    print(str(datetime.datetime.now()) + ' - Merging chunk with existing partial.', flush=True)

                    # This partial is now consumed.
                    partial_chunk = None

                # Where in the chunk to start reading from.
                start_position = 0

                # Repeat while there is an end-position.
                while start_position < len(chunk):
                    # This is to be expected with Server-Sent Events (SSE).
                    if chunk.startswith(start_needle, start_position) or (len(chunk) - start_position) < len(start_needle):
                        # Can the end_needle be found?
                        end_position = chunk.find(end_needle, start_position)

                        # Was the end_position found?
                        if end_position != -1:
                            # Start after the 'data: '.
                            start_position += len(start_needle)

                            # Add this result to the database.
                            add_results_to_database(database_connection=database_connection, database_cursor_meter_reading=database_cursor_meter_reading, database_cursor_meter_reading_result=database_cursor_meter_reading_result, timestamp=datetime.datetime.now(), json_object=json.loads(chunk[start_position:end_position+1]))

                            # Output the reading time of the chunk and a value for timestamp debugging.
                            #print(str(datetime.datetime.now()) + ' - ' + str(json_object['net-consumption']['ph-a']['p']) + ' W', flush=True)

                            # The next start_position is after this current substring.
                            start_position = end_position + len(end_needle)
                        # Can happen when the packets are delayed.
                        else:
                            # Store a reference to this ready to be consumed by the next chunk.
                            partial_chunk = chunk[start_position:]

                            # Notify the user.
                            print(str(datetime.datetime.now()) + ' - Incomplete chunk.', flush=True)

                            # This completes the chunk iteration loop as this now consumes from the start to the end as there was no end_position.
                            break
                    else:
                        # Notify the user.
                        print(str(datetime.datetime.now()) + ' - Bad line returned from meter stream.', flush=True)

                        # This is fatal, this is not going to be a valid chunk irrespective of how much appending of future chunks we perform.
                        raise ValueError('Bad line returned from meter stream:\r\n "' + chunk[start_position:] + '"')
    finally:
        # Close the database connection.
        database_connection.close()

# Launch the main method if invoked directly.
if __name__ == '__main__':
    main()