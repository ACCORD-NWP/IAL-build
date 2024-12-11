#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Get the oldest "diverging" common ancestor between two git references,
or in other words, the commit before the first diverging commit in refs respective histories.
"""
import argparse

from ..repositories import GitProxy

def main():
    args = get_args()
    r = GitProxy(args.repository)
    commit = r.fork_point(args.refA, args.refB)
    print("Ancestor (last commit between divergence) between {} and {} is:\n{}".format(args.refA, args.refB, commit))

def get_args():
    parser = argparse.ArgumentParser(description=' '.join([
        'Get the oldest "diverging" common ancestor between two git references,',
        'or in other words, the commit before the first diverging commit in refs respective histories.']))
    parser.add_argument('refA',
                        help='First reference.')
    parser.add_argument('refB',
                        help='Second reference, defaults to HEAD.',
                        nargs='?',
                        default='HEAD')
    parser.add_argument('-r', '--repository',
                        default='.',
                        help='Path to repository to explore. Default is current working dir.')
    return parser.parse_args()

