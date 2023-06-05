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

# Enable this mode to perform no actual requests.
TEST_ONLY = False

# This script's version.
VERSION = 0.1

class json_schema:
    @staticmethod
    def get_type_string(json_value):
        if type(json_value) in (int, float):
            return 'Number'
        # In Python, a bool is a sub-class of int.
        elif type(json_value) is bool:
            return 'Boolean'
        elif type(json_value) is str:
            return 'String'
        elif json_value is None:
            return 'Null'
        else:
            return 'Unknown'

    @staticmethod
    def get_table_name(table_field_map, table_name, json_key):
        # We can override some object names (and merge metadata).
        if table_field_map and (key_metadata := table_field_map.get(json_key)) and (value_name := key_metadata.get('value_name')):
            # This name has been overridden.
            table_name = value_name
        else:
            # Get a sensible default name for this table (that preserves its JSON scope).
            table_name = (table_name + '.' if table_name and table_name != '.' else '') + str(json_key).capitalize()

        return table_name

    @staticmethod
    def process_list_items(tables, table_field_map, table_name, json_value):
        # Take each of the items in the list and combine all the keys and their metadata.
        new_list_items = {}
        for list_item in json_value:
            # This could return multiple tables if there are nested types.
            new_list_schema = json_schema.get_schema(table_name=table_name, table_field_map=table_field_map, json_object=list_item)

            # Take each of the returned tables (the parent and any children).
            for child_table_key, child_table_value in new_list_schema.items():
                # This is the current parent table we were updating.
                if child_table_key == table_name:
                    new_list_items.update(new_list_schema[table_name])
                # This is an extra nested child table that was discovered.
                else:
                    # Add/Update this child table to the collection of tables.
                    # ToDo: This does not update the "optional" field at present (could potentially be added to merge_dictionaries if required?).
                    tables[child_table_key] = (json_schema.merge_dictionaries(tables[child_table_key], child_table_value) if child_table_key in tables else child_table_value)

        # If this has been mapped/merged to a duplicate table name, then we will need to append the existing dictionary.
        old_list_items = tables.get(table_name)

        # Take each of the new list item keys.
        for new_list_item_key, new_list_item_value in new_list_items.items():
            # Is this new key not present in all of the new items or not present in the old list of item keys (if applicable)?
            if any(new_list_item_key not in item for item in json_value) or (old_list_items and new_list_item_key not in old_list_items):
                # Mark this new key as optional (if it isn't already).
                if not ('optional' in new_list_item_value and new_list_item_value['optional']):
                    new_list_item_value['optional'] = True

        # If this has been mapped to a duplicate then we will need to append the existing dictionary.
        if old_list_items:
            # Take all the old list item keys.
            for old_list_item_key, old_list_item_value in old_list_items.items():
                # Is this old key not present in all of the new items?
                if any(old_list_item_key not in item for item in json_value):
                    # Mark this old key as optional (if it isn't already).
                    if not ('optional' in old_list_item_value and old_list_item_value['optional']):
                        old_list_item_value['optional'] = True

            # Merge the existing dictionary.
            tables[table_name].update(new_list_items)
        else:
            # Add the schema of this list of nested tables to child_tables.
            tables[table_name] = new_list_items

    def merge_dictionaries(a, b, path=None):
        "Recursively merges dictionary b into a.\nInspired by https://stackoverflow.com/questions/7204805/how-to-merge-dictionaries-of-dictionaries"
        # What path is currently being inspected.
        if path is None:
            path = []

        # Take each of the keys in dictionary b.
        for key in b:
            # Does the same key exist in a?
            if key in a:
                # Are both dictionaries?
                if isinstance(a[key], dict) and isinstance(b[key], dict):
                    # Merge the child dictionaries by invoking this recursively.
                    json_schema.merge_dictionaries(a[key], b[key], path + [str(key)])
                # Are they otherwise the same values.
                elif a[key] == b[key]:
                    pass # Same values do not require copying.
                # If a is a dictionary but b is a string then add the string to the dictionary as a description.
                elif isinstance(a[key], dict) and isinstance(b[key], str):
                    # Set the description in the a dictionary to include the b string.
                    a[key]['description'] = b[key]
                # If b is a dictionary but a is a string then add the string to the dictionary as a description.
                elif isinstance(b[key], dict) and isinstance(a[key], str):
                    # Set the description in the b dictionary to include the a string.
                    b[key]['description'] = a[key]

                    # Replace the a value with the recently updated b dictionary.
                    a[key] = b[key]
                # Do the types not otherwise match?
                else:
                    # Error as data loss could occur.
                    raise ValueError('Conflict at ' + ('.'.join(path + [str(key)])))
            # It doesn't, so just add it.
            else:
                a[key] = b[key]

        return a

    @staticmethod
    def get_schema(json_object, table_name='.', table_field_map=None):
        # The fields in the current table.
        current_table_fields = {}

        # Store any discovered nested tables in this dictionary.
        child_tables = {}

        # A field_map contains all the table meta-data both static and dynamic. Does this table already exist in the field map? Get a reference to just this table's field_map outside the loop.
        current_table_field_map = (table_field_map.get(table_name) if table_field_map else None)

        # If there is no root element (anonymous array) we must add one.
        if isinstance(json_object, list):
            json_object = { '.': json_object }

        # Take each key and value of the current table.
        for json_key, json_value in json_object.items():
            # Is this itself another object?
            if isinstance(json_value, dict):
                # We can override some object names (and merge metadata).
                child_table_name = json_schema.get_table_name(table_field_map=current_table_field_map, table_name=table_name, json_key=json_key)

                # This could return multiple tables if there are nested types.
                new_dict_schema = json_schema.get_schema(table_name=child_table_name, table_field_map=table_field_map, json_object=json_value)

                # Add the schema of the nested tables to child_tables (flattening the hierarchy).
                for child_table_key, child_table_value in new_dict_schema.items():
                    # Usually child_table_key is unique due to JSON scope based table naming, however if this type has been merged there can be a clash and object definitions may differ.
                    # ToDo: This does not update the "optional" field at present (could potentially be added to merge_dictionaries if required?).
                    child_tables[child_table_key] = (json_schema.merge_dictionaries(child_tables[child_table_key], child_table_value) if child_table_key in child_tables else child_table_value)

                # Add the type of this key.
                current_table_fields[json_key] = {'type':'Object', 'value':'`' + child_table_name + '` object'}

            # Is this a list of values?
            elif isinstance(json_value, list):
                # Are there any values and is the first value an object?
                if len(json_value) > 0 and isinstance(json_value[0], dict):
                    # We can override some object names (and merge metadata).
                    child_table_name = json_schema.get_table_name(table_field_map=current_table_field_map, table_name=table_name, json_key=json_key)

                    # As this is a list each item could have different metadata.
                    json_schema.process_list_items(tables=child_tables, table_field_map=table_field_map, table_name=child_table_name, json_value=json_value)

                    # Add the type of this key.
                    current_table_fields[json_key] = {'type':'Array(Object)', 'value':'Array of `' + child_table_name + '`'}

                # This is just an array of standard JSON types.
                else:
                    # Add the type of this key.
                    current_table_fields[json_key] = {'type':'Array(' + json_schema.get_type_string(json_value) + ')', 'value': 'Array of ' + json_schema.get_type_string(json_value)}

            # This is just a standard JSON type.
            else:
                # Add the type of this key.
                current_table_fields[json_key] = {'type':json_schema.get_type_string(json_value)}

        # Prepend this parent table (all its fields have been explored for nested objects).
        tables = {}
        tables[table_name] = current_table_fields
        tables.update(child_tables)

        return tables

