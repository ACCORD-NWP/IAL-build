#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Python handling of a pack.
"""
from __future__ import print_function, absolute_import, unicode_literals, division

import six
import os
import re
import subprocess
import tarfile
import io
import shutil
import glob
from contextlib import contextmanager

from bronx.stdtypes.date import now

from ial_build.util import copy_files_in_cwd
from . import PackError, COMPONENTS_MAP
from . import GmkpackTool

#: No automatic export
__all__ = []


class Pack(object):

    def __init__(self, packname, preexisting=True, homepack=None):
        """
        Create Pack object from the **packname**.
        """
        self.packname = packname
        if homepack in (None, ''):
            homepack = GmkpackTool.get_homepack()
        self.homepack = homepack
        self.abspath = os.path.join(self.homepack, packname)
        self._local = os.path.join(self.abspath, 'src', 'local')
        self._hub_local_src = os.path.join(self.abspath, 'hub', 'local', 'src')
        self._bin = os.path.join(self.abspath, 'bin')
        if not preexisting and os.path.exists(self.abspath):
            raise PackError("Pack already exists, while *preexisting* is False ({}).".format(self.abspath))
        if preexisting and not os.path.exists(self.abspath):
            raise PackError("Pack is supposed to preexist, while it doesn't ({}).".format(self.abspath))

    @property
    def is_incremental(self):
        """Is the pack incremental ? (vs. main)"""
        return '-a' not in self.genesis_options

    @contextmanager
    def _cd_local(self, subdir=None):
        """Context: in self._local"""
        owd = os.getcwd()
        if subdir is None:
            loc = self._local
        else:
            loc = os.path.join(self._local, subdir)
        try:
            os.chdir(loc)
            yield loc
        finally:
            os.chdir(owd)

# existing pack genesis -------------------------------------------------------

    @property
    def genesis(self):
        """Read pack/.genesis file and return it."""
        genesis = os.path.join(self.abspath, '.genesis')
        with io.open(genesis, 'r') as g:
            genesis = g.readline().strip()
        return genesis

    def _genesis_parse(self):
        genesis = self.genesis.split()[1:]
        arguments = {}
        options = []
        for i, arg in enumerate(genesis):
            if arg.startswith('-'):
                if i == len(genesis) - 1:  # last one, is an option
                    options.append(arg)
                elif genesis[i + 1].startswith('-'):  # next starts with '-', is an option
                    options.append(arg)
                else:
                    arguments[arg] = genesis[i + 1]
        if '-g' in arguments and arguments['-r'].startswith(arguments['-g']):
            arguments['-r'] = arguments['-r'][len(arguments['-g']):]  # FIXME: workaround gmkpack weirdery
        return arguments, options

    @property
    def genesis_arguments(self):
        """Return arguments (e.g. -r 47t1) of pack creation as a dict."""
        return self._genesis_parse()[0]

    @property
    def genesis_options(self):
        """Return options (e.g. -a) of pack creation as a list."""
        return self._genesis_parse()[1]

    @property
    def release(self):
        """Lastest ancestor main release to the pack."""
        return 'CY' + self.genesis_arguments['-r'].upper().replace('CY', '')  # CY might be or not be here

    @property
    def tag_of_latest_official_ancestor(self):
        """Tag of latest official ancestor."""
        assert self.is_incremental
        args = self.genesis_arguments
        tag = self.release
        if args['-b'] != 'main':
            tag += '_{}.{}'.format(args['-b'], args['-v'])
        return tag

# Methods around *ics_* compilation scripts -----------------------------------

    def ics_path_for(self, program):
        """Path of the compilation script for **program**."""
        return os.path.join(self.abspath, 'ics_' + program.lower())

    def ics_remove(self, program):
        """Remove the compilation script for **program**."""
        if self.ics_available_for(program):
            os.remove(self.ics_path_for(program))

    def ics_available_for(self, program):
        """Whether the compilation script exists for **program**."""
        return os.path.exists(self.ics_path_for(program))

    def ics_build_for(self, program, silent=False,
                      GMK_THREADS=32,
                      Ofrt=4,
                      partition=None,
                      no_compilation=False,
                      no_libs_update=False):
        """Build the 'ics_*' script for **program**."""
        args = self.genesis_arguments
        args.update({'-p':program.lower()})
        if os.path.exists(self.ics_path_for(program)):
            os.remove(self.ics_path_for(program))
        args.update({'-h':self.homepack})
        # build ics
        GmkpackTool.commandline(args, self.genesis_options, silent=silent)
        # modify number of threads
        pattern = 'export GMK_THREADS=(\d+)'
        self._ics_modify(program,
                         re.compile(pattern),
                         pattern.replace('(\d+)', str(GMK_THREADS)))
        # modify optimization level
        pattern = 'Ofrt=(\d)'
        self._ics_modify(program,
                         re.compile(pattern),
                         pattern.replace('(\d)', str(Ofrt)))
        # modify partition
        if partition is not None:
            pattern = '\#SBATCH -p (.+)'
            self._ics_modify(program,
                             re.compile(pattern),
                             pattern.replace('(.+)', partition).replace('\#', '#'))
        # switch off compilation
        if no_compilation:
            pattern = 'export ICS_ICFMODE=(.+)'
            self._ics_modify(program,
                             re.compile(pattern),
                             pattern.replace('(.+)', 'off'))
        # switch off libs update
        if no_libs_update:
            pattern = 'export ICS_UPDLIBS=(.+)'
            self._ics_modify(program,
                             re.compile(pattern),
                             pattern.replace('(.+)', 'off'))
        # ignore files
        if os.path.exists(self._ignored_sources_filepath):
            self.ics_ignore_files(program, self._ignored_sources_filepath)

    def ics_ignore_files(self, program, list_of_files):
        """
        Add **list_of_files** to be ignored to ics_program.

        :param list_of_files: a list of filenames,
            or a filename of a file containing the list of filenames
        """

        if isinstance(list_of_files, six.string_types):  # filename of a file containing list of files to ignore
            pattern = 'end_of_ignored_files'
            self._ics_insert(program, pattern,
                             ['cat {} >> $GMKWRKDIR/.ignored_files'.format(list_of_files)],
                             offset=1)
        else:  # a python list of files to ignore
            pattern = 'cat <<end_of_ignored_files> $GMKWRKDIR/.ignored_files'
            with io.open(list_of_files, 'r') as f:
                list_of_files = [l.strip() for l in f.readlines()]
            self._ics_insert(program, pattern, list_of_files, offset=1)

    @property
    def ics_available(self):
        """Lists the available ics_ compilation scripts."""
        return sorted([f for f in os.listdir(self.abspath)
                       if f.startswith('ics_')])

    def _ics_read(self, program):
        with io.open(self.ics_path_for(program), 'r') as f:
            ics = [line.rstrip() for line in f.readlines()]
        return ics

    def _ics_write(self, program, ics):
        with io.open(self.ics_path_for(program), 'w') as f:
            for line in ics:
                f.write(line + '\n')

    def _ics_modify(self, program, pattern, replacement):
        """
        Modify the ics_program script.

        :param pattern: a re.compile() pattern or a string;
            if line matches, replaced by **replacement**
        :param replacement: replacement line
        """
        ics = self._ics_read(program)
        for i, line in enumerate(ics):
            try:
                ok = line == pattern or pattern.match(line)
            except AttributeError:
                ok = False
            if ok:
                print("ial_build.pygmkpack.Pack._ics_modify():", ics[i], '=>', replacement)
                ics[i] = replacement
                break
        self._ics_write(program, ics)

    def _ics_insert(self, program, pattern, lines, offset=1):
        """
        Insert **lines** in ics_program after/before **pattern**.

        :param pattern: a re.compile() pattern or a string
        :param offset: 0 to insert before, 1 to insert after
        """
        ics = self._ics_read(program)
        for i, line in enumerate(ics):
            try:
                ok = line == pattern or pattern.match(line)
            except AttributeError:
                ok = False
            if ok:
                break
        for l in lines[::-1]:
            ics.insert(i + offset, l)
        self._ics_write(program, ics)

# Populate pack ---------------------------------------------------------------

    @property
    def origin_filepath(self):
        """File in which to find info about origin of the pack."""
        return os.path.join(self.abspath, '.populated_from')

# old school populating ways --------------------------------------------------

    def populate_from_tar(self, tar):
        """Populate the incremental pack with the contents of a **tar** file."""
        with tarfile.open(tar, 'r') as t:
            t.extractall(path=self._local)

    def populate_from_list_of_files_in_dir(self, list_of_files, directory, subdir=None):
        """
        Populate the incremental pack with the **list_of_files** from a given **directory**.

        :param subdir: if given, populate in src/local/subdir/
        """
        directory_abspath = os.path.abspath(directory)
        with self._cd_local(subdir=subdir):
            copy_files_in_cwd(list_of_files, directory_abspath)

    def populate_from_IALview_as_main(self, view):
        """
        Populate main pack with contents from a IALview.
        WARNING: temporary solution before 'bundle' implementation !
        """
        from ial_build.repositories import IALview
        assert isinstance(view, IALview)
        filter_file = self._configfile_for_sources_filtering('IAL', view.tags_history)
        msg = "Populating main pack with: '{}'".format(view.ref)
        print('\n' + msg + '\n' + '=' * len(msg))
        self._populate_from_repo_in_bulk(view.repository, filter_file=filter_file)
        # symbols to be ignored
        symbols_file = self._configfile_for_symbols_to_be_dummyfied(view.tags_history)
        self.ignore_dummy_symbols_from_file(symbols_file)
        self.write_view_info(view)

    def populate_from_IALview_as_incremental(self, view, start_ref=None):
        """
        Populate as incremental pack with contents from a IALview.
        WARNING: temporary solution before 'bundle' implementation !

        :param view: a IALview instance
        :param start_ref: increment of modification starts from this ref.
            If None, starts from latest official tagged ancestor.
        """
        from ial_build.repositories import IALview, GitError
        assert isinstance(view, IALview)
        if start_ref is None:
            assert self.tag_of_latest_official_ancestor == view.latest_official_tagged_ancestor, \
                "Latest official ancestor differ in pack ({}) and repository ({})".format(
                    self.tag_of_latest_official_ancestor, view.latest_official_tagged_ancestor)
            touched_files = view.touched_files_since_latest_official_tagged_ancestor
            print("Populating with modifications between '{}' and '{}'".
                format(view.latest_official_tagged_ancestor,
                       view.ref))
        else:
            touched_files = view.touched_files_since(start_ref)
            print("Populating with modifications between '{}' and '{}'".
                format(start_ref,
                       view.ref))
        if len(view.git_proxy.touched_since_last_commit) > 0:
            print("! Note:  non-committed files in the view are exported to the pack.")
        # files to be copied
        files_to_copy = []
        for k in ('A', 'M', 'T'):
            files_to_copy.extend(list(touched_files.get(k, [])))
        for k in ('R', 'C'):
            files_to_copy.extend([f[1] for f in touched_files.get(k, [])])  # new name of renamed or copied files
        self.populate_from_list_of_files_in_dir(files_to_copy, view.repository)
        # files to be ignored/deleted
        files_to_delete = list(touched_files.get('D', []))
        files_to_delete.extend([f[0] for f in touched_files.get('R', [])])  # original name of renamed files
        self.write_ignored_sources(files_to_delete)
        # files of unknown status
        for k in ('U', 'X', 'B'):
            if k in touched_files:
                raise GitError("Don't know what to do with files which Git status is: " + k)
        self.write_view_info(view)

    def populate_hub(self, latest_main_release):
        """
        Populate hub packages in main pack.
        WARNING: temporary solution before 'bundle' implementation !
        """
        from ial_build.config import GMKPACK_HUB_PACKAGES
        from ial_build.util import host_name
        msg = "Populating vendor packages in pack's hub:"
        print(msg + "\n" + "-" * len(msg))
        for package, properties in GMKPACK_HUB_PACKAGES.items():
            rootdir = properties[host_name()]
            version = properties[latest_main_release]
            project = properties['project']
            print("Package: '{}/{}' (v{}) from {}".format(project, package, version, rootdir))
            pkg_src = os.path.join(rootdir, package, version)
            pkg_dst = os.path.join(self._hub_local_src, project, package)
            shutil.copytree(pkg_src, pkg_dst, symlinks=True)
        print("-" * len(msg))

    def write_view_info(self, view):
        """Write view.info into self.origin_filepath."""
        openmode = 'a' if os.path.exists(self.origin_filepath) else 'w'
        with io.open(self.origin_filepath, openmode) as f:
            view.info(out=f)

# generic methods -------------------------------------------------------------

    def _populate_from_repo_in_bulk(self,
                                    repository,
                                    subdir=None,
                                    filter_file=None):
        """
        Populate a main pack src/local/ with the contents of a repo.

        :param subdir: if given, populate in src/local/{subdir}/
        :param filter_file: file in which to find list of files/dir to be filtered out
        """
        if subdir is None:
            dst = self._local
        else:
            dst = os.path.join(self._local, subdir)
            if not os.path.exists(dst):
                os.makedirs(dst)
        print("\n  Subprojects:")
        for f in sorted(os.listdir(repository)):
            if f == '.git':
                continue
            f_src = os.path.join(repository, f)
            if os.path.isdir(f_src):  # actual subproject
                print('  {}'.format(f))
            subprocess.check_call(['rsync', '-avq', f_src, dst])
        # filter a posteriori
        to_be_filtered = self.prepare_sources_filter(filter_file, subdir=subdir)
        self.filter_sources_a_posteriori(to_be_filtered)

    def _populate_from_repo_as_incremental_component(self,
                                                     repository,
                                                     initial_version,
                                                     subdir=None):
        """
        Populate the incremental pack with the diff since **initial_version**
        from **repository**.

        :param subdir: if given, populate in src/local/subdir/ (otherwise src/local/)
        """
        from ial_build.repositories import GitProxy
        repo = GitProxy(repository)
        touched_files = repo.touched_files_since(initial_version)
        # files to be copied
        files_to_copy = []
        for k in ('A', 'M', 'T'):
            files_to_copy.extend(list(touched_files.get(k, [])))
        for k in ('R', 'C'):
            files_to_copy.extend([f[1] for f in touched_files.get(k, [])])  # new name of renamed or copied files
        self.populate_from_list_of_files_in_dir(files_to_copy, repository, subdir=subdir)
        # files to be ignored/deleted
        files_to_delete = list(touched_files.get('D', []))
        files_to_delete.extend([f[0] for f in touched_files.get('R', [])])  # original name of renamed files
        self.write_ignored_sources(files_to_delete)
        # files of unknown status
        for k in ('U', 'X', 'B'):
            if k in touched_files:
                raise GitError("Don't know what to do with files which Git status is: " + k)

# Populate from bundle --------------------------------------------------------

    def bundle_initial_version_of_component(self, component):
        """
        In an incremenal pack, guess the initial version of **component** in the root pack.
        """
        if component.upper() == 'IAL':
            version = self.tag_of_latest_official_ancestor
        # elif component == ...
        # implement here whenever src/local components are introduced in bundle
        else:
            version = None  # this will turn component to be populated in bulk rather than as increment
        return version

    def bundle_populate_component(self,
                                  component,
                                  bundle,
                                  filter_file=None):
        """
        Populate src/local in incr pack from bundle.

        :param bundle: the ial_build.bundle.IALBundle object.
        :param filter_file: file in which to read the files to be
            filtered at populate time.
        """
        config = bundle.projects[component]
        pkg_dst = self.bundle_component_destination(component, config)
        repository = bundle.local_project_repo(component)
        if pkg_dst.startswith('hub'):
            # packages auto-compiled, in hub
            print("\n* '{}' ({}) from repo: {} via cache: {}".format(component,
                                                                                config['version'],
                                                                                config['git'],
                                                                                repository))
            if self.is_incremental:
                print("  ! Incremental hub packages is currently not an available feature -> populated in bulk")
                # TODO: option in bundle to tell if to be populated in case of incr pack
            pkg_dst = os.path.join(self.abspath, pkg_dst, component)
            if os.path.exists(pkg_dst):
                shutil.rmtree(pkg_dst)
            shutil.copytree(repository, pkg_dst, symlinks=True)
        elif pkg_dst.startswith('src/local'):
            # components to be compiled with gmkpack, in src/local
            print("\n* Component: '{}' ({}) from repo: {} via cache: {}".format(component,
                                                                                config['version'],
                                                                                config['git'],
                                                                                repository))
            subdir = pkg_dst.split(os.path.sep)
            if len(subdir) > 2:
                subdir = subdir[2]
                print("  -> to subdirectory: src/local/{}".format(subdir))
            else:
                subdir = None
            if not self.is_incremental or self.bundle_initial_version_of_component(component) is None:
                # main pack, or not able to determine an increment: bulk
                if self.is_incremental:
                    print("  ! Could not find initial version of component '{}'".format(component),
                          "in root pack --> populated in bulk")
                self._populate_from_repo_in_bulk(repository,
                                                 subdir=subdir,
                                                 filter_file=filter_file)
            else:
                # incremental pack
                self._populate_from_repo_as_incremental_component(repository,
                                                                  self.bundle_initial_version_of_component(component),
                                                                  subdir=subdir)
                print("  ! Incremental source update: no filtering.")

    def bundle_populate(self,
                        bundle,
                        cleanpack=False):
        """
        Populate pack from bundle.

        :param bundle: the ial_build.bundle.IALBundle object.
        :param cleanpack: if True, call cleanpack before populating
        """
        if cleanpack:
            self.cleanpack()
        # prepare
        hub_components = {component:config for component, config in bundle.projects.items()
                          if self.bundle_component_destination(component, config).startswith('hub')}
        gmkpack_components = {component:config for component, config in bundle.projects.items()
                              if self.bundle_component_destination(component, config).startswith('src/local')}
        tags_history = bundle.tags_history()
        # start with hub:
        msg = "Populating components in pack's hub:"
        print("\n" + msg + "\n" + "=" * len(msg))
        for component, config in hub_components.items():
            self.bundle_populate_component(component,
                                           bundle)
        # then src/local components:
        msg = "Populating components in pack's src/local:"
        print("\n" + msg + "\n" + "=" * len(msg))
        for component, config in gmkpack_components.items():
            filter_file = self._configfile_for_sources_filtering(component, tags_history[component])
            self.bundle_populate_component(component,
                                           bundle,
                                           filter_file=filter_file)
        print('-' * 80)
        if not self.is_incremental:
            # symbols to be ignored
            symbols_file = self._configfile_for_symbols_to_be_dummyfied(tags_history.get('IAL'))
            self.ignore_dummy_symbols_from_file(symbols_file)
        # log in pack
        shutil.copy(bundle.bundle_file, os.path.join(self.abspath, 'bundle.yml'))

    def bundle_component_destination(self, component, config):
        """
        Distinction between 'projects' (in src/local) and 'packages' (in hub),
        as specified in bundle (attribute 'gmkpack') or parameterized.

        The distinction is based on the component having a build system:
        - integrated and plugged in gmkpack: package
        - no build system, or not plugged in gmkpack: project
        """
        destination = config.get('gmkpack', COMPONENTS_MAP.get(component.lower(), None))
        assert destination is not None, ' '.join(["Destination of component '{}' within gmkpack is unknown,",
                                                  "please indicate in bundle file through attribute 'gmkpack',",
                                                  "e.g. gmkpack = src/local/oops or",
                                                  "hub/local/src/ecSDK"]).format(component)
        return destination

    def _bundle_write_properties(self, projects):
        """Write info into self.origin_filepath."""
        openmode = 'a' if os.path.exists(self.origin_filepath) else 'w'
        with io.open(self.origin_filepath, openmode) as f:
            f.write("\n{} --- populate from bundle successful with:\n".format(now()))
            for project, config in projects.items():
                f.write("* {}\n".format(project))
                f.write("    version: {}\n".format(config['version']))
                f.write("    from remote git: {}\n".format(config['git']))

# Filters ---------------------------------------------------------------------

    @property
    def _ignored_sources_filepath(self):
        """File in which to find the sources to be ignored at compilation time."""
        return os.path.join(self.abspath, '_ignored_sources')

    def filter_sources_a_posteriori(self, filter_list):
        """Remove sources files to be filtered from src/local/ (ensuring they are in src/local)."""
        for f in filter_list:
            f = os.path.abspath(f)  # eliminate potential ../
            if not f.startswith(self._local):  # file is out of pack/src/local: ignore
                print("! File '{}' is out of '{}': not removed".format(f, self._local))
                continue
            if os.path.isdir(f):
                print("Removed tree: " + f)
                shutil.rmtree(f)
            else:
                print("Removed file: " + f)
                os.remove(f)

    def prepare_sources_filter(self, filter_file, subdir=None):
        """
        Prepare a list of source files to be filtered out,
        list is read from file then expanded (wildcards, abs paths).
        """
        if filter_file is None:
            print("\nList of sources to be filtered out - None provided.")
            filter_list = []
        else:
            print("\nList of sources to be filtered out (read from file '{}'):".format(filter_file))
            with io.open(filter_file, 'r') as ff:
                filter_list = [f.strip() for f in ff.readlines()
                               if (not f.strip().startswith('#') and f.strip() != '')]  # ignore commented and blank lines
        # make abs paths
        for i, f in enumerate(filter_list):
            if not os.path.isabs(f):
                if subdir is None:
                    filter_list[i] = os.path.join(self._local, f)
                else:
                    filter_list[i] = os.path.join(self._local, subdir, f)
        # expand wildcards
        expanded_filter_list = []
        for f in filter_list:
            expanded_filter_list.extend(glob.glob(f))
        return expanded_filter_list

    def _configfile_for_sources_filtering(self, project, versions=None):
        """
        Find filter file in config or user config, for project and optionally version.
        If **version** is a list, the list is read in reverse order.
        User customization in ~/.config/ial_build/gmkpack/sources_filters/{version}.txt
        """
        from ial_build import package_rootdir
        user_dirpath = os.path.join(os.environ['HOME'], '.config', 'ial_build', 'gmkpack', 'sources_filters')
        base_dirpath = os.path.join(package_rootdir, 'conf', 'gmkpack', 'sources_filters')
        files = ['{}.txt'.format(project)]
        if versions is not None:
            if isinstance(versions, str):
                versions = [versions]
            if isinstance(versions, list):
                files += ['{}-{}.txt'.format(project, v) for v in versions]
        for d in (user_dirpath, base_dirpath):
            for f in files[::-1]:
                ff = os.path.join(d, f)
                if os.path.exists(ff):
                    return ff
        return None  # if no file has been found

    def _configfile_for_symbols_to_be_dummyfied(self, versions=None):
        """
        Find config file of symbols to be added as dummys at link time.
        If **version** is a list, the list is read in reverse order.
        User customization in ~/.config/ial_build/gmkpack/dummy_symbols/{version}.txt
        """
        from ial_build import package_rootdir
        user_dirpath = os.path.join(os.environ['HOME'], '.config', 'ial_build', 'gmkpack', 'dummy_symbols')
        base_dirpath = os.path.join(package_rootdir, 'conf', 'gmkpack', 'dummy_symbols')
        files = []
        if versions is not None:
            if isinstance(versions, str):
                versions = [versions]
            if isinstance(versions, list):
                files += ['{}.txt'.format(v) for v in versions]
        for d in (user_dirpath, base_dirpath):
            for f in files[::-1]:  # latest version first
                ff = os.path.join(d, f)
                if os.path.exists(ff):
                    return ff
        return None  # if no file has been found

    def ignore_dummy_symbols_from_file(self, filename):
        """Set symbols to be ignored in src/unsxref/verbose."""
        if filename is None:
            print("\nList of symbols to be dummyfied - None provided.")
            symbols_list = []
        else:
            print("\nList of symbols to be dummyfied (read from file '{}'):".format(filename))
            with io.open(filename, 'r') as ff:
                symbols_list = [f.strip() for f in ff.readlines()
                                if (not f.strip().startswith('#') and f.strip() != '')]  # ignore commented and blank lines
        for s in symbols_list:
            print(s)
            symbol_path = os.path.join(self.abspath, 'src', 'unsxref', 'verbose', s)
            with io.open(symbol_path, 'a'):
                os.utime(symbol_path, None)
        print('-' * 80)

    def write_ignored_sources(self, list_of_files):
        """Write sources to be ignored in a dedicated file."""
        if isinstance(list_of_files, six.string_types):  # already a file containing filenames: copy
            shutil.copyfile(list_of_files, self._ignored_sources_filepath)
        else:
            with io.open(self._ignored_sources_filepath, 'w') as f:  # a python list
                for l in list_of_files:
                    f.write(l + '\n')
        if 'ics_' in self.ics_available:
            self.ics_ignore_files('', self._ignored_sources_filepath)

# Executables -----------------------------------------------------------------

    @property
    def available_executables(self):
        """Lists the available executables."""
        return sorted(os.listdir(self._bin))

    def executable_ok(self, program):
        """Check that **program** executable has been made."""
        bins = os.listdir(self._bin)
        return program.lower() in bins or program.upper() in bins

# Compilation -----------------------------------------------------------------

    def compile(self, program, silent=False, clean_before=False, fatal=True):
        """Run interactively the ics_ compilation script for **program**"""
        assert os.path.exists(self.ics_path_for(program))
        cmd = [self.ics_path_for(program),]
        if clean_before:
            self.cleanpack()
        try:
            if silent:
                logdir = os.path.join(self.abspath, 'log')
                if not os.path.exists(logdir):
                    os.makedirs(logdir)
                if program == '':
                    outname = os.path.join(logdir,
                                           '.'.join(['_',
                                                     now().stdvortex]))
                else:
                    outname = os.path.join(logdir,
                                           '.'.join([program.lower(),
                                                     now().stdvortex]))
                with io.open(outname, 'w') as f:
                    ok = subprocess.check_call(cmd, stdout=f, stderr=f)
            else:
                outname = None
                ok = subprocess.check_call(cmd)
        except Exception:
            if fatal:
                raise
            else:
                ok = False
        else:
            ok = True if int(ok) == 0 else False
            if program != '':
                ok = self.executable_ok(program)
            if fatal and not ok:
                if program == '':
                    message = "Compilation failed."
                else:
                    message = "Build of {} failed.".format(program)
                if outname is not None:
                    message += " Output: " + outname
                raise PackError(message)
        report = {'OK':ok,
                  'Output':outname}
        return report

    def compile_all_programs(self, silent=False):
        """Run interactively the ics_ compilation script for **program**"""
        for program in [s.replace('ics_', '') for s in self.ics_available]:
            print("Start compilation of {}...".format(program))
            r = self.compile(program, silent=silent)
            print(r)
            print("...ended.")

    def compile_batch(self, program, batch_scheduler):
        """
        Run in batch the ics_ compilation script for **program**, using
        **batch_scheduler**
        """
        raise NotImplementedError("not yet")
        batch_scheduler.submit(self.ics_path_for(program))

# Pack contents ---------------------------------------------------------------

    def scanpack(self):
        """List the modified files (present in local directory)."""
        files = [f.strip()
                 for f in subprocess.check_output(['scanpack'], cwd=self._local).decode('utf-8').split('\n')
                 if f != '']
        return files

    def cleanpack(self):
        """Clean .o & .mod."""
        subprocess.check_call(['cleanpack', '-f'], cwd=self.abspath)

    def local2tar(self, tar_filename=None):
        """Extract the contents of the pack to a tarfile."""
        if tar_filename is None:
            tar_filename = os.path.join(self.abspath, now().stdvortex + '.tar')
        files = self.scanpack()
        with tarfile.open(tar_filename, 'w') as t:
            with self._cd_local():
                for f in files:
                    t.add(f)
        return tar_filename

# From pack to branch ---------------------------------------------------------

    # DEPRECATED: bundle case ?
    @property
    def _packname2branchname(self):
        args = self.genesis_arguments  # TODO: main pack case
        packname = self.packname
        # prune reference compiler version and compiler options
        suffix = '.{}.{}'.format(args['-l'], args['-o'])
        if packname.endswith(suffix):
            packname = packname.replace(suffix, '')
        # try to identify user and release
        _re_branch = re.compile('{}_{}_(.+)'.format(os.getlogin(), self.release))
        if _re_branch.match(packname):
            branchname = packname
        else:
            branchname = '_'.join([os.getlogin(), self.release, packname])
        return branchname

    # DEPRECATED: bundle case ?
    def save_as_IAL_branch(self, repository,
                           files_to_delete=[],
                           branchname=None,
                           preexisting_branch=False,
                           commit_message=None,
                           ask_confirmation=False,
                           register_in_GCOdb=False):
        """
        Save the contents of the pack into an IAL Branch.

        :param files_to_delete: either the filename of a file containing
            the list of files to ignore, or directly a list of files to delete
            in branch
        :param branchname: if None, generated from pack options as:
            <logname>_<release>_<packname>
        :param preexisting_branch: whether the branch already exists in the repository
        :param commit_message: if not None, activate committing the modifications
            after populating the branch with given commit message
        :param ask_confirmation: ask for confirmation about the repo/branch
            before actually creating branch and/or populating
        :param register_in_GCOdb: to register the branch in GCO database
        """
        from ial_build.repositories import IALview
        if not self.is_incremental:
            raise NotImplementedError("Populating branch from a main pack.")
        # guess branch name
        if branchname is None:
            branchname = self._packname2branchname
        touched_files = self.scanpack()
        if isinstance(files_to_delete, six.string_types):
            with io.open(files_to_delete, 'r') as f:
                files_to_delete = [file.strip() for file in f.readlines()]
        # printings
        print("Files modified or added:")
        for f in touched_files:
            print(f)
        print("-" * 80)
        if len(files_to_delete) > 0:
            print("Files to be deleted from repo:")
            for f in files_to_delete:
                print(f)
            print("-" * 80)
        if preexisting_branch:
            print("About to populate preexisting branch: '{}'".format(branchname))
        else:
            print("About to create & populate branch: '{}'".format(branchname))
            print("Starting from tag: {}".format(self.tag_of_latest_official_ancestor))
            print("In repository: {}".format(repository))
        if commit_message is not None:
            print("And commit with message: '{}'".format(commit_message))
        if ask_confirmation:
            ok = six.moves.input("Everything OK ? [y/n] ")
            if ok == 'n':
                print("Confirmation cancelled: exit.")
                exit()
            elif ok != 'y':
                print("Please answer by 'y' or 'n'. Exit.")
                exit()
        # now checkout branch
        if preexisting_branch:
            branch = IALview(repository, branchname)
        else:
            branch = IALview(repository, branchname,
                              new_branch=True,
                              start_ref=self.tag_of_latest_official_ancestor,
                              register_in_GCOdb=register_in_GCOdb)
        # copy modified/added files
        with branch.git_proxy.cd_repo():
            copy_files_in_cwd(touched_files, self._local)
        # remove files to be so
        assert isinstance(files_to_delete, list)
        for f in files_to_delete:
            branch.git_proxy.delete_file(f)
        print("=> Pack: '{}' saved as branch: '{}' in repository: {}".format(
            self.packname, branch.branch_name, repository))
        # commit  TOBECHECKED:
        if commit_message is not None:
            branch.git_proxy.stage(touched_files)
            branch.git_proxy.commit(commit_message, add=True)
            #print("Committed: {}".format(commit))
        else:
            print("Changes are not commited: cf. 'git status'")
        return branch

# Others -------------------------------------------------------------------

    def rmpack(self):
        """Delete pack."""
        shutil.rmtree(self.abspath)
