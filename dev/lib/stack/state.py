import json
import os
import shutil

import git as egit

from .repo import BASE_REF, HEAD_REF, fail, git, git_c, git_dir, git_ok, split_lines, tree_path
from .layout import PATCH_EXTENSIONS, matches, write_stack_dirs


REBASE_DIR = "vscodium-rebase"


def applied_skipped(state):
    applied = [os.path.join(d, n) for d, n, how, *_ in state["done"] if how == "applied"]
    skipped = [os.path.join(d, n) for d, n, how, *_ in state["done"] if how == "skipped"]
    return applied, skipped


def _state_path(repo):
    return os.path.join(git_dir(repo), REBASE_DIR, "state.json")


def read_state(repo):
    try:
        with open(_state_path(repo), encoding="utf-8") as f:
            return json.load(f)
    except OSError:
        return None


def write_state(repo, state):
    path = _state_path(repo)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(path + ".tmp", path)


def drop_state(repo):
    shutil.rmtree(os.path.dirname(_state_path(repo)), ignore_errors=True)


def _backup_root(repo):
    return os.path.join(git_dir(repo), REBASE_DIR, "backup")


def snapshot_patches(repo, dirs):
    root = _backup_root(repo)
    shutil.rmtree(root, ignore_errors=True)
    for d in dirs:
        dest = os.path.join(root, d)
        os.makedirs(dest, exist_ok=True)
        for f in os.listdir(d):
            if f.endswith(PATCH_EXTENSIONS) or f == ".patches":
                shutil.copyfile(os.path.join(d, f), os.path.join(dest, f))


def _restore_patches(repo, dirs):
    root = _backup_root(repo)
    if not os.path.isdir(root):
        return
    for d in dirs:
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.endswith(PATCH_EXTENSIONS) or f == ".patches":
                    os.remove(os.path.join(d, f))
        else:
            os.makedirs(d, exist_ok=True)
        saved = os.path.join(root, d)
        if os.path.isdir(saved):
            for f in os.listdir(saved):
                if f.endswith(PATCH_EXTENSIONS) or f == ".patches":
                    shutil.copyfile(os.path.join(saved, f), os.path.join(d, f))


def require_state(repo):
    state = read_state(repo)
    if not state:
        fail("No rebase in progress.")
    return state


def restore_from_state(repo, state):
    git_ok(repo, "am", "--abort")
    remove_rejects(repo, state)
    git_c(repo, "reset", "-q", "--hard", state["old_head"])
    added = split_lines(git(repo, "diff", "--name-only", "--no-renames", "--diff-filter=A", state["old_head"], state["onto"]))
    stray = sorted(set(added) & set(split_lines(git(repo, "ls-files", "--others", "--exclude-standard"))))
    if stray:
        git_ok(repo, "clean", "-fq", "--", *stray)
    egit.update_ref(repo=repo, ref=BASE_REF, newvalue=state["old_base"])
    if state["old_tip"]:
        egit.update_ref(repo=repo, ref=HEAD_REF, newvalue=state["old_tip"])
    else:
        git_ok(repo, "update-ref", "-d", HEAD_REF)
    write_stack_dirs(repo, state["old_dirs"])
    _restore_patches(repo, state.get("dirs", state["old_dirs"]))
    drop_state(repo)


def remove_rejects(repo, state):
    for path in state["rej"]:
        try:
            os.remove(tree_path(repo, path + ".rej"))
        except OSError:
            pass
    state["rej"] = []


def step_done(state, how):
    d, name = state["current"]
    state["done"].append([d, name, how, state["step_head"]])
    state["todo"].pop(0)
    state["current"] = None
    state["step_head"] = None


def skip_pending(state, wanted):
    for i, (d, name) in enumerate(state["todo"]):
        if matches(wanted, d, name):
            state["done"].append([d, name, "skipped", None])
            state["todo"].pop(i)
            print(f"skipped {os.path.join(d, name)}")
            return
    fail(f"{wanted} is not among the pending patches (./dev/rebase.sh --status).")
