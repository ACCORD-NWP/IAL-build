#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) Météo France (2020)
# This software is governed by the CeCILL-C license under French law.
# http://www.cecill.info

USUAL_BINARIES = ['masterodb',
                  'bator',
                  'ioassign',
                  'lfitools',
                  'pgd',
                  'prep',
                  'oovar',
                  'ootestvar',
                  ]

# The distinction is based on the component having a build system:
#         - integrated and plugged in gmkpack: package
#         - no build system, or not plugged in gmkpack: project
COMPONENTS_MAP = {'eckit':'hub/local/src/ecSDK',
                  'fckit':'hub/local/src/ecSDK',
                  'ecbuild':'hub/local/src/ecSDK',
                  'atlas':'hub/local/src/Atlas',
                  'ecflow_light':'hub/local/src/ecFlow_light',
                  'ectrans':'hub/local/src/Ectrans',
                  'field_api':'hub/local/src/Field_api',
                  # src/local
                  'ial':'src/local',
                  #'surfex':'src/local',
                  # mpa, falfi, ...
                  }
# gmkpack expects certain packages under a name different from the repo name
COMPONENTS_RENAME = {'oops':'oops_src',
                     'ecflow-light':'ecflow_light',
                     }
unsatisfied_references = {
    "CY48":["imultio_flush_",
            "imultio_notify_step_",
            "imultio_write_",
            ],
    "CY50":[],  # they have been added to dummies in auxlibs in the config file recommended for CY50
                          }


class PackError(Exception):
    pass


from .gmkpack import GmkpackTool
from .pack import Pack
