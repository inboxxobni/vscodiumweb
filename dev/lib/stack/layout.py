import os

from .repo import fail, git_dir


PATCH_EXTENSIONS = (".patch", ".json")


def config_label(quality, os_name):
    return ", ".join(filter(None, (quality, os_name)))


def _stack_dirs_path(repo):
    return os.path.join(git_dir(repo), "vscodium-stack-dirs")


def read_stack_dirs(repo):
    try:
        with open(_stack_dirs_path(repo), encoding="utf-8") as f:
            return [ln.strip() for ln in f if ln.strip()]
    except OSError:
        return []


def write_stack_dirs(repo, dirs):
    with open(_stack_dirs_path(repo), "w", encoding="utf-8") as f:
        f.write("".join(d + "\n" for d in dirs))


def build_dirs(patches_root, quality, os_name):
    dirs = [patches_root]
    if quality == "insider":
        dirs.append(os.path.join(patches_root, "insider"))
    if os_name:
        dirs.append(os.path.join(patches_root, os_name))
    dirs.append(os.path.join(patches_root, "user"))
    return [d for d in dirs if os.path.isdir(d)]


def user_dir(patches_root):
    return os.path.join(patches_root, "user")


def config_from_dirs(patches_root, dirs):
    names = {os.path.relpath(d, patches_root) for d in dirs} - {".", "insider", "user"}
    quality = "insider" if os.path.join(patches_root, "insider") in dirs else "stable"
    return quality, names.pop() if names else ""


def rebase_hint(quality, os_name):
    env = [f"OS_NAME={os_name}"] if os_name else []
    if quality == "insider":
        env.insert(0, "VSCODE_QUALITY=insider")
    return " ".join(env + ["./dev/rebase.sh"])


def patch_order(d):
    manifest = os.path.join(d, ".patches")
    ondisk = sorted(f for f in os.listdir(d) if f.endswith(PATCH_EXTENSIONS))
    if not os.path.exists(manifest):
        return ondisk
    with open(manifest, encoding="utf-8") as f:
        listed = [ln.rstrip("\n") for ln in f]
    for name in listed:
        if (not name or name != name.strip() or os.path.basename(name) != name
                or not name.endswith(PATCH_EXTENSIONS)):
            fail(f"{manifest} has an invalid entry: {name!r}; run ./dev/export.sh.")
        if not os.path.exists(os.path.join(d, name)):
            fail(f"{manifest} lists a file not on disk: {name}\n"
                  f"Remove that line, or restore the file "
                  f"(git checkout -- {os.path.join(d, name)}).")
    unlisted = [f for f in ondisk if f not in listed]
    if unlisted:
        fail(f"{d}: file(s) missing from .patches: {', '.join(unlisted)}.\n"
              f"Add them to {manifest} in apply order, or remove the file(s).")
    return listed


def stem(name):
    return name[:-len(".patch")] if name.endswith(".patch") else name


def matches(wanted, d, name):
    return wanted in (name, stem(name), os.path.join(d, name))
