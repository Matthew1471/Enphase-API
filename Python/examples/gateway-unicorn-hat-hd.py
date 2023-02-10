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

# We support command line arguments.
import argparse

# We generate a range of colours to use to show different production values.
import colorsys

# We timestamp any errors.
import datetime

# We handle a RemoteDisconnected exception.
import http.client

# We count forwards then backwards.
import itertools

# This script makes heavy use of JSON parsing.
import json

# We check what operating system we are running on and we check whether a file exists (and build OS independent paths).
import os

# We write to stderr.
import sys

# We use the sleep function to pause between screen draws.
import time

# Unicorn HAT HD uses pillow to generate images to then draw on the LEDs of the Unicorn HAT HD ("pip install pillow" if getting import errors).
from PIL import Image, ImageDraw, ImageFont

# We handle some of the exceptions we might get back.
import requests.exceptions

# All the shared Enphase® functions are in these packages.
from enphase_api.cloud.authentication import Authentication
from enphase_api.local.gateway import Gateway

def get_human_readable_power(watts, inHours = False):
    # Is the significant number of watts (i.e. positive or negative number) less than a thousand?
    if abs(round(watts)) < 1000:
        # Report the number in watts (rounded to the nearest number).
        return '{} W{}'.format(round(watts), 'h' if inHours else '')
    else:
        # Divide the number by a thousand and report it in kW (to 2 decimal places).
        return '{} kW{}'.format(round(watts / 1000, 2), 'h' if inHours else '')

def restricted_float(number):
    # Check this is a float.
    try:
        number = float(number)
    except ValueError:
        raise argparse.ArgumentTypeError('{!r} not a floating-point literal'.format(number))

    # Check this is within the required range.
    if number < 0.0 or number > 1.0:
        raise argparse.ArgumentTypeError('{!r} not in range [0.0, 1.0]'.format(number))

    # This should otherwise be an acceptable value.
    return number

def get_production_text(gateway, maximum_watts_per_panel):
    # Get Gateway status.
    production_json = gateway.api_call('/production.json')

    # We generate text colours for production thresholds within the HSV scale based off the number of microinverter devices (which should correspond to overall system size).
    number_of_microinverters = production_json['production'][0]['activeCount']

    # Get a reference to just the inverters bit of the Production JSON.
    inverters_json = production_json['production'][0]

    # Get the watts being generated now by the inverters.
    w_now = inverters_json['wNow']

    # Calculate the colour of the text based off the production wattage.
    color = tuple([int(n * 255) for n in colorsys.hsv_to_rgb(int(w_now / maximum_watts_per_panel) / number_of_microinverters, 1.0, 1.0)])

    # The inverters are polled every 5 minutes (so we can make sure we only attempt a refresh when there's likely new data).
    if inverters_json['readingTime'] != 0:
        # Take the reading time and add 5 minutes (300 seconds).
        next_reading_time = inverters_json['readingTime'] + 300

        # If the data is already stale try again in 60 seconds.
        if next_reading_time <= time.time(): next_reading_time = time.time() + 60
    else:
        # We should try in 60 seconds.
        next_reading_time = time.time() + 60

    # Return the response.
    return w_now, color, next_reading_time

def draw_scrolling_text(unicornhathd, line, color, font, screen_width, screen_height, speed, end_time):
    # Calculate the width and height of the text when rendered by the font.
    _, font_upper, font_width, font_height = font.getbbox(line)

    # Create a new image in memory that can fit all the text pixels (we scroll text wider than the screen, but there's no point storing a larger height).
    image = Image.new('RGB', (max(font_width, screen_width), screen_height), (0, 0, 0))

    # Create a draw object that uses our image canvas.
    draw = ImageDraw.Draw(image)

    # Draw the text in memory onto the canvas (we set the text colour based off system production energy we're generating).
    draw.text(xy=(0, -font_upper), text=line, fill=color, font=font)

    # We want to scroll left to right multiple times (at least once).
    while True:

        # For each pixel we are scrolling forwards then backwards.
        for scroll_x_offset in itertools.chain(range(font_width - screen_width), range(font_width - screen_width, 0, -1)):

            # Take each of the pixels on the x axis.
            for x in range(screen_width):

                # Take each of the pixels on the y axis for this position on the x axis.
                for y in range(screen_height):

                    # Get what the pixel should be according to the Pillow in memory image followed by the x axis scrolling offset.
                    pixel = image.getpixel((x + scroll_x_offset, y))

                    # Get the Red, Green, Blue values for this pixel.
                    r, g, b = [int(n) for n in pixel]

                    # Tell the Unicorn HAT HD to set the LED pixel buffer to be set to the same as the Pillow in memory image pixel.
                    unicornhathd.set_pixel((screen_width - 1) - x, y, r, g, b)

            # The screen has been re-drawn in the buffer so now set the Unicorn HAT HD to reflect the buffer (so the user won't watch it re-drawing).
            unicornhathd.show()

            # Pause before attempting to draw the next scrolling frame.
            time.sleep(speed)

        # Have we been asked to stop scrolling?
        if end_time <= time.time(): break