def get_header_section(name, endpoint, file_depth=0):
    # Heading.
    result = '= ' + name + '\n'

    # Table of Contents.
    result += ':toc: preamble\n'

    # Reference.
    result += 'Matthew1471 <https://github.com/matthew1471[@Matthew1471]>;\n\n'

    # Document Settings.
    result += '// Document Settings:\n\n'

    # Set the autogenerated seciond IDs to be the GitHub format, so links work across both platforms.
    result += '// Set the ID Prefix and ID Separators to be consistent with GitHub so links work irrespective of rendering platform. (https://docs.asciidoctor.org/asciidoc/latest/sections/id-prefix-and-separator/)\n'
    result += ':idprefix:\n'
    result += ':idseparator: -\n\n'

    # This project uses JSON code highlighting by default.
    result += '// Any code blocks will be in JSON by default.\n'
    result += ':source-language: json\n\n'

    # This will convert the admonitions to be icons rather than text (both on GitHub and outside of it).
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

    # The document's metadata.
    result += '// Document Variables:\n'
    result += ':release-version: 1.0\n'
    result += ':url-org: https://github.com/Matthew1471\n'
    result += ':url-repo: {url-org}/Enphase-API\n'
    result += ':url-contributors: {url-repo}/graphs/contributors\n\n'

    # Page Description.
    if 'description' in endpoint:
        result += endpoint['description']['long'] + '\n'
    else:
        print('Warning : ' + endpoint['name'] + " does not have a description.")
        result += 'This endpoint and its purpose has not been fully documented yet.\n'

    # Heading.
    result += '\n== Introduction\n\n'

    # Introduction.
    result += 'Enphase-API is an unofficial project providing an API wrapper and the documentation for Enphase(R)\'s products and services.\n\n'

    result += 'More details on the project are available from the link:' + ('../' * (file_depth + 1)) + 'README.adoc[project\'s homepage].\n'

    return result

