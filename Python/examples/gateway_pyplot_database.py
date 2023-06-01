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

import argparse # We support command line arguments.

import matplotlib.pyplot as plt          # Third party library; "pip install matplotlib"
import matplotlib.animation as animation # We use matplotlib animations for live data.
import matplotlib.dates                  # We use matplotlib date functions for comparisons.

import mysql.connector                   # Third party library; "pip install mysql-connector-python"

# Contains the program argument data.
args = None

# Contains the axes (or chart).
axes = None

# The cursor for the database connection.
database_cursor = None

# The matplotlib figure.
figure = None

# The reference to the Gateway wrapper itself.
gateway = None

# The lists which will hold the underlying raw data.
timestamp_data = []
production_data = []
consumption_net_data = []
consumption_total_data = []

# Reference to the plots and annotations.
production_plot = None
production_annotation = None
consumption_net_plot = None
consumption_net_annotation = None
consumption_total_plot = None
consumption_total_annotation = None

# Will map legend lines to artists.
legend_map = {}

# The last seen database ReadingID.
last_seen_reading_id = 0

# SQL statement.
get_meter_readings_sql = ('SELECT ReadingID, Timestamp, Production_P, NetConsumption_P, TotalConsumption_P '
                          'FROM MeterReading_SinglePhase_View '
                          'WHERE ReadingID > %s '
                          'ORDER BY ReadingID ASC')

def add_results_from_database():
    global last_seen_reading_id

    # Get the meter readings.
    database_cursor.execute(get_meter_readings_sql, (last_seen_reading_id,))

    # A flag to determine if there were any new records added.
    found_records = False

    # Take each of the new records and add them to the lists.
    for (reading_id, timestamp, production_p, net_consumption_p, total_consumption_p) in database_cursor:
        # Add the current date/time to the sample for the x-axis.
        timestamp_data.append(timestamp)

        # The current Production meter reading can read < 0 if energy (often a trace amount) is actually flowing the other way from the grid.
        production_data.append(max(0, production_p))

        # Consumption statistics.
        consumption_net_data.append(0-net_consumption_p)
        consumption_total_data.append(0-total_consumption_p)

        # We have seen at least one record.
        found_records = True

        # Update the last seen ID.
        last_seen_reading_id = reading_id

    return found_records

def on_pick(event):
    # On the pick event, take the line in the legend.
    legend_line = event.artist

    # Toggle the mapped plot visibility (based off the plot's visibility).
    original_artist = legend_map[legend_line]
    visible = not original_artist[0].get_visible()

    # Set the visibility on the plot and annotation.
    _ = [artist.set_visible(visible) for artist in original_artist]

    # Change the alpha on the line in the legend, so we can see what lines have been toggled.
    legend_line.set_alpha(1.0 if visible else 0.2)

    # Redraw the chart.
    figure.canvas.draw()

def setup_plot():
    # The figure.
    figure = plt.figure('Enphase® Gateway Meters', figsize=(12,6), facecolor='#DEDEDE')

    # Allow the figure to be clickable.
    figure.canvas.mpl_connect('pick_event', on_pick)

    # The axes (or chart).
    global axes
    axes = figure.subplots()
    axes.set_facecolor('#DEDEDE')

    # Annotate the axes.
    axes.set_title('Enphase® Gateway Meters\n')
    axes.set_xlabel('Time')
    axes.set_ylabel('Watts')

    # Plot the data.
    global production_plot, consumption_total_plot, consumption_net_plot
    production_plot, = axes.plot(timestamp_data, production_data, c='#EC5E29', label='Production', marker='o', markevery=[-1])
    consumption_total_plot, = axes.plot(timestamp_data, consumption_total_data, c='#29B7EC', label='Consumption', marker='o', markevery=[-1])
    consumption_net_plot, = axes.plot(timestamp_data, consumption_net_data, c='#29EC5E', label='Export/Import', marker='o', markevery=[-1], visible=False)

    # Draw a horizontal line at 0 indicating import/export threshold.
    axes.axhline(linewidth=0.3, color='k')

    # Add the optional peak and continuous wattage limit lines of the micro-inverters.
    if args.peak: axes.axhline(y=args.peak, linewidth=1, color='r')
    if args.continuous: axes.axhline(y=args.continuous, linewidth=1, color='y')

    # Label the most recent result (at the end).
    global production_annotation, consumption_total_annotation, consumption_net_annotation
    production_annotation = axes.annotate(str(production_data[-1]) + ' W', xy=(timestamp_data[-1], production_data[-1]), xytext=(0, 5), textcoords='offset points')
    consumption_total_annotation = axes.annotate(str(consumption_total_data[-1]) + ' W', xy=(timestamp_data[-1], consumption_total_data[-1]), xytext=(0, 5), textcoords='offset points')
    consumption_net_annotation = axes.annotate(str(consumption_net_data[-1]) + ' W', xy=(timestamp_data[-1], consumption_net_data[-1]), xytext=(0, 5), textcoords='offset points', visible=False)

    # Display the legend.
    legend = axes.legend()

    for legend_line in legend.get_lines():
        # Change the alpha on the line in the legend, so we can see what lines have been toggled.
        legend_line.set_alpha(1.0 if legend_line.get_visible() else 0.2)

        # Make all the legend lines visible.
        legend_line.set_visible(True)

    # Make each of the series clickable in the legend and map them to their relevant artists.
    artists = [[production_plot, production_annotation], [consumption_total_plot, consumption_total_annotation], [consumption_net_plot, consumption_net_annotation]]

    for legend_line, original_artists in zip(legend.get_lines(), artists):
        # Enable picking on the legend line (with a 5px tolerance).
        legend_line.set_picker(5)

        # Hold a reference to each of the relevant artists for this legend line.
        legend_map[legend_line] = original_artists

    # Remove spines.
    axes.spines[['left','right','top']].set_visible(False)

    # Configure the axes' grid.
    axes.yaxis.grid(linestyle='dashed', alpha=0.8)

    # Return the figure.
    return figure

