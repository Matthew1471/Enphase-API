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

"""
Generates the Enphase-API documentation in AsciiDoc.

This module takes:
- Each endpoint in the metadata document.
- Attempts to call any undocumented endpoints.
- Determines their schema.
- Writes the documentation of the endpoint to disk.
"""

import json     # This script makes heavy use of JSON parsing.
import os.path  # We check whether a file exists and manipulate filepaths.

# All the shared Enphase® functions are in these packages.
from enphase_api.cloud.authentication import Authentication
from enphase_api.local.gateway import Gateway

# Enable this mode to perform no actual requests.
TEST_ONLY = False

# This script's version.
VERSION = 0.1

class JSONSchema:
    """
    This class provides static methods to determine the JSON schema from a sample JSON string.
    """

    @staticmethod
    # pylint: disable=unidiomatic-typecheck
    def get_type_string(json_value):
        """
        This static method takes a JSON value and returns a string of the JSON type.
        """
        if type(json_value) in (int, float):
            return 'Number'
        # In Python, a bool is a sub-class of int.
        if type(json_value) is bool:
            return 'Boolean'
        if type(json_value) is str:
            return 'String'
        if json_value is None:
            return 'Null'

        return 'Unknown'

    @staticmethod
    def get_table_name(table_field_map, original_table_name, json_key):
        """
        This static method takes:

        - A table_field_map.
        - What the table name was called originally.
        - The current key.

        and returns either:

        - The overriden table name as per the table_field_map.
        or
        - It generates a table name making use of the original_table_name and the key.

        Making use of the original_table_name ensures the scope is preserved.
        """
        # We can override some object names (and merge metadata).
        if table_field_map and (key_metadata := table_field_map.get(json_key)) and type(key_metadata) == dict and (value_name := key_metadata.get('value_name')):
            # This name has been overridden.
            return value_name

        # Otherwise, is this not the root table?
        if original_table_name and original_table_name != '.':
            # Get a sensible default name for this table (that preserves its JSON scope).
            return original_table_name + '.' + str(json_key).capitalize()

        # Return just the capitalised JSON key.
        return str(json_key).capitalize()

    @staticmethod
    # pylint: disable=unidiomatic-typecheck
    # pylint: disable-next=invalid-name
    def merge_dictionaries(a, b, path=None, mark_optional_at_depth=None):
        """
        Recursively merges 'b' into 'a' and then returns 'a'.

        If mark_optional_at_depth is set then any additions,
        result in a "optional" key being set at that path.

        If at a current path one side is a dictionary but the other is a string,
        then the string is merged into the dictionary as a description.

        If it is unsafe to merge a path it will return an error.

        Inspired by:
        https://stackoverflow.com/questions/7204805/how-to-merge-dictionaries-of-dictionaries
        """
        # What path is currently being inspected.
        if path is None:
            path = []

        # Take each of the keys in dictionary 'b'.
        for key in b:
            # Does the same key exist in 'a'?
            if key in a:
                # Are both dictionaries?
                if type(a[key]) is dict and type(b[key]) is dict:
                    # Merge the child dictionaries by invoking this recursively.
                    JSONSchema.merge_dictionaries(a[key], b[key], path + [str(key)], mark_optional_at_depth)
                # Are they otherwise the same values.
                elif a[key] == b[key]:
                    # Same values do not require copying.
                    pass
                # If 'a' is a dictionary but 'b' is a string.
                elif type(a[key]) is dict and type(b[key]) is str:
                    # Set the description in the 'a' dictionary to include the 'b' string.
                    a[key]['description'] = b[key]
                # If 'b' is a dictionary but 'a' is a string.
                elif type(b[key]) is dict and type(a[key]) is str:
                    # Set the description in the 'b' dictionary to include the 'a' string.
                    b[key]['description'] = a[key]

                    # Replace the 'a' value with the recently updated 'b' dictionary.
                    a[key] = b[key]
                # If 'a' is an array of unknown but 'b' is defined.
                elif (key == 'type' and (a[key] == 'Array(Unknown)')) or (key == 'value' and (a[key] == 'Array of Unknown')):
                    # Unknown type and another type are compatible.
                    a[key] = b[key]
                # If 'b' is an array of unknown but 'a' is defined.
                elif (key == 'type' and (b[key] == 'Array(Unknown)')) or (key == 'value' and (b[key] == 'Array of Unknown')):
                    # Do not require copying.
                    pass
                # Do the types not otherwise match?
                else:
                    # Error as data loss could occur.
                    raise ValueError('Conflict at ' + ('.'.join(path + [str(key)])))
            # It doesn't exist in 'a', so just add it.
            else:
                # We can record where a value was optional.
                if len(path) == mark_optional_at_depth:
                    if type(b[key]) is dict and 'type' in b[key]:
                        b[key]['optional'] = True

                a[key] = b[key]

        # Do a sweeping check for keys that were in 'a' but not in 'b'.
        if len(path) == mark_optional_at_depth:
            # Take each of the keys in dictionary 'a'.
            for key in a:
                # Was this only in 'a' and not added as a result of a merge of 'b'
                # (but 'a' had a valid 'type' and was not just a description)?
                if key not in b and 'type' in a[key]:
                    a[key]['optional'] = True

        return a

    @staticmethod
    # pylint: disable=unidiomatic-typecheck
    def get_schema(json_object, table_name='.', table_field_map=None):
        """
        Recursively obtains the schema of the JSON from the specified json_object.
        If a table_name is specified this forms part of the dictionary's key.
        A table_field_map allows field names to be overridden.
        """

        # The fields in the current table.
        current_table_fields = {}

        # Store any discovered nested tables in this dictionary.
        child_tables = None

        # A field_map contains all the table metadata both static and learnt.
        # Does this table already exist in the field map?
        # Get a reference to just this table's field_map outside the loop.
        current_table_field_map = (table_field_map.get(table_name) if table_field_map else None)

        # If there is no root element (anonymous array) we must add one.
        if type(json_object) is list:
            json_object = { '.': json_object }

        # Take each key and value of the current table.
        for json_key, json_value in json_object.items():
            # Is this itself another object?
            if type(json_value) is dict:
                # We can override some object names (and merge metadata).
                child_table_name = JSONSchema.get_table_name(table_field_map=current_table_field_map, original_table_name=table_name, json_key=json_key)

                # This could return multiple tables if there are nested types.
                new_dict_schema = JSONSchema.get_schema(table_name=child_table_name, table_field_map=table_field_map, json_object=json_value)

                # Merge this table list.
                if child_tables:
                    child_tables = JSONSchema.merge_dictionaries(a=child_tables, b=new_dict_schema, mark_optional_at_depth=1)
                else:
                    child_tables = new_dict_schema

                # Add the type of this key.
                current_table_fields[json_key] = {'type':'Object', 'value':'`' + child_table_name + '` object'}

            # Is this a list of values?
            elif type(json_value) is list:
                # Are there any values.
                if len(json_value) > 0:
                    # Is the first value an object?
                    if type(json_value[0]) is dict:
                        # We can override some object names (and merge metadata).
                        child_table_name = JSONSchema.get_table_name(table_field_map=current_table_field_map, original_table_name=table_name, json_key=json_key)

                        # As this is a list each item could have different metadata;
                        # take each of the items in the list
                        # and combine all the keys and their metadata.
                        for list_item in json_value:
                            # This could return multiple tables if there are nested types.
                            new_list_schema = JSONSchema.get_schema(table_name=child_table_name, table_field_map=table_field_map, json_object=list_item)

                            # Merge this table list.
                            if child_tables:
                                child_tables = JSONSchema.merge_dictionaries(a=child_tables, b=new_list_schema, mark_optional_at_depth=1)
                            else:
                                child_tables = new_list_schema

                        # Add the type of this key.
                        current_table_fields[json_key] = {'type':'Array(Object)', 'value':'Array of `' + child_table_name + '`'}
                    # The first value must be a primitive type.
                    else:
                        # Add the type of the key.
                        type_string = JSONSchema.get_type_string(json_value[0])
                        current_table_fields[json_key] = {'type':'Array(' + type_string + ')', 'value': 'Array of ' + type_string}

                # This is just an array of standard JSON types.
                else:
                    # Add the type of this key.
                    type_string = JSONSchema.get_type_string(json_value)
                    current_table_fields[json_key] = {'type':'Array(' + type_string + ')', 'value': 'Array of ' + type_string}

            # This is just a standard JSON type.
            else:
                # Add the type of this key.
                current_table_fields[json_key] = {'type':JSONSchema.get_type_string(json_value)}

        # Prepend this parent table (all its fields have been explored for nested objects).
        tables = {}
        tables[table_name] = current_table_fields

        # Not all tables will have child tables.
        if child_tables:
            # Add any child tables to the list of tables.
            tables.update(child_tables)

        return tables

