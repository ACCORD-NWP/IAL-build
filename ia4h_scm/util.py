#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) Météo France (2020)
# This software is governed by the CeCILL-C license under French law.
# http://www.cecill.info
from __future__ import print_function, absolute_import, unicode_literals, division

"""
Utilities for IA4H source code management.
"""

import os
import shutil


class DirectoryFiltering(object):
    
    def __init__(self, directory_abspath, filter_list):
        """
        Directory filtering utility.
        
        :param filter_list: list of local files or subdirectories to be ignored
        """
        self.abspath = directory_abspath
        self.abspaths_to_be_ignored = []
        for f in filter_list:
            if not os.path.isabs(f):
                f = os.path.join(self.abspath, f)
            self.abspaths_to_be_ignored.append(os.path.join(self.abspath, f))
        self._filter_function = self._generate_filter_function()
    
    def _generate_filter_function(self):
        """
        Generate filter function for copytree **ignore** argument,
        from a list of absolute paths to be ignored.
        """
        def ignore(src, names):
            # absolute paths of files to be ignored in origin directory
            ignored_names = []
            for f in names:
                abs_f = os.path.join(src, f)
                for path in self.abspaths_to_be_ignored:
                    if abs_f == path:  # exact file
                        ignored_names.append(f)
                        break
                    elif os.path.join(path, '') in abs_f:  # the subdirectory is to be ignored
                        ignored_names.append(f)
                        break
            return ignored_names
        return ignore
    
    def copytree(self, dst, symlinks=False):
        shutil.copytree(self.abspath, dst,
                        symlinks=symlinks,
                        ignore=self._filter_function)
        
    