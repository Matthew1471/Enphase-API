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
import time     # We use the epoch seconds to determine the reading timestamps.

import pika     # Third party library; "pip install pika"

# All the shared Enphase® functions are in these packages.
from enphase_api.cloud.authentication import Authentication
from enphase_api.local.gateway import Gateway


def main():
    # Load credentials.
    with open('configuration/credentials_token.json', mode='r', encoding='utf-8') as json_file:
        credentials = json.load(json_file)

    # Do we have a valid JSON Web Token (JWT) to be able to use the service?
    if not (credentials.get('token') or Authentication.check_token_valid(credentials['token'], credentials['gatewaySerialNumber'])):
        # It is not valid so clear it.
        raise ValueError('No or expired token.')

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

        # Gather the AMQP connection parameters.
        amqp_parameters = pika.ConnectionParameters(host=amqp_host, credentials=amqp_credentials)

        # Connect to the AMQP broker.
        amqp_connection = pika.BlockingConnection(parameters=amqp_parameters)

        # Get reference to the virtual channel within AMQP.
        amqp_channel = amqp_connection.channel()

        # Declare a topic exchange if one does not already exist.
        amqp_channel.exchange_declare(exchange='Enphase', exchange_type='topic')

        try:
            # On a single phase system this returns almost every 21 - 23 seconds (occasionally 45 seconds), returning typically 21 - 23 results in multiple >= 701 bytes and <= 725 bytes chunks (likely a 16 KB = 16,384 byte pre-TLS pre-HTTP server-side buffer?) across 12 TCP/IP packets, so each result could be a per-second poll interval?
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
                    now = time.time()

                    # Have we received a chunk already?
                    if chunk_first_received:
                        # Was the previous chunk first recieved over 10 seconds ago so the buffer has just been flushed (we add on an allowance of 10 seconds for network latency)?
                        if chunk_first_received + 10 < now:
                            # Preserve the count of seconds to add on to the oldest reading.
                            counter = 0

                            # Flush the queue now we know how many were received in this batch.
                            while not queued_chunks.empty():
                                # Get the first chunk from the queue.
                                json_object = queued_chunks.get()

                                # We calculate the timestamp of the meter readings off the time the chunks were received.
                                json_object['timestamp'] = chunk_first_received + counter

                                # If we calculated there was a delay to the chunks we should add that on.
                                if chunk_delay:
                                    json_object['timestamp'] += chunk_delay

                                # Add this result to the AMQP broker.
                                amqp_channel.basic_publish(exchange='Enphase', routing_key='MeterStream', body=json.dumps(json_object))

                                # Output the reading time of the chunk and a value for timestamp debugging.
                                #print(str(json_object['timestamp']) + ' - ' + str(json_object['net-consumption']['ph-a']['p']) + ' W')

                                # The queue has no reliable method for determining queue size.
                                counter+=1

                            # Print statistics.
                            print(str(datetime.datetime.now()) + ' - Length:' + str(stats_length) + ',Count:' + str(stats_count) + ',Min:' + str(stats_min) + ',Max:' + str(stats_max) + ',Latency:' + str(chunk_delay))

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
                                print(str(datetime.datetime.now()) + ' - Incomplete chunk.')

                                # This completes the chunk iteration loop as this now consumes from the start to the end as there was no end_position.
                                break
                        else:
                            # This is fatal, this is not going to be a valid chunk irrespective of how much appending of future chunks we perform.
                            raise ValueError('Bad line returned from meter stream:\r\n "' + chunk[start_position:] + '"')

                    # Update the last received time.
                    chunk_last_received = now
        finally:
            # Close the AMQP connection.
            amqp_connection.close()
    else:
        # Let the user know why the program is exiting.
        raise ValueError('Unable to login to the gateway (bad, expired or missing token in credentials_token.json).')

# Launch the main method if invoked directly.
if __name__ == '__main__':
    main()