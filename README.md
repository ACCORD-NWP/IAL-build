IAL-build
=========

*Tools for Source Code Management and build of IAL code.*

This package wraps around IAL git repo management, bundling (ecbundle package) and build systems
(for now gmkpack only) to help transitioning from source code to IAL binary executables.
It provides a python package to do so, as well as a set of command-line tools.

Dependencies
------------

* `ecbundle` : https://github.com/ecmwf/ecbundle --- (quick install: `pip3 install --user git+https://github.com/ecmwf/ecbundle`)
* Some functionalities may also clone and use [IAL-bundle](https://github.com/ACCORD-NWP/IAL-bundle), especially for the research of "official" bundles for main cycles. If you don't have internet connection at time of use, you may have to specify a local, pre-cloned, origin repository for IAL-bundle, using env variable `DEFAULT_IALBUNDLE_REPO`, e.g. `DEFAULT_IALBUNDLE_REPO=~/repositories/IAL-bundle`, or specifying it using command-line options, cf. help with option `-h`.

Installation
------------

`pip install ial-build`

Documentation
-------------

**Cache directory**:

  When using a bundle (and `ecbundle`), the repositories are cloned/downloaded in a sort of cache directory, so as to speed-up the next use: only a fetch of the requested branch or git reference will be done.
  The requested git reference is then checkedout in this cache repository, before being copied/cloned into the pack (in the case of gmkpack).

Tools
-----

When installed with `pip`, a bunch of `ial-*` commands are available in order to :
* help finding bundles (`ial-find_bundle`, `ial-get_bundle`)
* make packs (gmkpack) from bundles or IAL branches (`ial-git2pack`, `ial-bundle2pack`).
They are auto-documented, see their argument `-h`.

Some examples:

### Prepare a bundle for a personal branch

* Find a bundle appropriate for my IAL branch <my_branch>, based on CY50:
  ```
  % ial-find_bundle my_branch
  BDL50-default
  ```

* Get this bundle:
  ```
  % ial-get_bundle BDL50-default [-t my_bundle.yml]
  ```

* Edit and replace `CY50` in `my_bundle.yml`

* Create a root pack from my bundle:
  ```
  % ial-bundle2pack my_bundle.yml [...pack creation arguments, cf. -h]
  ```

### Install a root pack of `BDL50-default`

```
ial-bundle2pack BDL50-default
```
will:
* look for a bundle tagged `BDL50-default` in the [IAL-bundle](https://github.com/ACCORD-NWP/IAL-bundle) repository,
* download it
* clone/fetch/checkout each package referenced in the bundle in the requested version, in a cache local directory (cf. option `-d`)
* create a pack (by default: main)
* populate the pack with the source codes checkedout for each package

### Install a root(=main) pack for the recommended (default) bundle for CY50

```
ial-git2pack -t main CY50 [...]
```
will:
* find a bundle appropriate for CY50 in IAL-bundle repository
* then do the same as `ial-bundle2pack`

### Install an incremental pack with the content of my IAL branch on top of its most recent official ancestor pack
```
ial-git2pack my_branch
```

### Install a pack with a modified branch in `oops` only

1. get a local copy of a bundle file that fits the basis of your development, e.g.
  ```
  ial-find_bundle --get_copy CY50
  ```
2. rename and edit your bundle file, setting your (potentially local) oops repository and branch
3. in the bundle file still, set attribute `incremental_pack` of the `oops_src` project to `True`
4. create your pack using
   ```
   ial-bundle2pack <my_bundle.yml> -t incr
   ```
