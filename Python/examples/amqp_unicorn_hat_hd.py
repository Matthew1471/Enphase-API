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

# We count forwards then backwards.
import itertools

# This script makes heavy use of JSON parsing.
import json

# We check what operating system we are running on and we check whether a file exists.
import os

# We write to stderr.
import sys

# We use the sleep function to pause between screen draws.
import time

# Unicorn HAT HD uses pillow to generate images to then draw on the LEDs of the Unicorn HAT HD ("pip install pillow" if getting import errors).
from PIL import Image, ImageDraw, ImageFont

# We look-up the weather.
import requests

# We handle some of the exceptions we might get back.
import requests.exceptions

# Third party library; "pip install pika"
import pika

class UnicornHATHelper:

    @staticmethod
    def draw_scrolling_text(unicornhathd, screen_width, screen_height, line, color, font, speed=0.04, end_time=time.time() + 60):
        # Calculate the width and height of the text when rendered by the font.
        _, font_upper, font_width, _ = font.getbbox(line)

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
                        red, green, blue = [int(n) for n in pixel]

                        # Tell the Unicorn HAT HD to set the LED pixel buffer to be set to the same as the Pillow in memory image pixel.
                        unicornhathd.set_pixel((screen_width - 1) - x, y, red, green, blue)

                # The screen has been re-drawn in the buffer so now set the Unicorn HAT HD to reflect the buffer (so the user won't watch it re-drawing).
                unicornhathd.show()

                # Pause before attempting to draw the next scrolling frame.
                time.sleep(speed)

            # Have we been asked to stop scrolling?
            if end_time <= time.time():
                # Pause briefly before returning.
                time.sleep(speed*2)

                # Return.
                break

    @staticmethod
    def draw_animation(unicornhathd, screen_width, screen_height, filename, speed=0.10):
        # Open the requested image (and ignore any transparency values).
        image = Image.open('resources/icons/' + filename + '.png').convert("RGB")

        # The images are left-to-right.
        unicornhathd.rotation(unicornhathd.get_rotation() + 90)

        # Get the image width and height.
        image_width, image_height = image.size

        # Take each of the frame x positions in the image.
        for frame_x in range(int(image_width / screen_width)):
            # Take each of the frame y positions in the image.
            for frame_y in range(int(image_height / screen_height)):
                # Take each of the pixels of the screen's x axis.
                for x in range(screen_width):
                    # Take each of the pixels of the screen's y axis for this position on the x axis.
                    for y in range(screen_height):
                        # Get what the pixel should be according to the Pillow in memory image followed by the x axis frame offset.
                        pixel = image.getpixel(((frame_x * screen_width) + y, (frame_y * screen_height) + x))

                        # Get the Red, Green, Blue values for this pixel.
                        red, green, blue = [int(n) for n in pixel]

                        # Tell the Unicorn HAT HD to set the LED pixel buffer to be set to the same as the Pillow in memory image pixel.
                        unicornhathd.set_pixel(x, y, red, green, blue)

                # The screen has been re-drawn in the buffer so now set the Unicorn HAT HD to reflect the buffer (so the user will not watch it re-drawing).
                unicornhathd.show()

                # Pause before attempting to draw the next scrolling frame.
                time.sleep(speed)

        # Restore rotation.
        unicornhathd.rotation(unicornhathd.get_rotation() - 90)

