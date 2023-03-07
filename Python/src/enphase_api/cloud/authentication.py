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

# We can check JWT claims/expiration first before making a request to prevent annoying Enphase® ("pip install pyjwt" if not already installed).
import jwt

# Third party library for making HTTP(S) requests; "pip install requests" if getting import errors.
import requests

class Authentication:
    """A class to talk to Enphase®'s Cloud based Authentication Server, Entrez (French for "Access").
    This server also supports granting tokens for local access to the Gateway.
    """

    # Authentication host, Entrez (French for "Access").
    AUTHENTICATION_HOST = 'https://entrez.enphaseenergy.com'

    # This prevents the requests module from creating its own user-agent (and ask to not be included in analytics).
    STEALTHY_HEADERS = {'User-Agent': None, 'Accept':'application/json', 'DNT':'1'}
    STEALTHY_HEADERS_FORM = {'User-Agent': None, 'Accept':'application/json', 'Content-Type':'application/x-www-form-urlencoded', 'DNT':'1'}

    # Holds the session cookie which contains the session token.
    session_cookies = None

    @staticmethod
    def _extract_token_from_response(response):
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
        # Build the login request payload.
        payload = {'username':username, 'password':password}

        # Send the login request.
        response = requests.post(Authentication.AUTHENTICATION_HOST + '/login', headers=Authentication.STEALTHY_HEADERS_FORM, data=payload)

        # There's only 1 cookie value that is important to maintain session once we are authenticated.
        # SESSION - This links our future requests to our existing login session on this server.
        self.session_cookies = {'SESSION': response.cookies.get('SESSION')}

        # Return a true/false on whether login was successful.
        return response.status_code == 200

    def get_site(self, site_name):
        return requests.get(Authentication.AUTHENTICATION_HOST + '/site/' + requests.utils.quote(site_name, safe=''), headers=Authentication.STEALTHY_HEADERS, cookies=self.session_cookies).json()

    def get_token_for_commissioned_gateway(self, gateway_serial_number):
        # The actual website also seems to set "uncommissioned" to "on", but this is not necessary or correct for commissioned gateways. Site name also is passed but not required.
        response = requests.post(Authentication.AUTHENTICATION_HOST + '/entrez_tokens', headers=Authentication.STEALTHY_HEADERS_FORM, cookies=self.session_cookies, data={'serialNum': gateway_serial_number})
        return self._extract_token_from_response(response.text)

    def get_token_for_uncommissioned_gateway(self):
        # The actual website also sets an empty "Site" key, but this is not necessary for uncommissioned gateway access.
        response = requests.post(Authentication.AUTHENTICATION_HOST + '/entrez_tokens', headers=Authentication.STEALTHY_HEADERS_FORM, cookies=self.session_cookies, data={'uncommissioned': 'true'})
        return self._extract_token_from_response(response.text)

    def get_token_from_enlighten_session_id(self, enlighten_session_id, gateway_serial_number, username):
        # This is probably used internally by the Enlighten website itself to authorise sessions via Entrez.
        return requests.post(Authentication.AUTHENTICATION_HOST + '/tokens', headers=Authentication.STEALTHY_HEADERS, cookies=self.session_cookies, json={'session_id': enlighten_session_id, 'serial_num': gateway_serial_number, 'username': username}).content

    @staticmethod
    def check_token_valid(token, gateway_serial_number=None):
        # An installer is always allowed to access any uncommissioned Gateway serial number (currently for a shorter time however).
        if gateway_serial_number:
            calculated_audience = [gateway_serial_number, 'un-commissioned']
        else:
            calculated_audience = ['un-commissioned']

        try:
            # Is the token still valid?
            jwt.decode(token, key='', algorithms='ES256', options={'verify_signature':False, 'require':['aud', 'iss', 'enphaseUser', 'exp', 'iat', 'jti', 'username'], 'verify_aud':True, 'verify_iss':True, 'verify_exp':True, 'verify_iat':True}, audience=calculated_audience, issuer='Entrez')

            # If we got to this line then no exceptions were generated by the above.
            return True

        # Should never happen as we do not currently validate the token's signature.
        except (jwt.exceptions.InvalidSignatureError, jwt.exceptions.InvalidKeyError):
            raise

        # We mask the specific reason and just ultimately inform the user that the token is invalid.
        except (jwt.exceptions.InvalidTokenError,
                jwt.exceptions.DecodeError,
                jwt.exceptions.ExpiredSignatureError,
                jwt.exceptions.InvalidAudienceError,
                jwt.exceptions.InvalidIssuerError,
                jwt.exceptions.InvalidIssuedAtError,
                jwt.exceptions.InvalidAlgorithmError,
                jwt.exceptions.MissingRequiredClaimError):

            # The token is invalid.
            return False

    def logout(self):
        response = requests.post(Authentication.AUTHENTICATION_HOST + '/logout', headers=Authentication.STEALTHY_HEADERS, cookies=self.session_cookies)
        return response.status_code == 200