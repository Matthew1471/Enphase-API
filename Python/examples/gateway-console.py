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

import datetime # We manipulate dates and times.
import json     # This script makes heavy use of JSON parsing.
import locale   # We play with encodings so it's good to check what we are set to support.
import os.path  # We check whether a file exists.
import sys      # We check whether we are running on Windows® or not.

# All the shared Enphase® functions are in these packages.
from enphase_api.cloud.authentication import Authentication
from enphase_api.local.gateway import Gateway


def get_human_readable_power(watts, inHours = False):
    # Is the significant number of watts (i.e. positive or negative number) less than a thousand?
    if abs(watts) < 1000:
        # Report the number in watts (rounded to the nearest number).
        return '{} W{}'.format(round(watts), 'h' if inHours else '')
    else:
        # Divide the number by a thousand and report it in kW (to 2 decimal places).
        return '{} kW{}'.format(round(watts / 1000, 2), 'h' if inHours else '')

# Load credentials.
with open('configuration\\credentials.json', 'r') as json_file:
    credentials = json.load(json_file)

# Do we have a valid JSON Web Token (JWT) to be able to use the service?
if credentials['Token']:
    # Check if the JWT is valid.
    if not Authentication.check_token_valid(credentials['Token'], credentials['GatewaySerialNumber']):
        # It is not valid so clear it.
        credentials['Token'] = None

# Do we still not have a Token?
if not credentials['Token']:
    # Create a Authentication object.
    authentication = Authentication()

    # Authenticate with Entrez (French for "Access").
    if not authentication.authenticate(credentials['EnphaseUsername'], credentials['EnphasePassword']):
        raise ValueError('Failed to login to Enphase Authentication server ("Entrez")')

    print(authentication.get_site('Matthew1471'))

# Download and store the certificate from the gateway so all future requests are secure.
if not os.path.exists('configuration\\gateway.cer'): Gateway.trust_gateway()

# Get an instance of the Gateway API wrapper object.
gateway = Gateway()

