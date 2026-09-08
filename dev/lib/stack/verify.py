import json
import os
import re
import shutil
import subprocess
import tempfile

from .repo import fail, git, plural, require_base


IMPORT_RE = re.compile(
    r"""^\s*(?:import|export)\b[^;'"]*?\bfrom\s*(['"])([^'"\n]+)\1|^\s*import\s*(['"])([^'"\n]+)\3"""
    r"""|\bimport\(\s*(['"])([^'"\n]+)\5\s*\)|\brequire\(\s*(['"])([^'"\n]+)\7\s*\)""", re.M)

RESOLVE_SUFFIXES = ("", ".ts", ".tsx", ".d.ts", ".js", ".mjs", ".cjs", ".json", "/index.ts", "/index.js", "/index.d.ts")


def _scan_imports(root, files):
    declared = {}

    def packages(directory):
        if directory not in declared:
            names = set(packages(os.path.dirname(directory))) if directory else set()
            for pj in (os.path.join(directory, "package.json"),) + (("remote/package.json",) if not directory else ()):
                if os.path.isfile(os.path.join(root, pj)):
                    with open(os.path.join(root, pj), encoding="utf-8") as f:
                        data = json.load(f)
                    for key in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
                        names.update(data.get(key, {}))
            declared[directory] = names
        return declared[directory]

    dangling, bare = set(), set()
    for path in files:
        with open(os.path.join(root, path), encoding="utf-8", errors="replace") as f:
            text = f.read()
        for m in IMPORT_RE.finditer(text):
            spec = m.group(2) or m.group(4) or m.group(6) or m.group(8)
            if spec.startswith("."):
                base = os.path.normpath(os.path.join(os.path.dirname(path), spec))
                stems = (base, re.sub(r"\.js$", "", base)) if base.endswith(".js") else (base,)
                if not any(os.path.lexists(os.path.join(root, b + suffix)) for b in stems for suffix in RESOLVE_SUFFIXES):
                    dangling.add(f"{path}: imports {spec}, which does not exist")
            elif not spec.startswith(("/", "node:", "vs/")):
                bare.add((path, "/".join(spec.split("/")[:2 if spec.startswith("@") else 1])))
    return dangling, bare, packages


def _source_files(listing):
    return [p for p in listing.split("\0") if p.endswith((".ts", ".tsx", ".js", ".mjs", ".cjs")) and "/node_modules/" not in p]


def verify_tree(repo):
    base = require_base(repo)
    files = _source_files(git(repo, "ls-files", "-z", "--", "src", "extensions"))
    dangling, bare, declared = _scan_imports(repo, files)
    tmp = tempfile.mkdtemp()
    try:
        with subprocess.Popen(["git", "-C", repo, "archive", base, "src", "extensions", "package.json", "remote/package.json"],
                              stdout=subprocess.PIPE) as archive:
            subprocess.check_call(["tar", "-x", "-C", tmp], stdin=archive.stdout)
        upstream, _bare, declared_upstream = _scan_imports(
            tmp, _source_files(git(repo, "ls-tree", "-r", "-z", "--name-only", base, "--", "src", "extensions")))
        problems = dangling - upstream
        for path, pkg in bare:
            if pkg not in declared(os.path.dirname(path)) and pkg in declared_upstream(os.path.dirname(path)):
                problems.add(f"{path}: imports {pkg}, which the patch stack removed from package.json")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for line in sorted(problems):
        print(line)
    if problems:
        fail(f"{plural(len(problems), 'import')} broken by the patch stack (upstream's own {len(dangling & upstream)} left alone); "
              "fix the patch that removed the target, or extend the removal to the importer.")
    print(f"verify: {plural(len(files), 'file')}; no import broken by the patch stack "
          f"({plural(len(dangling & upstream), 'pre-existing upstream problem')} ignored)")
