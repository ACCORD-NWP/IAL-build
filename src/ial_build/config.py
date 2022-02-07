#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) Météo France (2020)
# This software is governed by the CeCILL-C license under French law.
# http://www.cecill.info
from __future__ import print_function, absolute_import, unicode_literals, division
"""
Configuration parameters.
"""

import os
import re

IAL_OFFICIAL_TAGS_re = re.compile('CY(?P<release>\d{2}([TRH]\d)?)' +
                                  '(_(?P<radical>.+)\.(?P<version>\d{2}))?$')
IAL_OFFICIAL_PACKS_re = re.compile('(?P<prefix>((cy)|(CY))?)(?P<release>\d{2}([TRHtrh]\d)?)' + '_' +
                                   '(?P<radical>.+)\.(?P<version>\d{2})' + '\.' +
                                   '(?P<compiler_label>\w+)\.(?P<compiler_flag>\w+)' +
                                   '(?P<suffix>(\.pack)?)$')
IAL_BRANCHES_re = re.compile('_'.join(['(?P<user>\w+)',
                                       'CY(?P<release>\d{2}([TRH]\d)?)',
                                       '(?P<radical>.+)$']))

DEFAULT_BUNDLE_CACHE_DIR = os.path.join(os.environ['HOME'], 'bundles')

DEFAULT_IAL_REPO = os.environ.get('DEFAULT_IAL_REPO')
if DEFAULT_IAL_REPO in ('', None):
    _git_homepack = os.environ.get('GIT_HOMEPACK', os.path.join(os.environ['HOME'], 'repositories'))
    DEFAULT_IAL_REPO = os.path.join(_git_homepack, 'IAL')
DEFAULT_PACK_COMPILER_FLAG = '2y'

# temporary => UNTIL USE OF BUNDLE
_ecSDK_dir = {'belenos':'/home/gmap/mrpe/mary/public/ecSDK',
              'taranis':'/home/gmap/mrpe/mary/public/ecSDK',
              'lxcnrm':'/home/common/epygram/public/ecSDK',
              }
GMKPACK_HUB_PACKAGES = {'eckit':{'CY48':'1.4.4',
                                 'CY48T1':'mf_1.4.4_for48T2',
                                 'CY46T1':'1.4.4',
                                 'project':'ecSDK'},
                        'fckit':{'CY48':'0.6.4',
                                 'CY48T1':'0.6.4',
                                 'CY46T1':'0.6.4',
                                 'project':'ecSDK'},
                        'ecbuild':{'CY48':'3.1.0',
                                   'CY48T1':'3.1.0',
                                   'CY46T1':'3.1.0',
                                   'project':'ecSDK'}
                        }
for p in GMKPACK_HUB_PACKAGES.keys():
    GMKPACK_HUB_PACKAGES[p].update(**_ecSDK_dir)
# hosts recognition
hosts_re = {
    'belenos':re.compile('^belenos(login)?\d+\.belenoshpc\.meteo\.fr$'),
    'taranis':re.compile('^taranis(login)?\d+\.taranishpc\.meteo\.fr$'),
    'lxcnrm':re.compile('^[pls]x[a-z]+\d{1,2}$')
    }
