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

# We check if a file exists.
import os

# We optionally can download the certificate to provide security to future requests.
import ssl

# Disable the warning about insecure HTTPS requests.
import urllib3

# Third party library; "pip install requests" if getting import errors.
import requests

# We implement our own Requests adapter to amend TLS certificate hostname checking (Gateway is self-signed).
import enphase_api.local.ignore_hostname_adapter

class Gateway:
    # This prevents the requests module from creating its own user-agent.
    STEALTHY_HEADERS = {'User-Agent': None, 'Accept':'application/json', 'DNT':'1'}
    STEALTHY_HEADERS_JSON = {'User-Agent': None, 'Accept':'application/json', 'DNT':'1', 'Content-Type':'application/json'}
    STEALTHY_HEADERS_FORM = {'User-Agent': None, 'Accept':'application/json', 'DNT':'1', 'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8'}

    # This sets a 5 minute connect and read timeout.
    TIMEOUT = 300

    def __init__(self, host='https://envoy.local'):
        # The Gateway host (or if the network supports mDNS, "https://envoy.local").
        self.host = host

        # Using a session means Requests supports keep-alive.
        self.session = requests.Session()

        # If there is a Gateway.cer file already available then we implement certificate pinning.
        if os.path.exists('configuration/gateway.cer'):
            # Make the session verify all HTTPS requests with trust for this certficiate.
            self.session.verify = 'configuration/gateway.cer'

            # Requests to this host will ignore the hostname in the certificate being incorrect.
            self.session.mount(self.host, enphase_api.local.ignore_hostname_adapter.IgnoreHostnameAdapter())
        else:
            # Disable the warnings about making an insecure request.
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

            # Perform no verification of the remote host or the security of the connection.
            self.session.verify = False

    @staticmethod
    def trust_gateway(host='https://envoy.local'):
        # Create the configuration folder if it does not already exist.
        if not os.path.exists('configuration/'): os.makedirs('configuration/')

        # Save the Gateway's public certificate to disk.
        with open('configuration/gateway.cer', mode='w', encoding='utf-8') as file:
            # get_server_certificate needs the host and port as a tuple not a URL.
            parsed_url = urllib3.util.parse_url(host)

            # Download the certificate from the host.
            file.write(ssl.get_server_certificate(addr=(parsed_url.host, parsed_url.port or 443)))

    def login(self, token):
        """
        Authenticates with the IQ Gateway (with a JWT token).
        The IQ Gateway does not require Internet connectivity.
        """
        # Create a copy of the original header dictionary.
        headers = Gateway.STEALTHY_HEADERS.copy()

        # We append an OAuth 2.0 bearer token.
        headers["Authorization"] = "Bearer " + token

        # If successful this will return a "sessionId" cookie that validates our access to the gateway.
        response = self.session.post(self.host + '/auth/check_jwt', headers=headers, timeout=Gateway.TIMEOUT)

        # Check the response is positive.
        return response.status_code == 200 and response.text == '<!DOCTYPE html><h2>Valid token.</h2>\n'

    def login_oauth_code(self, code, code_verifier):
        """
        Authenticates with the IQ Gateway (with an OAuth 2.0 authorisation code).
        The IQ Gateway will require Internet connectivity.
        """

        # We skip calling /auth/callback as that's just client-side JS to perform the HTTP POST
        # to /auth/get_jwt with the correct code and code_verifier and then /auth/check_jwt.

        # Build the authorisation code request payload.
        json = {
                'client_id':'envoy-ui-1',
                #'grant_type':'authorization_code',
                'redirect_uri':'https://envoy.local/auth/callback',
                'code_verifier':code_verifier,
                'code':code
               }

        # In my opinion, the gateway should never return the access token to the end user,
        # a valid gateway "sessionId" cookie should be returned instead.
        #
        # The gateway is a trusted application / "confidential client" capable of holding the
        # JWT itself. This call should therefore be made internally,
        # thus preventing the user from accidentally leaking the access token.
        response = self.session.post(self.host + '/auth/get_jwt', headers=Gateway.STEALTHY_HEADERS_JSON, json=json, timeout=Gateway.TIMEOUT).json()

        # Did the gateway return an error?
        if 'message' in response:
            raise ValueError('Error exchanging authorisation code for an access token.') from ValueError(response['message'])

        # The gateway must have returned an access token.
        if 'access_token' in response:
            # Login with the JWT (in my opinion the gateway should have internally made this call for us).
            return self.login(response['access_token'])
        # Should never happen (gateway should always return an error or an access_token).
        else:
            raise ValueError('Error exchanging authorisation code for an access token.')

    def api_call(self, path, method='GET', json=None, response_raw=False):
        # Call the Gateway API endpoint.
        if method is None or method == 'GET':
            response = self.session.get(self.host + path, headers=Gateway.STEALTHY_HEADERS, timeout=Gateway.TIMEOUT)
        elif method == 'PUT':
            response = self.session.put(self.host + path, headers=Gateway.STEALTHY_HEADERS_JSON, json=json, timeout=Gateway.TIMEOUT)
        elif method == 'POST':
            response = self.session.post(self.host + path, headers=Gateway.STEALTHY_HEADERS_JSON, json=json, timeout=Gateway.TIMEOUT)
        elif method == 'DELETE':
            response = self.session.delete(self.host + path, headers=Gateway.STEALTHY_HEADERS_JSON, json=json, timeout=Gateway.TIMEOUT)

        # Has the session expired (after 10 minutes inactivity)?
        if response.status_code == 401:
            raise ValueError(response.reason)

        # Some requests might not be JSON responses.
        if not response_raw:
             # Return the JSON response.
            return response.json() if len(response.content) > 0 else None
        else:
            # This is a raw response.
            return response.text

    def api_call_form(self, path, method='GET', data=None):
        # Call the Gateway API endpoint.
        if method is None or method == 'GET':
            response = self.session.get(self.host + path, headers=Gateway.STEALTHY_HEADERS, timeout=Gateway.TIMEOUT)
        elif method == 'PUT':
            response = self.session.put(self.host + path, headers=Gateway.STEALTHY_HEADERS_FORM, data=data, timeout=Gateway.TIMEOUT)
        elif method == 'POST':
            response = self.session.post(self.host + path, headers=Gateway.STEALTHY_HEADERS_FORM, data=data, timeout=Gateway.TIMEOUT)
        elif method == 'DELETE':
            response = self.session.delete(self.host + path, headers=Gateway.STEALTHY_HEADERS_FORM, data=data, timeout=Gateway.TIMEOUT)

        # Has the session expired (after 10 minutes inactivity)?
        if response.status_code == 401:
            raise ValueError(response.reason)

        # Return the JSON response.
        return response.json()

    def api_call_stream(self, path):
        # Call the Gateway API endpoint (expecting a stream).
        response = self.session.get(self.host + path, headers=Gateway.STEALTHY_HEADERS, stream=True, timeout=Gateway.TIMEOUT)

        # Has the session expired (after 10 minutes inactivity)?
        if response.status_code == 401:
            raise ValueError(response.reason)

        # Return the Server-Sent-Events (SSE) response.
        return response