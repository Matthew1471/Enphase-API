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

import mysql.connector # Third party library; "pip install mysql-connector-python".
import pika            # Third party library; "pip install pika".


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
            raise ValueError('Unexpected meter reading report type "' + report_type + '" in JSON.')

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

def main():
    # Load credentials.
    with open('configuration/credentials_token.json', mode='r', encoding='utf-8') as json_file:
        credentials = json.load(json_file)

    # Gather the AMQP details from the credentials file.
    amqp_host = credentials.get('amqp_host', 'localhost')
    amqp_username = credentials.get('amqp_username', 'guest')
    amqp_password = credentials.get('amqp_password', 'guest')

    # Gather the AMQP credentials into a PlainCredentials object.
    amqp_credentials = pika.PlainCredentials(username=amqp_username, password=amqp_password)

    # The information that is visible to the broker.
    client_properties = {
        'connection_name': 'AMQP_Database_Meters',
        'product': 'Enphase-API',
        'version': '0.1',
        'information': 'https://github.com/Matthew1471/Enphase-API'
    }

    # Gather the AMQP connection parameters.
    amqp_parameters = pika.ConnectionParameters(
        host=amqp_host,
        credentials=amqp_credentials,
        client_properties=client_properties
    )

    try:
        # Connect to the AMQP broker.
        with pika.BlockingConnection(parameters=amqp_parameters) as amqp_connection:

            # Get reference to the virtual connection within AMQP.
            amqp_channel = amqp_connection.channel()

            # Declare a queue (if it does not already exist).
            amqp_result = amqp_channel.queue_declare(queue='Enphase_Database', durable=True)

            # Bind the queue to the exchange (if it is not already bound).
            amqp_channel.queue_bind(exchange='Enphase', queue=amqp_result.method.queue, routing_key='#')

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

                def amqp_callback(ch, method, properties, body):
                    # Convert the string back to JSON.
                    json_object = json.loads(body)

                    # Add this message to the database.
                    add_results_to_database(
                        database_connection=database_connection,
                        database_cursor_meter_reading=database_cursor_meter_reading,
                        database_cursor_meter_reading_result=database_cursor_meter_reading_result,
                        timestamp=json_object['timestamp'],
                        json_object=json_object['readings']
                    )

                # Create a consumer.
                amqp_channel.basic_consume(
                    queue=amqp_result.method.queue,
                    on_message_callback=amqp_callback,
                    auto_ack=True,
                    exclusive=True,
                    consumer_tag="AMQP_Database_Meters"
                )

                # Start consuming.
                print(str(datetime.datetime.now()) + ' - Waiting for messages. To exit press CTRL+C', flush=True)
                amqp_channel.start_consuming()
    except KeyboardInterrupt:
        print(str(datetime.datetime.now()) + ' - Closing connections.', flush=True)
    except Exception:
        # Notify the user.
        print(str(datetime.datetime.now()) + ' - Exception occurred.', flush=True)

        # Re-raise.
        raise

# Launch the main method if invoked directly.
if __name__ == '__main__':
    main()