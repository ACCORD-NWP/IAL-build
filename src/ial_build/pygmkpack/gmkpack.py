#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Python wrapping of *gmkpack* tool.
"""

import os
import re
import subprocess
import io

from ial_build.config import (IAL_OFFICIAL_PACKS_re, IAL_OFFICIAL_TAGS_re, IAL_BRANCHES_re,
                              DEFAULT_PACK_COMPILER_FLAG)
from . import PackError, USUAL_BINARIES

#: No automatic export
__all__ = []


class GmkpackTool(object):

    _default_branch_radical = 'main'
    _default_version_number = '00'
    _default_compiler_flag = DEFAULT_PACK_COMPILER_FLAG
    _OPTIONSPACK_re = re.compile(r'GMKFILE=(?P<gmkfile>.+)\s+<= -l (?P<label>\w+)\s+-o (?P<flag>\w+)$')
    OFFICIAL_PACKS_re = IAL_OFFICIAL_PACKS_re

    @staticmethod
    def clean_env():
        """Clean gmkpack env variables that could be detrimental, and set needed ones."""
        vars_to_unset = ('GMK_USER_PACKNAME_STYLE', 'PACK_EXT', 'PACK_PREFIX')
        for k in vars_to_unset:
            if k in os.environ:
                print("unset $" + k)
                del os.environ[k]
        vars_to_set = {'GMK_RELEASE_CASE_SENSITIVE':'1', }
        for k, v in vars_to_set.items():
            if os.environ.get(k, None) != v:
                print("export ${}={}".format(k, v))
                os.environ[k] = v

    @staticmethod
    def parse_programs(programs):
        if isinstance(programs, str):
            if programs == '__usual__':
                programs = USUAL_BINARIES
            else:
                programs = [p.strip() for p in programs.split(',')]
        elif not isinstance(programs, list):
            raise TypeError("**programs** must be a string (e.g. 'MASTERODB,BATOR') or a list")
        return programs

    @classmethod
    def commandline(cls,
                    arguments,
                    options=[],
                    silent=False):
        """
        Wrapper to gmkpack command.

        :param arguments: options with an argument to the command-line,
            to be passed as a dict, e.g. {'-l':'IMPIFC1801'}
        :param options: options without argument to the command-line,
            to be passed as a list, e.g. ['-a']
        :param silent: if True, hide gmkpack's stdout/stderr output
        """
        cls.clean_env()
        arguments_as_list = []
        for k, v in arguments.items():
            arguments_as_list.extend([k, v])
        arguments_as_list.extend(options)
        command = ['gmkpack',] + arguments_as_list
        print("Now running: " + ' '.join(command))
        if silent:
            with io.open(os.devnull, 'w') as devnull:
                r = subprocess.check_call(command, stdout=devnull, stderr=devnull)
        else:
            r = subprocess.check_call(command)
        return r

    @classmethod
    def scan_rootpacks(cls, directory):
        """Scan a 'rootpacks' directory, looking for official releases packs."""
        rootpacks = {}
        for p in os.listdir(directory):
            m = cls.OFFICIAL_PACKS_re.match(p)
            if m:
                rootpacks[p] = m.groupdict()
        return rootpacks

    @classmethod
    def find_matching_rootpacks(cls,
                                rootpacks_directory,
                                official_tag,
                                compiler_label=None,
                                compiler_flag=None):
        """Find rootpacks matching **official_tag**, with according label/flag if requested."""
        print("Find packs matching with ancestor '{}' in: {}".format(official_tag, rootpacks_directory))
        rootpacks = cls.scan_rootpacks(rootpacks_directory)
        compiler_label = cls.get_compiler_label(compiler_label)
        compiler_flag = cls.get_compiler_flag(compiler_flag)
        matching = {}
        for p in rootpacks.keys():
            if rootpacks[p]['radical'] == 'main':
                tag = 'CY{}'.format(rootpacks[p]['release'].upper())
            else:
                tag = 'CY{}_{}.{}'.format(rootpacks[p]['release'].upper(),
                                          rootpacks[p]['radical'],
                                          rootpacks[p]['version'])
            if tag == official_tag:
                if all([compiler_label in (None, rootpacks[p]['compiler_label']),
                        compiler_flag in (None, rootpacks[p]['compiler_flag'])]):
                    matching[p] = rootpacks[p]
        return matching

# ACCESSORS -------------------------------------------------------------------

    @staticmethod
    def get_homepack(homepack=None):
        """Get a HOMEPACK directory, from argument, $HOMEPACK, or $HOME/pack."""
        if homepack in (None, ''):
            homepack = os.environ.get('HOMEPACK')
            if homepack in (None, ''):
                homepack = os.path.join(os.environ.get('HOME'), 'pack')
        return homepack

    @staticmethod
    def get_rootpack(rootpack=None, fatal=True):
        """Get a ROOTPACK directory from argument, $ROOTPACK if defined, or None."""
        if rootpack in (None, ''):
            rootpack = os.environ.get('ROOTPACK')
        if rootpack in ('', None) and fatal:
            raise ValueError("rootpack must be passed by argument or defined by env variable $ROOTPACK")
        return rootpack if rootpack != '' else None

    @classmethod
    def get_compiler_label(cls, compiler_label=None, fatal=True):
        """Get compiler label, either from argument (if not None) or from env var $GMKFILE."""
        if compiler_label in (None, ''):
            # get GMKFILE
            gmkfile = os.environ.get('GMKFILE')
            assert gmkfile not in (None, ''), "Cannot guess compiler label (-l): $GMKFILE is not set."
            # parse optionspack
            options = [f.strip()
                       for f in subprocess.check_output(['optionspack']).decode('utf-8').split('\n')
                       if f != '']
            for o in options:
                m = cls._OPTIONSPACK_re.match(o)
                if m and m.group('gmkfile').strip() == gmkfile:
                    compiler_label = m.group('label').strip()
                    break
        if compiler_label in (None, ''):
            if fatal:
                raise ValueError("Compiler label not found, neither through env ($GMKFILE/optionspack) nor by argument")
            else:
                compiler_label = "No default found."
        return compiler_label

    @classmethod
    def get_compiler_flag(cls, compiler_flag=None):
        """Get compiler flage, either from argument, $GMK_OPT or default value."""
        if compiler_flag in (None, ''):
            compiler_flag = os.environ.get('GMK_OPT')
            if compiler_flag in (None, ''):
                compiler_flag = cls._default_compiler_flag
        if compiler_flag in (None, ''):
            raise ValueError("Compiler flag not found, neither through env ($GMK_OPT) nor by argument")
        return compiler_flag

# getargs newway methods  -----------------------------------------------------

    @staticmethod
    def mainpack_getargs_from_IAL_git_ref(IAL_git_ref,
                                          IAL_repo_path=None):
        """
        Get necessary arguments for main pack from IAL_git_ref.

        :IAL_repo_path: required only if IAL_git_ref is not conventional
        """
        from ial_build.repositories import IALview
        is_a_tag = IAL_OFFICIAL_TAGS_re.match(IAL_git_ref)
        is_a_conventional_branch = IAL_BRANCHES_re.match(IAL_git_ref)
        if is_a_tag:
            gmk_release = is_a_tag.group('release')
            gmk_branch = is_a_tag.group('radical')
            gmk_version = is_a_tag.group('version')
            gmk_prefix = 'CY'
        elif is_a_conventional_branch:
            gmk_release = is_a_conventional_branch.group('release')
            gmk_branch = is_a_conventional_branch.group('radical')
            gmk_version = '00'
            gmk_prefix = is_a_conventional_branch.group('user') + '_CY'
        else:
            print("Warning: pack nomenclature will not be perfectly mapping git reference.")
            assert IAL_repo_path is not None, "IAL repository path is required because git ref is not conventional."
            ial = IALview(IAL_repo_path, IAL_git_ref)
            ancestor = IAL_OFFICIAL_TAGS_re.match(ial.latest_official_tagged_ancestor).groupdict()
            gmk_release = ancestor['release']
            gmk_branch = IAL_git_ref
            gmk_version = '00'
            gmk_prefix = '_upon'
        args = {'-r':gmk_release,
                '-b':gmk_branch if gmk_branch is not None else 'main',
                '-n':gmk_version if gmk_version is not None else '00',
                '-g':gmk_prefix}
        return args

    @classmethod
    def pack_getargs_others(cls,
                            compiler_label=None,
                            compiler_flag=None,
                            homepack=None):
        """Get necessary arguments for pack from argument or env variables."""
        return {'-o':cls.get_compiler_flag(compiler_flag),
                '-l':cls.get_compiler_label(compiler_label),
                '-h':cls.get_homepack(homepack)}

    @staticmethod
    def incrpack_getargs_from_IAL_git_ref(IAL_git_ref,
                                          IAL_repo_path):
        """Get necessary arguments for incr pack from IAL_git_ref."""
        from ial_build.repositories import IALview
        ial = IALview(IAL_repo_path, IAL_git_ref)
        # ancestor, for root pack
        ancestor = IAL_OFFICIAL_TAGS_re.match(ial.latest_official_tagged_ancestor)
        args = {'-r':ancestor.group('release')}
        if ancestor.group('radical'):
            args['-b'] = ancestor.group('radical')
            args['-v'] = ancestor.group('version')
        return args

    @classmethod
    def incrpack_getargs_packname(cls, IAL_git_ref, compiler_label=None, compiler_flag=None):
        """Get incr pack name (-u), built from ref and compiler."""
        return {'-u':'.'.join([IAL_git_ref,
                               cls.get_compiler_label(compiler_label),
                               cls.get_compiler_flag(compiler_flag)])}

    @classmethod
    def incrpack_getargs_from_root_pack(cls,
                                        args,
                                        IAL_git_ref,
                                        IAL_repo_path,
                                        rootpack=None,
                                        compiler_label=None,
                                        compiler_flag=None):
        """Get arguments linked to syntax of root pack."""
        from ial_build.repositories import IALview
        rootpack = cls.get_rootpack(rootpack)
        args['-f'] = rootpack
        # ancestor, for root pack
        ial = IALview(IAL_repo_path, IAL_git_ref)
        ancestor = ial.latest_official_tagged_ancestor
        matching = cls.find_matching_rootpacks(rootpack, ancestor, compiler_label, compiler_flag)
        if len(matching) == 1:
            actual_rootpack = matching[list(matching.keys())[0]]
            if actual_rootpack.get('prefix'):
                args['-g'] = actual_rootpack.get('prefix')
            if actual_rootpack.get('suffix'):
                args['-e'] = actual_rootpack.get('suffix')
            lower_case = actual_rootpack.get('release', '').islower()
            if lower_case:
                args['-r'] = args['-r'].lower()
            return args
        else:
            if len(matching) == 0:
                radic = "Could not find a pack in ROOTPACK={}"
            else:
                radic = "Too many packs in ROOTPACK={}"
            raise ValueError(" ".join([radic,
                                       "matching latest tagged ancestor ({}) of IAL_git_ref={}",
                                       "and compiler specifs label={}, flag={}."]).format(rootpack,
                                           ancestor, IAL_git_ref, compiler_label, compiler_flag))

    @classmethod
    def getargs(cls,
                pack_type,
                IAL_git_ref,
                IAL_repo_path=None,
                compiler_label=None,
                compiler_flag=None,
                homepack=None,
                rootpack=None):
        """
        Build args to gmkpack command for creating a pack.

        :param pack_type: type of pack, among ('incr', 'main')
        :param IAL_git_ref: IAL git reference
        :param IAL_repo_path: IAL repository path
        :param compiler_label: Gmkpack's compiler label to be used
        :param compiler_flag: Gmkpack's compiler flag to be used
        :param homepack: directory in which to build pack
        :param rootpack: diretory in which to look for root pack
        """
        if pack_type == 'main':
            args = cls.mainpack_getargs_from_IAL_git_ref(IAL_git_ref, IAL_repo_path)
        elif pack_type == 'incr':
            args = cls.incrpack_getargs_from_IAL_git_ref(IAL_git_ref, IAL_repo_path)
            args.update(cls.incrpack_getargs_packname(IAL_git_ref,
                                                      compiler_label=compiler_label,
                                                      compiler_flag=compiler_flag))
            args.update(cls.incrpack_getargs_from_root_pack(args,
                                                            IAL_git_ref,
                                                            IAL_repo_path,
                                                            rootpack=rootpack,
                                                            compiler_label=compiler_label,
                                                            compiler_flag=compiler_flag))
        args.update(cls.pack_getargs_others(compiler_label=compiler_label,
                                            compiler_flag=compiler_flag,
                                            homepack=homepack))
        return args

# other methods ---------------------------------------------------------------

    @classmethod
    def args2packname(cls, args, pack_type):
        """Emulates gmkpack generation of pack name."""
        if pack_type == 'main':
            return '{}{}_{}.{}.{}.{}{}'.format(args.get('-g', ''), args['-r'], args['-b'],
                                               args['-n'], args['-l'], args['-o'],
                                               args.get('-e', ''))
        elif pack_type == 'incr':
            return args['-u']

    @classmethod
    def guess_pack_name(cls, IAL_git_ref, compiler_label, compiler_flag, pack_type,
                        IAL_repo_path=None,
                        abspath=False,
                        homepack=None,
                        to_bin=False):
        """
        Guess pack name given IAL git ref and compiler options.

        :param IAL_repo_path: is only necessary for main packs only if
            the **IAL_git_ref** happens not to be a conventional IAL name.
        :param abspath: join homepack and packname
        :param homepack: home of packs
        :param to_bin: add /bin to path, in case abspath=True
        """
        if pack_type == 'main':
            args = cls.getargs(pack_type,
                               IAL_git_ref,
                               IAL_repo_path=IAL_repo_path,
                               compiler_label=compiler_label,
                               compiler_flag=compiler_flag)
        elif pack_type == 'incr':
            args = cls.incrpack_getargs_packname(IAL_git_ref,
                                                 compiler_label,
                                                 compiler_flag)
        pack_name = cls.args2packname(args, pack_type)
        if abspath:
            path = os.path.join(cls.get_homepack(homepack), pack_name)
            if to_bin:
                path = os.path.join(path, 'bin')
            return path
        else:
            return pack_name

# Pack Building methods -------------------------------------------------------

    @classmethod
    def create_pack_from_args(cls, args, pack_type,
                              silent=False):
        from . import Pack
        packname = cls.args2packname(args, pack_type)
        pack = Pack(packname, preexisting=False, homepack=args.get('-h'))
        if os.path.exists(pack.abspath):
            raise PackError('Pack already exists, cannot create: {}'.format(pack.abspath))
        options = ['-a', '-K'] if pack_type == 'main' else []
        cls.commandline(args, options, silent=silent)
        return pack
