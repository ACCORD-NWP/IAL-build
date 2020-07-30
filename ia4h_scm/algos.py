#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function, absolute_import, unicode_literals, division
"""
Building executables algorithms.
"""
import six
import json

from .repositories import IA4Hview
from .pygmkpack import (Pack, PackError,
                        new_incremental_pack,
                        USUAL_BINARIES)

# TODO: handle multiple repositories/projects to pack

def IA4H_gitref_to_pack(repository, git_ref,
                        packname=None,
                        preexisting_pack=False,
                        clean_if_preexisting=True,
                        homepack=None,
                        rootpack=None,
                        other_pack_options={},
                        silent=False):
    """From git ref to pack."""
    if packname is None:
        packname = git_ref
    print("-" * 50)
    print("Start export of git ref: '{}' to pack: '{}'".format(git_ref, packname))
    view = IA4Hview(repository, git_ref)
    try:
        if preexisting_pack:
            pack = Pack(packname, preexisting=preexisting_pack, homepack=homepack)
            if clean_if_preexisting:
                pack.cleanpack()
        else:
            ancestor_info = view.latest_official_branch_from_main_release
            pack = new_incremental_pack(packname,
                                        view.latest_main_release_ancestor,
                                        initial_branch=ancestor_info.get('b', None),
                                        initial_branch_version=ancestor_info.get('v', None),
                                        homepack=homepack,
                                        rootpack=rootpack,
                                        other_pack_options=other_pack_options,
                                        silent=silent)
        pack.populate_from_IA4Hview(view)
    except Exception:
        print("Failed export of git ref to pack !")
        del view  # to restore the repository state
        raise
    else:
        print("Sucessful export of git ref: {} to pack: {}".format(git_ref, pack.abspath))
    finally:
        print("-" * 50)
    return pack


def pack_build_executables(pack,
                           programs=USUAL_BINARIES,
                           silent=False,
                           regenerate_ics=True,
                           cleanpack=True,
                           other_options={},
                           homepack=None,
                           fatal_build_failure='__any__',
                           dump_build_report=False):
    """Build pack executables."""
    if isinstance(pack, six.string_types):
        pack = Pack(pack, preexisting=True, homepack=homepack)
    elif not isinstance(pack, Pack):
        raise PackError("**pack** argument must be a pack name or a Pack instance")
    if isinstance(programs, six.string_types):
        if programs == '__usual__':
            programs = USUAL_BINARIES
        else:
            programs = [p.strip() for p in programs.split(',')]
    elif not isinstance(programs, list):
        raise TypeError("**programs** must be a string (e.g. 'MASTERODB,BATOR') or a list")
    build_report = {}
    first = True
    for program in programs:
        print("-" * 50)
        print("Build: {} ...".format(program))
        try:
            if not pack.ics_available_for(program) or regenerate_ics:
                print("(Re-)generate ics_{} script ...".format(program.lower()))
                pack.ics_build_for(program, **other_options)
        except Exception as e:
            message = "... ics_{} generation failed: {}".format(program, str(e))
            print(message)
            if fatal_build_failure == '__any__':
                raise
            else:
                build_report[program] = {'OK':False, 'Output':message}
        else:  # ics_ generation OK
            print("Run ics_ ...")
            compile_output = pack.compile(program,
                                          silent=silent,
                                          clean_before=cleanpack and first,
                                          fatal=fatal_build_failure=='__any__')
            if compile_output['OK']:
                print("... {} OK !".format(program))
            else:  # build failed but not fatal
                print("... {} failed !".format(program))
                if not silent:
                    print("-> build output: {}".format(compile_output['Output']))
            print("-" * 50)
            build_report[program] = compile_output
        first = False
    if fatal_build_failure == '__finally__':
        which = [k for k, v in build_report.items() if not v['OK']]
        OK = [k for k, v in build_report.items() if v['OK']]
        if len(which) > 0:
            print("Failed builds output(s):")
            for k in which:
                print("{:20}: {}".format(k, build_report[k]['Output']))
            print("-" * 50)
            message = "Build of executable(s) has failed: {}".format(which)
            if len(OK) > 0:
                message += "(OK for: {})".format(OK)
            raise PackError(message)
    if dump_build_report:
        with open('build_report.json', 'w') as out:
            json.dump(build_report, out)
    return pack, build_report
