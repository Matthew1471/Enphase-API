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
Enphase® API Documentation Generator

This module is responsible for generating documentation for the Enphase® API in AsciiDoc format.
It processes endpoint metadata, attempts to call undocumented endpoints to determine their schema,
and writes the resulting documentation to disk.

Usage:
1. The module loads endpoint metadata from a JSON file containing API details.
2. It processes each endpoint by calling the API to obtain example data and schema information.
3. The generated documentation includes information about endpoints, their URIs, descriptions,
   request and response schemas, and example usage.
4. The resulting AsciiDoc files are organized into sub-directories based on the API's structure.
5. An index file summarizing all endpoints and their descriptions is also generated.

Note:
- The module requires valid API credentials to authenticate requests.
- The generated documentation can be used for reference by developers using the Enphase® API.
"""

import json         # This script makes heavy use of JSON parsing.
import os.path      # We check whether a file exists and manipulate filepaths.
import urllib.parse # We URL encode URLs.

# All the shared Enphase® functions are in these packages.
from enphase_api.cloud.authentication import Authentication
from enphase_api.local.gateway import Gateway

# Enable this mode to perform no actual requests.
TEST_ONLY = False

# This script's version.
VERSION = 0.1

class JSONSchema:
    """
    A utility class for deriving JSON schemas from sample JSON data.

    This class provides static methods for determining the JSON schema structure
    and types based on given sample JSON data.
    """

    @staticmethod
    # pylint: disable=unidiomatic-typecheck
    def get_type_string(json_value):
        """
        Determine the JSON type of the given value and return it as a string.
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
    # pylint: disable=unidiomatic-typecheck
    def get_table_name(table_field_map, original_table_name, json_key):
        """
        Determine the appropriate table name based on mappings and original names.
        """
        # We can override some object names (and merge metadata).
        if (table_field_map
                and (key_metadata := table_field_map.get(json_key))
                and type(key_metadata) is dict
                and (value_name := key_metadata.get('value_name'))):
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
                    JSONSchema.merge_dictionaries(
                        a=a[key],
                        b=b[key],
                        path=path + [str(key)],
                        mark_optional_at_depth=mark_optional_at_depth
                    )
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
                elif ((key == 'type' and (a[key] == 'Array(Unknown)'))
                        or (key == 'value' and (a[key] == 'Array of Unknown'))):
                    # Unknown type and another type are compatible.
                    a[key] = b[key]
                # If 'b' is an array of unknown but 'a' is defined.
                elif ((key == 'type' and (b[key] == 'Array(Unknown)'))
                        or (key == 'value' and (b[key] == 'Array of Unknown'))):
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
        Recursively generate the schema for the given JSON data.

        Args:
            json_object: The JSON data for which to generate the schema.
            table_name: The name of the current table (default is '.').
            table_field_map: A mapping of fields to override table names and metadata (optional).

        Returns:
            A dictionary representing the schema of the JSON data.

        Note:
            This method is designed to help in automatically deriving JSON schemas.
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
                child_table_name = JSONSchema.get_table_name(
                    table_field_map=current_table_field_map,
                    original_table_name=table_name,
                    json_key=json_key
                )

                # This could return multiple tables if there are nested types.
                new_dict_schema = JSONSchema.get_schema(
                    json_object=json_value,
                    table_name=child_table_name,
                    table_field_map=table_field_map
                )

                # Merge this table list.
                if child_tables:
                    child_tables = JSONSchema.merge_dictionaries(
                        a=child_tables,
                        b=new_dict_schema,
                        mark_optional_at_depth=1
                    )
                else:
                    child_tables = new_dict_schema

                # Add the type of this key.
                current_table_fields[json_key] = {
                    'type':'Object',
                    'value':'`' + child_table_name + '` object'
                }

            # Is this a list of values?
            elif type(json_value) is list:
                # Are there any values.
                if len(json_value) > 0:
                    # Is the first value an object?
                    if type(json_value[0]) is dict:
                        # We can override some object names (and merge metadata).
                        child_table_name = JSONSchema.get_table_name(
                            table_field_map=current_table_field_map,
                            original_table_name=table_name,
                            json_key=json_key
                        )

                        # As this is a list each item could have different metadata;
                        # take each of the items in the list
                        # and combine all the keys and their metadata.
                        for list_item in json_value:
                            # This could return multiple tables if there are nested types.
                            new_list_schema = JSONSchema.get_schema(
                                json_object=list_item,
                                table_name=child_table_name,
                                table_field_map=table_field_map
                            )

                            # Merge this table list.
                            if child_tables:
                                child_tables = JSONSchema.merge_dictionaries(
                                    a=child_tables,
                                    b=new_list_schema,
                                    mark_optional_at_depth=1
                                )
                            else:
                                child_tables = new_list_schema

                        # Add the type of this key.
                        current_table_fields[json_key] = {
                            'type':'Array(Object)',
                            'value':'Array of `' + child_table_name + '`'
                        }
                    # The first value must be a primitive type.
                    else:
                        # Add the type of the key.
                        type_string = JSONSchema.get_type_string(json_value[0])
                        current_table_fields[json_key] = {
                            'type':'Array(' + type_string + ')',
                            'value': 'Array of ' + type_string
                        }

                # This is just an array of standard JSON types.
                else:
                    # Add the type of this key.
                    type_string = JSONSchema.get_type_string(json_value)
                    current_table_fields[json_key] = {
                        'type':'Array(' + type_string + ')',
                        'value': 'Array of ' + type_string
                    }

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