def get_request_section(request_json, file_depth=0, type_map=None):
    # Any used custom types are collected then output after the tables.
    used_custom_types = []

    # Check if there is anything to add to this section before printing the heading.
    if ('query' in request_json or 'data' in request_json) or ('auth_required' not in request_json or request_json['auth_required'] is not False):
        # Heading.
        result = '\n== Request\n\n'

        # Some IQ Gateway API requests now require authorisation.
        if 'auth_required' not in request_json or request_json['auth_required'] is not False:
            result += 'As of recent Gateway software versions this request requires a valid `sessionid` cookie obtained by link:' + ('../' * file_depth) + 'Auth/Check_JWT.adoc[Auth/Check_JWT].\n'

        # Get the request querystring table.
        if 'query' in request_json:
            # Get the table section but also any used and referenced custom types.
            table_section, used_custom_types = get_table_section(table_name='Request Querystring', table=request_json['query'], type_map=type_map, short_booleans=True)

            # Add the table section to the output.
            result += table_section

        # Get the request data table.
        if (field_map := request_json.get('field_map')) and len(field_map) > 0:
            # Ouput all the request content tables.
            result += '\n=== Request Content\n'

            # Add each of the tables from the derived json_schema.
            for table_name, table in field_map.items():
                # Get the table section but also any used and referenced custom types.
                table_section, table_used_custom_types = get_table_section(table_name=('`' + table_name + '` Object' if table_name and table_name != '.' else 'Root'), table=table, type_map=type_map, short_booleans=True)

                # Collect any used custom_types, ignoring any duplicates.
                for custom_type in table_used_custom_types:
                    if custom_type not in used_custom_types:
                        used_custom_types.append(custom_type)

            # Add the table section to the output.
            result += table_section
    else:
        # Skip this section.
        result = ''

    return result, used_custom_types

