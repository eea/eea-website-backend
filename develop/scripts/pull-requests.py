#!/usr/bin/env python3
"""List open pull requests for the backend add-ons.

The add-ons are collected from ``develop/sources.ini`` (mxdev checkouts) and
``requirements.txt`` (add-ons installed on top of ``eeacms/plone-backend``).

Usage::

    pull-requests.py [loglevel] [-j JOBS] [-x PATTERN ...]

loglevel:
  - fatal    Log only critical errors
  - critical Log only critical errors
  - error    Log only errors
  - warn     Log only warnings (default for ``make issues``)
  - warning  Log only warnings
  - info     Log only status messages
  - debug    Log all messages

Authentication, first match wins:

  1. ``gh`` CLI, when installed and logged in (``gh auth login``)
  2. ``GITHUB_TOKEN`` environment variable
  3. ``~/.github`` with a ``[github]`` section holding username/password::

        [github]
        username: foobar
        password: secret #betterleaks:allow

Output: TSV on stdout with the header
``updated_at, repository, url, author, title``, one row per open pull request,
sorted by ``updated_at`` descending and written at the end. While the add-ons
are checked in parallel, a single line progress counter is updated on stderr
(only when stderr is a terminal). Drafts are kept and flagged with ``(draft)``.
The summary is written to stderr, so stdout stays pipeable.

Pull requests matching an exclude pattern are skipped. The pattern is matched
against the title, labels, branch and author, case insensitive and ignoring
spaces and dashes, so ``-x volto19`` skips ``Volto 19 support`` as well:

    pull-requests.py WARN -x volto19 -x dependabot
    EXCLUDE="volto19 dependabot" make issues

Exit code: 1 when open pull requests were found, 0 otherwise.
"""

import argparse
import base64
import json
import logging
import os
import re
import shutil
import subprocess  # nosec B404
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from configparser import ConfigParser
from pathlib import Path
from urllib import error, request

DEVELOP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = DEVELOP_DIR.parent

API = "https://api.github.com"
TIMEOUT = 15
PER_PAGE = 100

COLUMNS = ("updated_at", "repository", "url", "author", "title")


def normalize(text):
    """Normalize text for case and separator insensitive matching"""
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def is_excluded(pull, patterns):
    """Check whether a pull request matches any of the exclude patterns"""
    if not patterns:
        return False
    labels = [label.get("name", "") for label in pull.get("labels") or []]
    head = (pull.get("head") or {}).get("ref", "")
    author = (pull.get("user") or {}).get("login", "")
    state = "draft" if pull.get("draft") else ""
    haystack = normalize(
        " ".join([pull.get("title", ""), *labels, head, author, state])
    )
    return any(normalize(pattern) in haystack for pattern in patterns if pattern)


def patterns_of(flags):
    """Combine ``--exclude`` flags with the ``EXCLUDE`` environment variable"""
    patterns = list(flags or [])
    patterns.extend(re.split(r"[\s,]+", os.environ.get(EXCLUDE_ENV, "")))
    return [pattern for pattern in patterns if pattern]


DEFAULT_JOBS = 8
JOBS_ENV = "JOBS"
EXCLUDE_ENV = "EXCLUDE"
LOGLEVELS = ("fatal", "critical", "error", "warn", "warning", "info", "debug")
PROGRESS_WIDTH = 100

# Add-ons hosted in the collective org instead of the eea org
COLLECTIVE_HOSTED = {"rss-provider"}


def parse_requirements(path):
    """Return package names from a pip requirements file"""
    names = []
    for line in path.read_text().splitlines():
        line = line.split("#")[0].strip()
        if not line or line.startswith("-"):
            continue
        name = re.split(r"[\s<>=!~\[;@]", line)[0].strip()
        if name:
            names.append(name)
    return names


def parse_sources(path):
    """Return package names from a mxdev sources.ini file"""
    config = ConfigParser()
    config.read(path)
    return [section for section in config.sections() if section != "settings"]


def addons():
    """Return the deduplicated list of backend add-ons, in file order"""
    names = []
    for path, parser in (
        (DEVELOP_DIR / "sources.ini", parse_sources),
        (REPO_ROOT / "requirements.txt", parse_requirements),
    ):
        if not path.exists():
            continue
        for name in parser(path):
            if name not in names:
                names.append(name)
    return names