class ScreenWeather:

    def __init__(self, unicornhathd, screen_width, screen_height, latitude, longitude, emulator=False):
        self.unicornhathd = unicornhathd
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.latitude = latitude
        self.longitude = longitude
        self.emulator = emulator

        self.weather_last_updated = None
        self.weather_filename = None

    def draw_screen(self):
        # If the weather has not been loaded yet, or it was loaded over 15 minutes ago.
        if not self.weather_last_updated or self.weather_last_updated + 900 < time.time():
            # Get the latest weather.
            weather_code, wind_speed, sunrise, sunset = self.get_weather_details()

            # Set the weather_last_updated date/time.
            self.weather_last_updated = time.time()

            # We convert the weather_code, wind_speed, sunrise and sunset into a PNG filename.
            self.weather_filename = self.get_weather_filename(weather_code=weather_code, wind_speed=wind_speed, sunrise=sunrise, sunset=sunset)

        # Draw the weather animation.
        UnicornHATHelper.draw_animation(
                                        unicornhathd=self.unicornhathd,
                                        screen_width=self.screen_width,
                                        screen_height=self.screen_height,
                                        filename=self.weather_filename
                                       )

        # Clear the screen while the next process runs.
        if not self.emulator:
            self.unicornhathd.off()

    def get_weather_details(self, timezone='Europe%2FLondon'):
        # Get a Y-m-d reference to today's date.
        today = datetime.datetime.today().strftime('%Y-%m-%d')

        # Build the weather URL.
        weather_url = 'https://api.open-meteo.com/v1/forecast?'
        weather_url += 'latitude=' + str(self.latitude)
        weather_url += '&longitude=' + str(self.longitude)
        weather_url += '&current_weather=true'
        weather_url += '&daily=sunrise,sunset'
        weather_url += '&start_date=' + today
        weather_url += '&end_date=' + today
        weather_url += '&timezone=' + timezone
        weather_url += '&timeformat=unixtime'

        # Request the weather.
        response = requests.get(weather_url, headers={'User-Agent': None, 'Accept':'application/json', 'DNT':'1'}, timeout=5).json()

        # Return some specific components from the weather data.
        return response['current_weather']['weathercode'], response['current_weather']['windspeed'], response['daily']['sunrise'][0], response['daily']['sunset'][0]

    def get_weather_filename(self, weather_code, wind_speed, sunrise, sunset):
        # Windy.
        if wind_speed >= 20:
            filename = 'wind' if sunrise <= time.time() <= sunset else 'cloudy'
        # Clear sky.
        elif weather_code == 0:
            filename = 'clear-day' if sunrise <= time.time() <= sunset else 'clear-night'
        # Mainly clear and Partly cloudy.
        elif 1 <= weather_code <= 2:
            filename = 'partly-cloudy-day' if sunrise <= time.time() <= sunset else 'partly-cloudy-night'
        # Overcast.
        elif weather_code == 3:
            filename = 'cloudy'
        # Fog and depositing rime fog.
        elif 45 <= weather_code <= 48:
            filename = 'fog'
        # Drizzle: Light, moderate, and dense intensity, Freezing Drizzle: Light and dense intensity, Rain: Slight, moderate and heavy intensity and Freezing Rain: Light and heavy intensity.
        elif 51 <= weather_code <= 67:
            filename = 'rain' if sunrise <= time.time() <= sunset else 'cloudy'
        # Snow fall: Slight, moderate, and heavy intensity and Snow grains.
        elif 71 <= weather_code <= 77:
            filename = 'snow' if sunrise <= time.time() <= sunset else 'cloudy'
        # Rain showers: Slight, moderate, and violent.
        elif 80 <= weather_code <= 82:
            filename = 'rain' if sunrise <= time.time() <= sunset else 'cloudy'
        # Snow showers slight and heavy.
        elif 85 <= weather_code <= 86:
            filename = 'snow' if sunrise <= time.time() <= sunset else 'cloudy'
        # Thunderstorm: Slight or moderate, Thunderstorm with slight and heavy hail.
        elif 95 <= weather_code <= 99:
            filename = 'cloudy' if sunrise <= time.time() <= sunset else 'cloudy'
        # Unknown weather_code.
        else:
            filename = 'error'

        # Return the calculated image filename.
        return filename

