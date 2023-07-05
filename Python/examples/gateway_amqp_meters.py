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
import time     # We use the current epoch seconds for the reading times.

import pika     # Third party library; "pip install pika"

# All the shared Enphase® functions are in these packages.
from enphase_api.cloud.authentication import Authentication
from enphase_api.local.gateway import Gateway


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

    # Are we able to login to the gateway?
    if gateway.login(credentials['token']):
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
        amqp_parameters = pika.ConnectionParameters(host=amqp_host, credentials=amqp_credentials, client_properties=client_properties)

        # Connect to the AMQP broker.
        amqp_connection = pika.BlockingConnection(parameters=amqp_parameters)

        # Get reference to the virtual channel within AMQP.
        amqp_channel = amqp_connection.channel()

        # Declare a topic exchange if one does not already exist.
        amqp_channel.exchange_declare(exchange='Enphase', exchange_type='topic')

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
                        print(str(datetime.datetime.now()) + ' - Merging chunk with existing partial.')

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

                                # We calculate the timestamp of the meter readings off the time the chunk was received.
                                json_object = dict({'timestamp':time.time(), 'readings':json.loads(chunk[start_position:end_position+1])})

                                # Add this result to the AMQP broker.
                                amqp_channel.basic_publish(exchange='Enphase', routing_key='MeterStream', body=json.dumps(json_object))

                                # Output the reading time of the chunk and a value for timestamp debugging.
                                #print(str(json_object['timestamp']) + ' - ' + str(json_object['readings']['net-consumption']['ph-a']['p']) + ' W')

                                # The next start_position is after this current substring.
                                start_position = end_position + len(end_needle)
                            # Can happen when the packets are delayed.
                            else:
                                # Store a reference to this ready to be consumed by the next chunk.
                                partial_chunk = chunk[start_position:]

                                # Notify the user.
                                print(str(datetime.datetime.now()) + ' - Incomplete chunk.')

                                # This completes the chunk iteration loop as this now consumes from the start to the end as there was no end_position.
                                break
                        else:
                            # Notify the user.
                            print(str(datetime.datetime.now()) + ' - Bad line returned from meter stream.')

                            # This is fatal, this is not going to be a valid chunk irrespective of how much appending of future chunks we perform.
                            raise ValueError('Bad line returned from meter stream:\r\n "' + chunk[start_position:] + '"')
        finally:
            # Close the AMQP connection.
            amqp_connection.close()
    else:
        # Let the user know why the program is exiting.
        raise ValueError('Unable to login to the gateway (bad, expired or missing token in credentials.json).')

# Launch the main method if invoked directly.
if __name__ == '__main__':
    main()