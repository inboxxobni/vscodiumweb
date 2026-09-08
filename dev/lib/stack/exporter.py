import os
import sys

import git as egit

from .repo import (BASE_REF, HEAD_REF, fail, git, git_c, git_dir, git_ok, mid_operation, plural,
                   require_base, rev)
from .layout import PATCH_EXTENSIONS, config_from_dirs, config_label, read_stack_dirs, stem
from .patchfile import json_content, mailbox_content, target_of
from .state import read_state
from .importer import import_stack


def _stack_patches(repo, base):
    shas = git(repo, "rev-list", "--reverse", base + "..HEAD").split()
    patches = egit.split_patches(egit.format_patch(repo, base + "..HEAD"))
    if len(shas) != len(patches):
        empty = [s for s in shas if not git(repo, "diff-tree", "--no-commit-id", "-r", "--name-only", s).strip()]
        fail("refusing to export commit(s) with no changes:\n"
              + "".join(f"  {git(repo, 'log', '-1', '--format=%h %s', s)}" for s in empty)
              + "Drop them (git rebase) and re-run ./dev/export.sh.")
    return list(zip(shas, patches))


def _has_binary(patch):
    return any(line.startswith("GIT binary patch")
               or (line.startswith("Binary files") and " differ" in line) for line in patch)


def _pending(state):
    pending = {}
    for d, name in state["todo"] if state else []:
        pending.setdefault(d, []).append(name)
    return pending


def _on_disk(dest):
    return sorted(f for f in os.listdir(dest) if f.endswith(PATCH_EXTENSIONS))


def _report_drift(groups, pending, contents):
    bad = []
    for dest, items in groups.items():
        names = [name for name, _, _ in items] + pending.get(dest, [])
        for name, _, _ in items:
            path = os.path.join(dest, name)
            try:
                with open(path, "rb") as f:
                    existing = f.read().decode("utf-8")
            except FileNotFoundError:
                existing = None
            if contents[path] != existing:
                bad.append(path)
        bad += [os.path.join(dest, f) + " (stale)" for f in _on_disk(dest) if f not in names]
        manifest = os.path.join(dest, ".patches")
        try:
            with open(manifest, encoding="utf-8") as f:
                listed = f.read()
        except FileNotFoundError:
            listed = None
        wanted = "".join(n + "\n" for n in names) if names else None
        if listed != wanted:
            bad.append(manifest)
    if bad:
        sys.stderr.write("drift: patches not up to date:\n  " + "\n  ".join(bad) + "\n")
        sys.exit(1)
    print("export: no drift")


