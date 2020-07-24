#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Python wrapping of *gmkpack*.
"""
from __future__ import print_function, absolute_import, unicode_literals, division

import six
import os
import re
import subprocess
import tarfile
import io
import shutil
from contextlib import contextmanager

from bronx.system.unistd import stdout_redirected, stderr_redirected
from bronx.stdtypes.date import now

#: No automatic export
__all__ = []

GCO_ROOTPACK = '/home/mf/dp/marp/martinezs/packs'
USUAL_BINARIES = ['masterodb', 'bator',
                  'pgd', 'prep',
                  'oovar', 'ootestvar',
                  'ioassign', 'lfitools']


class PackError(Exception):
    pass


def gmkpack_cmd(arguments,
                silent=False):
    """
    Wrapper to gmkpack command.
    
    :param arguments: arguments to the command-line to be passed as a dict,
        e.g. {'-l':'IMPIFC1801'}
    :param silent: if True, hide gmkpack's stdout/stderr output
    """
    arguments_as_list = []
    for k, v in arguments.items():
        arguments_as_list.extend([k, v])
    command = ['gmkpack',] + arguments_as_list
    if silent:
        with io.open(os.devnull, 'w') as devnull:
            r = subprocess.check_call(command, stdout=devnull, stderr=devnull)
    else:
        r = subprocess.check_call(command)
    return r


def new_incremental_pack(packname,
                         initial_release,
                         initial_branch=None,
                         initial_branch_version=None,
                         from_root=None,
                         homepack=None,
                         other_pack_options={},
                         silent=False):
    """
    Create a new incremental pack.

    :param packname: name of the pack
    :param initial_release: release to start from
    :param initial_branch: branch on release to start from
    :param initial_branch_version: version number on the branch to start from
    :param from_root: where to look for pack to start from (option -f of gmkpack)
    :param homepack: home directory for packs
    :param other_pack_options: arguments to the command-line to be passed as a dict,
        e.g. {'-l':'IMPIFC1801'}
    :param silent: to mute gmkpack
    """
    # TODO: main packs (include ignored files for compil)
    pack = Pack(packname, preexisting=False, homepack=homepack)
    if os.path.exists(pack.abspath):
        raise PackError('Pack already exists, cannot create: {}'.format(pack.abspath))
    args = {'-r':initial_release.lower().replace('cy', ''),
            '-u':packname}
    if initial_branch is not None:
        args['-b'] = initial_branch
        if initial_branch_version is not None:
            args['-v'] = initial_branch_version
    if from_root is not None:
        args['-f'] = from_root
    if from_root == GCO_ROOTPACK:
        args['-g'] = 'cy'
        args['-e'] = '.pack'
    args.update({'-h':pack.homepack})
    assert isinstance(other_pack_options, dict)
    args.update(other_pack_options)
    gmkpack_cmd(args, silent=silent)
    return pack


def get_homepack(homepack=None):
    """Get a HOMEPACK directory, in argument, $HOMEPACK, or $HOME/pack."""
    if homepack in (None, ''):
        homepack = os.environ.get('HOMEPACK')
    if homepack in (None, ''):
        homepack = os.path.join(os.environ.get('HOME'), 'pack')
    return homepack


def copy_files_in_cwd(list_of_files, originary_directory_abspath):
    """Copy a bunch of files from an originary directory to the cwd."""
    symlinks = {}
    if six.PY3:
        symlinks['follow_symlinks'] = True
    for f in list_of_files:
        dirpath = os.path.dirname(os.path.abspath(f))
        if not os.path.exists(dirpath):
            os.makedirs(dirpath)
        shutil.copyfile(os.path.join(originary_directory_abspath, f), f,
                        **symlinks)


class Pack(object):

    def __init__(self, packname, preexisting=True, homepack=None):
        """
        Create Pack object from the **packname**.
        """
        self.packname = packname
        self.homepack = get_homepack(homepack)
        self.abspath = os.path.join(self.homepack, packname)
        self._local = os.path.join(self.abspath, 'src', 'local')
        self._bin = os.path.join(self.abspath, 'bin')
        if not preexisting and os.path.exists(self.abspath):
            raise PackError("Pack already exists, while *preexisting* is False ({}).".format(self.abspath))
        if preexisting and not os.path.exists(self.abspath):
            raise PackError("Pack is supposed to preexist, while it doesn't ({}).".format(self.abspath))

    @contextmanager
    def _cd_local(self):
        """Context: in self._local"""
        owd = os.getcwd()
        try:
            os.chdir(self._local)
            yield self._local
        finally:
            os.chdir(owd)

    def genesis(self):
        """Read pack/.genesis file and return it."""
        genesis = os.path.join(self.abspath, '.genesis')
        with io.open(genesis, 'r') as g:
            genesis = g.readline().strip()
        return genesis
    
    @property
    def options(self):
        """Read pack/.genesis file and return it as a dict."""
        genesis = self.genesis().split()
        options = dict(zip(genesis[1::2], genesis[2::2]))
        options.pop('-p', None)
        return options
    
    @property
    def release(self):
        """Lastest ancestor main release to the pack."""
        return 'CY' + self.options['-r'].upper().replace('CY', '')  # CY might be or not be here
    
    @property
    def tag_of_latest_official_ancestor(self):
        """Tag of latest official ancestor."""
        options = self.options
        tag = self.release
        if options['-b'] != 'main':
            tag += '_{}.{}'.format(options['-b'], options['-v'])
        return tag
    
    # Methods around *ics_* compilation scripts --------------------------------
    
    def ics_path_for(self, program):
        """Path of the compilation script for **program**."""
        return os.path.join(self.abspath, 'ics_' + program.lower())

    def ics_available_for(self, program):
        """Whether the compilation script exists for **program**."""
        return os.path.exists(self.ics_path_for(program))
    
    def ics_build_for(self, program, silent=False,
                      GMK_THREADS=40,
                      Ofrt=2):
        """Build the 'ics_*' script for **program**."""
        args = self.options
        args.update({'-p':program.lower()})
        if os.path.exists(self.ics_path_for(program)):
            os.remove(self.ics_path_for(program))
        args.update({'-h':self.homepack})
        gmkpack_cmd(args, silent=silent)
        pattern = 'export GMK_THREADS=(\d+)'
        self._ics_modify(program,
                         re.compile(pattern),
                         pattern.replace('(\d+)', str(GMK_THREADS)))
        pattern = 'Ofrt=(\d)'
        self._ics_modify(program,
                         re.compile(pattern),
                         pattern.replace('(\d)', str(Ofrt)))
        if os.path.exists(self.ignored_files_filename):
            self.ics_ignore_files(program, self.ignored_files_filename)
    
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
            ics = [line.strip() for line in f.readlines()]
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
    
    # Populate pack ------------------------------------------------------------
    
    def populate_from_tar(self, tar):
        """Populate the incremental pack with the contents of a **tar** file."""
        with tarfile.open(tar, 'r') as t:
            t.extractall(path=self._local)
    
    def populate_from_files_in_dir(self, list_of_files, directory):
        """
        Populate the incremental pack with the **list_of_files**
        from a given **directory**.
        """
        directory_abspath = os.path.abspath(directory)
        with self._cd_local():
            copy_files_in_cwd(list_of_files, directory_abspath)
    
    def populate_from_IA4Hview(self, view):
        """
        Populate the incremental pack with contents from a IA4Hview.
        
        :param view: a IA4Hview instance
        """
        from .repositories import GitError, IA4Hview
        assert isinstance(view, IA4Hview)
        self._assert_IA4Hview_compatibility(view)
        touched_files = view.touched_files_since_latest_official_tagged_ancestor
        if len(view.git_proxy.touched_since_last_commit) > 0:
            print("! Note:  non-committed files in the view are exported to the pack.")
        # files to be copied
        files_to_copy = []
        for k in ('A', 'M', 'T'):
            files_to_copy.extend(list(touched_files.get(k, [])))
        for k in ('R', 'C'):
            files_to_copy.extend([f[1] for f in touched_files.get(k, [])])  # new name of renamed or copied files
        self.populate_from_files_in_dir(files_to_copy, view.repository)
        # files to be ignored/deleted
        files_to_delete = list(touched_files.get('D', []))
        files_to_delete.extend([f[0] for f in touched_files.get('R', [])])  # original name of renamed files
        self.ignore_files(files_to_delete)
        # files of unknown status
        for k in ('U', 'X', 'B'):
            if k in touched_files:
                raise GitError("Don't know what to do with files which Git status is: " + k)
    
    def _assert_IA4Hview_compatibility(self, view):
        """Assert that view and pack have the same original node (ancestor)."""
        branch_ancestor_info = view.latest_official_branch_from_main_release
        options = self.options
        pack_release = self.release
        assert branch_ancestor_info['r'] == pack_release, \
            "release: (view)={} vs. (pack)={}".format(branch_ancestor_info['r'],
                                                        pack_release)
        if branch_ancestor_info['b'] is not None:
            assert branch_ancestor_info['b'] == options['-b'], \
                "official view: (view)={} vs. (pack)={}".format(branch_ancestor_info['b'],
                                                                    options['-b'])
            assert branch_ancestor_info['v'] == options['-v'], \
                "official view version: (view)={} vs. (pack)={}".format(branch_ancestor_info['v'],
                                                                            options['-v'])
        else:
            assert options['-b'] == 'main'
    
    def ignore_files(self, list_of_files):
        """Write files to be ignored in a dedicated file."""
        if isinstance(list_of_files, six.string_types):  # already a file containing filenames: copy
            shutil.copyfile(list_of_files, self.ignored_files_filename)
        else:
            with io.open(self.ignored_files_filename, 'w') as f:  # a python list
                for l in list_of_files:
                    f.write(l + '\n')
        if 'ics_' in self.ics_available:
            self.ics_ignore_files('', self.ignored_files_filename)
   
    def _packname2branchname(self):
        options = self.options
        packname = self.packname
        # prune reference compiler version and compiler options
        suffix = '.{}.{}'.format(options['-l'], options['-o'])
        if packname.endswith(suffix):
            packname = packname.replace(suffix, '')
        # try to identify user and release
        _re_branch = re.compile('{}_{}_(.+)'.format(os.getlogin(), self.release))
        if _re_branch.match(packname):
            branchname = packname
        else:
            branchname = '_'.join([os.getlogin(), self.release, packname])
        return branchname

    def save_as_IA4H_branch(self, repository,
                            files_to_ignore=None,
                            branchname=None,
                            preexisting_branch=False,
                            commit_message=None,
                            push=False,
                            remote=None):
        """
        Save the contents of the pack into an IA4H Branch.
        
        :param files_to_ignore: either the filename of a file containing
            the list of files to ignore, or a list of filenames
        :param branchname: if None, generated from pack options as:
            <logname>_<release>_<packname>
        :param preexisting_branch: whether the branch already exists in the repository
        :param commit_message: if not None, activate committing the modifications
            after populating the branch with given commit message
        :param push: to push the branch to remote repository after committing
        :param remote: remote repository to be pushed to
        """
        from .repositories import IA4Hview
        # TODO: if branch has not been created with GCO-Git toolbox, the push may fail ?
        if branchname is None:
            branchname = self._packname2branchname
        if preexisting_branch:
            branch = IA4Hview(repository, branchname)
        else:
            branch = IA4Hview(repository, branchname,
                              new_branch=True,
                              start_ref=self.tag_of_latest_official_ancestor)
        touched_files = self.scanpack()
        if isinstance(files_to_ignore, six.string_types):
            with io.open(files_to_ignore, 'r') as f:
                files_to_ignore = [file.strip() for file in f.readlines()]
        with branch.git_proxy.cd_repo():
            copy_files_in_cwd(touched_files, self._local)
        if files_to_ignore is not None:
            assert isinstance(files_to_ignore, list)
            for f in files_to_ignore:
                branch.git_proxy.delete_file(f)
        print("=> Pack: {} saved as branch: {} in repository: {}".format(
            self.packname, branch.branch_name, repository))
        if commit_message is not None:
            branch.git_proxy.stage(touched_files)
            branch.git_proxy.commit(commit_message)
            #print("Committed: {}".format(commit))
            if push:
                branch.push(remote=remote)
                print("Pushed.")
        return branch
        
    # Executables --------------------------------------------------------------
    
    @property
    def available_executables(self):
        """Lists the available executables."""
        return sorted(os.listdir(self._bin))
    
    def executable_ok(self, program):
        """Check that **program** executable has been made."""
        bins = os.listdir(self._bin)
        return program.lower() in bins or program.upper() in bins
    
    # Compilation --------------------------------------------------------------
    
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
                outname = os.path.join(logdir,
                                       '.'.join([program.lower(),
                                                 now().stdvortex]))
                with io.open(outname, 'w') as f:
                    subprocess.check_call(cmd, stdout=f, stderr=f)
            else:
                outname = None
                subprocess.check_call(cmd)
        except Exception:
            if fatal:
                raise
        else:
            if fatal and not self.executable_ok(program):
                message = "Build of {} failed.".format(program)
                if outname is not None:
                    message += " Output: " + outname
                raise PackError(message)
        return {'OK':self.executable_ok(program),
                'Output':outname}
    
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
    
    # Pack contents ------------------------------------------------------------
    
    @property
    def ignored_files_filename(self):
        """File in which to find the files to be ignored at compilation."""
        return os.path.join(self.abspath, '.ignored_files.pygmkpack')
    
    def scanpack(self):
        """List the modified files (present in local directory)."""
        files = [f.strip()
                 for f in subprocess.check_output(['scanpack'], cwd=self._local).split('\n')
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

    # Others -------------------------------------------------------------------
    
    def rmpack(self):
        """Delete pack."""
        shutil.rmtree(self.abspath)
