#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) Météo France (2020)
# This software is governed by the CeCILL-C license under French law.
# http://www.cecill.info

import os
import io

"""
IAL (IFS-ARPEGE & LAM:ALADIN-AROME-ALARO-HARMONIE) source code management.
"""

package_rootdir = os.path.dirname(os.path.dirname(os.path.realpath(__path__[0])))  # realpath to resolve symlinks
__version__ = io.open(os.path.join(package_rootdir, 'VERSION'), 'r').read().strip()
