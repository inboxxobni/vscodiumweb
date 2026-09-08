import glob
import json
import os
import subprocess
import sys

import git as egit

from .repo import (BASE_REF, HEAD_REF, fail, git, git_c, git_dir, git_ok, git_version, plural, require_base,
                   rev, split_lines, tree_path)
from .layout import (build_dirs, config_from_dirs, config_label, matches, patch_order, read_stack_dirs,
                     stem, write_stack_dirs)
from .patchfile import TAG_RE, is_mailbox, patch_sections
from .apply import apply_step, plain_message
from .state import (applied_skipped, drop_state, read_state, remove_rejects, require_state,
                    restore_from_state, skip_pending, snapshot_patches, step_done, write_state)
from .conflicts import (apply_with_rejects, conflicted_paths, exclude_rejects, print_rows, rejects_for_conflicts,
                        report_conflict)


def _rebase_config():
    style = "zdiff3" if git_version() >= (2, 35) else "diff3"
    return ["-c", "merge.conflictStyle=" + style]


def _started(state):
    return state["done"] or state["current"]


def _start_onto(repo, state):
    if _started(state):
        return
    try:
        egit.update_ref(repo=repo, ref=BASE_REF, newvalue=state["onto"])
        git_c(repo, "reset", "-q", "--hard", state["onto"])
    except KeyboardInterrupt:
        print("\nPaused; ./dev/rebase.sh --continue resumes.")
        sys.exit(1)


def _rebase_run(repo, state, until=None):
    if until and not any(matches(until, d, name) for d, name in state["todo"]):
        fail(f"{until} is not among the pending patches (./dev/rebase.sh --status).")
    if until:
        state["until"] = until
    until = state.get("until")
    _start_onto(repo, state)
    while state["todo"]:
        d, name = state["todo"][0]
        label = os.path.join(d, name)
        state["current"] = [d, name]
        state["step_head"] = rev(repo, "HEAD")
        write_state(repo, state)
        try:
            error, missing = apply_step(repo, d, name, lenient=True, config=_rebase_config(),
                                        span=(state["old_base"], state["onto"]),
                                        threeway=state.get("conflicts") != "reject")
        except KeyboardInterrupt:
            git_ok(repo, "am", "--abort")
            if rev(repo, "HEAD") != state["step_head"]:
                step_done(state, "applied")
            else:
                git_c(repo, "reset", "-q", "--hard", state["step_head"])
                state["current"] = None
            write_state(repo, state)
            print("\nPaused; ./dev/rebase.sh --continue resumes.")
            sys.exit(1)
        if error:
            if conflicted_paths(repo):
                state["mode"] = "3way"
                state["rej"] = rejects_for_conflicts(repo, d, name)
            else:
                state["mode"] = "reject"
                state["rej"] = apply_with_rejects(repo, d, name)
            write_state(repo, state)
            report_conflict(repo, state, label, error)
            sys.exit(1)
        if rev(repo, "HEAD") == state["step_head"]:
            step_done(state, "skipped")
            print(f"skipped {label} (none of its paths exist upstream)")
        else:
            step_done(state, "applied")
            if missing:
                state.setdefault("notes", []).append(f"{label}: no longer upstream, dropped: {', '.join(missing)}")
            write_state(repo, state)
            print(f"applied {label}" + (f" ({plural(len(missing), 'path')} no longer upstream, dropped: "
                                       f"{', '.join(missing)})" if missing else ""))
        write_state(repo, state)
        if until and matches(until, d, name):
            state["until"] = None
            write_state(repo, state)
            print(f"\nStopped after {label}; ./dev/rebase.sh --continue resumes.")
            return
    _rebase_finish(repo, state)


def _check_variants(repo, patches_root):
    found, broken = 0, []
    for sub in ("*/client", "*/reh", "*/reh/*"):
        for f in sorted(glob.glob(os.path.join(patches_root, sub, "*.patch"))):
            found += 1
            if not git_ok(repo, "apply", "--check", "--ignore-whitespace", os.path.abspath(f)):
                broken.append(f)
    if found:
        print(f"variant patches (applied by packaging, not the stack): {found - len(broken)} of {found} "
              f"would apply to this tree" + (f"; broken: {', '.join(broken)}" if broken else ""))