class ScreenProduction:
    def __init__(self, unicornhathd, screen_width, screen_height, font, maximum_watts_per_panel, speed=0.04, emulator=False):
        self.unicornhathd = unicornhathd
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.font = font
        self.maximum_watts_per_panel = maximum_watts_per_panel
        self.speed = speed
        self.emulator = emulator

    def get_human_readable_power(self, watts, in_hours = False):
        # Is the significant number of watts (i.e. positive or negative number) less than 1,000?
        if abs(round(watts)) < 1000:
            # Report the number in watts (rounded to the nearest number).
            return str(round(watts)) + ' W' + ('h' if in_hours else '')

        # Divide the number by a thousand and report it in kW (to 2 decimal places).
        return str(round(watts / 1000, 2)) + ' kW' + ('h' if in_hours else '')

    def draw_screen(self, number_of_microinverters, watts, end_time):
        # Is there any power being generated?
        if watts >= 1:
            # The line of text we want to write on the screen is a wattage number to be formatted.
            line = self.get_human_readable_power(watts)

            # Calculate the colour of the text based off the production wattage.
            color = tuple([int(n * 255) for n in colorsys.hsv_to_rgb(int(watts / self.maximum_watts_per_panel) / number_of_microinverters, 1.0, 1.0)])

            # Display and scroll the production text on screen (until the end time).
            UnicornHATHelper.draw_scrolling_text(
                                                 unicornhathd=self.unicornhathd,
                                                 screen_width=self.screen_width,
                                                 screen_height=self.screen_height,
                                                 line=line,
                                                 color=color,
                                                 font=self.font,
                                                 speed=self.speed,
                                                 end_time=end_time
                                                )

class ScreenChart:
    def __init__(self, unicornhathd, screen_width, screen_height, maximum_watts_per_panel):
        self.unicornhathd = unicornhathd
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.maximum_peak_watts_per_panel = maximum_watts_per_panel

        # IQ7A Detected.
        if maximum_watts_per_panel == 366:
            self.maximum_continuous_watts_per_panel = 349
        # Unknown.
        else:
            self.maximum_continuous_watts_per_panel = None

        self.number_of_pixels = self.screen_width * self.screen_height

    def draw_screen(self, number_of_microinverters, production, consumption):
        total_capacity = number_of_microinverters * self.maximum_peak_watts_per_panel

        # Check the maxium_watts_per_panel setting is correct.
        if production > total_capacity:
            raise ValueError('Production (' + production + ') exceeds the total capacity (' + total_capacity + '), check maximum_watts_per_panel setting.')

        # Have we got more consumption than total production capacity?
        if consumption > total_capacity:
            # Set the total capacity to be the current consumption.
            total_capacity = consumption

        # Calculate how many watts each pixel represents.
        watts_per_pixel = (total_capacity / self.number_of_pixels)

        # Calculate how many pixels of production and consumption we have.
        number_of_production_pixels = int(production / watts_per_pixel)
        number_of_consumption_pixels = int(consumption / watts_per_pixel)

        # Some common RGB colours.
        red = (255, 0, 0)
        green = (0, 255, 0)
        light_green = (0, 150, 0)

        # Add the consumption pixels.
        pixels = [(number_of_consumption_pixels,red)]

        # The microinverters can only support a certain continuous load.
        if self.maximum_continuous_watts_per_panel:
            total_continuous_capacity = number_of_microinverters * self.maximum_continuous_watts_per_panel

            # Is the production exceeding the continuous output power?
            if production > total_continuous_capacity:
                number_of_continuous_pixels = int(total_continuous_capacity / watts_per_pixel)
                pixels.append((number_of_continuous_pixels,green))
                pixels.append((number_of_production_pixels,light_green))
            else:
                pixels.append((number_of_production_pixels,green))
        else:
            pixels.append((number_of_production_pixels,green))

        # Sort the pixels (in ascending order).
        pixels.sort()

        # By default the remaining pixels are off.
        if pixels[-1][0] < self.number_of_pixels:
            pixels.append((self.number_of_pixels,(0, 0, 0)))

        # The pixels are left-to-right.
        self.unicornhathd.rotation(self.unicornhathd.get_rotation() + 90)

        # Take each of the sorted pixel ranges.
        previous_index = 0
        for pixel_count, pixel_color in pixels:
            # Take each of the pixels within this range.
            for count in range(previous_index, pixel_count):
                # X = Top to Bottom
                # Y = Left To Right
                self.unicornhathd.set_pixel(int(count / self.screen_height), int(count % self.screen_width), *pixel_color)

            # This is the start pixel of the next iteration.
            previous_index = pixel_count

        # Show the contents of the buffer.
        self.unicornhathd.show()

        # Restore rotation.
        self.unicornhathd.rotation(self.unicornhathd.get_rotation() - 90)