def repo_of(name):
    """Map an add-on name to its GitHub ``owner/name`` repository"""
    if name.startswith("collective.") or name in COLLECTIVE_HOSTED:
        return f"collective/{name}"
    return f"eea/{name}"


class Progress:
    """Single line progress counter on stderr, only when stderr is a terminal"""

    def __init__(self, total, stream=None):
        self.total = total
        self.stream = stream if stream is not None else sys.stderr
        self.enabled = self.stream.isatty()
        self.count = 0

    def update(self, label=""):
        """Count one more finished item and redraw the line"""
        self.count += 1
        if not self.enabled:
            return
        text = "[{0:>{2}}/{1}] {3}".format(
            self.count, self.total, len(str(self.total)), label
        )
        self.stream.write("\r" + text[:PROGRESS_WIDTH].ljust(PROGRESS_WIDTH))
        self.stream.flush()

    def done(self):
        """Erase the progress line"""
        if not self.enabled:
            return
        self.stream.write("\r" + " " * PROGRESS_WIDTH + "\r")
        self.stream.flush()


class Github:
    """Minimal GitHub API client, ``gh`` first and token based fallback"""

    def __init__(self, loglevel=logging.WARNING, jobs=DEFAULT_JOBS, excludes=None):
        self.timeout = TIMEOUT
        self.status = 0
        self.jobs = jobs
        self.excludes = excludes or []
        self.username = ""
        self.password = ""  # betterleaks:allow
        self.read_credentials()
        self.token = ""
        self.gh = shutil.which("gh")
        self._gh_checked = False
        self._gh_works = False
        self._logger = None
        self.loglevel = loglevel

    @property
    def logger(self):
        """Logger"""
        if self._logger:
            return self._logger

        self._logger = logging.getLogger("github")
        self._logger.setLevel(self.loglevel)
        handler = logging.StreamHandler()
        handler.setLevel(self.loglevel)
        handler.setFormatter(logging.Formatter("%(message)s"))
        self._logger.addHandler(handler)
        return self._logger

    @property
    def credentials(self):
        """GitHub credentials from ``~/.github``"""
        return {"username": self.username, "password": self.password}

    def read_credentials(self):
        """Read the GitHub credentials stored in ``~/.github``"""
        cfg_file = Path.home() / ".github"
        if not cfg_file.exists():
            return
        config = ConfigParser()
        config.read([str(cfg_file)])
        if not config.has_section("github"):
            return
        section = config["github"]
        self.username = section.get("username", "")
        self.password = section.get("password", "")  # betterleaks:allow

    def _gh_available(self):
        """Check once that ``gh`` is installed and authenticated"""
        if self._gh_checked:
            return self._gh_works
        self._gh_checked = True
        if not self.gh:
            return False
        try:
            proc = subprocess.run(  # nosec B603
                [self.gh, "auth", "status"],
                capture_output=True,
                timeout=self.timeout,
                check=False,
            )
            self._gh_works = proc.returncode == 0
        except (OSError, subprocess.SubprocessError):
            self._gh_works = False
        if self._gh_works:
            self.logger.debug("Using gh CLI for GitHub API requests")
        return self._gh_works

    def _get_gh(self, path):
        """Request through ``gh api``"""
        proc = subprocess.run(  # nosec B603
            [self.gh, "api", path],
            capture_output=True,
            text=True,
            timeout=self.timeout,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or "gh api failed")
        return json.loads(proc.stdout or "[]")

    def _get_urllib(self, path):
        """Request through urllib, using a token or basic auth"""
        req = request.Request(API + path)
        token = self.token or ""
        if token:
            req.add_header("Authorization", f"token {token}")
        elif self.credentials["username"] or self.credentials["password"]:
            auth = "{username}:{password}".format(**self.credentials)
            req.add_header(
                "Authorization",
                "Basic " + base64.b64encode(auth.encode("utf-8")).decode("ascii"),
            )
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        with request.urlopen(req, timeout=self.timeout) as conn:  # nosec B310
            return json.loads(conn.read())

    def get(self, path, params=""):
        """GET a GitHub API path, ``gh`` first, urllib fallback"""
        if self._gh_available():
            try:
                return self._get_gh(path + params)
            except (OSError, RuntimeError, ValueError) as err:
                self.logger.warning("%s \t %s", err, path)

        if not self.token:
            self.logger.debug("Falling back to GITHUB_TOKEN or ~/.github")
        return self._get_urllib(path + params)

    def pull_requests(self, repo):
        """Return the open pull requests of a repository and the skipped count"""
        path = f"/repos/{repo}/pulls"
        pulls = self.get(path, f"?state=open&per_page={PER_PAGE}")
        rows = []
        skipped = 0
        for pull in pulls:
            if is_excluded(pull, self.excludes):
                skipped += 1
                continue
            title = pull.get("title", "-")
            if pull.get("draft"):
                title = f"{title} (draft)"
            rows.append(
                {
                    "updated_at": pull.get("updated_at", "")[:10],
                    "repository": repo,
                    "url": pull.get("html_url", "-"),
                    "author": (pull.get("user") or {}).get("login", "-"),
                    "title": title,
                }
            )
        return rows, skipped

    def start(self):
        """Check all add-ons for open pull requests, in parallel"""
        names = addons()
        self.token = self.token or os.environ.get("GITHUB_TOKEN", "")
        self._gh_available()  # probe once, from the main thread
        self.logger.info(
            "Checking %s backend add-ons for open pull requests", len(names)
        )

        repos = []
        for name in names:
            repo = repo_of(name)
            if repo not in repos:
                repos.append(repo)

        rows = []
        found = set()
        skipped = 0
        progress = Progress(len(repos))
        with ThreadPoolExecutor(max_workers=self.jobs) as pool:
            futures = {pool.submit(self.pull_requests, repo): repo for repo in repos}
            for future in as_completed(futures):
                repo = futures[future]
                progress.update(repo)
                try:
                    pulls, dropped = future.result()
                except (error.HTTPError, OSError, RuntimeError, ValueError) as err:
                    self.logger.warning("%s \t %s", err, repo)
                    continue
                self.logger.debug("Checked pulls: %s", repo)
                skipped += dropped
                if pulls:
                    found.add(repo)
                rows.extend(pulls)
        progress.done()

        self.write(rows)

        self.logger.warning(
            "Found %s open pull requests in %s %s (%schecked %s add-ons)",
            len(rows),
            len(found),
            "repository" if len(found) == 1 else "repositories",
            f"{skipped} excluded, " if skipped else "",
            len(names),
        )
        self.status = 1 if rows else 0
        return self.status

    @staticmethod
    def write(rows):
        """Write all TSV rows sorted by ``updated_at`` descending"""
        rows.sort(key=lambda row: row["repository"])
        rows.sort(key=lambda row: row["updated_at"], reverse=True)
        print("\t".join(COLUMNS), flush=True)
        for row in rows:
            print("\t".join(row[column] for column in COLUMNS), flush=True)

    __call__ = start


