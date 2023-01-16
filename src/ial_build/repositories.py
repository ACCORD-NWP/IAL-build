#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function, absolute_import, unicode_literals, division
"""
Management of repositories.
"""
import six
import subprocess
import os
import re
import sys
import io
from contextlib import contextmanager
import getpass

from .config import IAL_OFFICIAL_TAGS_re, IAL_BRANCHES_re


class GitError(Exception):
    pass


class GitProxy(object):

    re_author_in_commit = re.compile('Author: (?P<name>.+) <(?P<email>.+@.+)>$')
    re_detached_HEAD = re.compile('^\* \(HEAD detached at (?P<ref>.+)\)$')

    def __init__(self, repository='.'):
        self.repository = os.path.abspath(repository)
        assert os.path.exists(os.path.join(self.repository, '.git')), \
            "This is not a Git **repository** : {}".format(self.repository)

    @contextmanager
    def cd_repo(self):
        """Context: in self.repository"""
        owd = os.getcwd()
        try:
            os.chdir(self.repository)
            yield self.repository
        finally:
            os.chdir(owd)

    def _git_cmd(self, cmd, stderr=None, strip=True):
        """Wrapper to execute a git command."""
        out = subprocess.check_output(cmd, cwd=self.repository, stderr=stderr).decode('utf-8').split('\n')
        if strip:
            return [line.strip() for line in out if line != '']
        else:
            return out

    # Repository ---------------------------------------------------------------

    def fetch(self, ref=None, remote=None):
        """Fetch distant **remote**."""
        print("Fetch...")
        git_cmd = ['git', 'fetch']
        if remote is not None:
            git_cmd.append(remote)
            if ref is not None:
                git_cmd.append(ref)
        for out in self._git_cmd(git_cmd):
            print(out)
        print("     ...ok")

    def push(self, remote=None):
        """Push current branch to **remote**."""
        git_cmd = ['git', 'push']
        if remote is not None:
            git_cmd.append(remote)
        self._git_cmd(git_cmd)

    @property
    def currently_checkedout(self):
        """Return ref of what is currently checkedout."""
        git_cmd = ['git', 'branch']
        list_of_branches = self._git_cmd(git_cmd)
        for branch in list_of_branches:
            if branch.startswith('*'):
                m = self.re_detached_HEAD.match(branch)
                if m:
                    ref = m.group('ref')
                else:
                    ref = branch.split()[1]
                break
        return ref

    # Branch(es) ---------------------------------------------------------------

    @property
    def local_branches(self):
        """List of local branches."""
        return sorted([r['ref'] for r in self._refs_get()
                       if r['rtype'] == 'branch' and r['remote'] is None])

    def remote_branches(self, only_remote=None):
        """
        Dictionary of remote branches:
        {'remote1':[branch, ...],
         'remote2':...}
        If **only_remote**, keep only this.
        """
        remotes = {}
        for r in self._refs_get():
            if r['rtype'] == 'branch' and r['remote'] is not None:  # is a branch and not local
                if r['remote'] not in remotes:
                    remotes[r['remote']] = [r['ref']]
                else:
                    remotes[r['remote']].append(r['ref'])
        if only_remote:
            for k in list(remotes.keys()):
                if k != only_remote:
                    remotes.pop(k)
        return remotes

    def detached_branches(self, only_remote=None):
        """List remote branches as detached (remote/branch)."""
        detached = []
        for r, branches in self.remote_branches(only_remote).items():
            detached.extend([self.branch_as_detached(b, r) for b in branches])
        return detached

    def branch_as_detached(self, branch, remote=None):
        """
        Get branch as detached syntax (remote/branch).
        If **remote** is None:
          - if only one remote tracks **branch**, fine
          - if several, raise an error
        """
        if remote is not None:
            return '/'.join([remote, branch])
        else:  # recursive try on remotes
            detached = []
            for remote, branches in self.remote_branches().items():
                if branch in branches:
                    detached.append(self.branch_as_detached(branch, remote))
            if len(detached) > 1:
                msg = " ".join(["Branch '{}' has been found in more than one remote.",
                                "Need to specify remote from which to get as detached."])
                raise GitError(msg.format(branch))
            elif len(detached) == 0:
                raise GitError("Branch '{}' has been found in any remote.".format(branch))
            else:
                return detached[0]

    def current_branch_is_tracking(self, only_remote=None):
        """Return remote-tracking branch of the current branch, if existing."""
        git_cmd = ['git', 'for-each-ref', "--format=%(upstream:short)",
                   'refs/heads/' + self.currently_checkedout]
        remote_branch = self._git_cmd(git_cmd)
        if len(remote_branch) > 0:
            remote_branch = remote_branch[0]
            if only_remote not in (None, ''):
                if not remote_branch.startswith(only_remote + '/'):
                    remote_branch = None
        else:
            remote_branch = None
        return remote_branch

    def checkout_new_branch(self, branch, start_ref=None):
        """Create and checkout new branch, from current ref or **start_ref**."""
        print("Checkout new branch: '{}'".format(branch))
        git_cmd = ['git', 'checkout', '-b', branch]
        if start_ref is not None:
            git_cmd.append(start_ref)
        self._git_cmd(git_cmd)

    def pull(self, remote=None):
        """Update the local branch from remote's version."""
        print("Pull...")
        git_cmd = ['git', 'pull', '--ff-only']
        if remote is not None:
            git_cmd.append(remote)
        for out in self._git_cmd(git_cmd):
            print(out)
        print("    ...ok")

    def oldest_common_ancestor(self, refA, refB='HEAD'):
        """
        Get the oldest "diverging" common ancestor to refA and refB.

        From https://stackoverflow.com/questions/1527234/finding-a-branch-point-with-git

        diff -u <(git rev-list --first-parent topic) \
                     <(git rev-list --first-parent master) | \
                          sed -ne 's/^ //p' | head -1
        """
        from ial_build import package_rootdir
        return subprocess.check_output([os.path.join(package_rootdir, 'bin', 'git-oldest_common_ancestor'),
                                        refA,
                                        refB],
                                       cwd=self.repository).decode('utf-8').strip()

    # Ref(s) -------------------------------------------------------------------

    def _refs_get(self):
        git_cmd = ['git', 'show-ref']
        list_of_refs = [ref.split() for ref in self._git_cmd(git_cmd)]
        refs = []
        for h, r in list_of_refs:
            if r.startswith('refs/remotes'):
                if r.endswith('/HEAD'):
                    refs.append({'ref':r.split('/')[3],
                                 'hash':h,
                                 'rtype':'HEAD',
                                 'remote':r.split('/')[2]})
                else:
                    refs.append({'ref':r.split('/')[3],
                                 'hash':h,
                                 'rtype':'branch',
                                 'remote':r.split('/')[2]})
            elif r.startswith('refs/heads'):
                refs.append({'ref':r.split('/')[2],
                             'hash':h,
                             'rtype':'branch',
                             'remote':None})
            elif r.startswith('refs/tags'):
                refs.append({'ref':r.split('/')[2],
                             'hash':h,
                             'rtype':'tag',
                             'remote':None})
        return refs

    def ref_exists(self, ref):
        """Check whether a ref (tag, branch, commit) exists."""
        return (ref == 'HEAD' or
                self.ref_is_tag(ref) or
                self.ref_is_branch(ref) or
                self.commit_exists(ref))

    def ref_is_tag(self, ref):
        """Check whether reference is tag."""
        return ref in self.tags

    def ref_is_branch(self, ref):
        """Check whether reference is branch."""
        return (ref in self.local_branches or
                any([ref in remote for remote in self.remote_branches().values()]) or
                ref in self.detached_branches())

    def refs_common_ancestor(self, ref1, ref2):
        """Common ancestor commit between 2 references (commits, branches, tags)."""
        git_cmd = ['git', 'merge-base', ref1, ref2]
        commit = self._git_cmd(git_cmd)[0]
        return commit

    def ref_checkout(self, ref):
        """Checkout existing reference (commit, branch, tag)."""
        print("Checkout: '{}' ...".format(ref))
        git_cmd = ['git', 'checkout', ref]
        self._git_cmd(git_cmd)

    # Tag(s) -------------------------------------------------------------------

    @property
    def tags(self):
        """Return list of tags."""
        return sorted([r['ref'] for r in self._refs_get()
                       if r['rtype'] == 'tag'])

    def tag_points_to(self, tag):
        """Return the associated commit to **tag**."""
        assert self.ref_exists(tag)
        git_cmd = ['git', 'rev-list', '-n', '1', tag]
        commit = self._git_cmd(git_cmd)[0]
        return commit

    def tags_between(self, start_ref=None, end_ref='HEAD'):
        """Get the list of tags between 2 references (commits, branches, tags)."""
        if start_ref is None and end_ref:
            refs = end_ref
        else:
            refs = '{}...{}'.format(start_ref, end_ref)
        git_cmd = ['git', 'log', refs,
                   '--decorate', '--simplify-by-decoration']
        _re = re.compile('commit .+ \((.+)\)$')
        cmd_out = self._git_cmd(git_cmd)
        list_of_tagged_commits = [line for line in cmd_out if _re.match(line)]
        list_of_tags = [_re.match(line).group(1).split(', ') for line in list_of_tagged_commits]
        list_of_tags = [[ref[4:].strip() for ref in line if ref.startswith('tag:')]
                        for line in list_of_tags]
        return list_of_tags[::-1]

    def tags_history(self, ref='HEAD'):
        return self.tags_between(None, ref)

    # Commit(s) ----------------------------------------------------------------

    def commit_exists(self, commit):
        """Check whether commit is existing."""
        git_cmd = ['git', 'rev-parse', '--verify', commit + '^{commit}']
        try:
            self._git_cmd(git_cmd, stderr=subprocess.STDOUT)
            return True
        except subprocess.CalledProcessError:
            return False

    def commit(self, message, add=False):
        """
        Commit the staged modifications.

        :param message: commit message
        :param add: add locally modified files to stage before committing
        """
        git_cmd = ['git', 'commit', '-m', message]
        if add:
            git_cmd.append('-a')
        self._git_cmd(git_cmd)

    @property
    def latest_commit(self):
        """Latest commit in current history."""
        git_cmd = ['git', 'rev-parse', 'HEAD']
        return self._git_cmd(git_cmd)[0]

    @property
    def latest_commit_author(self):
        """Author/email of latest commit."""
        commit = self.log(['-1'])
        for l in commit:
            m = self.re_author_in_commit.match(l)
            if m:
                return m.groupdict()

    def parents(self, ref):
        """Get parent commit(s) of given ref."""
        parents = self._git_cmd(['git', 'rev-list', '--parents', '-n', '1', ref])[0].split()[1:]
        assert len(parents) in (1, 2), "Commit should have 1 or 2 parents only."
        return parents

    # Content ------------------------------------------------------------------

    def log(self, log_args=[], out=None):
        """
        Call `git log`.

        :param out: can be sys.stdout or an open file handle.
        """
        git_cmd = ['git', 'log'] + log_args
        log = self._git_cmd(git_cmd)
        if out is not None:
            out.write('-' * 50 + '\n')
            for l in log:
                out.write(l + '\n')
            out.write('-' * 50 + '\n')
        return log

    def touched_between(self, start_ref, end_ref):
        """
        Return the lists of Added, Modified, Deleted, Renamed (etc...) files
        between 2 references (commits, branches, tags).
        """
        assert self.ref_exists(start_ref)
        assert self.ref_exists(end_ref)
        git_cmd = ['git', 'diff', '--name-status', start_ref, end_ref]
        asdict = {'A':set(), 'R':set(), 'M':set(), 'C':set(), 'T':set(),
                  'D':set(),
                  'U':set(), 'X':set(), 'B':set()}
        touched = self._git_cmd(git_cmd)
        for line in touched:
            if line[0] in ('A', 'M', 'T', 'D'):
                asdict[line[0]].add(line[2:].strip())
            elif line[0] in ('C', 'R'):
                asdict[line[0]].add(tuple(line.split()[1:3]))  # syntax: R file1 file2
            else:
                asdict[line[0]].add(line)  # FIXME: don't know how to interpret this
        for k in list(asdict.keys()):
            if len(asdict[k]) == 0:
                asdict.pop(k)
        return asdict

    @property
    def touched_since_last_commit(self):
        """
        Return the lists of Added, Modified, Deleted, Renamed (etc...) files
        since last commit.
        """
        git_cmd = ['git', 'status', '-s', '--porcelain']
        touched = self._git_cmd(git_cmd)
        asdict = {'A':set(), 'R':set(), 'M':set(), 'C':set(), 'T':set(),
                  'D':set(),
                  'U':set(), 'X':set(), 'B':set()}
        for line in touched:
            line = line.replace('??', 'A')
            if line[0] in ('A', 'M', 'T', 'D'):
                asdict[line[0]].add(line[2:].strip())
            elif line[0] in ('C', 'R'):
                asdict[line[0]].add(tuple(line.split()[1::2]))  # syntax: R99 file1 -> file2
            else:
                asdict[line[0]].add(line)  # FIXME: don't know how to interpret this
        for k in list(asdict.keys()):
            if len(asdict[k]) == 0:
                asdict.pop(k)
        return asdict

    def touched_files_since(self, ref):
        """Lists touched files since **ref** (commit or tag), including uncommited."""
        uncommitted = self.touched_since_last_commit
        touched = self.touched_between(ref, 'HEAD')
        for k in uncommitted.keys():
            if k in touched:
                touched[k].update(uncommitted[k])
            else:
                touched[k] = uncommitted[k]
        return touched

    def preview_merge(self, contrib_ref, target_ref, common_ancestor=None):
        """
        Preview a merge potential conflicts.

        :param contrib_ref: reference (branch name) of the contribution to be merged
        :param target_ref: reference (tag, branch) of the target branch in which to merge the contribution
        :param common_ancestor: common ancestor to the *contribution* branch
            and the *target* branch.
        """
        if common_ancestor is None:
            common_ancestor = self.refs_common_ancestor(contrib_ref, target_ref)
            print('Auto-determined common ancestor: {}'.format(common_ancestor))
        touched_in_contrib = self.touched_between(common_ancestor, contrib_ref)
        touched_in_target = self.touched_between(common_ancestor, target_ref)
        potential_conflicts = {'{}/{}'.format(kc, kt):[]
                               for kc in touched_in_contrib.keys()
                               for kt in touched_in_target.keys()}
        for kc in touched_in_contrib.keys():
            for kt in touched_in_target.keys():
                conflict_key = '{}/{}'.format(kc, kt)
                if kc in ('A', 'M', 'T', 'D') and kt in ('A', 'M', 'T', 'D'):
                    for f in touched_in_contrib[kc]:
                        if f in touched_in_target[kt]:
                            potential_conflicts[conflict_key].append(f)
                elif kc in ('A', 'M', 'T', 'D') and kt in ('C', 'R'):
                    for fc in touched_in_contrib[kc]:
                        for ft in touched_in_target[kt]:
                            if fc in ft:
                                potential_conflicts[conflict_key].append((fc, ft))
                elif kc in ('C', 'R') and kt in ('A', 'M', 'T', 'D'):
                    for fc in touched_in_contrib[kc]:
                        if fc[0] in touched_in_target or fc[0] in touched_in_target:
                            potential_conflicts[conflict_key].append((fc, ft))
                elif kc in ('C', 'R') and kt in ('C', 'R'):
                    for fc in touched_in_contrib[kc]:
                        for ft in touched_in_target[kt]:
                            if not set(fc).isdisjoint(set(ft)):
                                potential_conflicts[conflict_key].append((fc, ft))
        for k in list(potential_conflicts.keys()):
            if len(potential_conflicts[k]) == 0:
                potential_conflicts.pop(k)
            else:
                potential_conflicts[k] = sorted(potential_conflicts[k])
        return potential_conflicts

    def stage(self, filenames):
        """
        Add file(s) to stage.

        :param filenames: either a filename or a list of
        """
        if isinstance(filenames, six.string_types):
            filenames = [filenames,]
        for f in filenames:
            git_cmd = ['git', 'add', f]
            self._git_cmd(git_cmd)

    def delete_file(self, filename):
        """Delete a file from git."""
        git_cmd = ['git', 'rm', filename]
        self._git_cmd(git_cmd)

    @property
    def is_clean(self):
        """
        Tell if there are uncommited changes (working, staged) in the current
        state of the working directory.
        """
        git_cmd = ['git', 'status', '--porcelain']
        status = self._git_cmd(git_cmd)
        return len(status) == 0

    def extract_file_from_to(self, git_ref, filepath,
                             destination=None,
                             overwrite=False):
        """
        Extract **filepath** from **git_ref** to a **destination** file, potentially outside the repo.

        :param overwrite: to allow overwriting of existing target file
        """
        git_cmd = ['git', 'show', '{}:{}'.format(git_ref, filepath)]
        f = self._git_cmd(git_cmd, strip=False)
        if destination is None:
            destination = tempfile.mkstemp()
        if os.path.exists(destination) and not overwrite:
            raise IOError("File '{}' already exists".format(destination))
        with io.open(destination, 'w') as out:
            out.writelines([l + '\n' for l in f])
        return destination


