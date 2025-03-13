#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Make or populate a pack from a bundle.
"""
import os
import argparse

from ial_build.algos import bundle_tag2pack, bundle_file2pack
from ial_build.pygmkpack import GmkpackTool
from ial_build.config import DEFAULT_BUNDLE_CACHE_DIR, DEFAULT_IALBUNDLE_REPO


def main():
    args = get_args()
    if os.path.exists(args.bundle):
        pack = bundle_file2pack(args.bundle,
                                src_dir=args.cache_directory,
                                update=args.update,
                                pack_type=args.pack_type,
                                preexisting_pack=args.preexisting_pack,
                                clean_if_preexisting=args.clean_if_preexisting,
                                compiler_label=args.compiler_label,
                                compiler_flag=args.compiler_flag,
                                homepack=args.homepack,
                                rootpack=args.rootpack)
    else:
        print("'{}' is not an existing local file, look for it as a tag in IAL-bundle repo.".format(args.bundle))
        # bundle is provided as a tag
        pack = bundle_tag2pack(args.bundle,
                               IAL_bundle_origin_repo=args.bundle_origin_repo,
                               src_dir=args.cache_directory,
                               update=args.update,
                               pack_type=args.pack_type,
                               preexisting_pack=args.preexisting_pack,
                               clean_if_preexisting=args.clean_if_preexisting,
                               compiler_label=args.compiler_label,
                               compiler_flag=args.compiler_flag,
                               homepack=args.homepack,
                               rootpack=args.rootpack)
    pack.ics_tune('', GMK_THREADS=int(args.threads_number))
    if args.programs != '':
        for p in GmkpackTool.parse_programs(args.programs):
            pack.ics_build_for(p)
            pack.ics_tune(p, GMK_THREADS=int(args.threads_number))
    pack.ics_tune('packages', GMK_THREADS=int(args.threads_number))

def get_args():
    parser = argparse.ArgumentParser(description='Make or populate a pack from a bundle.')
    parser.add_argument('bundle',
                        help="Either a local path to a bundle file, or a tag in IAL-bundle repo. " +
                             "Takes the local file if the path exists, otherwise look for it as a tag.")
    parser.add_argument('-r', '--bundle_origin_repo',
                        help="If providing a bundle tag: URL of IAL-bundle repository to clone, " +
                             "in which to look for bundle tag. " +
                             "Can be local (e.g. ~user/IAL-bundle)" +
                             "or distant (e.g. https://github.com/ACCORD-NWP/IAL-bundle.git)." +
                             "Default: " + DEFAULT_IALBUNDLE_REPO,
                        default=DEFAULT_IALBUNDLE_REPO)
    parser.add_argument('-l', '--compiler_label',
                        help='Compiler label. Through $GMKFILE, defaults to: "{}".'.format(
                            GmkpackTool.get_compiler_label(fatal=False)),
                        default=GmkpackTool.get_compiler_label(fatal=False))
    parser.add_argument('-o', '--compiler_flag',
                        help='Compiler flag. Defaults to $GMK_OPT: "{}".'.format(
                            GmkpackTool.get_compiler_flag()),
                        default=GmkpackTool.get_compiler_flag())
    parser.add_argument('-t', '--pack_type',
                        help='Type of pack (default: main).',
                        default='main',
                        choices=['incr', 'main'])
    parser.add_argument('-n', '--threads_number',
                        help='Number of threads to be set in compilation script.',
                        default=10)
    parser.add_argument('-u', '--no_update',
                        action='store_false',
                        help='Do not try to update local repos, so that non-commited modifications in repos are' +
                        'included. BEWARE that the checkedout version in each repo may then not be consistent' +
                        'with the version requested in the bundle.',
                        dest='update',
                        default=True)
    parser.add_argument('-e', '--preexisting_pack',
                        action='store_true',
                        help='Assume the pack already preexists (protection against unhappy overwrites).',
                        default=False)
    parser.add_argument('-c', '--clean_if_preexisting',
                        action='store_true',
                        help='Call cleanpack.',
                        default=False)
    parser.add_argument('-p', '--programs',
                        help="Programs which ics_{p} script to be generated, e.g. 'masterodb' or 'masterodb,bator'. " +
                        "If none, only compilation script (ics_) is generated; " +
                        "other scripts can be generated later, using commandline in the pack's .genesis file " +
                        "and adding -p argument.",
                        default='')
    parser.add_argument('-d', '--cache_directory',
                        help='Cache directory: where git repos are downloaded/updated before populating pack. ' +
                             'Defaults to $HOME/bundles: ' + DEFAULT_BUNDLE_CACHE_DIR,
                        default=DEFAULT_BUNDLE_CACHE_DIR)
    parser.add_argument('--homepack',
                        default=GmkpackTool.get_homepack(),
                        help='To specify a home directory for packs. Defaults to $HOMEPACK or $HOME/pack: ' +
                        GmkpackTool.get_homepack())
    parser.add_argument('-f', '--rootpack',
                        help="Home of root packs to start from, for incremental packs. " +
                        "Defaults to Gmkpack's $ROOTPACK: {}".format(GmkpackTool.get_rootpack(fatal=False)),
                        default=GmkpackTool.get_rootpack())
    return parser.parse_args()