def get_header_section(name, endpoint, file_depth=0):
    """
    Returns a string with the AsciiDoc heading.

    Takes:
    - The provided name.
    - An endpoint.
    - How many sub-directories deep the file will be stored in.
    """

    # Heading.
    result = '= ' + name + '\n'

    # Table of Contents.
    result += ':toc: preamble\n'

    # Reference.
    result += 'Matthew1471 <https://github.com/matthew1471[@Matthew1471]>;\n\n'

    # Document Settings.
    result += '// Document Settings:\n\n'

    # Set the autogenerated seciond IDs to be in GitHub format, so links work across both platforms.
    result += '// Set the ID Prefix and ID Separators to be consistent with GitHub so links work '
    result += 'irrespective of rendering platform.'
    result += ' (https://docs.asciidoctor.org/asciidoc/latest/sections/id-prefix-and-separator/)\n'
    result += ':idprefix:\n'
    result += ':idseparator: -\n\n'

    # This project uses JSON code highlighting by default.
    result += '// Any code blocks will be in JSON by default.\n'
    result += ':source-language: json\n\n'

    # This will convert the admonitions to be icons rather than text (in and out of GitHub).
    result += 'ifndef::env-github[:icons: font]\n\n'

    result += '// Set the admonitions to have icons (Github Emojis) if rendered on GitHub'
    result += ' (https://blog.mrhaki.com/2016/06/awesome-asciidoctor-using-admonition.html).\n'
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
        description = endpoint['description']
        result += (description['long'] if 'long' in description else description['short']) + '\n'
    else:
        print('Warning : ' + endpoint['name'] + " does not have a description.")
        result += 'This endpoint and its purpose has not been fully documented yet.\n'

    # Heading.
    result += '\n== Introduction\n\n'

    # Introduction.
    result += 'Enphase-API is an unofficial project providing an API wrapper and the documentation '
    result += 'for Enphase(R)\'s products and services.\n\n'

    result += 'More details on the project are available from the link:'
    result += ('../' * (file_depth + 1)) + 'README.adoc[project\'s homepage].\n'

    return result

