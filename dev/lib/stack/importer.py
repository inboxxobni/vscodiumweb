import os

import git as egit

from .repo import BASE_REF, HEAD_REF, fail, git_c, git_dir, git_ok, plural, require_base
from .layout import build_dirs, patch_order, rebase_hint, write_stack_dirs
from .apply import apply_step
from .state import read_state, restore_from_state


def _abandon_stack(repo):
    git_ok(repo, "update-ref", "-d", HEAD_REF)
    git_c(repo, "reset", "-q", "--hard", BASE_REF)
    try:
        os.remove(os.path.join(git_dir(repo), "vscodium-patches-hash"))
    except OSError:
        pass


def _require_no_rebase(repo):
    state = read_state(repo)
    if not state:
        return
    if os.environ.get("VSCODIUM_FORCE_RESET") == "1":
        restore_from_state(repo, state)
        return
    fail("A rebase is in progress in vscode/ (./dev/rebase.sh --status).\n"
          "Finish it with ./dev/rebase.sh --continue, or drop it with ./dev/rebase.sh --abort.")


def import_stack(repo, patches_root, quality=None, os_name=None, dirs=None):
    require_base(repo)
    _require_no_rebase(repo)
    for op in (["am", "--abort"], ["rebase", "--quit"]):
        git_ok(repo, *op)
    git_ok(repo, "update-ref", "-d", HEAD_REF)
    git_c(repo, "reset", "-q", "--hard", BASE_REF)
    if dirs is None:
        dirs = build_dirs(patches_root, quality, os_name)
    write_stack_dirs(repo, dirs)
    try:
        for d in dirs:
            for name in patch_order(d):
                label = os.path.join(d, name)
                print(f"applying {label}")
                error, _ = apply_step(repo, d, name)
                if error:
                    git_ok(repo, "am", "--abort")
                    fail(f"failed to apply {label}:\n{error}"
                          f"Fix that file, or run `{rebase_hint(quality, os_name)}` to update the stack.")
    except BaseException:
        _abandon_stack(repo)
        raise
    egit.update_ref(repo=repo, ref=HEAD_REF, newvalue="HEAD")
    n = egit.get_commit_count(repo, BASE_REF + "..HEAD")
    print(f"imported {plural(n, 'commit')} ({BASE_REF}..HEAD)")
