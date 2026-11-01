# EEA Main Website backend (Plone 6)

Plone 6 backend for EEA Main website. See also [Plone 6 frontend for EEA Main website](https://github.com/eea/eea-website-frontend)

## Documentation

Trainings on how to create your own website using Plone 6 is available as part of the Plone training at [https://training.plone.org](https://training.plone.org).


## Pre-requirements

* Python **3.10, 3.11**
* Python **python-venv** and **python-dev**
* Libraries
  - **libz**
  - **libjpeg**
  - **readline**
  - **libexpat**
  - **libssl** or **openssl**
  - **libxml2**
  - **libxslt**

### Ubuntu / Debian / Windows Bash

**Note** If you already have a higher version of python on your system, replace **python3.11** with your installed version bellow

    apt update
    apt install python3.11-venv python3.11-dev libpq-dev libldap2-dev libsasl2-dev git make gcc

Optionally set default `python3`:

    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

### Mac OS

    brew install zlib git readline jpeg libpng libyaml postgresql


## Install

In order to develop Plone 6 backend add-ons run:

    git clone https://github.com/eea/eea-website-backend.git
    cd eea-website-backend/develop
    make
    make start

The virtual environment is created in `.venv`:

    source .venv/bin/activate

To use other **Python** version run make with `-e` parameter:

    make -e PYTHON=python3.10
    make start

### Docker Sandbox (sbx)

Inside a Docker Sandbox run `make sandbox` once per new sandbox instead of `make`:

    make sandbox

It installs the native build dependencies Plone needs (libpq, libldap, libxml2, libjpeg ...),
installs Python 3.12 with `uv` (the sandbox ships a newer Python than Plone 6.1 supports) and
then runs `make all`. The Makefile detects the sandbox (`SANDBOX_NAME`/`WORKSPACE_DIR`) and
builds the environment in `.venv-sbx`, so the host `.venv` in the same bind-mounted directory
keeps working.

The sandbox network policy blocks `dist.plone.org`; allow it once on the host:

    sbx policy allow network dist.plone.org


## Develop

Add your addons to `develop/source.ini` and run:

    make develop

We recommend using [Visual Studio Code](https://code.visualstudio.com/) Editor
* Extensions:
  * [Remote Development](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.vscode-remote-extensionpack) - Windows only
  * [Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)
* Open Visual Studio Code and click **File > Open Folder**
* Browser your computer and select **eea-website-backend > develop**
* Within the **Explorer** open `develop > sources > eea.kitkat > eea > kitkat > interfaces.py` and type
  `from zope.component import query`. If you get the auto-complete options, you're done.
* Happy hacking!

**Note** `Hot reload` is not available for Plone backend development, thus you'll have to **restart** Plone after you edit Python code. Still, there are options to reload your changes without restarting Plone, by using `plone.reload` and `dm.plonepatches.reload`. Go to http://localhost:8080/@@reload `admin:admin`

See also: [Debugging Plone in Visual Studio Code](https://community.plone.org/t/our-pip-based-development-workflow-for-plone/14562#debugging-plone-in-visual-studio-code-11)

### Useful Visual Studio Code shortcuts

**Note** Replace `Ctrl` with `Cmd` key on MacOS

* **Ctrl+Shift+P** Trim Trailing Whitespace
* **Ctrl+Shift+P** Sort imports
* **Ctrl+click** on a `class / import` to go to definition


## Testing

You can manually run test in terminal, like:

    .venv/bin/zope-testrunner --test-path sources/eea.kitkat

Or via `Visual Studio Code`
* Go to `Run > Start Debugging (F5)` and select `Test Plone` debugger.
* You will need to add the add-ons you want to test to `.vscode/launch.json`, e.g.: `--test-path=sources/eea.banner`


## Cleanup

If you want to cleanup your development environment and start from scratch just remove the `develop` folder and re-run all steps from the [Install](#install) section:

    rm -rf ./develop
    git checkout ./develop
    git pull


## Copyright and license

The Initial Owner of the Original Code is European Environment Agency (EEA).
All Rights Reserved.

See [LICENSE.md](https://github.com/eea/eea-website-backend/blob/master/LICENSE.md) for details.

## Funding

[European Environment Agency (EU)](http://eea.europa.eu)