class DocumentationGenerator:
    """
    A class to generate generic documentation.
    This class can be used by other documetnation generators.
    """

    @staticmethod
    def get_header_settings_and_variables():
        """
        Generates a header containing reference information, document settings, and variables.

        This function constructs a header with reference information, document settings,
        and variables for documentation generation.

        Returns:
            str: The AsciiDoc generated header content.
        """

        # Reference.
        result = 'Matthew1471 <https://github.com/matthew1471[@Matthew1471]>;\n\n'

        # Document Settings.
        result += '// Document Settings:\n\n'

        # Set the autogenerated section IDs to be in GitHub format,
        # so links work consistently across both platforms.
        result += '// Set the ID Prefix and ID Separators to be consistent with GitHub so links '
        result += 'work irrespective of rendering platform.'
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

        return result

    @staticmethod
    def get_introduction_section(description=None, file_depth=0):
        """
        Generate the introduction section for Enphase-API documentation.

        This function constructs the introduction section for the Enphase-API documentation.
        It includes a heading, an optional description, and details about the project.

        Args:
            description (str, optional): An optional description to be included in the introduction.
            file_depth (int, optional): The depth of the file in the directory structure.

        Returns:
            str: The AsciiDoc content for the introduction section.
        """

        # Heading.
        result = '== Introduction\n\n'

        if description:
            result += description + '\n\n'

        result += 'Enphase-API is an unofficial project providing an API wrapper and the '
        result += 'documentation for Enphase(R)\'s products and services.\n\n'

        result += 'More details on the project are available from the link:'
        result += ('../' * (file_depth + 1)) + 'README.adoc[project\'s homepage].\n'

        return result