def rebase_redo(repo):
    state = require_state(repo)
    if state["current"]:
        fail(f"{os.path.join(*state['current'])} is still in progress; finish it (--continue), --skip it, or --abort before --redo.")
    last = state["done"][-1] if state["done"] else None
    if not last or len(last) < 4 or not last[3]:
        fail("Nothing to redo (./dev/rebase.sh --status).")
    d, name, _how, start = state["done"].pop()
    git_c(repo, "reset", "-q", "--hard", start)
    state["todo"].insert(0, [d, name])
    write_state(repo, state)
    print(f"undid {os.path.join(d, name)}; applying it again")
    _rebase_run(repo, state)


def _rebase_finish(repo, state):
    drop_state(repo)
    applied, skipped = applied_skipped(state)
    print(f"\nRebased {plural(len(applied), 'patch')} onto {state['onto'][:8]}."
          + (f" Skipped {len(skipped)}: {', '.join(skipped)}." if skipped else ""))
    for note in state.get("notes", []):
        print(f"  {note}")
    _check_variants(repo, read_stack_dirs(repo)[0])
    print("Next: ./dev/export.sh    (writes the rebased patches; skipped ones are removed)")
    print("      ./dev/verify.sh    (finds imports the rebased stack broke)")
    pin = os.path.join("upstream", state["quality"] + ".json")
    try:
        with open(pin, encoding="utf-8") as f:
            pinned = json.load(f)["commit"]
    except (OSError, ValueError, KeyError):
        pinned = None
    if pinned != state["onto"]:
        print(f"Then point {pin} at {state['onto']} so a fresh clone builds against it.")


def _conflict_mode(reject):
    configured = subprocess.run(["git", "config", "--get", "vscodium.conflicts"],
                                capture_output=True, text=True).stdout.strip()
    if configured not in ("", "3way", "reject"):
        fail(f"vscodium.conflicts is {configured!r}; use 3way or reject.")
    return "reject" if reject or configured == "reject" else "3way"


def rebase_start(repo, patches_root, onto, quality, os_name, until, reject=False):
    base = require_base(repo)
    if read_state(repo):
        fail("A rebase is already in progress (./dev/rebase.sh --status).")
    imported = read_stack_dirs(repo)
    derived_quality, derived_os = config_from_dirs(patches_root, imported)
    quality = quality or derived_quality
    os_name = os_name or derived_os
    dirs = build_dirs(patches_root, quality, os_name)
    if not onto and rev(repo, HEAD_REF):
        with open(os.path.join("upstream", quality + ".json"), encoding="utf-8") as f:
            onto = json.load(f)["commit"]
    if onto and not rev(repo, onto + "^{commit}"):
        subprocess.check_call(["git", "-C", repo, "fetch", "--depth", "1", "origin", onto])
        onto = "FETCH_HEAD"
    onto = rev(repo, (onto or base) + "^{commit}")
    todo = [[d, name] for d in dirs for name in patch_order(d)]
    if until and not any(matches(until, d, name) for d, name in todo):
        fail(f"{until} is not among the patches to apply.")
    state = {
        "onto": onto, "old_base": base, "old_head": rev(repo, "HEAD"), "old_tip": rev(repo, HEAD_REF),
        "old_dirs": imported, "dirs": dirs, "quality": quality, "os_name": os_name,
        "todo": todo, "done": [], "current": None, "step_head": None, "mode": "3way", "rej": [], "until": until,
        "conflicts": _conflict_mode(reject),
    }
    snapshot_patches(repo, dirs)
    exclude_rejects(repo)
    write_state(repo, state)
    write_stack_dirs(repo, dirs)
    config = config_label(quality, os_name)
    how = " with .rej files" if state["conflicts"] == "reject" else ""
    if onto == base:
        print(f"Re-applying {plural(len(todo), 'patch')} ({config}) onto {onto[:8]}{how}")
    else:
        print(f"Rebasing {plural(len(todo), 'patch')} ({config}): {base[:8]} -> {onto[:8]}{how}")
    _rebase_run(repo, state, until)