def get_request_section(request_json, file_depth=0, type_map=None):
    """
    Returns a string with the AsciiDoc request section.
    This takes:
    - The provided request_json,
    - How many sub-directories deep the file will be stored in
    - A type map listing the different types.
    """

    # Any used custom types are collected then output after the tables.
    used_custom_types = []

    # Heading.
    result = '\n== Request\n\n'

    # List available methods.
    if 'methods' in request_json:
        result += 'The `/' + request_json['uri'] + '` endpoint supports the following:\n'
        result += get_methods_section(request_json['methods'])
    else:
        result += 'A HTTP `GET` to the `/' + request_json['uri'] + '` endpoint provides the following response data.\n\n'

    # Some IQ Gateway API requests now require authorisation.
    if 'auth_required' not in request_json or request_json['auth_required'] is not False:
        result += 'As of recent Gateway software versions this request requires a valid '
        result += '`sessionid` cookie obtained by link:'
        result += ('../' * file_depth) + 'Auth/Check_JWT.adoc[Auth/Check_JWT].\n'

    # Get the request querystring table.
    if 'query' in request_json:
        # Get the table section but also any used and referenced custom types.
        table_section, used_custom_types = get_table_section(table_name='Querystring', table=request_json['query'], type_map=type_map, short_booleans=True, level=3)

        # Add the table section to the output.
        result += table_section

    # Get the request data table.
    if (field_map := request_json.get('field_map')):
        # Ouput all the request content tables.
        result += '\n=== Message Body\n'

        # Add each of the tables from the derived json_schema.
        for table_name, table in field_map.items():
            # Format the table_name.
            if table_name and table_name != '.':
                table_name = '`' + table_name + '` Object'
            else:
                table_name = 'Root'

            # Get the table section but also any used and referenced custom types.
            table_section, table_used_custom_types = get_table_section(table_name=table_name, table=table, type_map=type_map, short_booleans=True, level=4)

            # Collect any used custom_types, ignoring any duplicates.
            for custom_type in table_used_custom_types:
                if custom_type not in used_custom_types:
                    used_custom_types.append(custom_type)

            # Add the table section to the output.
            result += table_section

    return result, used_custom_types

