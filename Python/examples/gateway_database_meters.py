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

import datetime # We output the current date/time for debugging.
import json     # This script makes heavy use of JSON parsing.
import os.path  # We check whether a file exists.
import time     # We use the current epoch seconds for reading times and to delay.

import mysql.connector # Third party library; "pip install mysql-connector-python".

# All the shared Enphase® functions are in these packages.
from enphase_api.cloud.authentication import Authentication
from enphase_api.local.gateway import Gateway


# SQL statements.
ADD_METER_READING = (
    'INSERT INTO `MeterReading` (Timestamp, '
    'Production_Phase_A_ID, Production_Phase_B_ID, Production_Phase_C_ID, '
    'NetConsumption_Phase_A_ID, NetConsumption_Phase_B_ID, NetConsumption_Phase_C_ID, '
    'TotalConsumption_Phase_A_ID, TotalConsumption_Phase_B_ID, TotalConsumption_Phase_C_ID'
    ') VALUES (FROM_UNIXTIME(%s), %s, %s, %s, %s, %s, %s, %s, %s, %s)'
)

ADD_METER_READING_RESULT = (
    'INSERT INTO `MeterReading_Result` (p, q, s, v, i, pf, f) VALUES (%s, %s, %s, %s, %s, %s, %s)'
)

# Maps each type of inserted meter reading record ID to the relevant place in our SQL parameters.
OFFSET_MAPPING = {
    'production': 0,
    'net-consumption': 1,
    'total-consumption': 2,
}

def add_results_to_database(database_connection, database_cursor_meter_reading, database_cursor_meter_reading_result, timestamp, json_object):
    # Initialise to empty by default so they convert to a database NULL if not later set.
    report_ids = [None] * 9

    # Take each of the meter types.
    for meter_readings in json_object:

        # Get the parameter index offset for this meters' meter type.
        offset = OFFSET_MAPPING.get(meter_readings['reportType'])
        if offset is None:
            raise ValueError('Unexpected meter reading report type "' + meter_readings['reportType'] + '" in JSON.')

        # Take each of the phase readings.
        for phase_count, meter_reading_result in enumerate(meter_readings['lines']):

            # Too many phases?
            if phase_count > 2:
                raise ValueError('Unexpected phase #' + phase_count + ' in JSON.')

            # Map each of the JSON values to our database columns.
            meter_reading_values = (
                meter_reading_result['actPower'],
                meter_reading_result['reactPwr'],
                meter_reading_result['apprntPwr'],
                meter_reading_result['rmsVoltage'],
                meter_reading_result['rmsCurrent'],
                meter_reading_result['pwrFactor'],
                meter_reading_result['freqHz']
            )

            try:
                # Add to the database the meter reading(s).
                # Using a dictionary instead of a tuple prevented query preparation,
                # possibly due to a MySQL Connector bug.
                database_cursor_meter_reading_result.execute(ADD_METER_READING_RESULT, meter_reading_values)
            except mysql.connector.errors.DataError:
                print(json_object, flush=True)
                raise

            # Get the result ID for this phase insert.
            report_ids[(offset*3)+phase_count] = database_cursor_meter_reading_result.lastrowid

    # Add the meters' readings.
    database_cursor_meter_reading.execute(ADD_METER_READING, (timestamp,) + tuple(report_ids))

    # Make sure data is committed to the database.
    database_connection.commit()

def get_secure_gateway_session(credentials):
    # Do we have a valid JSON Web Token (JWT) to be able to use the service?
    if not (credentials.get('token') and Authentication.check_token_valid(credentials['token'], credentials.get('gatewaySerialNumber'))):
        # It is either not present or not valid.
        raise ValueError('No or expired token.')

    # Did the user override the library default hostname to the Gateway?
    host = credentials.get('host')

    # Download and store the certificate from the gateway so all future requests are secure.
    if not os.path.exists('configuration/gateway.cer'):
        Gateway.trust_gateway(host)

    # Instantiate the Gateway API wrapper (with the default library hostname if None provided).
    gateway = Gateway(host)

    # Are we not able to login to the gateway?
    if not gateway.login(credentials['token']):
        # Let the user know why the program is exiting.
        raise ValueError('Unable to login to the gateway (bad, expired or missing token in credentials_token.json).')

    # Return the initialised gateway object.
    return gateway

def main():
    # Load credentials.
    with open('configuration/credentials_token.json', mode='r', encoding='utf-8') as json_file:
        credentials = json.load(json_file)

    # Use a secure gateway initialisation flow.
    gateway = get_secure_gateway_session(credentials)

    # Gather the database details from the credentials file.
    database_host = credentials.get('database_host', 'localhost')
    database_username = credentials.get('database_username', 'root')
    database_password = credentials.get('database_password', '')
    database_database = credentials.get('database_database', 'Enphase')

    # Connect to the MySQL/MariaDB database.
    with mysql.connector.connect(
        host=database_host,
        user=database_username,
        password=database_password,
        database=database_database
    ) as database_connection:

        # Get references to 2 database cursors (that will PREPARE duplicate SQL statements).
        database_cursor_meter_reading = database_connection.cursor(prepared=True)
        database_cursor_meter_reading_result = database_connection.cursor(prepared=True)

        # Notify the user.
        print(str(datetime.datetime.now()) + ' - Collecting meter readings. To exit press CTRL+C', flush=True)

        try:
            # Repeat forever unless the user presses CTRL + C.
            while True:
                # Request the data from the meter reports.
                response = gateway.api_call('/ivp/meters/reports')

                # Add this result to the database.
                add_results_to_database(
                    database_connection=database_connection,
                    database_cursor_meter_reading=database_cursor_meter_reading,
                    database_cursor_meter_reading_result=database_cursor_meter_reading_result,
                    timestamp=time.time(),
                    json_object=response
                )

                # Capture interval, in fractional seconds.
                time.sleep(0.99)
        except KeyboardInterrupt:
            # Notify the user.
            print(str(datetime.datetime.now()) + ' - Closing connections.', flush=True)
        except Exception:
            # Notify the user.
            print(str(datetime.datetime.now()) + ' - Exception occurred.', flush=True)

            # Re-raise.
            raise

# Launch the main method if invoked directly.
if __name__ == '__main__':
    main()