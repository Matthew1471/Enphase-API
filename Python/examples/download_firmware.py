#!/usr/bin/env python3
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
This example provides functionality to download the Enphase® IQ Gateway firmware
from the Amazon CloudFront CDN server.
"""

# High-level file operations.
import shutil

# We create directories.
import os

# We obtain the hostname from a URL.
from urllib.parse import urlparse

# Enphase package some things in XML still.
import xml.etree.ElementTree as ET

# Third party library for making HTTP(S) requests;
# "pip install requests" if getting import errors.
import requests


# Where to store the downloaded files.
local_path = '../../Research/Firmware Downloads/'

# The path to the Amazon CloudFront CDN.
cdn_host = 'https://upgrade-fleet-qa.enphaseenergy.com/'
cdn_uri = 'jenkins-signing-complete-signing-master-3763-96c2a8-rlsv2/'

# The expected user-agent.
user_agent = {'User-Agent':'EnvoyDLR_20230510/000000000000'}

# https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-setting-signed-cookie-custom-policy.html
credentials = {
    'CloudFront-Policy': 'eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly91cGdyYWRlLWZsZWV0LXFhLmVucGhhc2VlbmVyZ3kuY29tL2plbmtpbnMtc2lnbmluZy1jb21wbGV0ZS1zaWduaW5nLW1hc3Rlci0zNzYzLTk2YzJhOC1ybHN2Mi8qIiwiQ29uZGl0aW9uIjp7IkRhdGVMZXNzVGhhbiI6eyJBV1M6RXBvY2hUaW1lIjoxNzczODI5NzIzfX19XX0_',
    'CloudFront-Signature': 'BCzsxarK9Mjr8S2HIwFUsAcdaDGhKUXAsYF91IHhDAcP6UcWXZr2nAO1ulf4zDR47zT~DGWVJG9~2jkOGKuA1ZroyFUTwlcdM5yiN~A1ukE83WSL5Y0ort34v2WqHSzRp4JbY9UV4Mm3-lggMvsToPI94Kc-ImXPuKJrfJ-lLXqiRb9Q9NqT4VIyoSTdSOtMdB-YDm1rp2OLphMS5dopHcP1HLwlQ9XmjAkphxPSNAxgrE6N2vxDiS5JioXTEDFEjEa3lD59nUWJd51vqgKoHors-4jVrpWRGF-5thWG~3Qz1ZNymd2gwsyTcHXsExhxdnWpIUq2lF3eJAQ4vAfHNw__',
    'CloudFront-Key-Pair-Id': 'K3CB90V8ECKAKP'
}

def download_file(filename, extensions, subfolder=''):
    # Take each of the file extensions requested.
    for extension in extensions:
        # Generate the full URL.
        url = cdn_host + cdn_uri + subfolder + filename + '.' + extension

        # Update the user.
        print(f'Downloading: {url}')

        # Request the file.
        with requests.get(url, headers=user_agent, cookies=credentials, stream=True) as response:
            # Check the request succeeded.
            if response.status_code == 200:
                # Define the full directory path.
                dir_path = os.path.dirname(local_path + urlparse(cdn_host).hostname + '/' + cdn_uri + subfolder + filename)

                # Create directories if they don't exist.
                os.makedirs(dir_path, exist_ok=True)

                # Write the file to disk.
                with open(os.path.join(dir_path, filename + '.' + extension), 'wb') as out_file:
                    shutil.copyfileobj(response.raw, out_file)
            else:
                print(f'Error: Failed to download ({response.status_code}): {url}')

def download_upgrade_files():
    # Parse the upgrade files XML.
    tree = ET.parse(local_path + urlparse(cdn_host).hostname + '/' + cdn_uri + 'upgrade_files.xml')
    root = tree.getroot()

    # Extract "imgDir".
    subfolder = root.attrib.get("imgDir")

    # Use a set to store unique filenames.
    unique_filenames = set()

    # Iterate over "name" attribute (typically inside an imgInfoEntry tag).
    for entry in root.findall(".//imgInfoEntry"):
        unique_filenames.add(entry.attrib.get("name"))

    # Download the unique filenames.
    for filename in unique_filenames:
        file_name_parts = os.path.splitext(filename)
        download_file(file_name_parts[0], [file_name_parts[1].lstrip('.'), 'sum', 'mf.sig'], subfolder + '/')

    # Download the mobile package information.
    download_file('mobile_pkg_info', ['xml'], subfolder + '/')

def main():
    # Get the package version information.
    download_file('pkg_versions', ['xml', 'sum', 'mf.sig'])

    # Get the upgrade files information.
    download_file('upgrade_files', ['xml', 'sum', 'mf.sig'])

    # Download all the upgrade files.
    download_upgrade_files()

    # Update the user.
    print('\nThe firmware was saved successfully.')

# Launch the main function if invoked directly.
if __name__ == '__main__':
    main()