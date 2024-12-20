IAL-build
=========

*Tools for Source Code Management and build of IAL code.*

This package wraps around IAL git repo management, bundling (ecbundle package) and build systems
(for now gmkpack only) to help transitioning from source code to IAL binary executables.
It provides a python package to do so, as well as a set of command-line tools.

Dependencies
------------

* `ecbundle` : https://github.com/ecmwf/ecbundle
* Some functionalities may also clone and use [IAL-bundle](https://github.com/ACCORD-NWP/IAL-bundle). If you don't have internet connection at time of use, you may have to specify a local, pre-cloned, origin repository for IAL-bundle, using env variable `DEFAULT_IALBUNDLE_REPO`, e.g. `DEFAULT_IALBUNDLE_REPO=~/repositories/IAL-bundle`

Installation
------------

* on `belenos`:

  ```
  module use ~mary/public/modulefiles
  module load ecbundle
  module load IAL-build
  ```

* at CNRM:
  - install `ecbundle`, e.g. `pip3 install --user git+https://github.com/ecmwf/ecbundle`
  - ```
    IAL_BUILD_PACKAGE=/home/common/epygram/public/IAL-build/default
    export PATH=$IAL_BUILD_PACKAGE/bin:$PATH
    export PYTHONPATH=$IAL_BUILD_PACKAGE/src:$PYTHONPATH
    ```
  
* in general:
  - install `ecbundle`, e.g. `pip3 install git+https://github.com/ecmwf/ecbundle`
  - Clone this repo, then add paths to the package:
    ```
    export PATH=<path to package>/bin:$PATH
    export PYTHONPATH=<path to package>/src:$PYTHONPATH
    ```

Documentation
-------------

(tbc) 

* cache dir
* gmkpack specificities (src/local, hub, ...)

Tools
-----

In the `bin/` directory, the `ial-*` commands can help finding bundles, create IAL branches and make packs (gmkpack) from bundles or IAL branches.
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
