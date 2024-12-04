#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) Météo France (2020)
# This software is governed by the CeCILL-C license under French law.
# http://www.cecill.info

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
                  'atlas':'hub/local/src',
                  # src/local
                  'ial':'src/local',
                  'oops_src':'src/local',
                  #'surfex':'src/local',
                  # mpa, falfi, ...
                  }


class PackError(Exception):
    pass


from .gmkpack import GmkpackTool
from .pack import Pack
