import os
import re
import subprocess
import sys


BASE_REF = "refs/vscodium/base"

HEAD_REF = "refs/vscodium/head"

COMMITTER_NAME = "VSCodium"

COMMITTER_EMAIL = "scripts@vscodium.com"

GIT_CONFIG = [
    "-c", "user.name=" + COMMITTER_NAME,
    "-c", "user.email=" + COMMITTER_EMAIL,
    "-c", "commit.gpgsign=false",
    "-c", "core.hooksPath=/dev/null",
    "-c", "gc.auto=0",
    "-c", "rerere.enabled=true",
]


def fail(message):
    sys.stderr.write(message.rstrip("\n") + "\n")
    sys.exit(1)


def plural(count, noun):
    if count == 1:
        return f"1 {noun}"
    return f"{count} {noun}" + ("es" if noun.endswith(("s", "x", "z", "ch", "sh")) else "s")


def git(repo, *args):
    return subprocess.check_output(["git", "-C", repo, *args], text=True)


def git_c(repo, *args):
    subprocess.check_call(["git", "-C", repo, *GIT_CONFIG, *args])


def git_ok(repo, *args):
    return subprocess.call(["git", "-C", repo, *args],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0


def rev(repo, ref):
    return subprocess.run(["git", "-C", repo, "rev-parse", "--verify", "-q", ref],
                          capture_output=True, text=True).stdout.strip()


_GIT_DIRS = {}


def git_dir(repo):
    if repo not in _GIT_DIRS:
        _GIT_DIRS[repo] = git(repo, "rev-parse", "--absolute-git-dir").strip()
    return _GIT_DIRS[repo]


_GIT_VERSION = None


def git_version():
    global _GIT_VERSION
    if _GIT_VERSION is None:
        match = re.search(r"(\d+)\.(\d+)", subprocess.check_output(["git", "--version"], text=True))
        _GIT_VERSION = (int(match.group(1)), int(match.group(2))) if match else (0, 0)
    return _GIT_VERSION


def require_base(repo):
    base = rev(repo, BASE_REF)
    if not base:
        fail(f"{repo}/ was not created by this tooling ({BASE_REF} is missing).\n"
              f"Move it aside and run ./dev/build.sh to make a fresh clone.")
    return base


def mid_operation(repo):
    path = git_dir(repo)
    return any(os.path.isdir(os.path.join(path, d)) for d in ("rebase-apply", "rebase-merge"))


def tree_path(repo, path):
    return os.path.join(repo, *path.split("/"))


def split_lines(output):
    return [p for p in output.split("\n") if p]