def get_type_section(used_custom_types, type_map):
    # Heading.
    result = '\n== Types\n'

    # Take each used custom type.
    for used_custom_type in used_custom_types:
        # Check the custom_type is defined.
        if custom_type := type_map.get(used_custom_type):
            # Type Sub Heading.
            result += '\n=== `' + used_custom_type + '` Type\n\n'

            # Type Table Header.
            result += '[cols=\"1,1,2\", options=\"header\"]\n'
            result += '|===\n'
            result += '|Value\n'
            result += '|Name\n'
            result += '|Description\n\n'

            # Type Table Rows.
            for current_field in custom_type:
                # Field Value.
                result += '|`' + current_field['value'] + '`' + ('?' if 'uncertain' in current_field else '') + '\n'

                # Field Name.
                result += '|' + current_field['name'] + '\n'

                # Field Description.
                result += '|' + current_field['description'] + '\n\n'

            # End of Table.
            result += '|===\n'

    return result

def get_table_row(field_name, field_metadata=None, type_map=None, short_booleans=False):
    # Field Name.
    result = '|`' + field_name + '`' + (' (Optional)' if field_metadata and 'optional' in field_metadata and field_metadata['optional'] else '') + '\n'

    # Field Type.
    if isinstance(field_metadata, dict) and 'type' in field_metadata:
        field_type = (field_metadata['type'] if 'type' in field_metadata else 'Unknown')
    else:
        field_type = 'Unknown'
    result += '|' + field_type + '\n'

    # Field Value.
    result += '|'
    if isinstance(field_metadata, dict) and 'value' in field_metadata:
        result += field_metadata['value']
    else:
        # Did the user provide further details about this string field in the field map?
        if field_type == 'String' and (value_name := field_metadata.get('value_name')):
            result += '`' + value_name + '`'

            # Add an example value if available.
            if value_name in type_map and len(type_map[value_name]) > 0:
                result += ' (e.g. `' + type_map[value_name][0]['value'] + '`)'
        else:
            result += field_type

            # Did the user provide further details about this number field in the field map?
            if field_type == 'Number' and field_metadata.get('allow_negative') is False:
                result += ' (> 0)'
            # Booleans will always be 0 or 1.
            elif field_type == 'Boolean':
                result += ' (e.g. `' + ('0` or `1' if short_booleans else 'true` or `false') + '`)'

    result += '\n'

    # Field Description. Did the user provide further details about this field in the field map?
    result += '|'

    # Is "Description" one of the things the user has declared.
    if field_metadata and 'description' in field_metadata:
        # Add the description.
        result += field_metadata['description']

        # Is this a string or array that has a custom type?
        if field_type == 'String' and (field_value_name:= field_metadata.get('value_name')):
            # Update the description to mark the type.
            result += ' In the format `' + field_value_name + '`.'
    else:
        # This field is not currently documented.
        result += '???'

    result += '\n\n'

    # Return the result but also any custom types that we referenced.
    return result

def get_table_section(table_name, table, type_map, short_booleans=False):
    # Sub Heading.
    result = '\n=== ' + table_name + '\n\n'

    # Table Header.
    result += '[cols=\"1,1,1,2\", options=\"header\"]\n'
    result += '|===\n'
    result += '|Name\n'
    result += '|Type\n'
    result += '|Values\n'
    result += '|Description\n\n'

    # Any used custom types are collected then output after the tables.
    used_custom_types = []

    # Table Rows (and collect any referenced custom types).
    for field_name, field_metadata in table.items():
        # Add this row.
        result += get_table_row(field_name=field_name, field_metadata=field_metadata, type_map=type_map, short_booleans=short_booleans)

        # Was this a custom type?
        if field_metadata.get('type') == 'String' and (field_value_name:= field_metadata.get('value_name')):
            # We do not want to collect duplicates.
            if field_value_name not in used_custom_types:
                # Mark that we need to ouput this custom type after this table.
                used_custom_types.append(field_value_name)

    # End of Table.
    result += '|===\n'

    return result, used_custom_types

