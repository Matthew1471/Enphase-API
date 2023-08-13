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

import pika     # Third party library; "pip install pika"

# All the shared Enphase® functions are in these packages.
from enphase_api.cloud.authentication import Authentication
from enphase_api.local.gateway import Gateway


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

    # Gather the AMQP details from the credentials file.
    amqp_host = credentials.get('amqp_host', 'localhost')
    amqp_username = credentials.get('amqp_username', 'guest')
    amqp_password = credentials.get('amqp_password', 'guest')

    # Gather the AMQP credentials into a PlainCredentials object.
    amqp_credentials = pika.PlainCredentials(username=amqp_username, password=amqp_password)

    # The information that is visible to the broker.
    client_properties = {
        'connection_name': 'Gateway_AMQP_Meters',
        'product': 'Enphase-API',
        'version': '0.1',
        'information': 'https://github.com/Matthew1471/Enphase-API'
    }

    # Gather the AMQP connection parameters.
    amqp_parameters = pika.ConnectionParameters(
        host=amqp_host,
        credentials=amqp_credentials,
        heartbeat=300,
        client_properties=client_properties
    )

    # Connect to the AMQP broker.
    with pika.BlockingConnection(parameters=amqp_parameters) as amqp_connection:
        # Get reference to the virtual channel within AMQP.
        amqp_channel = amqp_connection.channel()

        # Declare a topic exchange if one does not already exist.
        amqp_channel.exchange_declare(exchange='Enphase', exchange_type='topic')

        # Notify the user.
        print(str(datetime.datetime.now()) + ' - Collecting meter readings. To exit press CTRL+C', flush=True)

        try:
            # Repeat forever unless the user presses CTRL + C.
            while True:
                # Request the data from the meter reports.
                response = gateway.api_call('/ivp/meters/reports')

                # Add this result to the AMQP broker.
                amqp_channel.basic_publish(
                    exchange='Enphase',
                    routing_key='MeterStream',
                    body=json.dumps(dict({'timestamp':time.time(), 'readings':response}))
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