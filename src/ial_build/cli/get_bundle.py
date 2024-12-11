#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Get a copy of a bundle from IAL-bundle repository.
"""
import argparse
import sys

from ial_build.bundle import TmpIALbundleRepo
from ial_build.config import (DEFAULT_IAL_REPO,
                              DEFAULT_IALBUNDLE_REPO)


def main():
    args = get_args()
    IALbundles = TmpIALbundleRepo(args.IAL_bundle_origin_repo, verbose=args.verbose)
    IALbundles.get_bundle(args.bundle_tag,
                          to_file=args.output,
                          overwrite=args.overwrite)

def get_args():
    parser = argparse.ArgumentParser(description='Get a copy of a bundle from IAL-bundle repository.')
    parser.add_argument('bundle_tag',
                        help='Bundle tag to be fetched.')
    parser.add_argument('-v', '--verbose',
                        action='store_true')
    parser.add_argument('-f', '--force_overwrite',
                        help="To allow overwriting of existing target file",
                        dest='overwrite',
                        action='store_true')
    output = parser.add_mutually_exclusive_group()
    output.add_argument('-t', '--target_file',
                        help="To write bundle in a specified target file.",
                        dest='output',
                        default="__tag__")
    output.add_argument('-s', '--stdout',
                        help="To write bundle to stdout.",
                        action='store_const',
                        dest='output',
                        const=sys.stdout)
    parser.add_argument('-o', '--IAL_bundle_origin_repo',
                        help="URL of the 'IAL-bundle' repository to clone. " +
                             "Default: " + DEFAULT_IALBUNDLE_REPO,
                        default=DEFAULT_IALBUNDLE_REPO)
    return parser.parse_args()
