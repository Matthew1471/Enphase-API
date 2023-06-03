﻿#!/usr/bin/env python
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

import json     # This script makes heavy use of JSON parsing.
import os.path  # We check whether a file exists and manipulate filepaths.

# All the shared Enphase® functions are in these packages.
from enphase_api.cloud.authentication import Authentication
from enphase_api.local.gateway import Gateway

# Enable this mode to perform no actual requests.
test_only = True

def get_header_section(endpoint):
    result = '= ' + endpoint['name'] + '\n'
    result += ':toc: preamble\n'
    result += 'Matthew1471 <https://github.com/matthew1471[@Matthew1471]>;\n\n'

    result += '// Document Settings:\n\n'

    result += '// Set the ID Prefix and ID Separators to be consistent with GitHub so links work irrespective of rendering platform. (https://docs.asciidoctor.org/asciidoc/latest/sections/id-prefix-and-separator/)\n'
    result += ':idprefix:\n'
    result += ':idseparator: -\n\n'

    result += '// Any code blocks will be in JSON5 by default.\n'
    result += ':source-language: json5\n\n'

    result += 'ifndef::env-github[:icons: font]\n\n'

    result += '// Set the admonitions to have icons (Github Emojis) if rendered on GitHub (https://blog.mrhaki.com/2016/06/awesome-asciidoctor-using-admonition.html).\n'
    result += 'ifdef::env-github[]\n'
    result += ':status:\n'
    result += ':caution-caption: :fire:\n'
    result += ':important-caption: :exclamation:\n'
    result += ':note-caption: :paperclip:\n'
    result += ':tip-caption: :bulb:\n'
    result += ':warning-caption: :warning:\n'
    result += 'endif::[]\n\n'

    result += '// Document Variables:\n'
    result += ':release-version: 1.0\n'
    result += ':url-org: https://github.com/Matthew1471\n'
    result += ':url-repo: {url-org}/Enphase-API\n'
    result += ':url-contributors: {url-repo}/graphs/contributors\n\n'

    result += 'A HTTP GET to `/' + endpoint['uri'] + '` can be used to get ' + endpoint['long_description'] + '.\n'

    result += '\n== Introduction\n\n'

    result += 'Enphase-API is an unofficial project providing an API wrapper and the documentation for Enphase(R)\'s products and services.\n\n'

    result += 'More details on the project are available from the link:../../../README.adoc[project\'s homepage].\n'

    return result

def get_request_section(request_json):
    # Heading.
    result = '\n== Request\n\n'

    result += 'As of recent Gateway software versions this request requires a valid `sessionid` cookie obtained by link:../Auth/Check_JWT.adoc[Auth/Check_JWT].\n'

    result += '\n=== Request Querystring\n\n'

    # Table Header.
    result += '[cols="1,1,1,2", options="header"]\n'
    result += '|===\n'
    result += '|Name\n'
    result += '|Type\n'
    result += '|Values\n'
    result += '|Description\n\n'

    # Table rows.
    for query_item in request_json:
        result += '|`' + query_item['name'] + '` ' + ('(Optional)' if 'optional' in query_item and query_item['optional'] else '') + '\n'
        result += '|' + query_item['type'] + '\n'
        result += '|' + query_item['value'] + '\n'
        result += '|' + query_item['description'] + '\n\n'

    # End of Table.
    result += '|===\n'

    return result

def get_type_string(json_value):
    if isinstance(json_value, (int, float)):
        return 'Number'
    elif isinstance(json_value, bool):
        return 'Boolean'
    elif isinstance(json_value, str):
        return 'String'
    elif json_value is None:
        return 'Null'
    else:
        return 'Unknown'