def _subject(repo):
    return git(repo, "log", "-1", "--format=%s", "HEAD").strip()


def _head_is(repo, name):
    tag = TAG_RE.match(_subject(repo))
    return bool(tag) and tag.group(1).rpartition("/")[2] in (name, stem(name))


def _note_resolution(repo, d, name, label):
    if name.endswith(".json"):
        return
    wanted = set(patch_sections(d, name))
    got = set(split_lines(git(repo, "diff-tree", "--no-commit-id", "-r", "--name-only", "HEAD")))
    if wanted - got:
        git_ok(repo, "rerere", "forget", "--", *sorted(wanted - got))
        print(f"note: {label} changes {plural(len(wanted), 'file')} but this commit changes {len(got)}; "
              f"untouched: {', '.join(sorted(wanted - got))} (not remembered for rerere; --redo re-applies it)")


def _finish_step(repo, state, label, am):
    d, name = state["current"]
    if state["mode"] == "3way":
        unmerged = split_lines(git(repo, "diff", "--name-only", "--diff-filter=U"))
        if unmerged:
            fail(f"{label} still has unresolved files:\n" + "".join(f"  {p}\n" for p in unmerged)
                  + "Resolve and `git add` them, then re-run ./dev/rebase.sh --continue.")
    else:
        left = [p for p in state["rej"] if os.path.exists(tree_path(repo, p + ".rej"))]
        if left:
            fail(f"{label} still has rejected hunks:\n" + "".join(f"  {p}.rej\n" for p in left)
                  + "Apply them by hand, delete the .rej files and `git add` the files, "
                  "then re-run ./dev/rebase.sh --continue.")
    unstaged = split_lines(git(repo, "diff", "--name-only"))
    if unstaged:
        fail("unstaged changes in vscode/:\n" + "".join(f"  {p}\n" for p in unstaged)
              + "`git add` them (or discard them), then re-run ./dev/rebase.sh --continue.")
    if git_ok(repo, "diff", "--cached", "--quiet"):
        fail(f"nothing is staged for {label}.\n"
              f"If the patch is no longer needed: ./dev/rebase.sh --skip")
    if am:
        git_c(repo, "am", "--continue")
    else:
        git_c(repo, "commit", "--no-verify", "-q", "-m", plain_message(d, name))


