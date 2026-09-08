import os
import re
import shutil
import subprocess
import sys
import tempfile

from .repo import GIT_CONFIG, git, git_dir, plural, split_lines, tree_path
from .patchfile import patch_sections
from .state import applied_skipped


CONFLICT_LABELS = {
    "UU": "both modified",
    "AA": "both added",
    "DU": "deleted by us",
    "UD": "deleted by them",
    "DD": "both deleted",
    "AU": "added by us",
    "UA": "added by them",
}

CONFLICT_NOTES = {
    "UU": "conflict markers; the failed hunks are in {rej}",
    "AA": "conflict markers; the patch's version is in {rej}",
    "DU": "gone upstream; the patch's hunks are in {rej}: port them, or git rm it (--skip if nothing is left)",
    "UD": "the patch deletes it, upstream changed it (git rm keeps it deleted)",
    "DD": "gone from both sides; git rm it (or --skip if nothing is left)",
    "AU": "the patch adds it, absent upstream; its version is in {rej}",
    "UA": "upstream added it too; the patch's version is in {rej}",
}


def exclude_rejects(repo):
    exclude = os.path.join(git_dir(repo), "info", "exclude")
    os.makedirs(os.path.dirname(exclude), exist_ok=True)
    try:
        with open(exclude, encoding="utf-8") as f:
            if "*.rej\n" in f.readlines():
                return
    except OSError:
        pass
    with open(exclude, "a", encoding="utf-8") as f:
        f.write("*.rej\n")


def conflicted_paths(repo):
    fields = git(repo, "status", "--porcelain", "-z").split("\0")
    entries, i = [], 0
    while i < len(fields) and fields[i]:
        code, path = fields[i][:2], fields[i][3:]
        i += 2 if "R" in code or "C" in code else 1
        if code in CONFLICT_LABELS:
            entries.append((code, path))
    return entries


def _reject_hunks(repo, path, section):
    ours = subprocess.run(["git", "-C", repo, "show", "HEAD:" + path], capture_output=True).stdout
    tmp = os.path.realpath(tempfile.mkdtemp())
    try:
        target = os.path.join(tmp, "work", *path.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            f.write(ours)
        subprocess.run(["git", "apply", "--reject", "--ignore-whitespace", "-C1"],
                       input=section.encode("utf-8"), cwd=os.path.join(tmp, "work"),
                       env={**os.environ, "GIT_CEILING_DIRECTORIES": tmp},
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            with open(target + ".rej", "rb") as f:
                return f.read()
        except OSError:
            return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _write_reject(repo, path, data):
    target = tree_path(repo, path + ".rej")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "wb") as f:
        f.write(data)


def rejects_for_conflicts(repo, d, name):
    sections = patch_sections(d, name)
    written = []
    for code, path in conflicted_paths(repo):
        section = sections.get(path)
        if not section:
            continue
        data = (_reject_hunks(repo, path, section) if code == "UU" else None) or section.encode("utf-8")
        _write_reject(repo, path, data)
        written.append(path)
    return written


def apply_with_rejects(repo, d, name):
    sections = patch_sections(d, name)
    proc = subprocess.run(["git", "-C", repo, "apply", "--reject", "--ignore-whitespace",
                           os.path.abspath(os.path.join(d, name))], capture_output=True, text=True)
    failed = set(re.findall(r"^error: (.+?): ", proc.stderr, re.M)) & set(sections)
    written = []
    for path, section in sections.items():
        gone = not os.path.lexists(tree_path(repo, path)) and "\n+++ /dev/null" not in section
        if os.path.exists(tree_path(repo, path + ".rej")):
            written.append(path)
        elif path in failed or gone:
            _write_reject(repo, path, section.encode("utf-8"))
            written.append(path)
    git(repo, "add", "-A")
    return written


def _conflict_rows(repo, state):
    if state["mode"] == "3way":
        rejects = set(state["rej"])
        remaining = set(split_lines(subprocess.check_output(
            ["git", "-C", repo, *GIT_CONFIG, "rerere", "remaining"], text=True)))
        for code, path in conflicted_paths(repo):
            if code == "UU" and path not in remaining:
                note = "rerere replayed your earlier resolution; review it, then git add"
            else:
                note = CONFLICT_NOTES[code].format(rej=path + ".rej") if path in rejects or code == "UD" else ""
            yield CONFLICT_LABELS[code], path, note
        return
    for path in state["rej"]:
        if not os.path.exists(tree_path(repo, path + ".rej")):
            continue
        if os.path.lexists(tree_path(repo, path)):
            yield "rejected hunks", path, f"apply {path}.rej by hand, then delete it"
        else:
            yield "gone upstream", path, f"the patch's hunks are in {path}.rej; port or delete them"


def print_rows(repo, state):
    for label, path, note in _conflict_rows(repo, state):
        print(f"  {label:16}{path}")
        if note:
            print(f"  {'':16}{note}")


def report_conflict(repo, state, label, error):
    print(f"\n{label} did not apply cleanly:")
    sys.stdout.write("".join(f"  {ln}\n" for ln in error.splitlines()))
    if state["mode"] == "reject" and state.get("conflicts") != "reject":
        print("  (no 3-way merge: the upstream this patch was made against is not in this clone)")
    print()
    print_rows(repo, state)
    applied = len(applied_skipped(state)[0])
    left = len(state["todo"]) - 1
    print("\nResolve and `git add` (or `git rm`) each file, then:  ./dev/rebase.sh --continue  (not git am)")
    print("  ./dev/rebase.sh --skip [<patch>]    drop this patch (or a pending one)")
    print("  ./dev/rebase.sh --abort             put vscode/ back as it was")
    print(f"  ./dev/export.sh                     save the {plural(applied, 'patch')} rebased so far ({left} left)")