def get_schema(json_object, table_name='', object_map=None):
    # The fields in the current table.
    current_table_fields = {}

    # Store any discovered nested tables in this dictionary.
    child_tables = {}

    # Take each key and value of the current table.
    for json_key, json_value in json_object.items():

        # Is this itself another object?
        if isinstance(json_value, dict):
            # Get a sensible name for this nested table (that preserves its scope).
            child_table_name = (table_name + '.' if len(table_name) else '') + json_key.capitalize()

            # Add the schema of this nested table to child_tables.
            child_tables[child_table_name] = get_schema(json_value, table_name=child_table_name, object_map=object_map)

            # Add the type of this key.
            current_table_fields[json_key] = {'type':'Object', 'value':'`' + child_table_name + '`'} 

        # Is this a list of values?
        elif isinstance(json_value, list):

            # Are there any values and is the first value an object?
            if len(json_value) > 0 and isinstance(json_value[0], dict):

                # We can override some object names (and merge).
                child_table_name_lower = (table_name + '.' if len(table_name) else '') + json_key
                if child_table_name_lower in object_map:
                    # This name has been overridden.
                    child_table_name = object_map[child_table_name_lower]
                else:
                    # Get a sensible default name for this nested table (that preserves its JSON scope).
                    child_table_name = (table_name + '.' if len(table_name) else '') + json_key.capitalize()

                # Take each of the items in the list and combine all the keys and their metadata.
                list_items = {}
                for list_item in json_value:
                    list_items.update(get_schema(list_item, table_name=child_table_name, object_map=object_map)[child_table_name])

                # If this has been mapped/merged to a duplicate table name then we will need to append the existing dictionary.
                if child_table_name in child_tables:
                    # Get a reference to the existing list items.
                    old_list_items = child_tables[child_table_name]
                else:
                    old_list_items = None

                # Take each of the new list item keys.
                for new_list_item_key, new_list_item_value in list_items.items():
                    # Is this new key not present in all of the new items or not present in the old list of item keys (if applicable)?
                    if any(new_list_item_key not in item for item in json_value) or (old_list_items and new_list_item_key not in old_list_items):
                        # Mark this new key as optional.
                        new_list_item_value['optional'] = True
                        
                # If this has been mapped to a duplicate then we will need to append the existing dictionary.
                if old_list_items:
                    # Take all the old list item keys.
                    for old_list_item_key, old_list_item_value in old_list_items.items():
                        # Is this old key not present in all the new items?
                        if any(old_list_item_key not in item for item in json_value):
                            # Mark this old key as optional.
                            old_list_item_value['optional'] = True

                    # Get the existing dictionary.
                    child_tables[child_table_name].update(list_items)
                else:
                    # Add the schema of this list of nested tables to child_tables.
                    child_tables[child_table_name] = list_items

                # Add the type of this key.
                current_table_fields[json_key] = {'type':'Array(Object)', 'value':'Array of `' + child_table_name + '`'} 

            # This is just an array of standard JSON types.
            else:
                # Add the type of this key.
                current_table_fields[json_key] = {'type':'Array(' + get_type_string(json_value) + ')', 'value':get_type_string(json_value)} 

        # This is just a standard JSON type.
        else:
            # Add the type of this key.
            current_table_fields[json_key] = {'type':get_type_string(json_value), 'value':get_type_string(json_value)}        
    
    # Prepend this parent table (all its fields have been explored for nested objects).
    tables = {}
    tables[table_name] = current_table_fields
    tables.update(child_tables)

    return tables

def table_to_string(table_name, table, description_map=None):
    # Heading.
    schema_string = '\n=== ' + ('`' + table_name + '` Object' if len(table_name) > 0 else 'Root') + '\n\n'

    # Table Header.
    schema_string += '[cols=\"1,1,1,2\", options=\"header\"]\n'
    schema_string += '|===\n'
    schema_string += '|Name\n'
    schema_string += '|Type\n'
    schema_string += '|Values\n'
    schema_string += '|Description\n\n'

    # Table Rows.
    for name, metadata in table.items():
        schema_string += '|`' + name + '`' + (' (Optional)' if 'optional' in metadata and metadata['optional'] else '') + '\n'
        schema_string += '|' + metadata['type'] + '\n'
        schema_string += '|' + metadata['value'] + '\n'

        full_name = (table_name + '.' if len(table_name) > 0 else '') + name

        schema_string += '|' + (description_map[full_name] if description_map and full_name in description_map else '???') + '\n\n'

    # End of Table.
    schema_string += '|===\n'

    return schema_string

def get_example_section(uri, example_item, json_object):
    output = '\n\n=== ' + example_item['name'] + '\n\n'

    output += '.GET */' + uri + ('?' + example_item['uri'] if 'uri' in example_item else '') + '* Response\n'
    output += '[source,json5,subs="+quotes"]\n'
    output += '----\n'
    output += str(json_object) + '\n'
    output += '----'

    return output

