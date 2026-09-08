import os
import shutil
import subprocess

from .repo import GIT_CONFIG, fail, git, git_c, plural, tree_path
from .layout import stem
from .patchfile import is_mailbox, json_paths, location, read_mailbox


def _apply_json(repo, d, name, lenient, span=None):
    path = os.path.join(d, name)
    try:
        paths = json_paths(path)
    except ValueError as exc:
        fail(str(exc))
    present = lambda rel: bool(git(repo, "ls-files", "-z", "--", rel))
    renamed = {}
    if span and not all(present(rel) for rel in paths):
        fields = git(repo, "diff", "-M", "--name-status", "--diff-filter=R", "-z", *span).split("\0")
        renamed = {fields[i + 1]: fields[i + 2] for i in range(0, len(fields) - 2, 3)}
    removed, missing = [], []
    for rel in paths:
        if not present(rel):
            if rel in renamed and present(renamed[rel]):
                print(f"  {rel} was renamed upstream to {renamed[rel]}; removing that instead")
                rel = renamed[rel]
            else:
                missing.append(rel)
                continue
        git(repo, "rm", "-r", "-q", "--", rel)
        target = tree_path(repo, rel)
        if os.path.isdir(target) and not os.path.islink(target):
            shutil.rmtree(target)
        removed.append(rel)
    if missing and not lenient:
        return "path(s) to remove do not exist:\n" + "".join(f"  {m}\n" for m in missing), missing
    if removed:
        message = f"[{name}] remove {plural(len(removed), 'path')}\n\n{location(d, name)}"
        git_c(repo, "commit", "--no-verify", "-q", "-m", message)
    return None, missing


def _run_am(repo, mailbox, config=(), threeway=True):
    proc = subprocess.run(
        ["git", "-C", repo, *GIT_CONFIG, *config, "am", "--keep", "--keep-cr"] + (["--3way"] if threeway else []),
        input=mailbox.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if proc.returncode == 0:
        return None
    lines = proc.stdout.decode("utf-8", "replace").splitlines()
    return "".join(ln + "\n" for ln in lines if not ln.startswith("hint:"))


def plain_message(d, name):
    return f"[{stem(name)}] {stem(name)}\n\n{location(d, name)}"


def _apply_plain(repo, d, name):
    path = os.path.abspath(os.path.join(d, name))
    proc = subprocess.run(["git", "-C", repo, "apply", "--index", "--ignore-whitespace", path],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if proc.returncode != 0:
        return proc.stdout.decode("utf-8", "replace")
    git_c(repo, "commit", "--no-verify", "-q", "-m", plain_message(d, name))
    return None


def apply_step(repo, d, name, lenient=False, config=(), span=None, threeway=True):
    if name.endswith(".json"):
        return _apply_json(repo, d, name, lenient, span)
    if is_mailbox(os.path.join(d, name)):
        return _run_am(repo, read_mailbox(d, name), config, threeway), []
    return _apply_plain(repo, d, name), []