def update_axes():
    # Plot the data.
    production_plot.set_data(timestamp_data, production_data)
    consumption_total_plot.set_data(timestamp_data, consumption_total_data)
    consumption_net_plot.set_data(timestamp_data, consumption_net_data)

    # Update the annotations.
    production_annotation.xy = (timestamp_data[-1], production_data[-1])
    production_annotation.set_text(str(production_data[-1]) + ' W')

    consumption_total_annotation.xy = (timestamp_data[-1], consumption_total_data[-1])
    consumption_total_annotation.set_text(str(consumption_total_data[-1]) + ' W')

    consumption_net_annotation.xy = (timestamp_data[-1], consumption_net_data[-1])
    consumption_net_annotation.set_text(str(consumption_net_data[-1]) + ' W')

def animate(_):
    # Store this before it is potentially over-written.
    most_recent_timestamp = timestamp_data[-1]

    # If there are no new meter readings to add then we skip re-drawing.
    if add_results_from_database():
        # Update the axes.
        update_axes()

        # Get current zoom.
        old_x_lim = axes.get_xlim()
        old_y_lim = axes.get_ylim()

        # Check whether the current zoom included the old end datapoint (i.e. user appeared deliberately interested in fresh data).
        user_viewing_recent_data = (old_x_lim[0] <= matplotlib.dates.date2num(most_recent_timestamp) <= old_x_lim[1])

        # Check whether the newest added data would now fall out of the old zoom view.
        new_data_visible_in_old_view = (old_x_lim[0] <= matplotlib.dates.date2num(timestamp_data[-1]) <= old_x_lim[1])

        # Ensure the axis are auto-scaled after adding new data.
        axes.relim()
        axes.autoscale()

        # Update the toolbar memory to the new zoomed out axis limits.
        figure.canvas.toolbar.update()
        figure.canvas.toolbar.push_current()

        # Was the user looking at old data before we added more data or were they looking at fresh data that now wil be outside of their view.
        if not user_viewing_recent_data or (user_viewing_recent_data and new_data_visible_in_old_view):
            # Restore old axis zoom (recent datapoint was never in zoom range anyway or zoom range still covers the new data).
            axes.set_xlim(old_x_lim)
            axes.set_ylim(old_y_lim)

def main():
    # Create an instance of argparse to handle any command line arguments.
    parser = argparse.ArgumentParser(prefix_chars='/-', add_help=False, description='A program that connects to an MySQL/MariaDB® database and plots the meter values graphically.')

    # Arguments to control the database connection.
    database_group = parser.add_argument_group('Database')
    database_group.add_argument('/DBHost', '-DBHost', '--DBHost', dest='database_host', default='127.0.0.1', help='The database server host (defaults to "127.0.0.1").')
    database_group.add_argument('/DBUsername', '-DBUsername', '--DBUsername', dest='database_username', default='root', help='The database username (defaults to "root").')
    database_group.add_argument('/DBPassword', '-DBPassword', '--DBPassword', dest='database_password', default='', help='The database password (defaults to blank).')
    database_group.add_argument('/DBDatabase', '-DBDatabase', '--DBDatabase', dest='database_database', default='Enphase', help='The database schema (defaults to "Enphase").')

    # Arguments to control how the program generally behaves.
    general_group = parser.add_argument_group('General')
    general_group.add_argument('/Animate', '-Animate', '--Animate', action='store_true', dest='animate', help='Allow chart to refresh every 10 seconds.')
    general_group.add_argument('/From', '-From', '--From', type=int, dest='start_from', help='The earliest ReadingID to read from.')
    general_group.add_argument('/Peak', '-Peak', '--Peak', type=int, dest='peak', help='The peak wattage from array (num of inverters * 366 for IQ 7A) before clipping.')
    general_group.add_argument('/Continuous', '-Continuous', '--Continuous', type=int, dest='continuous', help='The maximum continuous wattage from array (num of inverters * 349 for IQ 7A) before clipping.')

    # We want this to appear last in the argument usage list.
    general_group.add_argument('/?', '/Help', '/help', '-h','--help','-help', action='help', help='Show this help message and exit.')

    # Handle any command line arguments.
    global args
    args = parser.parse_args()

    # Connect to the MySQL/MariaDB database.
    database_connection = mysql.connector.connect(user=args.database_username, password=args.database_password, host=args.database_host, database=args.database_database, autocommit=True)

    try:
        # Get reference to the database cursor (that will PREPARE duplicate SQL statements).
        global database_cursor
        database_cursor = database_connection.cursor(prepared=True)

        # Allow the user to change the start from timestamp.
        global last_seen_reading_id
        if args.start_from: last_seen_reading_id = args.start_from

        # Add the inital batch of records from the database to the lists.
        print('Loading existing records in database (this may take a while).')
        add_results_from_database()
        print('Loaded existing records.')

        # Draw the initial plot.
        global figure
        figure = setup_plot()

        # Set a timer to animate the chart every 15 seconds.
        if args.animate: _ = animation.FuncAnimation(figure, animate, interval=5000)

        # Show the plot screen.
        plt.show()
    finally:
        # Close the database connection.
        database_connection.close()

# Launch the main method if invoked directly.
if __name__ == '__main__':
    main()