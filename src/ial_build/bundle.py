#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Utility to deal with bundles in sight of their build.
"""
import json
import os
import io
import tempfile
import subprocess
import re
import shutil
import sys
import uuid

from .pygmkpack import Pack, GmkpackTool
from .config import DEFAULT_BUNDLE_CACHE_DIR, DEFAULT_IALBUNDLE_REPO
from .repositories import GitProxy, IALview


class IALbundleRepo(GitProxy):

    def find_bundle_tags_for_IAL_git_ref(self, IAL_repo_path,
                                         IAL_git_ref=None,
                                         verbose=False):
        """
        Find the most recent bundle tag(s) in IAL-bundle repository, available for **IAL_git_ref** ancestors.
        Ancestors are looked for in **IAL_repo_path**.
        If IAL_git_ref==None, take the currently checkedout ref.
        """
        IAL = IALview(IAL_repo_path, IAL_git_ref, need_for_checkout=False)
        assert IAL.git_proxy.ref_exists(IAL.ref), "Unknown IAL git reference: {}".format(IAL.ref)
        print("Looking for registered bundles for ancestors of '{}'".format(IAL.ref))
        matching = []
        for t in IAL.official_tagged_ancestors[::-1]:
            # for a tag syntaxed 'CY<id>', bundle tag is 'BDL<id>'
            matching = [btag for btag in self.tags
                        if re.match('BDL{}-.+'.format(t[2:]), btag)]
            if len(matching) > 0:
                break
            else:
                if verbose:
                    print("No bundle found for tag: {}".format(t))
        if matching == []:
            raise ValueError("No bundle has been found for reference '{}' or any of its ancestors.".format(IAL.ref))
        else:
            return {'official_tagged_ancestor':t, 'bundles':matching}

    def print_bundle_tags_for_IAL_git_ref(self, IAL_repo_path,
                                          IAL_git_ref=None,
                                          verbose=False):
        """
        Find the most recent bundle tag(s) in IAL-bundle repository, available for **IAL_git_ref** ancestors.
        Ancestors are looked for in **IAL_repo_path**.
        If IAL_git_ref==None, take the currently checkedout ref.
        """
        bundles = self.find_bundle_tags_for_IAL_git_ref(IAL_repo_path,
                                                        IAL_git_ref=IAL_git_ref,
                                                        verbose=verbose)
        print("Historised bundles associated with ancestor '{}' :".format(bundles['official_tagged_ancestor']))
        for b in bundles['bundles']:
            print(" - {}".format(b))

    def get_bundle_for_IAL_git_ref(self, IAL_repo_path,
                                   IAL_git_ref=None,
                                   to_file='__tmp__',
                                   overwrite=False,
                                   verbose=False):
        """
        Get bundle from IAL-bundle repository, coherent with the given **IAL_git_ref** ancestors.
        Get the most recent bundle in IAL-bundle repository, available for **IAL_git_ref** ancestors.
        Raise an error if several are found.
        Ancestors are looked for in **IAL_repo_path**.
        If IAL_git_ref==None, take the currently checkedout ref.

        :param to_file: path/name in which to get the bundle file
                        if '__tmp__', a unique random file is used
                        if '__tag__, the file is ./<bundle_tag>.yml
                        Can also be sys.stdout
        :param overwrite: to allow overwriting of existing target file
        """
        found = self.find_bundle_tags_for_IAL_git_ref(IAL_repo_path,
                                                      IAL_git_ref=IAL_git_ref,
                                                      verbose=verbose)
        ancestor = found['official_tagged_ancestor']
        bundle_tags = found['bundles']
        if len(bundle_tags) == 1:
            bundle_tag = bundle_tags[0]
            print("Found 1 tagged bundle '{}' for IAL tagged ancestor '{}'".format(bundle_tag, ancestor))
            return self.get_bundle(bundle_tag,
                                   to_file=to_file,
                                   overwrite=overwrite)
        else:
            raise ValueError("Found multiple bundles for {}: {}".format(ancestor, bundle_tags))

    def get_bundle(self, bundle_tag,
                   to_file='__tag__',
                   overwrite=False):
        """
        Get required bundle from IAL-bundle repository.

        :param to_file: path/name in which to get the bundle file
                        if '__tmp__', a unique random file is used
                        if '__tag__, the file is ./<bundle_tag>.yml
                        Can also be sys.stdout
        :param overwrite: to allow overwriting of existing target file
        """
        if to_file == '__tmp__':
            to_file = tempfile.mkstemp(suffix='.yml')[1]
            print("Using temporary file for bundle:", to_file)
            overwrite = True
        elif to_file == '__tag__':
            to_file = '{}.yml'.format(bundle_tag)
            print("Copy to:", to_file)
        to_file = self.extract_file_from_to(bundle_tag, 'bundle.yml',
                                            destination=to_file,
                                            overwrite=overwrite)
        if to_file != sys.stdout:
            return IALBundle(to_file, ID=bundle_tag)


class TmpIALbundleRepo(IALbundleRepo):

    def __init__(self, origin_repo=None, in_dir=None, verbose=False):
        """
        Temporary IALbundleRepo, cloned from **origin_repo** in directory **in_dir**.
        If **in_dir** is None, use a tempdir.
        Warning ! In any case, the clone repository is deleted when this object is deleted.
        """
        if origin_repo is None:
            origin_repo = DEFAULT_IALBUNDLE_REPO
        if in_dir is None:
            in_dir = tempfile.mkdtemp()
        std = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) if not verbose else {}
        subprocess.check_call(['git', 'clone', origin_repo, 'IAL-bundle'], cwd=in_dir,
                              **std)
        if verbose:
            print("-" * 80)
        super(TmpIALbundleRepo, self).__init__(os.path.join(in_dir, 'IAL-bundle'))

    def __del__(self):
        shutil.rmtree(self.repository)


class IALBundle(object):

    def __init__(self, bundle_file, ID=None, src_dir=None):
        """
        :param bundle: bundle file (yaml)
        :param src_dir: directory where to find sources of the projects
        """
        from ecbundle.bundle import Bundle
        self.bundle_file = bundle_file
        if ID is None:
            self.ID = os.path.basename(bundle_file)
        else:
            self.ID = ID
        self.ecbundle = Bundle(self.bundle_file)
        self.projects = {}
        for project in self.ecbundle.get('projects'):
            for name, conf in project.items():
                self.projects[name] = dict(conf)
        self.downloaded = None  # none = unknown
        self.src_dir = src_dir

    def _switch_remotes(self):
        """
        Switch remotes of repositories to other names (temporarily),
        so as to comply with required remotes from bundle.
        """
        self._to_rename = {}
        for p, conf in self.projects.items():
            if os.path.exists(self.local_project_repo(p)):
                r = GitProxy(self.local_project_repo(p))
                req_remote_url = os.path.expanduser(os.path.expandvars(conf['git']))
                req_remote = conf.get('remote', 'origin')
                if req_remote in r.remotes.keys() and req_remote_url != r.remotes[req_remote]:
                    # temporarily rename existing remote
                    tmp = str(uuid.uuid4())
                    self._to_rename[p] = [{'initial':req_remote, 'tmp':tmp}]
                    r.remote_rename(req_remote, tmp)
                    # look for an existing remote matching with required one
                    matching = False
                    for remote, remote_url in r.remotes.items():
                        matching = (remote_url == req_remote_url)
                        if matching:
                            # temporarily rename this one as req_remote
                            self._to_rename[p].append({'initial':remote,'tmp':req_remote})
                            r.remote_rename(remote, req_remote)
                            break
                    # no matching remote found: add
                    if not matching:
                        r.remote_add(req_remote, req_remote_url)
                        self._to_rename[p].append({'initial':str(uuid.uuid4()), 'tmp':req_remote})

    def _switch_remotes_back(self):
        """Switch back remote to their initial values. To be called after _switch_remotes() only !"""
        for p, list_of_remotes in self._to_rename.items():
            r = GitProxy(self.local_project_repo(p))
            for remote in list_of_remotes[::-1]:
                r.remote_rename(remote['tmp'], remote['initial'])

    def download(self,
                 src_dir=None,
                 update=True,
                 threads=1,
                 no_colour=True,
                 dryrun=False):
        """
        Download repositories and (optionnally) checkout according versions.

        :param src_dir: directory in which to download/update repositories of projects
        :param update: if repositories are to be updated/checkedout
        :param threads: number of threads to do parallel downloads
        :param no_colour: Disable color output
        """
        import logging
        from ecbundle.logging import logger
        logger.setLevel(logging.DEBUG)
        from ecbundle import BundleDownloader
        # (re)define src_dir
        if src_dir is None and self.src_dir is None:
            self.src_dir = os.getcwd()
        elif src_dir is not None:
            if self.src_dir is not None:
                print("IALBundle: src_dir overwritten by download to '{}'".format(src_dir))
            self.src_dir = src_dir
        self._switch_remotes()
        # downloads
        try:
            b = BundleDownloader(bundle=self.bundle_file,
                                 src_dir=self.src_dir,
                                 update=update,
                                 threads=threads,
                                 no_colour=no_colour,
                                 dryrun=dryrun,
                                 dry_run=dryrun,
                                 shallow=False,
                                 forced_update=update)
            if b.download() != 0:
                raise RuntimeError("Downloading repositories failed.")
        finally:
            self._switch_remotes_back()
        self.downloaded = True
        self.src_dir = b.src_dir()

    def local_project_repo(self, project):
        """Path to locally downloaded repository of project."""
        assert self.src_dir is not None, "Bundle has to be downloaded or 'src_dir' attribute defined." 
        return os.path.join(self.src_dir, project)

    def tags_history(self):
        """Get tags' history for each project's version."""
        history = {}
        cwd = os.getcwd()
        for p in self.projects.keys():
            repo = GitProxy(self.local_project_repo(p))
            history[p] = []
            for t in repo.tags_history(self.projects[p]['version']):
                history[p].extend(t)
        return history

    def dump(self, f):
        """Dump back the bundle in an open bundle file handler."""
        with io.open(self.bundle_file, 'r') as b:
            f.writelines(b.readlines())

# gmkpack binding -------------------------------------------------------------

    def gmkpack_guess_pack_name(self,
                                pack_type,
                                compiler_label=None,
                                compiler_flag=None,
                                abspath=False,
                                homepack=None,
                                to_bin=False):
        """
        Guess pack name from a number of arguments.

        :param pack_type: type of pack, among ('incr', 'main')
        :param compiler_label: gmkpack compiler label
        :param compiler_flag: gmkpack compiler flag
        :param abspath: True if the absolute path to pack is requested (instead of basename)
        :param homepack: home of pack
        :param to_bin: True if the path to binaries subdirectory is requested
        """
        IAL_git_ref = self.projects['IAL']['version']
        IAL_repo_path = self.local_project_repo('IAL')  # no need to check it has been downloaded, only useful in certain cases
        packname = GmkpackTool.guess_pack_name(IAL_git_ref, compiler_label, compiler_flag,
                                               pack_type=pack_type,
                                               IAL_repo_path=IAL_repo_path)
        # finalisation
        path_elements = [packname]
        if abspath:
            path_elements.insert(0, GmkpackTool.get_homepack())
        if to_bin:
            path_elements.append('bin')
        return os.path.join(*path_elements)

    def gmkpack_create_pack(self, pack_type,
                            compiler_label=None,
                            compiler_flag=None,
                            homepack=None,
                            rootpack=None,
                            silent=False):
        """
        Create pack according to IAL version in bundle.

        :param pack_type: type of pack, among ('incr', 'main')
        :param compiler_label: Gmkpack's compiler label to be used
        :param compiler_flag: Gmkpack's compiler flag to be used
        :param homepack: directory in which to build pack
        :param rootpack: diretory in which to look for root pack (incr packs only)
        :param silent: to hide gmkpack's stdout
        """
        # prepare IAL arguments for gmkpack
        IAL_git_ref = self.projects['IAL']['version']
        assert self.downloaded, "Bundle projects to be downloaded before creation of pack."
        IAL_repo_path = self.local_project_repo('IAL')
        args = GmkpackTool.getargs(pack_type,
                                   IAL_git_ref,
                                   IAL_repo_path,
                                   compiler_label=compiler_label,
                                   compiler_flag=compiler_flag,
                                   homepack=homepack,
                                   rootpack=rootpack)
        try:
            return GmkpackTool.create_pack_from_args(args, pack_type, silent=silent)
        except Exception:
            print("Creation of pack failed !")
            raise

    def gmkpack_populate_pack(self, pack, cleanpack=False):
        """
        Populate a pack with the contents of the bundle's projects.

        :param cleanpack: if True, call cleanpack before populating
        """
        assert isinstance(pack, Pack)
        assert self.downloaded, "Bundle projects to be downloaded before populating a pack."
        try:
            pack.bundle_populate(self, cleanpack=cleanpack)
        except Exception:
            print("Failed export of bundle to pack !")
            raise
        else:
            print("\nSucessful export of bundle: {} to pack: {}".format(self.bundle_file, pack.abspath))
        finally:
            print("-" * 50)