def restricted_float(number):
    # Check this is a float.
    try:
        number = float(number)
    except ValueError:
        raise argparse.ArgumentTypeError(str(number) + ' not a floating-point literal')

    # Check this is within the required range.
    if number < 0.0 or number > 1.0:
        raise argparse.ArgumentTypeError(str(number) + ' not in range [0.0, 1.0]')

    # This should otherwise be an acceptable value.
    return number

def main():
    # Create an instance of argparse to handle any command line arguments.
    parser = argparse.ArgumentParser(prefix_chars='/-', add_help=False, description='A program that connects to an Enphase® Gateway and displays the production values on a Unicorn HAT HD.')

    # Arguments to control the display of data on the Unicorn HAT HD.
    display_group = parser.add_argument_group('Display')
    display_group.add_argument('/Brightness', '-Brightness', '--Brightness', dest='brightness', type=restricted_float, help='How bright the screen should be (defaults to 0.5).')
    display_group.add_argument('/Delay', '-Delay', '--Delay', dest='delay', type=float, default=0.04, help='How long to wait (in seconds) before drawing the next frame (defaults to 0.04 which is every 40ms).')
    display_group.add_argument('/Rotate', '-Rotate', '--Rotate', dest='rotate', type=int, default=90, help='How many degress to rotate the screen by (defaults to 90).')

    # Arguments to control how the program generally behaves.
    general_group = parser.add_argument_group('General')
    general_group.add_argument('/NumberOfMicroinverters', '-NumberOfMicroinverters', '--NumberOfMicroinverters', dest='number_of_microinverters', type=int, default=14, help='How many microinverters are installed (defaults to 14).')
    general_group.add_argument('/MaxWattsPerPanel', '-MaxWattsPerPanel', '--MaxWattsPerPanel', dest='maximum_watts_per_panel', type=int, default=384, help='How many watts maximum can each panel generate (defaults to 384 which is the limit of an IQ8H).')

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
    with open('configuration/credentials_token.json', mode='r', encoding='utf-8') as json_file:
        credentials = json.load(json_file)

    # Rotate the image (e.g. if the screen is on its side).
    if args.rotate:
        unicornhathd.rotation(args.rotate)

    # Set the brightness of the screen (defaults to 0.5).
    if args.brightness:
        unicornhathd.brightness(args.brightness)

    # Get the screen dimensions for the Unicorn HAT HD.
    screen_width, screen_height = unicornhathd.get_shape()

    # If running on Microsoft Windows® instead of a Raspberry Pi (such as when developing) get the font from the resources directory instead.
    if os.name != 'nt':
        # Which font to use to render the text.
        font_path = '/usr/share/fonts/truetype/freefont/FreeSansBold.ttf'
    else:
        # https://ftp.gnu.org/gnu/freefont/
        font_path = 'resources/FreeSansBold.ttf'

    # Use `fc-list` to show a list of installed fonts on your system, or "ls /usr/share/fonts/" and explore.
    # There's also more fonts in apt packages "fonts-droid" and "fonts-roboto".
    font = ImageFont.truetype(font_path, 20)

    # Should we display the weather?
    if credentials.get('latitude') and credentials.get('longitude') and os.path.exists('resources/icons/'):
        screen_weather = ScreenWeather(
                                        unicornhathd=unicornhathd,
                                        screen_width=screen_width,
                                        screen_height=screen_height,
                                        latitude=credentials['latitude'],
                                        longitude=credentials['longitude'],
                                        emulator=args.emulate_HAT
                                        )
    else:
        screen_weather = None

    # Set up an instance of the production screen.
    screen_production = ScreenProduction(
                                            unicornhathd=unicornhathd,
                                            screen_width=screen_width,
                                            screen_height=screen_height,
                                            font=font,
                                            maximum_watts_per_panel=args.maximum_watts_per_panel,
                                            speed=args.delay,
                                            emulator=args.emulate_HAT
                                        )

    # Set up an instance of the chart screen.
    screen_chart = ScreenChart(
                                unicornhathd=unicornhathd,
                                screen_width=screen_width,
                                screen_height=screen_height,
                                maximum_watts_per_panel=args.maximum_watts_per_panel,
                                )

    # Gather the AMQP details from the credentials file.
    amqp_host = credentials.get('amqp_host', 'localhost')
    amqp_username = credentials.get('amqp_username', 'guest')
    amqp_password = credentials.get('amqp_password', 'guest')

    # Gather the AMQP credentials into a PlainCredentials object.
    amqp_credentials = pika.PlainCredentials(username=amqp_username, password=amqp_password)

    # The information that is visible to the broker.
    client_properties = {
                            'connection_name': 'AMQP_Unicorn_HAT_HD',
                            'product': 'Enphase-API',
                            'version': '0.1',
                            'information': 'https://github.com/Matthew1471/Enphase-API'
                        }

    # Gather the AMQP connection parameters.
    amqp_parameters = pika.ConnectionParameters(host=amqp_host, credentials=amqp_credentials, client_properties=client_properties)

    # Connect to the AMQP broker.
    amqp_connection = pika.BlockingConnection(parameters=amqp_parameters)

    # Get reference to the virtual connection within AMQP.
    amqp_channel = amqp_connection.channel()

    # Declare a queue (if it does not already exist).
    amqp_result = amqp_channel.queue_declare(queue='Enphase_Unicorn_HAT_HD', durable=False, exclusive=True, auto_delete=True)

    # Bind the queue to the exchange (if it is not already bound).
    amqp_channel.queue_bind(exchange='Enphase', queue=amqp_result.method.queue, routing_key='#')

    # We may reference this when no messages are obtained from the queue.
    timestamp = 0

    try:
        # Repeat forever unless the user presses CTRL + C.
        while True:
            # Optionally draw the weather.
            if screen_weather:
                # A weather request may fail.
                try:
                    screen_weather.draw_screen()
                # Sometimes unable to connect
                except requests.exceptions.ConnectionError as exception:
                    # Log this error.
                    print(datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S') + ' - Problem connecting for the weather.\n ' +  str(exception), file=sys.stderr)
                # This happens generally if there are wider issues on the network.
                except requests.exceptions.ReadTimeout:
                    # Log this non-critial often transient error.
                    print(datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S') + ' - The weather request timed out.', file=sys.stderr)
                except requests.exceptions.JSONDecodeError as exception:
                    # Log this non-critial often transient error.
                    print(datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S') + ' - The weather returned bad JSON..\n ' + str(exception), file=sys.stderr)

            # AMQP get a meter response.
            while True:
                # Get a message.
                method_frame, header_frame, body = amqp_channel.basic_get(amqp_result.method.queue, auto_ack=True)

                # Was there a message?
                if method_frame:
                    # If there are more messages keep consuming until this is the last one.
                    if method_frame.message_count > 0:
                        continue

                    json_object = json.loads(body)
                    timestamp = json_object['timestamp']
                    production_power = json_object['readings']['production']['ph-a']['p']
                    consumption_power = json_object['readings']['total-consumption']['ph-a']['p']
                else:
                    # Ran out of responses.
                    break

            # Check the data is within the last 5 seconds.
            if timestamp > time.time()-5:
                # Draw the production power screen (until the end time).
                screen_production.draw_screen(number_of_microinverters=args.number_of_microinverters, watts=production_power, end_time=time.time() + 5)

                # Draw the chart screen (for 5 seconds).
                screen_chart.draw_screen(number_of_microinverters=args.number_of_microinverters, production=production_power, consumption=consumption_power)
                time.sleep(5)
            elif not screen_weather:
                # Display and scroll the red error text on screen for 10 seconds (if the weather won't otherwise loop).
                UnicornHATHelper.draw_scrolling_text(unicornhathd=unicornhathd, screen_width=screen_width, screen_height=screen_height, line='Error', color=(255, 0, 0), font=font, speed=args.delay, end_time=time.time() + 10)
    # Did the user press CTRL + C to attempt to quit this application?
    except KeyboardInterrupt:
        # Clear the buffer, immediately update Unicorn HAT HD to turn off all the pixels.
        unicornhathd.off()
    # Clear the display so the LEDs are not left stuck on when this program quits.
    finally:
        # Clear the buffer, immediately update Unicorn HAT HD to turn off all the pixels.
        unicornhathd.off()

# Launch the main method if invoked directly.
if __name__ == '__main__':
    main()