class IALview(object):
    """Utilities around IAL repository."""
    _re_official_tags = IAL_OFFICIAL_TAGS_re
    _re_branches = IAL_BRANCHES_re

    def __init__(self, repository,
                 ref=None,
                 need_for_checkout=True,
                 remote='origin',
                 new_branch=False,
                 start_ref=None,
                 register_in_GCOdb=False,
                 fetch=False):
        """
        Hold **ref** from **repository**. If **ref** is None, takes the currently checked out ref.

        :param need_for_checkout: if False, do not checkout **ref** when initializing.
                                  WARNING: this is hazardous, a number of methods may not work !
                                  Better know what you are doing !
        :param remote: fetch ref from a remote
        :param new_branch: if the **ref** is a new branch to be created
        :param start_ref: start reference, in case a new branch to be created
        :param register_in_GCOdb: register branch in GCO database.
        :param fetch: to fetch branch on remote or not
        """
        self.repository = os.path.abspath(repository)
        self.git_proxy = GitProxy(self.repository)
        if ref is None:
            ref = self.git_proxy.currently_checkedout
        self.ref = ref
        if fetch:
            self.git_proxy.fetch(remote=remote,
                                 ref=ref if remote is not None else None)
        # initial state (to get back at the end)
        self.initial_checkedout = self.git_proxy.currently_checkedout
        # determine if need to checkout
        if need_for_checkout:
            if self.git_proxy.ref_exists(ref):
                assert not new_branch, "ref: {} already exists, while **new_branch** is True.".format(ref)
                if self.git_proxy.ref_is_branch(ref):
                    need_for_checkout = (self.initial_checkedout != ref)
                elif self.git_proxy.ref_is_tag(ref):
                    if self.git_proxy.tag_points_to(ref) == self.git_proxy.latest_commit and self.git_proxy.is_clean:
                        # ref is a tag, HEAD points on same commit and working copy is clean
                        need_for_checkout = False
                elif ref == 'HEAD':
                    need_for_checkout = False
                else:  # regular commit
                    if self.git_proxy.latest_commit == ref:
                        need_for_checkout = False
            else:
                assert new_branch, ("ref:'{}' does not exist in repository:'{}'; ".format(ref, self.repository) +
                                    "cannot checkout unless **new_branch**.")
        # actual checkout if needed
        if need_for_checkout:
            # need to switch branch
            assert self.git_proxy.is_clean, \
                    "Repository: {} : working directory is not clean. Reset or commit changes manually.".format(self.repository)
            if new_branch:
                assert start_ref is not None
                self.git_proxy.checkout_new_branch(ref, start_ref)
                if register_in_GCOdb:
                    start_commit = self.git_proxy.tag_points_to(start_ref)
                    self.GCOdb_register(start_commit)
            else:
                if self.git_proxy.ref_is_branch(ref) and ref in self.git_proxy.detached_branches():
                    #raise NotImplementedError("Checking out detached branch")
                    self.git_proxy.ref_checkout(ref)
                elif self.git_proxy.ref_is_branch(ref) and ref not in self.git_proxy.local_branches:
                    # remote branch: need to checkout as new local branch
                    tracked = self.git_proxy.branch_as_detached(ref, remote)
                    print("Branch '{}' to be tracked as new branch from '{}'".format(ref, tracked))
                    self.git_proxy.checkout_new_branch(ref, tracked)
                else:
                    self.git_proxy.ref_checkout(ref)

    def __del__(self):
        try:
            if self.initial_checkedout not in (self.git_proxy.latest_commit, self.git_proxy.currently_checkedout):
                # need to checkout back
                if self.git_proxy.is_clean:
                    self.git_proxy.ref_checkout(self.initial_checkedout)
                else:
                    print("! Warning ! Working directory is not clean at time of quiting the branch. Reset or commit changes manually.")
                    print("(Unable to go back to previously checkedout state : {})".format(self.initial_checkedout))
        except Exception:
            pass

    def info(self, out=sys.stdout):
        """Write info about the view."""
        info = ["-" * 50,
                "*** View of ref: '{}' ***".format(self.ref),
                self.git_proxy.log(['-1', '--decorate'])[0],
                "Latest official tagged ancestor: " + self.latest_official_tagged_ancestor,
                ]
        touched_since_last_commit = self.git_proxy.touched_since_last_commit
        if len(touched_since_last_commit) > 0:
            info.extend(["Latest commit: " + self.git_proxy.latest_commit,
                         "Since last commit: "])
            for m, files in touched_since_last_commit.items():
                info.append("  {}:".format(m))
                info.extend(["    " + str(f) for f in files])
        else:
            info.append("Commit: " + self.git_proxy.latest_commit)
        info.append("-" * 50)
        for line in info:
            out.write(line + '\n')

    def new_branch_classical_nomenclature(self, branch_radical):
        """Return a GCO-classically formatted branch name, based on current HEAD."""
        return '{}_{}_{}'.format(getpass.getuser(), self.latest_main_release_ancestor, branch_radical)

    @property
    def is_current_ref_IAL_conventional(self):
        return self.is_ref_IAL_conventional(self.ref)

    @classmethod
    def is_ref_IAL_conventional(self, git_ref):
        tag = cls._re_official_tags.match(git_ref)
        branch = cls._re_branches.match(git_ref)
        match = tag if tag else branch
        return match is not None

    @property
    def self_ref_split(self):
        return self.split_ref(self.ref)

    @classmethod
    def split_ref(cls, git_ref):
        """
        Split the parts in the ref name, e.g.:

        - for a branch named 'mary_CY47T1_dev', return {'user':'mary', 'release':'47T1', 'radical':'dev'}
        - for a tag named 'CY47_t1.04', return {'release':'47', 'radical':'t1', 'version':'04'}
        - for a tag named 'CY47T1', return {'release':'47T1'}

        (the returned dict is always complete, with None for non-relevant parts)
        """
        split = {'user':None, 'radical':None, 'version':None}
        tag = cls._re_official_tags.match(git_ref)
        branch = cls._re_branches.match(git_ref)
        match = tag if tag else branch
        if match:
            split.update(match.groupdict())
            return split
        else:
            raise SyntaxError(" ".join(["Cannot recognize parts in git ref,",
                                        "which syntax must look like one of",
                                        "mary_CY47T1_dev (branch), CY47T1_r1.04 (tag), CY47T1 (tag)"]))

    def GCOdb_register(self, start_commit=None):  # TODO: delete
        """
        DEPRECATED !
        Register branch in GCO database (proxy to 'git_branch -q -a').
        """
        cmd = ['git_branch', '-q', '-a']
        if start_commit is not None:
            cmd.append(start_commit)
        else:
            start_commit = '?'
        print("Register branch: '{}' in GCO database, with base commit: '{}'".format(self.git_proxy.current_branch, start_commit))
        subprocess.check_call(cmd, cwd=self.git_proxy.repository)

    # History ------------------------------------------------------------------

    @property
    def tags_history(self):
        """Tags in chronological order in history of git_ref."""
        history = []
        for t in self.git_proxy.tags_history(self.ref):
            history.extend(t)
        return history

    @property
    def official_tagged_ancestors(self):
        """All official tagged ancestors."""
        official_tags = []
        for tags in self.git_proxy.tags_between('CY38', 'HEAD'):  # CY38 is the first one under Git
            for tag in tags[::-1]:  # The latest is a priori the first one
                if self._re_official_tags.match(tag):
                    official_tags.append(tag)
        return official_tags

    @property
    def latest_tagged_ancestor(self):
        """Latest tagged ancestor."""
        tags = self.git_proxy.tags_between('CY38', 'HEAD')[-1]  # CY38 is the first one under Git
        return tags[0]

    @property
    def latest_main_release_ancestor(self):
        """Latest main release which is ancestor to the branch."""
        for tag in self.official_tagged_ancestors[::-1]:  # start from latest one
            if self._re_official_tags.match(tag).group('radical') is None:  # is it a main release
                return tag

    @property
    def latest_official_tagged_ancestor(self):
        """Latest official tagged ancestor."""
        return self.official_tagged_ancestors[-1]

    @property
    def latest_official_branch_from_main_release(self):
        """
        Get information on the latest official branch between main release and
        current branch, if any.
        """
        latest_official_tagged_ancestor = self.official_tagged_ancestors[-1]
        return self._re_official_tags.match(latest_official_tagged_ancestor).groupdict()

    # Content ------------------------------------------------------------------
    def touched_files_since(self, ref):
        """Lists touched files since **ref** (commit or tag)."""
        return self.git_proxy.touched_files_since(ref)

    @property
    def touched_files_since_latest_tagged_ancestor(self):
        """Lists touched files since *self.latest_tagged_ancestor*."""
        return self.touched_files_since(self.latest_tagged_ancestors)

    @property
    def touched_files_since_latest_official_tagged_ancestor(self):
        """Lists touched files since *self.latest_official_tagged_ancestor*."""
        return self.touched_files_since(self.latest_official_tagged_ancestor)

    def prep_doc(self,
                 metadata,
                 outdir=None,
                 from_start_ref=None,
                 from_oldest_common_ancestor_with=None):
        """
        Pre-fill branch doc template.

        :param outdir: output directory for the doc file
        :param from_start_ref: starting reference to collect branch deltas. Mutually exclusive with the next arg.
        :param from_oldest_common_ancestor_with: consider branch from the oldest common ancestor with the given branch.
            Typically, integration branch. Mutually exclusive with the former arg.

        **metadata** is expected to be a dict(
            numerical_impact=... : None, False or '' if bit-repro; otherwise a str describing scope and magnitude
                of numerical impact [mandatory]
            authors=... : a str naming authors of contribution
            oneline_doc=... : a str describing the purpose of the branch in one line, for the summary table [mandatory]
            fulldoc=... : a str of list of str, detailed documentation of the branch
            config_adaptations=... : a str of list of str, description of the required config (namelist, param file...)
                adaptations
        """
        from ial_build import package_rootdir
        template_file = os.path.join(package_rootdir, 'templates', 'contribution_documentation.tex')
        with io.open(template_file, 'r') as t:
            template = [l.strip() for l in t.readlines()]
        # Ref
        if from_start_ref == from_oldest_common_ancestor_with == None:
            raise ValueError("One of ('from_oldest_common_ancestor_with', 'from_start_ref') must be provided.")
        elif None not in (from_oldest_common_ancestor_with, from_start_ref):
            raise ValueError("Only one of ('from_oldest_common_ancestor_with', 'from_start_ref') can be provided.")
        elif from_start_ref is None:
            # find oldest common ancestor with integration branch
            if self.git_proxy.ref_is_tag(self.ref):
                ref = self.git_proxy.tag_points_to(self.ref)  # get actual commit
            elif self.git_proxy.ref_is_branch(self.ref):
                ref = self.git_proxy.latest_commit  # get HEAD commit of branch
            else:  # actual commit
                ref = self.ref
            start_ref = self.git_proxy.oldest_common_ancestor(from_oldest_common_ancestor_with, ref)
            commit_len = min(len(ref), len(start_ref))
            if ref[:commit_len] == start_ref[:commit_len]:
                # commit is straightforward in branch (not merged), then:
                if self.git_proxy.ref_is_branch(self.ref):
                    # there is no way of guessing the start_ref
                    raise ValueError("No way of guessing the start reference of a firstly-integrated branch; " +
                                     "please provide explicit start ref.")
                else:  # individual commit (or tag)
                    # start_ref is direct parent
                    parents = self.git_proxy.parents(self.ref)
                    if len(parents) == 1:
                        start_ref = parents[0]
                    elif len(parents) == 2:
                        raise ValueError("This ref ({}) is a merge commit; ".format(self.ref) +
                                         "documenting can be requested for branches or individual commits only.")
            start_ref = start_ref[:10]
        elif from_oldest_common_ancestor_with is None:
            # consider branch explicitly from provided start_ref
            start_ref = from_start_ref
        if self.git_proxy.ref_is_tag(start_ref):
            start_ref_to_print = '{} ({})'.format(start_ref, self.git_proxy.tag_points_to(start_ref))
        else:
            start_ref_to_print = start_ref
        print("Start ref:", start_ref_to_print)
        # Set branch
        for i, line in enumerate(template):
            template[i] = line
        # Repro/impact
        repro_symbol = {True:'$\checkmark$', False:'$\\neq$'}
        repro_word = {True:'YES', False:'NO'}
        if metadata['numerical_impact'] in ('', 'None', 'False', None, False):
            numerical_impact = ''
        else:
            numerical_impact = '\\noindent ' + metadata['numerical_impact']
        repro = numerical_impact == ''
        # Authors
        authors = metadata.get('authors', self.git_proxy.latest_commit_author['name'])
        # Replace
        def replace_in_line(i, key, replacement):
            if key in template[i]:
                template[i] = template[i].replace(key, replacement)

        for i, line in enumerate(template):
            replace_in_line(i, '__branch_protected_underscores__', self.ref.replace('_', '\_').replace('%', '\%'))  # FIXME:
            replace_in_line(i, '__branch__', self.ref.replace('%', '_'))  # FIXME:
            replace_in_line(i, '__start_ref__', start_ref_to_print.replace('_', '\_'))
            replace_in_line(i, '__repro_symbol__', repro_symbol[repro])
            replace_in_line(i, '__repro_word__', repro_word[repro])
            replace_in_line(i, '__numerical_impact__', numerical_impact)
            replace_in_line(i, '__oneline_doc__', metadata['oneline_doc'])
            replace_in_line(i, '__authors__', authors)
        # Set contents
        touched = self.touched_files_since(start_ref)
        contents = []
        for k, files in touched.items():
            for f in files:
                contents.append('{}    {}'.format(k, f))
        index0 = template.index('__as returned by: git diff --name-status__')
        del template[index0]
        for f in sorted(contents, reverse=True):
            template.insert(index0, f)
        # Documentation
        index0 = template.index('__fulldoc__')
        del template[index0]
        for f in metadata.get('fulldoc', ['---'])[::-1]:
            template.insert(index0, f)
        # Config adaptations
        index0 = template.index('__config_adaptations__')
        del template[index0]
        for f in metadata.get('config_adaptations', ['---'])[::-1]:
            template.insert(index0, f)
        # Commits
        commits = self.git_proxy.log(['{}...{}'.format(start_ref, 'HEAD'), '--oneline'])
        index0 = template.index('__commits__')
        del template[index0]
        for f in commits[::-1]:
            template.insert(index0, f)
        # Output
        if outdir is None:
            outdir = ial_build.config.IAL_DOC_OUTPUT_DIR
        if not os.path.exists(outdir):
            os.makedirs(outdir)
        outfile = self.ref.replace('/', ':').replace('%', '_') + '.tex'
        print("Output filename: {}".format(outfile))
        outfile = os.path.join(outdir, outfile)
        with io.open(outfile, 'w') as out:
            out.writelines([l + '\n' for l in template])
        print("Output written in: {}".format(outfile))
