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
import queue    # We use a queue as the response is buffered with no timestamps.

import mysql.connector # Third party library; "pip install mysql-connector-python"
import pika            # Third party library; "pip install pika"


# SQL statements.
add_meter_reading = ('INSERT INTO `MeterReading` (Timestamp, '
                      'Production_Phase_A_ID, Production_Phase_B_ID, Production_Phase_C_ID, '
                      'NetConsumption_Phase_A_ID, NetConsumption_Phase_B_ID, NetConsumption_Phase_C_ID, '
                      'TotalConsumption_Phase_A_ID, TotalConsumption_Phase_B_ID, TotalConsumption_Phase_C_ID'
                      ') VALUES (FROM_UNIXTIME(%s), %s, %s, %s, %s, %s, %s, %s, %s, %s)')
add_meter_reading_result = ('INSERT INTO `MeterReading_Result` (p, q, s, v, i, pf, f) VALUES (%s, %s, %s, %s, %s, %s, %s)')

def add_results_to_database(database_connection, database_cursor_meter_reading, database_cursor_meter_reading_result, body):
    # Convert the string back to JSON.
    json_object = json.loads(body)

    # Take each of the meter types.
    for meter_reading_type, meter_reading_type_result in json_object['readings'].items():
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
    database_cursor_meter_reading.execute(add_meter_reading, (json_object['timestamp'],) + production_phase_list_id + net_consumption_phase_list_id + total_consumption_phase_list_id)

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
    amqp_parameters = pika.ConnectionParameters(host=amqp_host, credentials=amqp_credentials, client_properties=client_properties)

    # Connect to the AMQP broker.
    amqp_connection = pika.BlockingConnection(parameters=amqp_parameters)

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
    database_connection = mysql.connector.connect(host=database_host, user=database_username, password=database_password, database=database_database)

    # Get references to 2 database cursors (that will PREPARE duplicate SQL statements).
    database_cursor_meter_reading = database_connection.cursor(prepared=True)
    database_cursor_meter_reading_result = database_connection.cursor(prepared=True)

    try:
        def amqp_callback(ch, method, properties, body):
            # Add this record to the database.
            add_results_to_database(database_connection=database_connection, database_cursor_meter_reading=database_cursor_meter_reading, database_cursor_meter_reading_result=database_cursor_meter_reading_result, body=body)

        # Create a consumer.
        amqp_channel.basic_consume(queue='Enphase_Database', on_message_callback=amqp_callback, auto_ack=True, exclusive=True, consumer_tag="AMQP_Database_Meters")

        # Start consuming.
        print(str(datetime.datetime.now()) + ' - Waiting for messages. To exit press CTRL+C')
        amqp_channel.start_consuming()
    except KeyboardInterrupt:
        print(str(datetime.datetime.now()) + ' - Closing connections.')
    finally:
        # Close the AMQP connection.
        amqp_connection.close()

        # Close the database connection.
        database_connection.close()

# Launch the main method if invoked directly.
if __name__ == '__main__':
    main()