def get_methods_section(methods):
    """
    Returns a string with the AsciiDoc methods section.
    From the provided dictionary of methods, a method table is then created.
    """

    # Sub Heading.
    result = '\n=== Methods\n'

    # Method Table Header.
    result += '[cols=\"1,2\", options=\"header\"]\n'
    result += '|===\n'
    result += '|Method\n'
    result += '|Description\n\n'

    # Take each method.
    for method, description in methods.items():
        # Method Name.
        result += '|`' + method + '`\n'

        # Method Description.
        result += '|' + description + '\n\n'

    # End of Table.
    result += '|===\n'

    return result

def get_type_section(used_custom_types, type_map):
    """
    Returns a string with the AsciiDoc types section, from the provided dictionary of custom types
    referenced and the dictionary of custom types.
    """

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
                result += '|`' + str(current_field['value']) + '`'
                if 'uncertain' in current_field:
                    result += '?'
                result += '\n'

                # Field Name.
                result += '|' + current_field['name'] + '\n'

                # Field Description.
                result += '|' + current_field['description'] + '\n\n'

            # End of Table.
            result += '|===\n'

    return result

# pylint: disable=unidiomatic-typecheck
def get_table_row(field_name, field_metadata=None, type_map=None, short_booleans=False):
    """
    Returns a string with a single AsciiDoc table row (Name, Type, Value, Description).

    Takes:
    - The provided field_name.
    - Dictionary of field_metadata.
    - A custom types map.

    Optionally the examples can include 0 or 1 to represent booleans rather than True or False.
    """

    # Field Name.
    result = '|`' + field_name + '`'
    if field_metadata and 'optional' in field_metadata and field_metadata['optional']:
        result += ' (Optional)'
    result += '\n'

    # Field Type.
    if type(field_metadata) is dict and 'type' in field_metadata:
        field_type = (field_metadata['type'] if 'type' in field_metadata else 'Unknown')
    else:
        field_type = 'Unknown'
    result += '|' + field_type + '\n'

    # Field Value.
    result += '|'
    if type(field_metadata) is dict and 'value' in field_metadata:
        result += field_metadata['value']
    # Did the user provide further details about this field in the field map?
    elif type(field_metadata) is dict and field_type not in ('Object','Array(Object)','Array(Unknown)') and (value_name := field_metadata.get('value_name')):
            result += '`' + value_name + '`'

            # Add an example value if available.
            if type_map and value_name in type_map and len(type_map[value_name]) > 0:
                result += ' (e.g. `' + str(type_map[value_name][0]['value']) + '`)'
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

        # Is this a field that has a custom type?
        if field_type not in ('Object','Array(Object)','Array(Unknown)') and (field_value_name:= field_metadata.get('value_name')):
            # Update the description to mark the type.
            result += ' In the format `' + field_value_name + '`.'
    else:
        # This field is not currently documented.
        result += '???'

    result += '\n\n'

    # Return the result but also any custom types that we referenced.
    return result

def get_table_section(table_name, table, type_map, short_booleans=False, level=3):
    """
    Returns a string and list:

    With a single AsciiDoc table (Name, Type, Values, Description) as the string,
    from the provided table_name, table, dictionary of custom types map.

    Optionally the examples can include 0 or 1 to represent booleans rather than True or False.
    The level parameter sets how deep the heading should be written.

    Any used custom types are collected and returned in the returned list.
    """

    # Sub Heading.
    result = '\n' + ('=' * level) + ' ' + table_name + '\n\n'

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
        # pylint: disable-next=unidiomatic-typecheck
        if type(field_metadata) is dict and field_metadata.get('type') not in ('Object','Array(Object)','Array(Unknown)') and (field_value_name:= field_metadata.get('value_name')):
            # We do not want to collect duplicates.
            if field_value_name not in used_custom_types:
                # Mark that we need to ouput this custom type after this table.
                used_custom_types.append(field_value_name)

    # End of Table.
    result += '|===\n'

    return result, used_custom_types

