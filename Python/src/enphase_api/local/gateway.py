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

# Third party library; we use a proper OAuth2 library ("pip install requests-oauthlib" if not already installed).
import oauthlib.oauth2
import requests_oauthlib.oauth2_auth

# We implement our own Requests adapter to amend TLS certificate hostname checking (Gateway is self-signed).
import enphase_api.local.ignoreHostnameAdapter

class Gateway:
    # This prevents the requests module from creating its own user-agent.
    STEALTHY_HEADERS = {'User-Agent': None, 'Accept':'application/json', 'DNT':'1'}

    def __init__(self, host='https://envoy.local'):
        # The Gateway host (or if the network supports mDNS, "https://envoy.local").
        self.host = host

        # We use a proper OAuth2 library (rather than just appending the Authorization header on ourselves) in case the device uses more OAuth features in future.
        self.client = oauthlib.oauth2.MobileApplicationClient('')

        # Using a session means Requests supports keep-alive.
        self.session = requests.Session()

        # If there is a Gateway.cer file already available then we implement certificate pinning.
        if os.path.exists('configuration/gateway.cer'):

            # Make the session verify all HTTPS requests with trust for this certficiate.
            self.session.verify = 'configuration/gateway.cer'

            # Requests to this host will ignore the hostname in the certificate being incorrect.
            self.session.mount(self.host, enphase_api.local.ignoreHostnameAdapter.IgnoreHostnameAdapter())
        else:
            # Disable the warnings about making an insecure request.
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

            # Perform no verification of the remote host or the security of the connection.
            self.session.verify = False

    @staticmethod
    def trust_gateway(host='https://envoy.local'):
        # get_server_certificate needs the host and port as a tuple not a URL.
        parsed_host = urllib3.util.parse_url(host)

        # Create the configuration folder if it does not already exist.
        if not os.path.exists('configuration/'): os.makedirs('configuration/')

        # Save the Gateway's public certificate to disk.
        with open('configuration/gateway.cer', mode='w', encoding='utf-8') as file:
            # Download the certificate from the host.
            file.write(ssl.get_server_certificate(addr=(parsed_host.hostname, parsed_host.port or 443)))

    def login(self, token):
        # If successful this will return a "sessionid" cookie that validates our access to the gateway.
        response = self.session.post(self.host + '/auth/check_jwt', headers=Gateway.STEALTHY_HEADERS, auth=requests_oauthlib.oauth2_auth.OAuth2(client=self.client, token={'access_token': token}))

        # Check the response is positive.
        return response.status_code == 200 and response.text == '<!DOCTYPE html><h2>Valid token.</h2>\n'

    def api_call(self, path):
        # Call the Gateway API endpoint.
        response = self.session.get(self.host + path, headers=Gateway.STEALTHY_HEADERS)

        # Has the session expired?
        if response.status_code == 401:
            raise ValueError(response.reason)

        # Return the JSON response.
        return response.json()

    def api_call_stream(self, path):
        return self.session.get(self.host + path, headers=Gateway.STEALTHY_HEADERS, stream=True)