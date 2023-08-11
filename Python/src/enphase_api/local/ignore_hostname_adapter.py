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

# Requests references passed from calling code.
from requests.adapters import HTTPAdapter, DEFAULT_POOLBLOCK

class IgnoreHostnameAdapter(HTTPAdapter):
    """
    An HTTP adapter that ignores hostname verification for TLS/SSL connections.

    This adapter is designed to be used with the Requests library to create an
    HTTP adapter that disregards hostname verification when making TLS/SSL connections.
    It subclasses the HTTPAdapter class and overrides the init_poolmanager method
    to disable hostname verification by setting the 'assert_hostname' parameter to False.

    Args:
        HTTPAdapter (class): The base HTTPAdapter class from the Requests library.
    """

    def init_poolmanager(self, connections, maxsize, block=DEFAULT_POOLBLOCK, **pool_kwargs):
        """
        Initialize the connection pool manager with disabled hostname verification.

        Overrides the init_poolmanager method of the base HTTPAdapter class to
        set the 'assert_hostname' parameter to False in order to disable hostname
        verification for TLS/SSL connections.

        Args:
            connections (int): The maximum number of connections allowed in the pool.
            maxsize (int): The maximum number of connections to keep in the pool.
            block (bool, optional): Whether to block when the pool is full. Defaults to DEFAULT_POOLBLOCK.
            **pool_kwargs: Additional keyword arguments to pass to the pool manager.

        Returns:
            None
        """
        pool_kwargs['assert_hostname'] = False
        super(IgnoreHostnameAdapter, self).init_poolmanager(connections=connections, maxsize=maxsize, block=block, **pool_kwargs)