def get_example_section(uri, example_item):
    # Sub Heading.
    result = '\n\n=== ' + example_item['name'] + '\n'

    # We use a dictionary to store requests and/or responses for output as part of a loop.
    example_output = {}

    # Was there request details?
    if 'data' in example_item:
        example_output['Request'] = json.dumps(example_item['data'])

    # Add the response.
    if not 'raw' in example_item:
        example_output['Response'] = json.dumps(example_item['response'])
    else:
        example_output['Response'] = example_item['raw']

    # Add the example_output Request, Response or both.
    for example_type, example_content in example_output.items():
        # List the example request/response details.
        result += '\n.' + (example_item['method'] if 'method' in example_item else 'GET') + ' */' + uri + ('?' + example_item['uri'] if 'uri' in example_item else '') + '* ' + example_type + '\n'

        # We can override JSON responses and present raw text instead.
        if example_type == 'Request' or 'raw' not in example_item:
            result += '[source,json,subs="+quotes"]'
        else:
            result += '[listing]'

        # Add the example content (JSON or raw).
        result += '\n----\n'
        result += example_content + '\n'
        result += '----'

    return result

def get_not_yet_documented():
    # Heading.
    result = '\n== Request & Response\n\n'

    # Placeholder Text.
    result += 'This has not yet been documented. Please check back later.\n'

    return result