def export_stack(repo, patches_root, dry_run=False, verify=True):
    base = require_base(repo)
    state = read_state(repo)
    merges = git(repo, "rev-list", "--merges", base + "..HEAD").strip()
    if merges:
        fail("the patch stack must be linear; found merge commit(s):\n" + merges)
    if not state and (not rev(repo, HEAD_REF) or mid_operation(repo)):
        fail("vscode/ does not hold a fully imported patch stack; refusing to rewrite patches/.\n"
              "Finish or abort the am/rebase in vscode/, or run ./dev/build.sh to re-import.")

    groups = {}
    order_seq = []
    for sha, patch in _stack_patches(repo, base):
        dest, name = target_of(patch, patches_root)
        if name.endswith(".patch") and _has_binary(patch):
            fail(f"refusing to export {os.path.join(dest, name)} ({sha[:8]}): it changes a binary file.\n"
                  f"git am cannot re-apply it. Put binary assets in src/<quality>/ instead.")
        order_seq.append((dest, name))
        groups.setdefault(dest, []).append([name, patch, sha])
    for dest, items in groups.items():
        seen = set()
        for item in items:
            name = item[0]
            if name in seen:
                root, ext = os.path.splitext(name)
                n = 2
                while f"{root}-{n}{ext}" in seen:
                    n += 1
                item[0] = f"{root}-{n}{ext}"
                sys.stderr.write(f"{dest}: duplicate name, writing {item[0]}\n")
            seen.add(item[0])
    imported = [d for d in read_stack_dirs(repo) if os.path.isdir(d)]
    for dest in groups:
        if imported and dest not in imported:
            quality, os_name = config_from_dirs(patches_root, imported)
            fail(f"{groups[dest][0][0]} targets {dest}, which this clone did not import "
                  f"({config_label(quality, os_name)}).\n"
                  f"Export it from a clone built for that directory, or tag the commit [user/...].")
    order = -1
    for dest, name in order_seq:
        rank = imported.index(dest) if dest in imported else order
        if rank < order:
            print(f"note: {os.path.join(dest, name)} is applied before {', '.join(imported[rank + 1:])} "
                  f"but sits above their commits; if the re-import fails, move it down "
                  f"(git rebase -i {BASE_REF}) or tag it [user/{stem(name)}].")
        order = max(order, rank)
    for d in imported:
        groups.setdefault(d, [])
    pending = _pending(state)

    contents = {}
    for dest, items in groups.items():
        for name, patch, sha in items:
            path = os.path.join(dest, name)
            contents[path] = json_content(repo, sha, path) if name.endswith(".json") else mailbox_content(patch)

    if dry_run:
        _report_drift(groups, pending, contents)
        return

    tip_before = rev(repo, HEAD_REF)
    before = {}
    for dest in groups:
        for f in os.listdir(dest):
            if f.endswith(PATCH_EXTENSIONS) or f == ".patches":
                with open(os.path.join(dest, f), "rb") as fh:
                    before[os.path.join(dest, f)] = fh.read()

    written = 0
    for dest, items in groups.items():
        keep = pending.get(dest, [])
        owned = {name for name, _, _ in items} | set(keep)
        dropped = [f for f in _on_disk(dest) if f not in owned]
        if dropped:
            sys.stderr.write(
                f"{dest}: removing patch file(s) that no commit in this clone produces "
                f"(dropped, skipped, or never imported):\n"
                + "".join(f"  {o}\n" for o in dropped))
        for f in _on_disk(dest):
            if f not in keep:
                os.remove(os.path.join(dest, f))
        manifest = os.path.join(dest, ".patches")
        if not items and not keep:
            if os.path.exists(manifest):
                os.remove(manifest)
            continue
        for name, _, _ in items:
            with open(os.path.join(dest, name), "wb") as f:
                f.write(contents[os.path.join(dest, name)].encode("utf-8"))
            written += 1
        with open(manifest, "w", newline="\n", encoding="utf-8") as pl:
            pl.write("".join(name + "\n" for name in [name for name, _, _ in items] + keep))
    rewritten = []
    for path, blob in before.items():
        try:
            with open(path, "rb") as fh:
                if fh.read() != blob:
                    rewritten.append(path)
        except OSError:
            pass
    if rewritten:
        sys.stderr.write("rewrote from this clone's commits:\n"
                         + "".join(f"  {p}\n" for p in sorted(rewritten)))

    if not state:
        egit.update_ref(repo=repo, ref=HEAD_REF, newvalue="HEAD")
    try:
        os.remove(os.path.join(git_dir(repo), "vscodium-patches-hash"))
    except OSError:
        pass
    print(f"exported {plural(written, 'patch')}")

    if state:
        left = sum(len(v) for v in pending.values())
        print(f"rebase in progress: {plural(left, 'pending patch')} left untouched; "
              f"./dev/rebase.sh --continue applies them")
    elif verify and git(repo, "status", "--porcelain").strip():
        print("working tree not clean; skipping round-trip self-verify to preserve your changes")
    elif verify:
        ordered = sorted(groups.keys(), key=lambda d: imported.index(d) if d in imported else len(imported))
        _verify_roundtrip(repo, patches_root, ordered, before, tip_before)


def _verify_roundtrip(repo, patches_root, present_dirs, before, tip_before):
    want_tree = git(repo, "rev-parse", "HEAD^{tree}").strip()
    want_head = git(repo, "rev-parse", "HEAD").strip()
    egit.update_ref(repo=repo, ref="refs/vscodium/pre-verify", newvalue=want_head)

    def restore():
        git_ok(repo, "am", "--abort")
        git_c(repo, "reset", "-q", "--hard", "refs/vscodium/pre-verify")
        for d in present_dirs:
            for f in os.listdir(d):
                if f.endswith(PATCH_EXTENSIONS) or f == ".patches":
                    os.remove(os.path.join(d, f))
        for path, blob in before.items():
            with open(path, "wb") as fh:
                fh.write(blob)
        if tip_before:
            egit.update_ref(repo=repo, ref=HEAD_REF, newvalue=tip_before)
        else:
            git_ok(repo, "update-ref", "-d", HEAD_REF)

    try:
        try:
            import_stack(repo, patches_root, dirs=present_dirs)
        except BaseException as exc:
            restore()
            fail(f"SELF-VERIFY FAILED: re-import errored ({exc}).\n"
                  f"vscode/ and patches/ were restored; nothing was written.")
        got_tree = git(repo, "rev-parse", "HEAD^{tree}").strip()
        if got_tree != want_tree:
            restore()
            fail("SELF-VERIFY FAILED: re-import does not reproduce HEAD.\n"
                  "vscode/ and patches/ were restored; nothing was written.")
        print("self-verify: re-import reproduces HEAD exactly (no drop); ./dev/verify.sh checks the tree itself")
    finally:
        git_ok(repo, "update-ref", "-d", "refs/vscodium/pre-verify")