def get_example_section(uri, example_item):
    """
    Returns a string with the AsciiDoc example section, from the provided uri and example_item.
    """

    # Sub Heading.
    result = '\n\n=== ' + example_item['name'] + '\n'

    # We use a dictionary to store requests and/or responses for output as part of a loop.
    example_output = {}

    # Was there request details?
    if 'request_form' in example_item:
        example_output['Request'] = example_item['request_form']
    elif 'request_json' in example_item:
        example_output['Request'] = json.dumps(example_item['request_json'])

    # Add the response.
    if not 'response_raw' in example_item:
        if example_item['response'] != None:
            example_output['Response'] = json.dumps(example_item['response'])
        else:
            example_item['response_raw'] = 'No data was returned.'
            example_output['Response'] = example_item['response_raw']
    else:
        # We allow the raw value to opt-out of displaying anything.
        if example_item['response_raw']:
            example_output['Response'] = example_item['response_raw']

    # Add the example_output Request, Response or both.
    for example_type, example_content in example_output.items():
        # List the example request/response details.
        result += '\n.'
        result += (example_item['method'] if 'method' in example_item else 'GET')
        result += ' */' + uri
        if 'request_query' in example_item:
            result += '?' + example_item['request_query']
        result += '* ' + example_type + '\n'

        # We can override JSON responses and present raw text instead.
        if (example_type == 'Request' and 'request_form' in example_item):
            result += '[source,http]'
        elif (example_type == 'Response' and 'response_raw' in example_item):
            result += '[listing]'
        else:
            result += '[source,json,subs="+quotes"]'

        # Add the example content (JSON or raw).
        result += '\n----\n'
        result += example_content + '\n'
        result += '----'

    return result

def get_not_yet_documented():
    """
    Returns a string with the AsciiDoc "Not Yet Documented" section.
    This is a placeholder for endpoints that cannot be fully documented yet.
    """

    # Heading.
    result = '\n== Request & Response\n\n'

    # Placeholder Text.
    result += 'This has not yet been documented. Please check back later.\n'

    return result

