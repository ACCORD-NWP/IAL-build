#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) Météo France (2020)
# This software is governed by the CeCILL-C license under French law.
# http://www.cecill.info

from __future__ import print_function, absolute_import, unicode_literals, division

import os

"""
IAL (IFS-ARPEGE & LAM:ALADIN-AROME-ALARO-HARMONIE) source code management.
"""

__version__ = '1.1.0'
package_rootdir = os.path.dirname(os.path.dirname(os.path.realpath(__path__[0])))  # realpath to resolve symlinks