def main():
    # Create an instance of argparse to handle any command line arguments.
    parser = argparse.ArgumentParser(prefix_chars='/-', add_help=False, description='A program that connects to an Enphase® Gateway and displays the production values on a Unicorn HAT HD.')

    # Arguments to control the display of data on the Unicorn HAT HD.
    display_group = parser.add_argument_group('Display')
    display_group.add_argument('/Brightness', '-Brightness', '--Brightness', dest='brightness', type=restricted_float, help='How bright the screen should be (defaults to 0.5).')
    display_group.add_argument('/Delay', '-Delay', '--Delay', dest='delay', type=float, default=0.05, help='How long to wait (in seconds) before drawing the next frame (defaults to 0.05 which is every 50ms).')
    display_group.add_argument('/Rotate', '-Rotate', '--Rotate', dest='rotate', type=int, default=90, help='How many degress to rotate the screen by (defaults to 90).')

    # Arguments to control how the program generally behaves.
    general_group = parser.add_argument_group('General')
    general_group.add_argument('/Host', '-Host', '--Host', dest='host', help='The Enphase® Gateway URL (defaults to config or https://envoy.local).')
    general_group.add_argument('/MaxWattsPerPanel', '-MaxWattsPerPanel', '--MaxWattsPerPanel', dest='maximum_watts_per_panel', type=int, default=460, help='How many watts maximum can each panel generate (defaults to 460 which is the limit of an IQ7A).')

    # Arguments that can overide default behaviour when testing this program.
    testing_group = parser.add_argument_group('Testing')
    testing_group.add_argument('/EmulateHAT', '-EmulateHAT', '--EmulateHAT', dest='emulate_HAT', action='store_true', help='Emulate a Unicorn HAT HD on a development machine.')

    # We want this to appear last in the argument usage list.
    general_group.add_argument('/?', '/Help', '/help', '-h','--help','-help', action='help', help='Show this help message and exit.')

    # Handle any command line arguments.
    args = parser.parse_args()

    # We allow emulation of the Unicorn HAT HD if requested via command line arguments.
    if not args.emulate_HAT:
        # This program requires a Unicorn HAT HD (https://shop.pimoroni.com/products/unicorn-hat-hd)
        import unicornhathd
    else:
        # Alternatively you can simulate a Unicorn HAT HD ("pip install unicorn-hat-sim").
        from unicorn_hat_sim import unicornhathd

    # Load credentials.
    with open(os.path.join('configuration','credentials_token.json'), mode='r', encoding='utf-8') as json_file:
        credentials = json.load(json_file)

    # Do we have a valid JSON Web Token (JWT) to be able to use the service?
    if not (credentials.get('Token') and Authentication.check_token_valid(credentials['Token'], credentials['GatewaySerialNumber'])):
        # It is not valid so clear it.
        raise ValueError('No or expired token.')

    # Did the user override the config or library default hostname to the Gateway?
    if args.host:
        # Get an instance of the Gateway API wrapper object (using the argument hostname).
        gateway = Gateway(args.host)
    elif credentials.get('Host'):
        # Get an instance of the Gateway API wrapper object (using the hostname specified in the config).
        gateway = Gateway(credentials['Host'])
    else:
        # Get an instance of the Gateway API wrapper object (using the library default hostname).
        gateway = Gateway()

    # Are we able to login to the gateway?
    if gateway.login(credentials['Token']):

        # Rotate the image (e.g. if the screen is on its side).
        if args.rotate: unicornhathd.rotation(args.rotate)

        # Set the brightness of the screen (defaults to 0.5).
        if args.brightness: unicornhathd.brightness(args.brightness)

        # Get the screen dimensions for the Unicorn HAT HD.
        screen_width, screen_height = unicornhathd.get_shape()

        # If running on Microsoft Windows® instead of a Raspberry Pi (such as when developing) get the font from the resources directory instead.
        if os.name != 'nt':
            # Which font to use to render the text.
            font_path = '/usr/share/fonts/truetype/freefont/FreeSansBold.ttf'
        else:
            # https://ftp.gnu.org/gnu/freefont/
            font_path = os.path.join('resources','FreeSansBold.ttf')

        # Use `fc-list` to show a list of installed fonts on your system, or "ls /usr/share/fonts/" and explore.
        # There's also more fonts in apt packages "fonts-droid" and "fonts-roboto".
        font = ImageFont.truetype(font_path, 20)

        try:
            # Repeat forever unless the user presses CTRL + C.
            while True:
                # Sometimes a request will intermittently fail and in this event we return error text.
                try:
                    # Get the text to display.
                    w_now, color, end_time = get_production_text(gateway=gateway, maximum_watts_per_panel=args.maximum_watts_per_panel)

                    # Is there any power being generated?
                    if w_now != 0:
                        # The line of text we want to write on the screen is a wattage number to be formatted.
                        line = get_human_readable_power(w_now)

                        # Display and scroll the production text on screen (until the end time).
                        draw_scrolling_text(unicornhathd=unicornhathd, line=line, color=color, font=font, screen_width=screen_width, screen_height=screen_height, speed=args.delay, end_time=end_time)
                    else:
                        # Turn off the screen.
                        unicornhathd.off()

                        # Wait for 60 seconds before re-trying.
                        time.sleep(60)
                # Sometimes unable to connect (especially if using mDNS and it does not catch our query)
                except requests.exceptions.ConnectionError as exception:
                    # Log this error.
                    print('{} - Problem connecting..\n {}'.format(datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S'), exception), file=sys.stderr)

                    # Display and scroll the red error text on screen for 60 seconds.
                    draw_scrolling_text(unicornhathd=unicornhathd, line='Error', color=(255, 0, 0), font=font, screen_width=screen_width, screen_height=screen_height, speed=args.delay, end_time=time.time() + 60)
                # This happens generally if there are wider issues on the network.
                except requests.exceptions.ReadTimeout:
                    # Log this non-critial often transient error.
                    print('{} - Request timed out..'.format(datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S')), file=sys.stderr)

                    # Display and scroll the red error text on screen for 60 seconds.
                    draw_scrolling_text(unicornhathd=unicornhathd, line='Error', color=(255, 0, 0), font=font, screen_width=screen_width, screen_height=screen_height, speed=args.delay, end_time=time.time() + 60)
                except requests.exceptions.JSONDecodeError:
                    # Log this non-critial often transient error.
                    print('{} - The Gateway returned bad JSON..'.format(datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S')), file=sys.stderr)

                    # Display and scroll the red error text on screen for 60 seconds.
                    draw_scrolling_text(unicornhathd=unicornhathd, line='Error', color=(255, 0, 0), font=font, screen_width=screen_width, screen_height=screen_height, speed=args.delay, end_time=time.time() + 60)
                # Sometimes the Gateway can fail to respond properly.
                except http.client.RemoteDisconnected as exception:
                    # Log this non-critial often transient error.
                    print('{} - The Gateway abruptly disconnected..\n {}'.format(datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S'), exception), file=sys.stderr)

                    # Display and scroll the red error text on screen for 60 seconds.
                    draw_scrolling_text(unicornhathd=unicornhathd, line='Error', color=(255, 0, 0), font=font, screen_width=screen_width, screen_height=screen_height, speed=args.delay, end_time=time.time() + 60)
        # Did the user press CTRL + C to attempt to quit this application?
        except KeyboardInterrupt:
            # Clear the buffer, immediately update Unicorn HAT HD to turn off all the pixels.
            unicornhathd.off()
        # Clear the display so the LEDs are not left stuck on when this program quits.
        finally:
            # Clear the buffer, immediately update Unicorn HAT HD to turn off all the pixels.
            unicornhathd.off()

    # Token is not valid and this program will not refresh it (this program is not given the Enphase® username and password).
    else:
        # Let the user know why the program is exiting.
        raise ValueError('Unable to login to the gateway (bad, expired or missing token in credentials_token.json).')

# Launch the main method if invoked directly.
if __name__ == '__main__':
    main()