def process_single_endpoint(gateway, key, endpoint):
    """
    Generates the Enphase-API documentation in AsciiDoc for a specific endpoint.

    This takes:
     - An instance of the gateway wrapper.
     - The metadata key.
     - A single endpoint to document.
    """

    # Skip if the endpoint is not meant to be documented.
    if not 'documentation' in endpoint:
        print('Warning : Skipping \'' + key + '\' due to lack of \'documentation\' filepath.')
        return False

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
        endpoint_response = endpoint['response'] if 'response' in endpoint else {}

        # Are there any examples?
        if 'examples' in endpoint_request:
            previous_request_schema = None
            previous_response_schema = None

            # Take each of the examples to learn the schema.
            for example in endpoint_request['examples']:
                # The user can supply the JSON to use instead of us directly querying for it.
                if 'response_json' in example:
                    if example['response_json']:
                        # Extract the sample and use it as the response.
                        example['response'] = json.loads(example['response_json'])
                    else:
                        example['response'] = None
                # The user can disable requesting data for a specific endpoint example.
                elif 'disabled' in example:
                    print('Warning : Skipping disabled example \'' + example['name'] + '\' for \'' + key + '\'.')
                    continue
                elif not TEST_ONLY:
                    # Notify the user we are about to query the API.
                    print('Requesting example \'' + example['name'] + '\' for \'' + key + '\'.')

                    # Build the URI.
                    request_uri = '/' + endpoint_request['uri']
                    if 'request_query' in example:
                        request_uri += '?' + example['request_query']

                    # The API supports a mixture of JSON and form payloads.
                    if 'request_form' not in example:
                        # Some API requests contain JSON payloads.
                        if 'request_json' in example:
                            data = example['request_json']
                        else:
                            data = None

                        if 'response_raw' not in example:
                            # Perform a request on the resource (with a JSON response).
                            example['response'] = gateway.api_call(path=request_uri, method=example.get('method'), json=data)
                        else:
                            # Perform a request on the resource (but with a raw response).
                            example['response'] = None
                            example['response_raw'] = gateway.api_call(path=request_uri, method=example.get('method'), json=data, response_raw=True)
                    else:
                        # This is a legacy form API request.
                        example['response'] = gateway.api_call_form(path=request_uri, method=example.get('method'), data=example['request_form'])

                    # This variable can be inspected to hardcode a sample in API_Details.
                    if 'response_raw' not in example:
                        debug_variable = json.dumps({ 'response_json': json.dumps(example['response']) })[1:-1]
                    else:
                        # This prevents the program from attempting to parse it as JSON.
                        debug_variable = '"response_json": null,\n'
                        debug_variable += json.dumps({ 'response_raw': example['response_raw']})[1:-1]

                    # This is a good place to set a breakpoint to cache the response.
                    set_breakpoint_here = debug_variable
                else:
                    print('Warning : Skipping example \'' + example['name'] + '\' for \'' + key + '\' as no sample JSON defined and TEST_ONLY is True.')
                    continue

                # It's possible for an API endpoint to return nothing.
                if example['response']:
                    # Obtain the response schema for the current example.
                    # We can override some known types, provide known value criteria
                    # and descriptions using the field_map.
                    current_response_schema = JSONSchema.get_schema(table_field_map=endpoint_response.get('field_map'), json_object=example['response'])

                    # Have we already obtained a response schema from a previous example?
                    if previous_response_schema:
                        # Merge the current_response_schema into the previous_response_schema.
                        previous_response_schema = JSONSchema.merge_dictionaries(a=previous_response_schema, b=current_response_schema, mark_optional_at_depth=1)
                    else:
                        # Just take the current_response_schema as the previous_response_schema.
                        previous_response_schema = current_response_schema

                # Is there JSON request information?
                if 'request_json' in example:
                    # Extract the sample and use it as the request.
                    example['request_json'] = json.loads(example['request_json'])

                    # Obtain the request schema for the current example.
                    # We can override some known types, provide known value criteria
                    # and descriptions using the field_map.
                    current_request_schema = JSONSchema.get_schema(table_field_map=endpoint_request.get('field_map'), json_object=example['request_json'])

                    # Have we already obtained a request schema from a previous example?
                    if previous_request_schema:
                        # Merge the current_request_schema with the previous_request_schema.
                        previous_request_schema = JSONSchema.merge_dictionaries(a=previous_request_schema, b=current_request_schema, mark_optional_at_depth=1)
                    else:
                        # Take the current_request_schema as the previous_request_schema.
                        previous_request_schema = current_request_schema

            # Is there a request schema to process?
            if previous_request_schema:
                # Merge the request field_map dictionary with any configured values.
                if 'field_map' in endpoint_request:
                    previous_request_schema = JSONSchema.merge_dictionaries(a=previous_request_schema, b=endpoint_request['field_map'], mark_optional_at_depth=None)

                endpoint_request['field_map'] = previous_request_schema

            # Is there a response schema to process?
            if previous_response_schema:
                # Merge the response field_map dictionary with any configured values.
                if 'field_map' in endpoint_response:
                    previous_response_schema = JSONSchema.merge_dictionaries(a=previous_response_schema, b=endpoint_response['field_map'], mark_optional_at_depth=None)

                endpoint_response['field_map'] = previous_response_schema

        # Get the request section but also any used and referenced custom types.
        request_section, table_used_custom_types = get_request_section(endpoint_request, file_depth=file_depth-1, type_map=type_map)

        # Collect any used custom_types, ignoring any duplicates.
        for custom_type in table_used_custom_types:
            if custom_type not in used_custom_types:
                used_custom_types.append(custom_type)

        # Add the request section to the output.
        output += request_section

        # Are there any results?
        if 'field_map' in endpoint_response:
            # Ouput all the response tables.
            output += '\n== Response\n'

            # Add each of the tables from the derived json_schema.
            for table_name, table in endpoint_response['field_map'].items():
                # Format the table_name.
                if table_name and table_name != '.':
                    table_name = '`' + table_name + '` Object'
                else:
                    table_name = 'Root'

                # Get the table section but also any used and referenced custom types.
                table_section, table_used_custom_types = get_table_section(table_name=table_name, table=table, type_map=type_map)

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
            for example in endpoint_request['examples']:
                # We cannot output an example without a name.
                if not 'name' in example:
                    print('Warning : Skipping a \'' + key + '\' example as missing example name.')
                    continue

                # We cannot output an example without a response
                # (either from querying the API earlier or hardcoding one).
                if not 'response' in example:
                    print('Warning : Skipping example \'' + example['name'] + '\' for \'' + key + '\' due to lack of response.')
                    continue

                # Take the obtained JSON as an example.
                output += get_example_section(uri=endpoint_request['uri'], example_item=example)
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

    return True

def main():
    """
    Generates the Enphase-API documentation in AsciiDoc.

    This takes:
    - Each endpoint in the metadata document.
    - Attempts to call any undocumented endpoints.
    - Determines their schema.
    - Writes the documentation of the endpoint.
    """

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

        # Get an instance of the Gateway API wrapper object (using the config specified hostname).
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
            # Process this endpoint.
            process_single_endpoint(gateway=gateway, key=key, endpoint=endpoint)
    else:
        # Let the user know why the program is exiting.
        raise ValueError('Unable to login to the gateway (bad, expired or missing token in credentials.json).')

# Launch the main method if invoked directly.
if __name__ == '__main__':
    main()