if __name__ == "__main__":
    try:
        DEFAULT_JOBS_ENV = int(os.environ.get(JOBS_ENV, DEFAULT_JOBS))
    except ValueError:
        DEFAULT_JOBS_ENV = DEFAULT_JOBS

    PARSER = argparse.ArgumentParser(
        description="List open pull requests for the backend add-ons",
    )
    PARSER.add_argument(
        "loglevel",
        nargs="?",
        default="info",
        type=str.lower,
        choices=LOGLEVELS,
        help="logging level (default: info)",
    )
    PARSER.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=DEFAULT_JOBS_ENV,
        help=f"number of parallel requests (default: {DEFAULT_JOBS}, env: {JOBS_ENV})",
    )
    PARSER.add_argument(
        "-x",
        "--exclude",
        action="append",
        default=[],
        metavar="PATTERN",
        help="exclude pull requests matching PATTERN in the title, labels, "
        f"branch or author (repeatable, env: {EXCLUDE_ENV})",
    )

    ARGS = PARSER.parse_args()

    if ARGS.loglevel in ["fatal", "critical"]:
        LOGLEVEL = logging.FATAL
    elif ARGS.loglevel == "error":
        LOGLEVEL = logging.ERROR
    elif ARGS.loglevel in ["warn", "warning"]:
        LOGLEVEL = logging.WARNING
    elif ARGS.loglevel == "info":
        LOGLEVEL = logging.INFO
    else:
        LOGLEVEL = logging.DEBUG

    daemon = Github(
        loglevel=LOGLEVEL, jobs=max(1, ARGS.jobs), excludes=patterns_of(ARGS.exclude)
    )
    daemon.start()

    sys.exit(daemon.status)
