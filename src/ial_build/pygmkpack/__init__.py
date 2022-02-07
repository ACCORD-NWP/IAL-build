#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) Météo France (2020)
# This software is governed by the CeCILL-C license under French law.
# http://www.cecill.info

from __future__ import print_function, absolute_import, unicode_literals, division

USUAL_BINARIES = ['masterodb', 'bator',
                  'ioassign', 'lfitools',
                  'pgd', 'prep',
                  'oovar', 'ootestvar',
                  ]

# The distinction is based on the component having a build system:
#         - integrated and plugged in gmkpack: package
#         - no build system, or not plugged in gmkpack: project
COMPONENTS_MAP = {'eckit':'hub/local/src/ecSDK',
                  'fckit':'hub/local/src/ecSDK',
                  'ecbuild':'hub/local/src/ecSDK',
                  # src/local
                  'ial':'src/local',
                  'oops':'src/local/oops_src'
                  # __future__
                  'atlas':'hub/local/src',
                  'surfex':'src/local/surfex',
                  # mpa, falfi, ...
                  }


class PackError(Exception):
    pass


from .gmkpack import GmkpackTool
from .pack import Pack