class EndpointDocumentationGenerator:
    """
    A class to generate documentation for a specific API endpoint.
    """

    @staticmethod
    def get_header_section(name, endpoint, file_depth=0):
        """
        Generate the AsciiDoc heading and introductory section for documentation.

        Args:
            name (str): The name of the section.
            endpoint (dict): Information about the endpoint.
            file_depth (int, optional): How many sub-directories deep the file will be stored in.

        Returns:
            str: A string containing the AsciiDoc heading and introductory section.

        Note:
            This function constructs the heading, table of contents, shared settings, and
            introductory content for the AsciiDoc documentation of an API endpoint.
        """

        # Heading.
        result = '= ' + name + '\n'

        # Table of Contents.
        result += ':toc: preamble\n'

        # Shared block of data.
        result += DocumentationGenerator.get_header_settings_and_variables()

        # Page Description.
        long_description = None
        if 'description' in endpoint:
            description = endpoint['description']
            result += description['short'] + '\n\n'

            # We can add the long description later.
            if 'long' in description:
                long_description = description['long']
        else:
            print('Warning : "' + name + '" does not have a description.')
            result += 'This endpoint and its purpose has not been fully documented yet.\n\n'

        # Introduction.
        result += DocumentationGenerator.get_introduction_section(
            description=long_description,
            file_depth=file_depth
        )

        return result

    @staticmethod
    def get_request_section(request_json, file_depth=0, type_map=None):
        """
        Generate the AsciiDoc section for the request details of an API endpoint.

        Args:
            request_json (dict): Information about the request of the API endpoint.
            file_depth (int, optional): How many sub-directories deep the file will be stored in.
            type_map (dict, optional): A type map listing different data types.

        Returns:
            tuple: A tuple containing a string with the AsciiDoc request section and a list of used
                   custom types.

        Note:
            This function constructs the request section of the AsciiDoc documentation for an API
            endpoint, including methods, authorization requirements, querystring table, and request
            data tables.
        """

        # Any used custom types are collected then output after the tables.
        used_custom_types = []

        # Heading.
        result = '\n== Request\n\n'

        # List available methods.
        if 'methods' in request_json:
            result += 'The `/' + request_json['uri'] + '` endpoint supports the following:\n'
            result += EndpointDocumentationGenerator.get_methods_section(request_json['methods'])
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
            table_section, used_custom_types = EndpointDocumentationGenerator.get_table_section(
                table_name='Querystring',
                table=request_json['query'],
                type_map=type_map,
                short_booleans=True,
                level=3
            )

            # Add the table section to the output.
            result += table_section

        # Get the request data table.
        if (field_map := request_json.get('field_map')):
            # Ouput all the request content tables.
            result += '\n=== Message Body\n'

            # Some API endpoints may not have all available methods declared yet.
            if 'methods' in request_json:
                result += '\nWhen making a '

                already_output_method = False
                for method in request_json['methods']:
                    if method == 'GET':
                        continue
                    if already_output_method:
                        result += ' or '
                    result += '`' + method + '`'
                    already_output_method = True

                result += ' request:\n'

            # Add each of the tables from the derived json_schema.
            for table_name, table in field_map.items():
                # Format the table_name.
                if table_name and table_name != '.':
                    table_name = '`' + table_name + '` Object'
                else:
                    table_name = 'Root'

                # Get the table section but also any used and referenced custom types.
                table_section, table_used_custom_types = (
                    EndpointDocumentationGenerator.get_table_section(
                        table_name=table_name,
                        table=table,
                        type_map=type_map,
                        short_booleans=True,
                        level=4
                    )
                )

                # Collect any used custom_types, ignoring any duplicates.
                for custom_type in table_used_custom_types:
                    if custom_type not in used_custom_types:
                        used_custom_types.append(custom_type)

                # Add the table section to the output.
                result += table_section

        return result, used_custom_types

    @staticmethod
    def get_methods_section(methods):
        """
        Generate the AsciiDoc section for the supported methods of an API endpoint.

        Args:
            methods (dict):
                A dictionary of supported methods and their descriptions.

        Returns:
            str:
                A string containing the AsciiDoc methods section with a table of methods and
                descriptions.

        Note:
            This method constructs the methods section of the AsciiDoc documentation for an API
            endpoint, listing the supported HTTP methods and their descriptions.
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

    @staticmethod
    def get_example_section(uri, example_item):
        """
        Generate the AsciiDoc example section for an API endpoint using the provided URI and
        example data.

        Args:
            uri (str):
                The URI of the API endpoint.
            example_item (dict):
                Information about the example, including request and response details.

        Returns:
            str:
                A string containing the AsciiDoc example section with request and response details.

        Note:
            This method constructs the example section of the AsciiDoc documentation for an API
            endpoint, showcasing example requests and responses, including JSON formatting and raw
            text.
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
            if example_item['response'] is not None:
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

    @staticmethod
    def get_type_section(used_custom_types, type_map):
        """
        Generate the AsciiDoc section for custom data types based on the provided information.

        Args:
            used_custom_types (list): A list of custom types referenced in the documentation.
            type_map (dict): A dictionary containing definitions of custom data types.

        Returns:
            str: A string containing the AsciiDoc types section with details about
                 custom data types.

        Note:
            This method constructs the types section of the AsciiDoc documentation for custom data
            types, including values, names, and descriptions of each type's fields.
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

    @staticmethod
    # pylint: disable=unidiomatic-typecheck
    def get_table_row(field_name, field_metadata=None, type_map=None, short_booleans=False):
        """
        Generate a single AsciiDoc table row containing field details
        (Name, Type, Value, Description).

        Args:
            field_name (str): The name of the field.
            field_metadata (dict, optional):
                Metadata for the field, including type, value, description, etc.
            type_map (dict, optional):
                A map of custom data types.
            short_booleans (bool, optional):
                If True, represent booleans as 0 or 1 instead of true or false.

        Returns:
            str: A string containing the AsciiDoc table row with field details.

        Note:
            This method constructs a table row in AsciiDoc format, presenting field information
            including name, type, value, and description. It is used to create tables of fields in
            API documentation.
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
        elif (type(field_metadata) is dict
                and field_type not in ('Object','Array(Object)','Array(Unknown)')
                and (value_name := field_metadata.get('value_name'))):
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
            if (field_type not in ('Object','Array(Object)','Array(Unknown)')
                    and (field_value_name:= field_metadata.get('value_name'))):
                # Update the description to mark the type.
                result += ' In the format `' + field_value_name + '`.'
        else:
            # This field is not currently documented.
            result += '???'

        result += '\n\n'

        # Return the result but also any custom types that we referenced.
        return result

    @staticmethod
    def get_table_section(table_name, table, type_map, short_booleans=False, level=3):
        """
        Generate an AsciiDoc table section containing field details for the provided table.

        Args:
            table_name (str): The name of the table.
            table (dict): A dictionary of field metadata for the table.
            type_map (dict): A map of custom data types.
            short_booleans (bool, optional): If True, represent booleans as 0 or 1 instead of true
                                             or false.
            level (int, optional): The heading level for the section.

        Returns:
            tuple: A tuple containing a string of the AsciiDoc table section and a list of used
                   custom types.

        Note:
            This method constructs an AsciiDoc table section with field details including name,
            type, values and descriptions. The level parameter determines the depth of the heading.
            Used custom types are collected and returned as a list.
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
            result += EndpointDocumentationGenerator.get_table_row(
                field_name=field_name,
                field_metadata=field_metadata,
                type_map=type_map,
                short_booleans=short_booleans
            )

            # Was this a custom type?
            # pylint: disable-next=unidiomatic-typecheck
            if (type(field_metadata) is dict
                    and field_metadata.get('type') not in ('Object','Array(Object)','Array(Unknown)')
                    and (field_value_name:= field_metadata.get('value_name'))):
                # We do not want to collect duplicates.
                if field_value_name not in used_custom_types:
                    # Mark that we need to ouput this custom type after this table.
                    used_custom_types.append(field_value_name)

        # End of Table.
        result += '|===\n'

        return result, used_custom_types

    @staticmethod
    def get_not_yet_documented():
        """
        Generate an AsciiDoc section for endpoints that are not yet documented.

        Returns:
            str: A string containing the AsciiDoc "Not Yet Documented" section.

        Note:
            This section serves as a placeholder for endpoints that are currently not documented.
            The section informs readers that the documentation is pending.
        """

        # Heading.
        result = '\n== Request & Response\n\n'

        # Placeholder Text.
        result += 'This has not yet been documented. Please check back later.\n'

        return result

    @staticmethod
    def process_endpoint(gateway, key, endpoint):
        """
        Generate Enphase-API documentation in AsciiDoc format for a specific endpoint.

        Args:
            gateway (Gateway): An instance of the gateway wrapper.
            key (str): The metadata key for the endpoint.
            endpoint (dict): A dictionary containing the metadata of the endpoint.

        Returns:
            bool: True if the documentation was successfully generated, False otherwise.

        Note:
            This method processes the metadata of a specific API endpoint to generate AsciiDoc
            documentation. It handles generating sections for requests, responses, examples,
            custom types, and more.
        """

        # Skip if the endpoint is not meant to be documented.
        if not 'documentation' in endpoint:
            print('Warning : Skipping \'' + key + '\' due to lack of \'documentation\' filepath.')
            return False

        # Count how many sub-folders this file will be under (including the "IQ Gateway API/").
        file_depth = endpoint['documentation'].count('/') + 1

        # Add the documentation header.
        output = EndpointDocumentationGenerator.get_header_section(
            name=key.replace('/','-'),
            endpoint=endpoint,
            file_depth=file_depth
        )

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

                    # An example can over-ride a URL.
                    endpoint_uri = endpoint_request['uri']
                    if 'request_eid' in example:
                        endpoint_uri = endpoint_uri.replace('{EID}', str(example['request_eid']))

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
                        request_uri = '/' + endpoint_uri
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
                                example['response'] = gateway.api_call(
                                    path=request_uri,
                                    method=example.get('method'),
                                    json=data
                                )
                            else:
                                # Perform a request on the resource (but with a raw response).
                                example['response'] = None
                                example['response_raw'] = gateway.api_call(
                                    path=request_uri,
                                    method=example.get('method'),
                                    json=data,
                                    response_raw=True
                                )
                        else:
                            # This is a legacy form API request.
                            example['response'] = gateway.api_call(
                                path=request_uri,
                                method=example.get('method'),
                                data=example['request_form']
                            )

                        # This variable can be inspected to hardcode a sample in API_Details.
                        if 'response_raw' not in example:
                            debug_variable = json.dumps({
                                'response_json': json.dumps(example['response'])
                            })[1:-1]
                        else:
                            # This prevents the program from attempting to parse it as JSON.
                            debug_variable = '"response_json": null,\n'
                            debug_variable += json.dumps({
                                'response_raw': example['response_raw']
                            })[1:-1]

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
                        current_response_schema = JSONSchema.get_schema(
                            json_object=example['response'],
                            table_field_map=endpoint_response.get('field_map')
                        )

                        # Have we already obtained a response schema from a previous example?
                        if previous_response_schema:
                            # Merge the current_response_schema into the previous_response_schema.
                            previous_response_schema = JSONSchema.merge_dictionaries(
                                a=previous_response_schema,
                                b=current_response_schema,
                                mark_optional_at_depth=1
                            )
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
                        current_request_schema = JSONSchema.get_schema(
                            json_object=example['request_json'],
                            table_field_map=endpoint_request.get('field_map')
                        )

                        # Have we already obtained a request schema from a previous example?
                        if previous_request_schema:
                            # Merge the current_request_schema with the previous_request_schema.
                            previous_request_schema = JSONSchema.merge_dictionaries(
                                a=previous_request_schema,
                                b=current_request_schema,
                                mark_optional_at_depth=1
                            )
                        else:
                            # Take the current_request_schema as the previous_request_schema.
                            previous_request_schema = current_request_schema

                # Is there a request schema to process?
                if previous_request_schema:
                    # Merge the request field_map dictionary with any configured values.
                    if 'field_map' in endpoint_request:
                        previous_request_schema = JSONSchema.merge_dictionaries(
                            a=previous_request_schema,
                            b=endpoint_request['field_map'],
                            mark_optional_at_depth=None
                        )

                    endpoint_request['field_map'] = previous_request_schema

                # Is there a response schema to process?
                if previous_response_schema:
                    # Merge the response field_map dictionary with any configured values.
                    if 'field_map' in endpoint_response:
                        previous_response_schema = JSONSchema.merge_dictionaries(
                            a=previous_response_schema,
                            b=endpoint_response['field_map'],
                            mark_optional_at_depth=None
                        )

                    endpoint_response['field_map'] = previous_response_schema

            # Get the request section but also any used and referenced custom types.
            request_section, table_used_custom_types = (
                EndpointDocumentationGenerator.get_request_section(
                    request_json=endpoint_request,
                    file_depth=file_depth-1,
                    type_map=type_map
                )
            )

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
                    table_section, table_used_custom_types = \
                        EndpointDocumentationGenerator.get_table_section(
                            table_name=table_name,
                            table=table,
                            type_map=type_map
                        )

                    # Collect any used custom_types, ignoring any duplicates.
                    for custom_type in table_used_custom_types:
                        if custom_type not in used_custom_types:
                            used_custom_types.append(custom_type)

                    # Add the table section to the output.
                    output += table_section

            # Output any used custom types.
            if type_map and len(used_custom_types) > 0:
                # Ouput the custom type section.
                output += EndpointDocumentationGenerator.get_type_section(
                    used_custom_types=used_custom_types,
                    type_map=type_map
                )

            # Add the examples.
            if 'examples' in endpoint_request:
                output += '\n== Examples'

                # There can be multiple examples for the same endpoint.
                for example in endpoint_request['examples']:
                    # We cannot output an example without a name.
                    if not 'name' in example:
                        print('Warning : Skipping a \'' + key + '\' example as missing its name.')
                        continue

                    # We cannot output an example without a response
                    # (either from querying the API earlier or hardcoding one).
                    if not 'response' in example:
                        print('Warning : Skipping example \'' + example['name'] + '\' for \'' + key + '\' due to lack of response.')
                        continue

                    # Take the obtained JSON as an example.
                    output += EndpointDocumentationGenerator.get_example_section(
                        uri=endpoint_uri,
                        example_item=example
                    )
        else:
            # Add placeholder text.
            output += EndpointDocumentationGenerator.get_not_yet_documented()

        # Generate a suitable filename to store our documentation in.
        filename = '../../Documentation/IQ Gateway API/' + endpoint['documentation']

        # Create any required sub-directories.
        os.makedirs(os.path.dirname(filename), exist_ok=True)

        # Write the output to the file.
        with open(filename, mode='w', encoding='utf-8') as text_file:
            text_file.write(output)

        return True

class IndexDocumentationGenerator:
    """
    A class to generate an index file for the documentation.
    """

    @staticmethod
    def get_header_section(file_depth=1):
        """
        Generate the AsciiDoc index heading for the IQ Gateway API documentation.

        Args:
            file_depth (int, optional): How many sub-directories deep the file will be stored in.

        Returns:
            str: A string containing the AsciiDoc index heading.

        Note:
            This method generates the index heading for the IQ Gateway API documentation,
            including the table of contents and introductory sections.
        """

        # Heading.
        result = '= IQ Gateway API\n'

        # Table of Contents.
        result += ':toc:\n'

        # Shared block of data.
        result += DocumentationGenerator.get_header_settings_and_variables()

        # Introduction.
        result += DocumentationGenerator.get_introduction_section(file_depth=file_depth)

        return result

    @staticmethod
    def create_index(endpoint_metadata):
        """
        Generate and create the index documentation for all the endpoints.

        This function takes endpoint metadata and constructs the index documentation,
        containing information about the API endpoints, their URIs, and descriptions.

        Args:
            endpoint_metadata (dict): A dictionary containing metadata for different endpoints.

        Returns:
            None: The index documentation is written to a file specified by the function.
        """

        # Generate a suitable filename to store our documentation in.
        filename = '../../Documentation/' + 'IQ Gateway API/README.adoc'

        # Create any required sub-directories.
        os.makedirs(os.path.dirname(filename), exist_ok=True)

        # Build the output.
        output = IndexDocumentationGenerator.get_header_section()

        # Heading.
        output += '\n== Endpoints\n\n'

        # We store a reference to the previous path.
        previous_path = None
        table_open = False

        # Write each of the endpoints.
        for key in sorted(endpoint_metadata, key=str.casefold):

            metadata = endpoint_metadata[key]
            path = key.split(' / ')

            # Add any headers.
            for count in range(len(path) - 1):
                if (previous_path is None
                        or len(previous_path)-1 < count
                        or previous_path[count] != path[count]):

                    # Finish off any previous table.
                    if table_open:
                        output += '|===\n\n'
                        table_open = False

                    output += ('='*(3+count)) + ' ' + ' - '.join(path[:count+1]) + '\n\n'

            # Add any tables.
            if previous_path is None or previous_path[:-1] != path[:-1]:
                output += '[cols="1,1,2", options="header"]\n'
                output += '|===\n'
                output += '|Name\n'
                output += '|URI\n'
                output += '|Description\n\n'

                table_open = True

            previous_path = path

            # Add the item.
            output += '|`link:' + urllib.parse.quote(metadata['documentation']) + '[' + path[-1] + ']`\n'

            output += '|`'
            if 'removed' in metadata['request'] and metadata['request']['removed'] is True:
                output += '+++<s>+++'
            output += '/' + metadata['request']['uri']
            if 'removed' in metadata['request'] and metadata['request']['removed'] is True:
                output += '+++</s>+++'

            if 'uri2' in metadata['request']:
                output += '` and `/' + metadata['request']['uri2']

            output += '`\n'

            output += '|' + metadata['description']['short'] + '\n\n'

        output += '|==='

        # Write the output to the file.
        with open(filename, mode='w', encoding='utf-8') as text_file:
            text_file.write(output)

def get_secure_gateway_session(credentials):
    """
    Establishes a secure session with the Enphase® IQ Gateway API.

    This function manages the authentication process to establish a secure session with
    an Enphase® IQ Gateway.

    It handles JWT validation, token acquisition (if required) and initialises
    the Gateway API wrapper for subsequent interactions.

    It also downloads and stores the certificate from the gateway for secure communication.

    Args:
        credentials (dict): A dictionary containing the required credentials.

    Returns:
        Gateway: An initialised Gateway API wrapper object for interacting with the gateway.

    Raises:
        ValueError: If authentication fails or if required credentials are missing.
    """

    # Do we have a valid JSON Web Token (JWT) to be able to use the service?
    if not (credentials.get('token')
                and Authentication.check_token_valid(
                    token=credentials['token'],
                    gateway_serial_number=credentials.get('gatewaySerialNumber'))):
        # It is not valid so clear it.
        credentials['token'] = None

    # Do we still not have a Token?
    if not credentials.get('token'):
        # Do we have a way to obtain a token?
        if credentials.get('enphaseUsername') and credentials.get('enphasePassword'):
            # Create a Authentication object.
            authentication = Authentication()

            # Authenticate with Entrez (French for "Access").
            if not authentication.authenticate(
                username=credentials['enphaseUsername'],
                password=credentials['enphasePassword']):
                raise ValueError('Failed to login to Enphase Authentication server ("Entrez")')

            # Does the user want to target a specific gateway or all uncommissioned ones?
            if credentials.get('gatewaySerialNumber'):
                # Get a new gateway specific token (installer = short-life, owner = long-life).
                credentials['token'] = authentication.get_token_for_commissioned_gateway(
                    gateway_serial_number=credentials['gatewaySerialNumber']
                )
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
    host = credentials.get('host')

    # Download and store the certificate from the gateway so all future requests are secure.
    if not os.path.exists('configuration/gateway.cer'):
        Gateway.trust_gateway(host)

    # Instantiate the Gateway API wrapper (with the default library hostname if None provided).
    gateway = Gateway(host)

    # Are we not able to login to the gateway?
    if not gateway.login(credentials['token']):
        # Let the user know why the program is exiting.
        raise ValueError('Unable to login to the gateway (bad, expired or missing token in credentials.json).')

    # Return the initialised gateway object.
    return gateway

def main():
    """
    Generate Enphase-API documentation in AsciiDoc.

    This function loads endpoint metadata, attempts to call undocumented endpoints,
    determines their schema, and writes the corresponding documentation.

    It performs the following steps:
    - Output program banner.
    - Load credentials from 'configuration/credentials.json'.
    - Initialize a secure gateway session (unless in TEST_ONLY mode).
    - Load endpoint metadata from 'resources/API_Details.json'.
    - Process each endpoint in the metadata using EndpointDocumentationGenerator.
    - Create the index page using IndexDocumentationGenerator.
    """

    # Output program banner.
    banner = 'Gateway Generate Documentation V' + str(VERSION) + '\n'
    hyphens = '-' * len(banner) + '\n'
    print(hyphens + banner + hyphens)

    # Load credentials.
    with open('configuration/credentials.json', mode='r', encoding='utf-8') as json_file:
        credentials = json.load(json_file)

    # Use a secure gateway initialisation flow.
    gateway = None if TEST_ONLY else get_secure_gateway_session(credentials)

    # Load endpoints.
    with open('resources/API_Details.json', mode='r', encoding='utf-8') as json_file:
        endpoint_metadata = json.load(json_file)

    # Take each endpoint in the metadata.
    for key, endpoint in endpoint_metadata.items():
        # Process this endpoint.
        EndpointDocumentationGenerator.process_endpoint(gateway=gateway, key=key, endpoint=endpoint)

    # Create index page.
    IndexDocumentationGenerator.create_index(endpoint_metadata)

# Launch the main method if invoked directly.
if __name__ == '__main__':
    main()