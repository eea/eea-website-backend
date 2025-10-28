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

PLONE_VERSION=6.1.3
#`docker run -i --rm eeacms/plone-backend env | grep PLONE_VERSION | sed "s/PLONE_VERSION=//g"`
PYTHON?=python3.11

# Top-level targets
.PHONY: all
all: bootstrap install develop

.PHONY: clean
clean:			## Cleanup environment
	rm -rf bin include lib lib64 inituser pyvenv.cfg *.egg-info node_modules

.PHONY: bootstrap
bootstrap:		## Bootstrap python environment
	$(PYTHON) -m venv .
	bin/pip install --upgrade pip mxdev plonecli pylint black ruff -c "https://dist.plone.org/release/$(PLONE_VERSION)/constraints.txt"

.PHONY: install
install:		## Install Plone and develop add-ons
	bin/pip install Plone plone.volto -c "https://dist.plone.org/release/$(PLONE_VERSION)/constraints.txt"
	bin/pip install zope.testrunner plone.app.testing plone.reload dm.plonepatches.reload collective.exportimport -c "https://dist.plone.org/release/$(PLONE_VERSION)/constraints.txt"
	bin/pip install relstorage==4.0.0 psycopg2==2.9.5 python-ldap==3.4.3 pas.plugins.ldap==1.8.2 -c "https://dist.plone.org/release/$(PLONE_VERSION)/constraints.txt"
	bin/mkwsgiinstance -d . -u admin:admin
	mkdir -p var/blobstorage var/filestorage

.PHONY: develop
develop:		## Develop source.ini add-ons using mxdev
	bin/pip install -r ../requirements.txt -c ../constraints.txt
	bin/pip install plone.autoinclude==2.0.0
	bin/mxdev -c sources.ini
	bin/pip install -r requirements-mxdev.txt

.PHONY: status
status: 		## Check sources for changes
	./scripts/status.sh

.PHONY: pull
pull:			## Pull sources from git
	./scripts/pull.sh

.PHONY: start
start:			## Start Plone backend (standalone)
	bin/runwsgi -v etc/zope.ini config_file=zope.conf

.PHONY: relstorage
relstorage:		## Start Plone backend (RelStorage/PostgreSQL)
	docker compose up -d
	bin/runwsgi -v etc/zope.ini config_file=relstorage.conf

.PHONY: release
release:		## See release candidates
	bin/python scripts/release.py

.PHONY: help
help:			## Show this help.
	@echo -e "$$(grep -hE '^\S+:.*##' $(MAKEFILE_LIST) | sed -e 's/:.*##\s*/:/' -e 's/^\(.\+\):\(.*\)/\\x1b[36m\1\\x1b[m:\2/' | column -c2 -t -s :)"
	head -n 12 Makefile
