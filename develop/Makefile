##############################################################################
# Run:
#    make
#    make start
#
# Go to:
#
#     http://localhost:8080
#
# Create a new Plone Site (admin:admin)
#
##############################################################################
# SETUP MAKE
#
## Defensive settings for make: https://tech.davis-hansson.com/p/make/
SHELL:=bash
.ONESHELL:
# for Makefile debugging purposes add -x to the .SHELLFLAGS
.SHELLFLAGS:=-eu -o pipefail -O inherit_errexit -c
.SILENT:
.DELETE_ON_ERROR:
MAKEFLAGS+=--warn-undefined-variables
MAKEFLAGS+=--no-builtin-rules

# Colors
# OK=Green, warn=yellow, error=red
ifeq ($(TERM),)
# no colors if not in terminal
	MARK_COLOR=
	OK_COLOR=
	WARN_COLOR=
	ERROR_COLOR=
	NO_COLOR=
else
	MARK_COLOR=`tput setaf 6`
	OK_COLOR=`tput setaf 2`
	WARN_COLOR=`tput setaf 3`
	ERROR_COLOR=`tput setaf 1`
	NO_COLOR=`tput sgr0`
endif

##############################################################################
# SETTINGS AND VARIABLE

PLONE_VERSION=6.1.5
#`docker run -i --rm eeacms/plone-backend env | grep PLONE_VERSION | sed "s/PLONE_VERSION=//g"`
PYTHON?=python3.12

# The environment lives in .venv, not in this directory. sbx bind-mounts the workspace at
# the same path as on the host but runs a different OS, so a venv created on the host can't
# be used in the sandbox: sbx exports SANDBOX_NAME and WORKSPACE_DIR, and the sandbox gets
# its own .venv-sbx next to it.
SANDBOX_NAME?=
WORKSPACE_DIR?=
IN_SANDBOX:=$(if $(or $(SANDBOX_NAME),$(WORKSPACE_DIR)),1,)
VENV?=$(if $(IN_SANDBOX),.venv-sbx,.venv)

# Native build dependencies for Plone, from plone/container-backend Dockerfile.builder,
# mapped to Ubuntu 26.04 names: libjpeg62-turbo-dev -> libjpeg-turbo8-dev,
# libpcre3-dev -> libpcre2-dev, libmagic1 -> libmagic1t64 (+ -dev for magic.h),
# libtiff5-dev/libtiff6 -> libtiff-dev. gosu/busybox belong to the Plone image
# entrypoint and are not needed for development.
SANDBOX_DEPS=build-essential pkg-config libbz2-dev libffi-dev libjpeg-turbo8-dev \
	libmagic1t64 libmagic-dev libsasl2-dev libldap2-dev libopenjp2-7-dev \
	libpcre2-dev libpq-dev libssl-dev libtiff-dev libxml2-dev libxslt1-dev zlib1g-dev

# Top-level targets
.PHONY: all
all: bootstrap install develop

.PHONY: sandbox
sandbox:		## Prepare an sbx sandbox (build deps + Python 3.12 + make all)
	if [ -z "$(IN_SANDBOX)" ]; then \
		echo "Not an sbx sandbox: SANDBOX_NAME/WORKSPACE_DIR are unset, nothing to do."; \
		echo "On the host follow the Pre-requirements in README.md instead."; \
		exit 0; \
	fi; \
	sudo apt-get update; \
	sudo apt-get install -y --no-install-recommends $(SANDBOX_DEPS); \
	pkg-config --exists libxml-2.0 libxslt zlib libjpeg libtiff-4 libopenjp2 libpq openssl libffi libsasl2 libpcre2-8 libmagic; \
	test -f /usr/include/ldap.h; \
	if ! curl -fsS -o /dev/null https://dist.plone.org/release/$(PLONE_VERSION)/constraints.txt; then \
		echo "dist.plone.org is blocked by the sandbox network policy."; \
		echo "Run this once on the host, then retry: sbx policy allow network dist.plone.org"; \
		exit 1; \
	fi; \
	uv python install 3.12; \
	$(MAKE) PYTHON="$$(uv python find 3.12)" all

.PHONY: clean
clean:			## Cleanup environment
	rm -rf "$(VENV)"
	rm -rf bin include lib lib64 share inituser pyvenv.cfg
	rm -rf *.egg-info node_modules

.PHONY: bootstrap
bootstrap:		## Bootstrap python environment
	$(PYTHON) -m venv $(VENV)
	rm -f plone-constraints.txt.tmp
	curl -fsSL -o plone-constraints.txt.tmp https://dist.plone.org/release/$(PLONE_VERSION)/constraints.txt
	mv plone-constraints.txt.tmp plone-constraints.txt
	$(VENV)/bin/pip install --upgrade pip mxdev plonecli pylint black ruff -c plone-constraints.txt

.PHONY: install
install:		## Install Plone and develop add-ons
	$(VENV)/bin/pip install Plone plone.volto -c plone-constraints.txt
	$(VENV)/bin/pip install zope.testrunner plone.app.testing plone.reload dm.plonepatches.reload collective.exportimport -c plone-constraints.txt
	$(VENV)/bin/pip install relstorage==4.3.0 psycopg2==2.9.13 python-ldap==3.4.8 pas.plugins.ldap==1.8.4 -c plone-constraints.txt
	$(VENV)/bin/mkwsgiinstance -d . -u admin:admin
	mkdir -p var/blobstorage var/filestorage

.PHONY: develop
develop:		## Develop source.ini add-ons using mxdev
	$(VENV)/bin/pip install -r ../requirements.txt -c ../constraints.txt
	$(VENV)/bin/pip install plone.autoinclude -c plone-constraints.txt
	$(VENV)/bin/mxdev -c sources.ini
	$(VENV)/bin/pip install -r requirements-mxdev.txt

.PHONY: issues
issues: 		## Check github for open pull-requests
	python3 ./scripts/pull-requests.py WARN

.PHONY: status
status: 		## Check sources for changes
	./scripts/status.sh

.PHONY: pull
pull:			## Pull sources from git
	./scripts/pull.sh

.PHONY: start
start:			## Start Plone backend (standalone)
	$(VENV)/bin/runwsgi -v etc/zope.ini config_file=zope.conf

.PHONY: relstorage
relstorage:		## Start Plone backend (RelStorage/PostgreSQL)
	docker compose up -d
	$(VENV)/bin/runwsgi -v etc/zope.ini config_file=relstorage.conf

.PHONY: alpha
alpha:		## Start Plone backend (RelStorage/PostgreSQL with alpha features)
	$(VENV)/bin/runwsgi -v etc/zope.ini config_file=alpha.conf

.PHONY: release
release:		## See release candidates
	$(VENV)/bin/python scripts/release.py

.PHONY: help
help:			## Show this help.
	@echo -e "$$(grep -hE '^\S+:.*##' $(MAKEFILE_LIST) | sed -e 's/:.*##\s*/:/' -e 's/^\(.\+\):\(.*\)/\\x1b[36m\1\\x1b[m:\2/' | column -c2 -t -s :)"
	head -n 12 Makefile