def main():
    # Output program banner.
    banner = 'Gateway Generate Documentation V' + str(VERSION) + '\n'
    hyphens = '-' * len(banner) + '\n'
    print(hyphens + banner + hyphens)

    # Load credentials.
    with open('configuration/credentials_token.json', mode='r', encoding='utf-8') as json_file:
        credentials = json.load(json_file)

    # Do we have a valid JSON Web Token (JWT) to be able to use the service?
    if not TEST_ONLY and not (credentials.get('token') or Authentication.check_token_valid(credentials['token'], credentials['gatewaySerialNumber'])):
        # It is not valid so clear it.
        raise ValueError('No or expired token.')

    # Did the user override the config or library default hostname to the Gateway?
    if credentials.get('host'):
        # Download and store the certificate from the gateway so all future requests are secure.
        if not os.path.exists('configuration/gateway.cer'):
            Gateway.trust_gateway(credentials['host'])

        # Get an instance of the Gateway API wrapper object (using the hostname specified in the config).
        gateway = Gateway(credentials['host'])
    else:
        # Download and store the certificate from the gateway so all future requests are secure.
        if not os.path.exists('configuration/gateway.cer'):
            Gateway.trust_gateway()

        # Get an instance of the Gateway API wrapper object (using the library default hostname).
        gateway = Gateway()

    # Are we able to login to the gateway?
    if TEST_ONLY or gateway.login(credentials['token']):
        # Load endpoints.
        with open('resources/API_Details.json', mode='r', encoding='utf-8') as json_file:
            endpoint_metadata = json.load(json_file)

        # Take each endpoint in the metadata.
        for key, endpoint in endpoint_metadata.items():
            # Skip if the endpoint is not meant to be documented.
            if not 'documentation' in endpoint:
                print('Warning : Skipping \'' + key + '\' due to lack of \'documentation\' filepath.')
                continue

            # This script currently exclusively writes "IQ Gateway API" documents.
            endpoint['documentation'] = 'IQ Gateway API/' + endpoint['documentation']

            # Count how many sub-folders this file will be under.
            file_depth = endpoint['documentation'].count('/')

            # Add the documentation header.
            output = get_header_section(name=key, endpoint=endpoint, file_depth=file_depth)

            # We can specify the custom types of some values.
            type_map = (endpoint['type_map'] if 'type_map' in endpoint else None)

            # Any used custom types are collected then output after the tables.
            used_custom_types = []

            # Check this documentation file supports making requests to the endpoint.
            if 'request' in endpoint:
                # Get a reference to the current endpoint's request details.
                endpoint_request = endpoint['request']

                # Get a reference to the current endpoint's response details.
                if 'response' in endpoint:
                    endpoint_response = endpoint['response']
                else:
                    endpoint_response = {'field_map' : {}}

                # Take each of the examples to learn the schema.
                if 'examples' in endpoint_request:
                    json_request_schema = {}
                    json_response_schema = {}
                    for example_item in endpoint_request['examples']:
                        # The user can supply the JSON to use instead of us directly querying for it.
                        if 'sample' in example_item:
                            # Extract the sample and use it as the response.
                            example_item['response'] = json.loads(example_item['sample'])
                        elif not TEST_ONLY:
                            # Perform a GET request on the resource.
                            print('Requesting example \'' + example_item['name'] + '\' for \'' + key + '\'.')
                            example_item['response'] = gateway.api_call('/' + endpoint_request['uri'] + ('?' + example_item['uri'] if 'uri' in example_item else ''))

                            # This variable can be inspected to hardcode a sample in API_Details.
                            debug_variable = json.dumps({ 'sample': json.dumps(example_item['response']) })[1:-1]
                            set_breakpoint_here = debug_variable
                        else:
                            print('Warning : Skipping example \'' + example_item['name'] + '\' for \'' + key + '\' as no sample JSON defined and TEST_ONLY is True.')
                            continue

                        # Get the response schema recursively (we can override some known types, provide known value criteria and descriptions using the field_map).
                        json_response_schema.update(json_schema.get_schema(table_field_map=endpoint_response.get('field_map'), json_object=example_item['response']))

                        # Get the request schema recursively (we can override some known types, provide known value criteria and descriptions using the field_map).
                        if 'data' in example_item:
                            # Extract the sample and use it as the request.
                            example_item['data'] = json.loads(example_item['data'])
                            json_request_schema.update(json_schema.get_schema(table_field_map=endpoint_request.get('field_map'), json_object=example_item['data']))

                    # Merge the request field_map dictionary with any configured values.
                    if len(json_request_schema) > 0:
                        endpoint_request['field_map'] = (json_schema.merge_dictionaries(json_request_schema, endpoint_request['field_map']) if 'field_map' in endpoint_request else json_request_schema)

                    # Merge the response field_map dictionary with any configured values.
                    endpoint_response['field_map'] = json_schema.merge_dictionaries(json_response_schema, endpoint_response['field_map'])

                # Get the request section but also any used and referenced custom types.
                request_section, table_used_custom_types = get_request_section(endpoint_request, file_depth=file_depth-1, type_map=type_map)

                # Collect any used custom_types, ignoring any duplicates.
                for custom_type in table_used_custom_types:
                    if custom_type not in used_custom_types:
                        used_custom_types.append(custom_type)

                # Add the request section to the output.
                output += request_section

                # Are there any results?
                if len(endpoint_response['field_map']) > 0:
                    # Ouput all the response tables.
                    output += '\n== Response\n'

                    # Add each of the tables from the derived json_schema.
                    for table_name, table in endpoint_response['field_map'].items():
                        # Get the table section but also any used and referenced custom types.
                        table_section, table_used_custom_types = get_table_section(table_name=('`' + table_name + '` Object' if table_name and table_name != '.' else 'Root'), table=table, type_map=type_map)

                        # Collect any used custom_types, ignoring any duplicates.
                        for custom_type in table_used_custom_types:
                            if custom_type not in used_custom_types:
                                used_custom_types.append(custom_type)

                        # Add the table section to the output.
                        output += table_section

                # Output any used custom types.
                if type_map and len(used_custom_types) > 0:
                    # Ouput the custom type section.
                    output += get_type_section(used_custom_types, type_map)

                # Add the examples.
                if 'examples' in endpoint_request:
                    output += '\n== Examples'

                    # There can be multiple examples for the same endpoint.
                    for example_item in endpoint_request['examples']:
                        # We cannot output an example without a response (either from querying the API earlier or hardcoding one).
                        if not 'response' in example_item:
                            print('Warning : Skipping example \'' + example_item['name'] + '\' for \'' + key + '\' due to lack of response.')
                            continue

                        # Take the obtained JSON as an example.
                        output += get_example_section(uri=endpoint_request['uri'], example_item=example_item)
            else:
                # Add placeholder text.
                output += get_not_yet_documented()

            # Generate a suitable filename to store our documentation in.
            filename = '../../Documentation/' + endpoint['documentation']

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