# Are we able to login to the gateway?
if gateway.login(credentials['Token']):
    # We can force the gateway to poll the inverters early (by default it only does this automatically every 5 minutes).
    #gateway.apiCall('/installer/pcu_comm_check')

    # Get gateway production, consumption and storage status.
    productionStatistics = gateway.apiCall('/production.json')

    # The meter status tells us if they are enabled and what mode they are operating in (production for production meter but net-consumption or total-consumption for consumption meter).
    metersStatus = gateway.apiCall('/ivp/meters')

    # The Production meter can be not present (not Gateway Metered) or individually turned off (and they require a working CT clamp).
    eimProductionWNow = None
    eimProductionWhToday = None
    eimProductionWhLast7Days = None

    meterStatisticsProduction = [meterStatus for meterStatus in metersStatus if meterStatus['measurementType'] == 'production'][0]
    if (meterStatisticsProduction['state'] == 'enabled'):
        # Get the Production section of the Production Statistics JSON that matches the configured meter mode.
        productionStatisticsProductionEIM = [productionStatistic for productionStatistic in productionStatistics['production'] if productionStatistic['type'] == 'eim' and productionStatistic['measurementType'] == meterStatisticsProduction['measurementType']][0]

        # Is the production meter responding?
        if productionStatisticsProductionEIM['activeCount'] > 0:
            # Production statistics.
            eimProductionWNow = productionStatisticsProductionEIM['wNow']
            eimProductionWhToday = productionStatisticsProductionEIM['whToday']
            eimProductionWhLast7Days = productionStatisticsProductionEIM.get('whLastSevenDays')

    # The Consumption meter can be not present (not Gateway Metered) or individually turned off (and they require a working CT clamp).
    eimConsumptionWNow = None
    eimConsumptionWhToday = None

    meterStatisticsConsumption = [meterStatus for meterStatus in metersStatus if meterStatus['measurementType'] == 'net-consumption' or meterStatus['measurementType'] == 'total-consumption'][0]
    if (meterStatisticsConsumption['state'] == 'enabled'):
        # Get the Consumption section for the right meter of the Production Statistics JSON.
        productionStatisticsConsumptionEIM = [productionStatistic for productionStatistic in productionStatistics['consumption'] if productionStatistic['type'] == 'eim' and productionStatistic['measurementType'] == meterStatisticsConsumption['measurementType']][0]

        # Is the consumption meter responding?
        if productionStatisticsConsumptionEIM['activeCount'] > 0:
            # Consumption statistics.
            eimConsumptionWNow = productionStatisticsConsumptionEIM['wNow']
            eimConsumptionWhToday = productionStatisticsConsumptionEIM['whToday']

    # We support Unicode and ANSI modes of running this application.
    # Check the Windows® console can display UTF-8 characters.
    if sys.platform != 'win32' or (sys.version_info.major >= 3 and sys.version_info.minor >= 6) or locale.getpreferredencoding() == 'cp65001':
        stringNames = {'Production': '⚡', 'Microinverter': '⬛', 'Meter': '✏️', 'Lifetime': '⛅', 'Details': '⏰ '}
    else:
        stringNames = {'Production': 'Production:', 'Microinverter': '-', 'Meter': 'Meter:', 'Lifetime': 'Lifetime:', 'Details': ''}

    # Get the Inverters section of the Production Statistics JSON.
    productionStatisticsInverters = [productionStatistic for productionStatistic in productionStatistics['production'] if productionStatistic['type'] == 'inverters'][0]

    # Generate the status (with emojis if runtime is utf-8 capable).
    status  = u'\n{} Inverters {} ({} Inverters)'.format(stringNames['Production'], get_human_readable_power(productionStatisticsInverters['wNow']), productionStatisticsInverters['activeCount'])

    # Used to calculate the microinverter automatic polling interval (gateway polls microinverters automatically every 5 minutes).
    mostRecentInverterData = None

    # Get Inverters status.
    invertersStatistics = gateway.apiCall('/api/v1/production/inverters')

    # Get panel by panel status.
    for inverterStatistic in invertersStatistics:
        status += u'\n  {} {} W (Serial: {}, Last Seen: {})'.format(stringNames['Microinverter'], inverterStatistic['lastReportWatts'], inverterStatistic['serialNumber'], datetime.datetime.fromtimestamp(inverterStatistic['lastReportDate']))

        # Used to calculate the microinverter polling interval (gateway polls microinverters every 5 minutes).
        if not mostRecentInverterData or mostRecentInverterData < datetime.datetime.fromtimestamp(inverterStatistic['lastReportDate']): mostRecentInverterData = datetime.datetime.fromtimestamp(inverterStatistic['lastReportDate'])

    # This will always be present (even without a production meter).
    status += u'\n{} Total Generated {}'.format(stringNames['Lifetime'], get_human_readable_power(productionStatisticsInverters['whLifetime'], True))

    # This requires a configured Production meter.
    if eimProductionWNow != None:

        # The current Production meter reading can read < 0 if energy (often a trace amount) is actually flowing the other way from the grid.
        status += u'\n\n{} Current Production {}'.format(stringNames['Meter'], get_human_readable_power(max(0, eimProductionWNow)).rjust(9, ' '))

        # The production meter needs to have been running for at least a day for this to be non-zero.
        if eimProductionWhToday:
            status += u' ({} Today'.format(get_human_readable_power(eimProductionWhToday, True))

            # The production meter has to have been running for at least 7 days for this to be non-zero.
            if eimProductionWhLast7Days: status += u' / {} Last 7 Days'.format(get_human_readable_power(eimProductionWhLast7Days, True))

            status += u')'

    # This requires a configured Consumption meter.
    if eimConsumptionWNow:
        status += u'\n{} Current Consumption {}'.format(stringNames['Meter'], get_human_readable_power(eimConsumptionWNow).rjust(8, ' '))

        # The consumption meter needs to have been running for at least a day for this to be non-zero.
        if eimConsumptionWhToday: status += u' ({} today)'.format(get_human_readable_power(eimConsumptionWhToday, True))

    # This was when the poll of all the microinverters had completed.
    invertersReadingTime = productionStatisticsInverters['readingTime']

    # Microinverters do not power up in very low light.
    if invertersReadingTime != 0:
        # Microinverters are only automatically polled by the gateway every 5 minutes (and they do not respond in very low light).
        nextRefreshTime = datetime.datetime.fromtimestamp(invertersReadingTime) + datetime.timedelta(minutes=5)

        # Print when the next update will be available.
        status += u'\n\n{}Data Will Next Be Refreshed At {}'.format(stringNames['Details'], nextRefreshTime.time())
    else:
        # Print when the last microinverter reported back to the gateway.
        status += u'\n\n{}The Last Microinverter Reported At {}'.format(stringNames['Details'], mostRecentInverterData)

    # Output to the console.
    print(status)

else:
    # Let the user know why the program is exiting.
    print('Unable to login to the gateway (bad, expired or missing token in credentials.json).')