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

import json     # This script makes heavy use of JSON parsing.
import os.path  # We check whether a file exists and manipulate filepaths.

# All the shared Enphase® functions are in these packages.
from enphase_api.cloud.authentication import Authentication
from enphase_api.local.gateway import Gateway

def get_header(endpoint):
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

    result += 'A HTTP GET to `' + endpoint['url'] + '` can be used to get a JSON formatted object of the ' + endpoint['name'] + ' data.\n'

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

def get_schema(json_object, table_name=''):
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
            child_tables[child_table_name] = get_schema(json_value, child_table_name)

            # Add the type of this key.
            current_table_fields[json_key] = {'type':'Object', 'value':'`' + child_table_name + '`'} 

        # Is this a list of values?
        elif isinstance(json_value, list):

            # Are there any values and is the first value an object?
            if len(json_value) > 0 and isinstance(json_value[0], dict):
                # Get a sensible name for this nested table (that preserves its scope).
                child_table_name = (table_name + '.' if len(table_name) else '') + json_key.capitalize()
                
                # Take each of the items in the list and combine all the keys and their metadata.
                list_items = {}
                for list_item in json_value:
                    list_items.update(get_schema(list_item, child_table_name)[child_table_name])
                
                # Find keys that are not present in all items and mark those keys as optional.
                for list_item_key, list_item_value in list_items.items():
                    if any(list_item_key not in item for item in json_value):
                        list_item_value['optional'] = True

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

def table_to_string(table_name, table):
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
        schema_string += '|`' + name + (' (Optional)' if 'optional' in metadata and metadata['optional'] else '') + '`\n'
        schema_string += '|' + metadata['type'] + '\n'
        schema_string += '|' + metadata['value'] + '\n'
        schema_string += '|???\n\n'

    # End of Table.
    schema_string += '|===\n'

    return schema_string

def add_example(url, json_object):
    output = '\n'
    output += '== Examples\n\n'
    output += '=== Get Data\n'
    output += '.GET *' + url + '* Response\n'
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
    if not (credentials.get('token') or Authentication.check_token_valid(credentials['token'], credentials['gatewaySerialNumber'])):
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
    if 1==1 or gateway.login(credentials['token']):

        # Load endpoints.
        with open('resources/API_Details.json', mode='r', encoding='utf-8') as json_file:
            endpoint_metadata = json.load(json_file)

        # The URLs we will be describing.
        endpoint = endpoint_metadata['Production']

        # Perform a GET request on the resource.
        #json_object = gateway.api_call(endpoint['url'])
        json_object = json.loads('{"production":[{"type":"inverters","activeCount":10,"readingTime":0,"wNow":0,"whLifetime":314441},{"type":"eim","activeCount":1,"measurementType":"production","readingTime":1676757919,"wNow":-0.0,"whLifetime":276144.03,"varhLeadLifetime":0.024,"varhLagLifetime":205023.785,"vahLifetime":458229.78,"rmsCurrent":0.763,"rmsVoltage":239.037,"reactPwr":175.992,"apprntPwr":182.823,"pwrFactor":0.0,"whToday":3694.0,"whLastSevenDays":49814.0,"vahToday":7451.0,"varhLeadToday":2.0,"varhLagToday":3909.0}],"consumption":[{"type":"eim","activeCount":1,"measurementType":"total-consumption","readingTime":1676757919,"wNow":370.516,"whLifetime":781493.591,"varhLeadLifetime":765078.737,"varhLagLifetime":205039.176,"vahLifetime":1254065.428,"rmsCurrent":4.567,"rmsVoltage":239.146,"reactPwr":-938.239,"apprntPwr":1092.2,"pwrFactor":0.34,"whToday":15261.591,"whLastSevenDays":101733.591,"vahToday":21683.428,"varhLeadToday":14879.737,"varhLagToday":3905.176},{"type":"eim","activeCount":1,"measurementType":"net-consumption","readingTime":1676757919,"wNow":370.516,"whLifetime":646231.428,"varhLeadLifetime":765078.713,"varhLagLifetime":15.391,"vahLifetime":1254065.428,"rmsCurrent":3.804,"rmsVoltage":239.255,"reactPwr":-762.247,"apprntPwr":908.029,"pwrFactor":0.41,"whToday":0,"whLastSevenDays":0,"vahToday":0,"varhLeadToday":0,"varhLagToday":0}],"storage":[{"type":"acb","activeCount":0,"readingTime":0,"wNow":0,"whNow":0,"state":"idle"}]}')
        
        # Add the documentation header.
        output = get_header(endpoint)
        
        # Get the schema recursively.
        json_schema = get_schema(json_object)

        # Ouput all the tables.
        output += '\n== Response\n'

        for table_name, table in json_schema.items():
            output += table_to_string(table_name, table)

        # Take the obtained JSON as an example.
        output += add_example(endpoint['url'], json_object)

        filename = 'output/' + endpoint['documentation']

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