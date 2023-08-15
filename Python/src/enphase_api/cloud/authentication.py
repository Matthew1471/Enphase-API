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
Enphase-API Authentication Module
This module provides classes and methods for interacting with the Enphase® authentication server.
It supports maintaining an authenticated session and generating JWT tokens for use with an IQ Gateway.
"""

# Used to generate an OAuth 2.0 Proof Key for Code Exchange (PKCE) code verifier.
import base64
import hashlib
import random
import string

# We extract the code from the returned OAuth 2.0 URL.
import urllib.parse

# We can check JWT claims/expiration first before making a request ("pip install pyjwt" if not already installed).
import jwt

# Third party library for making HTTP(S) requests; "pip install requests" if getting import errors.
import requests

# Remove urllib3 added user-agent (https://github.com/psf/requests/issues/5671)
import urllib3


class Authentication:
    """
    A class to talk to Enphase®'s Cloud based Authentication Server, Entrez (French for "Access").
    This server also supports granting tokens for local access to an IQ Gateway.
    """

    # Authentication host, Entrez (French for "Access").
    AUTHENTICATION_HOST = 'https://entrez.enphaseenergy.com'

    # This prevents the requests + urllib3 module from creating its own user-agent.
    HEADERS = {'User-Agent': urllib3.util.SKIP_HEADER, 'Accept':'application/json'}

    # This sets a 5 minute connect and read timeout.
    TIMEOUT = 300

    # Holds the session cookie which contains the session token.
    session_cookies = None

    @staticmethod
    def _extract_token_from_response(response):
        """
        Extract the access token from the HTML response of the Entrez authentication server.

        This internal method searches for the access token within the HTML response
        using predefined markers. If the markers change, the method may need to be updated.

        Args:
            response (str): The HTML response from the Entrez authentication server.

        Returns:
            str: The extracted access token.

        Raises:
            ValueError: If the access token cannot be found in the response.
                        This may indicate changes in the response structure.
        """

        # The text that indicates the beginning of a token, if this changes a lot we may have to turn this into a regular expression.
        start_needle = '<textarea name="accessToken" id="JWTToken" cols="30" rows="10" >'

        # Look for the start token text.
        start_position = response.find(start_needle)

        # Check the response contains the expected start of a token result.
        if start_position != -1:
            # Skip past the start_needle.
            start_position += len(start_needle)

            # Look for the end of the token text.
            end_position = response.find('</textarea>', start_position)

            # Check the end_position can be found.
            if end_position != -1:
                # The token can be returned.
                return response[start_position:end_position]

            # The token cannot be returned.
            raise ValueError('Unable to find the end of the token in the Authentication Server repsonse (the response page may have changed).')

        # The token cannot be returned.
        raise ValueError('Unable to find access token in Authentication Server response (the response page may have changed).')

    def authenticate(self, username, password):
        """
        Authenticate with Entrez (with a username and password) and maintains a session.

        Args:
            username (str): The user's Enphase® username for authentication.
            password (str): The user's Enphase® password for authentication.

        Returns:
            bool: True if authentication is successful, False otherwise.
        """

        # Build the login request payload.
        data = {'username':username, 'password':password}

        # Send the login request.
        response = requests.post(
            url=Authentication.AUTHENTICATION_HOST + '/login',
            headers=Authentication.HEADERS,
            data=data,
            timeout=Authentication.TIMEOUT
        )

        # There's only 1 cookie value that is important to maintain session once we are authenticated.
        # SESSION - This links our future requests to our existing login session on this server.
        self.session_cookies = {'SESSION': response.cookies.get('SESSION')}

        # Return a true/false on whether login was successful.
        return response.status_code == 200

    @staticmethod
    def authenticate_oauth(username, password, gateway_serial_number='un-commissioned'):
        """
        Authenticate with Entrez (with a username and password) using OAuth 2.0.
        This is currently using the "Authorization Code Flow with Proof Key for Code Exchange (PKCE)" grant.

        Args:
            username (str): The user's Enphase® username for authentication.
            password (str): The user's Enphase® password for authentication.
            gateway_serial_number (str, optional): The serial number of the IQ Gateway. Defaults to 'un-commissioned'.

        Returns:
            tuple: A tuple containing the authorisation code and code verifier.
        """

        # OAuth 2.0 Proof Key for Code Exchange (PKCE) in case response is intercepted.
        uri_unreserved_characters = string.ascii_letters + string.digits + '-._~'
        code_verifier = ''.join(random.choices(uri_unreserved_characters, k=40))

        # This is sent in the initial request hashed
        # (before the auth server knows the plaintext to prove the request came from us).
        sha256_digest = hashlib.sha256(code_verifier.encode('ascii')).digest()
        code_challenge = base64.urlsafe_b64encode(sha256_digest).decode('ascii').rstrip('=')

        # Build the login and authorisation code request (with PKCE) payload.
        data = {
            'username':username,
            'password':password,
            'codeChallenge':code_challenge,
            'redirectUri':'https://envoy.local/auth/callback',
            'client':'envoy-ui',
            'clientId':'envoy-ui-client',
            'authFlow':'oauth',
            'serialNum':gateway_serial_number
        }

        # Send the login request.
        response = requests.post(
            url=Authentication.AUTHENTICATION_HOST + '/login',
            headers=Authentication.HEADERS,
            data=data,
            timeout=Authentication.TIMEOUT,
            allow_redirects=False
        )

        # If succesful the authentication server will recommend a redirect to the redirectUri.
        if response.status_code == 302 and 'location' in response.headers:
            # What is the URL it is redirecting to?
            redirect = response.headers['location']

            # Split out the component parts of the URL.
            parsed_url = urllib.parse.urlparse(redirect)

            # Parse the query string components.
            query_params = urllib.parse.parse_qs(parsed_url.query)

            # Was there a "code" query string key?
            if 'code' in query_params:
                # Return the code and the code_verifier.
                return query_params.get('code')[0], code_verifier

        # If we got to this line then an error occurred.
        raise ValueError('Unable to authenticate using OAuth 2.0.')

    def get_site(self, site_name):
        """
        Get site details (site ID number, full site name and associated IQ Gateway serial numbers) from a partial site name.

        Args:
            site_name (str): The partial site name.

        Returns:
            dict: The JSON response containing the site details.
        """

        # Send the site details request.
        response = requests.get(
            url=Authentication.AUTHENTICATION_HOST + '/site/' + requests.utils.quote(site_name, safe=''),
            headers=Authentication.HEADERS,
            cookies=self.session_cookies,
            timeout=Authentication.TIMEOUT
        )

        # Return the response.
        return response.json()

    def get_token_for_commissioned_gateway(self, gateway_serial_number):
        """
        Get a JWT token for a specific IQ Gateway which has been commissioned.

        Args:
            gateway_serial_number (str): The serial number of a commissioned IQ Gateway.

        Returns:
            str: The JWT token.
        """

        # Build the request payload.
        # The official form sends additional keys but they are not required.
        data = {'serialNum': gateway_serial_number}

        # Send the form request for a token.
        response = requests.post(
            url=Authentication.AUTHENTICATION_HOST + '/entrez_tokens',
            headers=Authentication.HEADERS,
            cookies=self.session_cookies,
            data=data,
            timeout=Authentication.TIMEOUT
        )

        # Return just the token.
        return self._extract_token_from_response(response.text)

    def get_token_for_uncommissioned_gateway(self):
        """
        Get a JWT token for all IQ Gateways which have yet to be commissioned.

        Returns:
            str: The JWT token.
        """

        # Build the request payload.
        # The official form sends additional keys but they are not required.
        data = {'uncommissioned': 'true'}

        # Send the form request for a token.
        response = requests.post(
            url=Authentication.AUTHENTICATION_HOST + '/entrez_tokens',
            headers=Authentication.HEADERS,
            cookies=self.session_cookies,
            data=data,
            timeout=Authentication.TIMEOUT
        )

        # Return just the token.
        return self._extract_token_from_response(response.text)

    def get_token_from_enlighten_session_id(self, enlighten_session_id, gateway_serial_number, username):
        """
        Get a JWT token for a specific IQ Gateway using an Enlighten session ID.

        Args:
            enlighten_session_id (str): The Enlighten session ID.
            gateway_serial_number (str): The serial number of the IQ Gateway.
            username (str): The Enphase® username associated with the session.

        Returns:
            bytes: The token content.
        """

        # Build the request payload.
        json = {
            'session_id': enlighten_session_id,
            'serial_num': gateway_serial_number,
            'username': username
        }

        # This is probably used internally by the Enlighten website itself to authorise sessions via Entrez.
        response = requests.post(
            url=Authentication.AUTHENTICATION_HOST + '/tokens',
            headers=Authentication.HEADERS,
            cookies=self.session_cookies,
            json=json,
            timeout=Authentication.TIMEOUT
        )

        # Return just the token.
        return response.content

    @staticmethod
    def get_token_from_oauth(code, code_verifier):
        """
        Perform an OAuth 2.0 authorisation code exchange for a token (with PKCE).
        This method does not require an open session on the authentication serer.

        Args:
            code (str): The authorisation code.
            code_verifier (str): The PKCE code verifier.

        Returns:
            dict: The JSON response containing the token information.
        """

        # Build the exchange authorisation code for a token (with PKCE) request payload.
        data = {
            'code': code,
            'code_verifier': code_verifier,
            'redirect_uri': 'https://envoy.local/auth/callback',
            'client_id':'envoy-ui-1',
            'grant_type':'authorization_code'
        }

        # This is used internally by the IQ Gateway to exchange an authorisation code for a token.
        response = requests.post(
            url=Authentication.AUTHENTICATION_HOST + '/oauth/token',
            headers=Authentication.HEADERS,
            data=data,
            timeout=Authentication.TIMEOUT
        )

        # Return the JSON response.
        return response.json()

    @staticmethod
    def check_token_valid(token, gateway_serial_number=None, verify_signature=False):
        """
        This performs JWT token validation to confirm whether a token would likely be valid for a local API authentication call.

        Args:
            token (str): The JWT token.
            gateway_serial_number (str, optional): The serial number of the IQ Gateway. Defaults to None.
            verify_signature (bool, optional): Whether to verify the token signature. Defaults to False.

        Returns:
            bool: True if the token is valid, False otherwise.
        """

        # An installer is always allowed to access any uncommissioned IQ Gateway serial number (for a shorter time however).
        if gateway_serial_number:
            calculated_audience = [gateway_serial_number, 'un-commissioned']
        else:
            calculated_audience = ['un-commissioned']

        # We require "aud", "iss", "enphaseUser", "exp", "iat", "jti" and "username" values.
        require = ['aud', 'iss', 'enphaseUser', 'exp', 'iat', 'jti', 'username']

        try:
            # PyJWT requires "cryptography" to be able to support ES256.
            if verify_signature:
                # The Entrez production JWT public key.
                public_key = (
                    '-----BEGIN PUBLIC KEY-----\n'
                    'MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE6PhAU3Mk4W7Ara5hCWPHDtv8LY0CtBwEVj4k4Tu8KRBMOhbTcHHnxYJ3UKppIKyraB2GFUmOhGP9O2jmcb4UAw==\n'
                    '-----END PUBLIC KEY-----'
                )

                # Is the token still valid?
                jwt.decode(token, key=public_key, algorithms='ES256', options={'require':require}, audience=calculated_audience, issuer='Entrez')
            else:
                # While the signature itself is not verified, we enforce required fields and validate "aud", "iss", "exp" and "iat" values.
                options = {'verify_signature':False, 'require':require, 'verify_aud':True, 'verify_iss':True, 'verify_exp':True, 'verify_iat':True}

                # Is the token still valid?
                jwt.decode(token, options=options, audience=calculated_audience, issuer='Entrez')

            # If we got to this line then no exceptions were generated by the above.
            return True

        # We mask the specific reason and just ultimately inform the user that the token is invalid.
        except (
            jwt.exceptions.InvalidTokenError,
            jwt.exceptions.DecodeError,
            jwt.exceptions.InvalidSignatureError,
            jwt.exceptions.ExpiredSignatureError,
            jwt.exceptions.InvalidAudienceError,
            jwt.exceptions.InvalidIssuerError,
            jwt.exceptions.InvalidIssuedAtError,
            jwt.exceptions.InvalidAlgorithmError,
            jwt.exceptions.MissingRequiredClaimError
        ):

            # The token is invalid.
            return False

    def logout(self):
        """
        Close the current session to the authentication server.

        Returns:
            bool: True if logout is successful, False otherwise.
        """

        # Send the logout request.
        response = requests.post(
            url=Authentication.AUTHENTICATION_HOST + '/logout',
            headers=Authentication.HEADERS,
            cookies=self.session_cookies,
            timeout=Authentication.TIMEOUT
        )

        # Just return whether this call was successful or not.
        return response.status_code == 200