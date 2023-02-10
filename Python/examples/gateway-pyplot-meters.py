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

import datetime    # We timestamp any errors.
import http.client # We handle a RemoteDisconnected exception.
import json        # This script makes heavy use of JSON parsing.
import os.path     # We check whether a file exists.
import sys         # We write to stderr.

import matplotlib.pyplot as plt          # Third party library; "pip install matplotlib"
import matplotlib.animation as animation # We use matplotlib animations for live data.

import requests.exceptions               # We handle some of the exceptions we might get back.

# All the shared Enphase® functions are in these packages.
from enphase_api.cloud.authentication import Authentication
from enphase_api.local.gateway import Gateway

def animate(_):
    # Sometimes a request will intermittently fail and in this event we retry.
    try:
        # Get gateway production, consumption and storage status.
        productionStatistics = gateway.api_call('/production.json')
    # Sometimes unable to connect (especially if using mDNS and it does not catch our query)
    except requests.exceptions.ConnectionError as exception:
        # Log this error.
        print('{} - Problem connecting..\n {}'.format(datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S'), exception), file=sys.stderr)

        # No point continuing this function.
        return
    except requests.exceptions.JSONDecodeError:
        # Log this non-critial often transient error.
        print('{} - The Gateway returned bad JSON..'.format(datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S')), file=sys.stderr)

        # No point continuing this function.
        return
    # Sometimes the Gateway can fail to respond properly.
    except http.client.RemoteDisconnected:
        # Log this non-critial often transient error.
        print('{} - The Gateway abruptly disconnected..'.format(datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S')), file=sys.stderr)

        # No point continuing this function.
        return

    # Add the current date/time to the sample for the x-axis.
    timestampData.append(datetime.datetime.now())

    # The Production meter can be not present (not Gateway Metered) or individually turned off (and they require a working CT clamp).
    meterStatisticsProduction = [meterStatus for meterStatus in metersStatus if meterStatus['measurementType'] == 'production'][0]
    if (meterStatisticsProduction['state'] == 'enabled'):
        # Get the Production section of the Production Statistics JSON that matches the configured meter mode.
        productionStatisticsProductionEIM = [productionStatistic for productionStatistic in productionStatistics['production'] if productionStatistic['type'] == 'eim' and productionStatistic['measurementType'] == meterStatisticsProduction['measurementType']][0]

        # Is the production meter responding?
        if productionStatisticsProductionEIM['activeCount'] > 0:
            # The current Production meter reading can read < 0 if energy (often a trace amount) is actually flowing the other way from the grid.
            productionData.append(max(0, productionStatisticsProductionEIM['wNow']))
        else:
            productionData.append(0)
    else:
        productionData.append(0)

    # The Consumption meter can be not present (not Gateway Metered) or individually turned off (and they require a working CT clamp).
    meterStatisticsConsumption = [meterStatus for meterStatus in metersStatus if meterStatus['measurementType'] == 'net-consumption' or meterStatus['measurementType'] == 'total-consumption'][0]
    if (meterStatisticsConsumption['state'] == 'enabled'):
        # Get the Consumption section for the right meter of the Production Statistics JSON.
        productionStatisticsConsumptionEIM = [productionStatistic for productionStatistic in productionStatistics['consumption'] if productionStatistic['type'] == 'eim' and productionStatistic['measurementType'] == meterStatisticsConsumption['measurementType']][0]

        # Is the consumption meter responding?
        if productionStatisticsConsumptionEIM['activeCount'] > 0:
            # Consumption statistics.
            consumptionData.append(productionStatisticsConsumptionEIM['wNow'])
        else:
            consumptionData.append(0)
    else:
        consumptionData.append(0)

    # Clear the chart ready for redrawing.
    axes.cla()

    # Annotate the axes.
    axes.set_title('Enphase® Gateway Meters\n')
    axes.set_xlabel('Time')
    axes.set_ylabel('Watts')

    # Plot the data.
    axes.plot(timestampData, productionData, c='#EC5E29', label='Production')
    axes.plot(timestampData, consumptionData, c='#1787AD', label='Consumption')
    axes.axhline(linewidth=0.3, color='k')

    # Add a scatter point at the end.
    axes.scatter(timestampData[-1], productionData[-1], c='#EC5E29')
    axes.scatter(timestampData[-1], consumptionData[-1], c='#1787AD')

    # Label the most recent result (at the end).
    axes.annotate(str(productionData[-1]) + ' W', xy=(timestampData[-1], productionData[-1]), xytext=(0, 5), textcoords='offset points')
    axes.annotate(str(consumptionData[-1]) + ' W', xy=(timestampData[-1], consumptionData[-1]), xytext=(0, 5), textcoords='offset points')

    # Display the legend.
    axes.legend()

    # Remove spines.
    axes.spines[['left','right','top']].set_visible(False)

    # Configure the axes' grid.
    axes.yaxis.grid(linestyle='dashed', alpha=0.8)

# Load credentials.
with open('configuration/credentials_token.json', mode='r', encoding='utf-8') as json_file:
    credentials = json.load(json_file)

# Do we have a valid JSON Web Token (JWT) to be able to use the service?
if not (credentials.get('Token') or Authentication.check_token_valid(credentials['Token'], credentials['GatewaySerialNumber'])):
    # It is not valid so clear it.
    raise ValueError('No or expired token.')

# Download and store the certificate from the gateway so all future requests are secure.
if not os.path.exists('configuration/gateway.cer'): Gateway.trust_gateway()

# Did the user override the library default hostname to the Gateway?
if credentials.get('Host'):
    # Get an instance of the Gateway API wrapper object (using the hostname specified in the config).
    gateway = Gateway(credentials['Host'])
else:
    # Get an instance of the Gateway API wrapper object (using the library default hostname).
    gateway = Gateway()

# Are we able to login to the gateway?
if gateway.login(credentials['Token']):
    # The meter status tells us if they are enabled and what mode they are operating in (production for production meter but net-consumption or total-consumption for consumption meter).
    metersStatus = gateway.api_call('/ivp/meters')

    # The lists which will hold the data.
    timestampData = []
    productionData = []
    consumptionData = []

    # The figure.
    figure = plt.figure('Enphase® Gateway Meters', figsize=(12,6), facecolor='#DEDEDE')

    # The axes (or chart).
    axes = figure.subplots()
    axes.set_facecolor('#DEDEDE')

    # Set a timer to animate the chart every 1000ms.
    animation = animation.FuncAnimation(figure, animate, interval=1000)

    # Show the plot screen.
    plt.show()

else:
    # Let the user know why the program is exiting.
    raise ValueError('Unable to login to the gateway (bad, expired or missing token in credentials_token.json).')