def rebase_continue(repo, until=None, skip=None):
    state = require_state(repo)
    _start_onto(repo, state)
    until = until or state.get("until")
    current = state["current"]
    if skip and not (current and matches(skip, *current)):
        skip_pending(state, skip)
        write_state(repo, state)
        if current:
            print(f"still stopped on {os.path.join(*current)}; resolve it, then ./dev/rebase.sh --continue")
            return
        skip = None
    if current:
        d, name = current
        label = os.path.join(d, name)
        am = os.path.isdir(os.path.join(git_dir(repo), "rebase-apply"))
        moved = rev(repo, "HEAD") != state["step_head"]
        plain = name.endswith(".patch") and not is_mailbox(os.path.join(d, name))
        if skip is not None:
            git_ok(repo, "am", "--skip")
            git_c(repo, "reset", "-q", "--hard", state["step_head"])
            remove_rejects(repo, state)
            step_done(state, "skipped")
            print(f"skipped {label}")
        elif am and moved:
            fail(f"{label} was committed by hand while git am was still running.\n"
                  f"Run `git -C vscode reset --soft {state['step_head'][:8]}`, then "
                  f"./dev/rebase.sh --continue, so the commit keeps the patch's name and note.")
        elif am or (plain and not moved):
            _finish_step(repo, state, label, am)
            remove_rejects(repo, state)
            step_done(state, "applied")
            print(f"applied {label}")
            _note_resolution(repo, d, name, label)
        elif moved and _head_is(repo, name):
            remove_rejects(repo, state)
            step_done(state, "applied")
            print(f"applied {label}")
            _note_resolution(repo, d, name, label)
        elif moved:
            fail(f"HEAD moved to {rev(repo, 'HEAD')[:8]} \"{_subject(repo)}\", which is not {label}'s commit.\n"
                  f"If that commit is your resolution of this patch, tag its subject [{stem(name)}] "
                  f"(git -C vscode commit --amend); otherwise put vscode/ back with "
                  f"`git -C vscode reset --hard {state['step_head'][:8]}`. Then ./dev/rebase.sh --continue.")
        elif git(repo, "status", "--porcelain", "--untracked-files=no").strip():
            fail(f"{label}: the previous `git am` was ended by hand and vscode/ has uncommitted "
                  f"changes.\nCommit them onto this patch, or discard them "
                  f"(git -C vscode reset --hard), then ./dev/rebase.sh --continue; or --skip / --abort.")
        else:
            git_c(repo, "reset", "-q", "--hard", state["step_head"])
            remove_rejects(repo, state)
            state["current"] = None
        if state["current"] is None and until and matches(until, d, name):
            state["until"] = None
        write_state(repo, state)
        if state["current"] is None and until and matches(until, d, name):
            print(f"\nStopped after {label}; ./dev/rebase.sh --continue resumes.")
            return
    elif skip is not None:
        if not state["todo"]:
            fail("Nothing left to skip (./dev/rebase.sh --status).")
        skip_pending(state, os.path.join(*state["todo"][0]))
        write_state(repo, state)
    _rebase_run(repo, state, until)


def rebase_abort(repo, force):
    state = require_state(repo)
    since = state["onto"] if git_ok(repo, "merge-base", "--is-ancestor", state["onto"], "HEAD") else state["old_head"]
    unsaved = egit.get_commit_count(repo, since + "..HEAD")
    if unsaved and not force:
        fail(f"--abort would discard {plural(unsaved, 'rebased commit')} and any patches "
              f"./dev/export.sh wrote during the rebase.\n"
              f"Run ./dev/rebase.sh --abort -f to discard them.")
    restore_from_state(repo, state)
    print(f"vscode/ is back on {state['old_head'][:8]} (base {state['old_base'][:8]}) with its "
          f"{plural(len(state['todo']) + len(state['done']), 'patch')}.")
    rr_cache = os.path.join(git_dir(repo), "rr-cache")
    if os.path.isdir(rr_cache) and os.listdir(rr_cache):
        print("rerere still remembers the conflicts you resolved; `git -C vscode rerere clear` forgets them.")


def rebase_status(repo):
    state = require_state(repo)
    applied, skipped = applied_skipped(state)
    pending = state["todo"][1:] if state["current"] else state["todo"]
    config = config_label(state["quality"], state["os_name"])
    print(f"Rebasing onto {state['onto'][:8]} ({config}): "
          f"{len(applied)} applied, {len(skipped)} skipped, {len(pending)} pending")
    if state.get("until"):
        print(f"  stops after {state['until']}")
    if state.get("conflicts") == "reject":
        print("  conflicts: .rej files")
    commits = egit.get_commit_count(repo, state["onto"] + "..HEAD")
    if not _started(state) and rev(repo, "HEAD") != state["onto"]:
        print("  interrupted before the first patch; ./dev/rebase.sh --continue resumes")
    elif commits != len(applied) + (1 if state["current"] and _head_is(repo, state["current"][1]) else 0):
        print(f"  note: {plural(commits, 'commit')} on the stack for {plural(len(applied), 'applied patch')}; "
              f"./dev/export.sh writes untagged ones as user patches")
    if state["current"]:
        print(f"  stopped on {os.path.join(*state['current'])}:")
        print_rows(repo, state)
    for d, name in pending[:5]:
        print(f"  pending  {os.path.join(d, name)}")
    if len(pending) > 5:
        print(f"  ... {len(pending) - 5} more")
    print("./dev/rebase.sh --continue | --skip [<patch>] | --redo | --abort;  ./dev/export.sh saves the rebased ones")