def main():

    # Load credentials.
    with open('configuration/credentials_token.json', mode='r', encoding='utf-8') as json_file:
        credentials = json.load(json_file)

    # Do we have a valid JSON Web Token (JWT) to be able to use the service?
    if not test_only and not (credentials.get('token') or Authentication.check_token_valid(credentials['token'], credentials['gatewaySerialNumber'])):
        # It is not valid so clear it.
        raise ValueError('No or expired token.')

    # Did the user override the config or library default hostname to the Gateway?
    if credentials.get('host'):
        # Download and store the certificate from the gateway so all future requests are secure.
        if not os.path.exists('configuration/gateway.cer'): Gateway.trust_gateway(credentials['host'])

        # Get an instance of the Gateway API wrapper object (using the hostname specified in the config).
        gateway = Gateway(credentials['host'])
    else:
        # Download and store the certificate from the gateway so all future requests are secure.
        if not os.path.exists('configuration/gateway.cer'): Gateway.trust_gateway()

        # Get an instance of the Gateway API wrapper object (using the library default hostname).
        gateway = Gateway()

    # Are we able to login to the gateway?
    if test_only or gateway.login(credentials['token']):

        # Load endpoints.
        with open('resources/API_Details.json', mode='r', encoding='utf-8') as json_file:
            endpoint_metadata = json.load(json_file)

        # The URLs we will be describing (this will later be in a for loop).
        current_endpoint = endpoint_metadata['Production']

        # Add the documentation header.
        output = get_header_section(current_endpoint)

        # Does the endpoint support any request query strings?
        if 'query' in current_endpoint['request']:
            output += get_request_section(current_endpoint['request']['query'])
        
        # Perform a GET request on the resource.
        #json_object = gateway.api_call('/' + endpoint['uri'])
        json_object = json.loads('{"production":[{"type":"inverters","activeCount":10,"readingTime":0,"wNow":0,"whLifetime":314441},{"type":"eim","activeCount":1,"measurementType":"production","readingTime":1676757919,"wNow":-0.0,"whLifetime":276144.03,"varhLeadLifetime":0.024,"varhLagLifetime":205023.785,"vahLifetime":458229.78,"rmsCurrent":0.763,"rmsVoltage":239.037,"reactPwr":175.992,"apprntPwr":182.823,"pwrFactor":0.0,"whToday":3694.0,"whLastSevenDays":49814.0,"vahToday":7451.0,"varhLeadToday":2.0,"varhLagToday":3909.0}],"consumption":[{"type":"eim","activeCount":1,"measurementType":"total-consumption","readingTime":1676757919,"wNow":370.516,"whLifetime":781493.591,"varhLeadLifetime":765078.737,"varhLagLifetime":205039.176,"vahLifetime":1254065.428,"rmsCurrent":4.567,"rmsVoltage":239.146,"reactPwr":-938.239,"apprntPwr":1092.2,"pwrFactor":0.34,"whToday":15261.591,"whLastSevenDays":101733.591,"vahToday":21683.428,"varhLeadToday":14879.737,"varhLagToday":3905.176},{"type":"eim","activeCount":1,"measurementType":"net-consumption","readingTime":1676757919,"wNow":370.516,"whLifetime":646231.428,"varhLeadLifetime":765078.713,"varhLagLifetime":15.391,"vahLifetime":1254065.428,"rmsCurrent":3.804,"rmsVoltage":239.255,"reactPwr":-762.247,"apprntPwr":908.029,"pwrFactor":0.41,"whToday":0,"whLastSevenDays":0,"vahToday":0,"varhLeadToday":0,"varhLagToday":0}],"storage":[{"type":"acb","activeCount":0,"readingTime":0,"wNow":0,"whNow":0,"state":"idle"}]}')

        # We can override some known types.
        object_map = None
        if 'map_object' in current_endpoint['response']:
            object_map = current_endpoint['response']['map_object']

        # Get the schema recursively.
        json_schema = get_schema(json_object, object_map=object_map)

        # Ouput all the response tables.
        output += '\n== Response\n'

        # We can map some known descriptions.
        description_map = None
        if 'map_description' in current_endpoint['response']:
            description_map = current_endpoint['response']['map_description']

        for table_name, table in json_schema.items():
            output += table_to_string(table_name, table, description_map)

        # Add the examples.
        output += '\n'
        output += '== Examples'

        count = 1
        for example_item in current_endpoint['request']['examples']:
            # We skip calling the first example as this has already been queried above.
            if not test_only and count > 1:
                json_object = gateway.api_call('/' + current_endpoint['uri'] + ('?' + example_item['uri'] if 'uri' in example_item else ''))

            # Take the obtained JSON as an example.
            output += get_example_section(current_endpoint['uri'], example_item, json_object)

        # Generate a suitable filename to store our documentation in.
        filename = 'output/' + current_endpoint['documentation']

        # Create any required sub-directories.
        os.makedirs(os.path.dirname(filename), exist_ok=True)

        # Write the output to the file.
        with open(filename, mode='w', encoding='utf-8') as text_file:
            text_file.write(output)

    else:
        # Let the user know why the program is exiting.
        raise ValueError('Unable to login to the gateway (bad, expired or missing token in credentials.json).')

# Launch the main method if invoked directly.
if __name__ == '__main__':
    main()