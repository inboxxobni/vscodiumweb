import json
import os
import re
from email.header import decode_header, make_header

import git as egit
from patches import PATCH_DIR_PREFIX, PATCH_FILENAME_PREFIX

from .repo import fail, git
from .layout import PATCH_EXTENSIONS, stem, user_dir


TAG_RE = re.compile(r"^\[([A-Za-z0-9][\w.-]*(?:/[A-Za-z0-9][\w.-]*)*)\] ?")

SUBJECT_WIDTH = 78


def location(d, name):
    return f"{PATCH_DIR_PREFIX}{d}\n{PATCH_FILENAME_PREFIX}{name}\n"


def is_mailbox(path):
    with open(path, "rb") as f:
        return f.readline().startswith(b"From ")


def _decode_subject(subject):
    if "=?" not in subject:
        return subject
    try:
        return str(make_header(decode_header(subject)))
    except (UnicodeDecodeError, ValueError):
        return subject


def _subject_span(lines):
    for i, line in enumerate(lines):
        if line.startswith("Subject: "):
            subject = line[len("Subject: "):].strip()
            j = i + 1
            while j < len(lines) and lines[j][:1] in (" ", "\t") and lines[j].strip():
                subject += " " + lines[j].strip()
                j += 1
            return i, j, _decode_subject(subject)
        if line.startswith(("diff -", "---", "\n", "\r\n")):
            break
    return None


def _fold_subject(subject):
    lines, line = [], "Subject:"
    for word in subject.split(" "):
        if line == "Subject:" or len(line) + 1 + len(word) <= SUBJECT_WIDTH:
            line += " " + word
        else:
            lines.append(line + "\n")
            line = " " + word
    lines.append(line + "\n")
    return lines


def _header_lines(lines):
    for line in lines:
        if line.startswith(("diff -", "---")):
            return
        yield line


def _trailer(lines, prefix):
    for line in _header_lines(lines):
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return None


def target_of(patch, patches_root):
    span = _subject_span(patch)
    subject = span[2] if span else ""
    tag = TAG_RE.match(subject)
    trailer_dir = _trailer(patch, PATCH_DIR_PREFIX)
    trailer_name = _trailer(patch, PATCH_FILENAME_PREFIX)
    if tag:
        parent, _, name = tag.group(1).rpartition("/")
        if not name.endswith(PATCH_EXTENSIONS):
            name += ".patch"
        if parent:
            dest = os.path.join(patches_root, *parent.split("/"))
        else:
            dest = trailer_dir or patches_root
        if not subject[tag.end():].strip():
            fail(f"commit {subject!r} has no description after its [{tag.group(1)}] tag.")
    elif trailer_name:
        dest, name = trailer_dir or user_dir(patches_root), trailer_name
    else:
        dest, name = user_dir(patches_root), egit.munge_subject_to_filename(subject)
    patches_abs = os.path.abspath(patches_root)
    inside = os.path.relpath(os.path.abspath(dest), patches_abs).split(os.sep)[0] != ".."
    if os.path.isabs(dest) or not inside or not os.path.isdir(dest):
        fail(f"no such patch directory for {subject!r}: {dest}")
    if os.path.basename(name) != name or name in (".", "..") or not re.match(r"^[\w.-]+$", name):
        fail(f"refusing unsafe patch filename: {name!r}")
    return dest, name


def read_mailbox(d, name):
    with open(os.path.join(d, name), encoding="utf-8", newline="") as f:
        lines = f.readlines()
    span = _subject_span(lines)
    if not span:
        fail(f"{os.path.join(d, name)}: no Subject: line.")
    i, j, subject = span
    if not subject.startswith(f"[{stem(name)}]"):
        subject = f"[{stem(name)}] {subject}"
    lines[i:j] = [f"Subject: {subject}\n"]
    out, located = [], False
    for line in lines:
        if not located and line.startswith(("diff -", "---")):
            out.append(location(d, name))
            located = True
        out.append(line)
    return "".join(out)


def mailbox_content(patch):
    i, j, subject = _subject_span(patch)
    tag = TAG_RE.match(subject)
    if tag:
        subject = subject[tag.end():]
    lines = patch[:i] + _fold_subject(subject) + patch[j:]
    return egit.join_patch(lines)


def json_paths(path):
    with open(path, encoding="utf-8") as f:
        actions = json.load(f)
    if not isinstance(actions, list):
        raise ValueError(f"{path}: expected a list of actions, got {type(actions).__name__}")
    paths = []
    for action in actions:
        if not isinstance(action, dict) or action.get("action") != "remove":
            raise ValueError(f"{path}: each action must be {{\"action\": \"remove\", \"paths\": [...]}}")
        rels = action.get("paths")
        if not isinstance(rels, list):
            raise ValueError(f"{path}: a remove action needs a \"paths\" list")
        for rel in rels:
            if not isinstance(rel, str) or os.path.isabs(rel) or os.path.normpath(rel).split(os.sep)[0] in (".", "..", ".git"):
                raise ValueError(f"{path}: invalid removal path: {rel!r}")
            if rel not in paths:
                paths.append(rel)
    return paths


def json_content(repo, sha, path):
    fields = git(repo, "diff-tree", "--no-commit-id", "-r", "--name-status", "-z", sha).split("\0")
    deleted, other, i = set(), [], 0
    while i < len(fields) - 1:
        status, name = fields[i], fields[i + 1]
        i += 3 if status[:1] in "RC" else 2
        if status == "D":
            deleted.add(name)
        else:
            other.append(name)
    if other:
        fail(f"{path} ({sha[:8]}) must only delete files; it also changes:\n"
              + "".join(f"  {p}\n" for p in other)
              + "Move those changes to a .patch commit.")
    trees = {}

    def files_under(d):
        if d not in trees:
            listed = git(repo, "ls-tree", "-r", "--name-only", "-z", sha + "^", "--", d).split("\0")
            trees[d] = [f for f in listed if f.startswith(d + "/")]
        return trees[d]

    def holds(entry):
        if entry in deleted:
            return True
        files = files_under(entry)
        return bool(files) and all(f in deleted for f in files)

    def children(d):
        return {f[len(d) + 1:].split("/")[0] for f in files_under(d)}

    def covered_by(p):
        return files_under(p) or [p]

    try:
        previous = json_paths(path)
    except (OSError, ValueError, KeyError):
        previous = []
    entries = [p for p in previous if holds(p)]
    covered = {f for p in entries for f in covered_by(p)}
    for f in sorted(deleted):
        if f in covered:
            continue
        parts = f.split("/")
        chosen = f
        for k in range(1, len(parts)):
            d = "/".join(parts[:k])
            if any(p == d or p.startswith(d + "/") for p in previous):
                continue
            if len(children(d)) > 1 and all(x in deleted for x in files_under(d)):
                chosen = d
                break
        entries.append(chosen)
        covered.update(covered_by(chosen))
    return json.dumps([{"action": "remove", "paths": entries}], indent=2) + "\n"


def _diff_sections(text):
    sections = {}
    for chunk in re.split(r"(?m)^(?=diff --git )", text)[1:]:
        for line in chunk.splitlines():
            if line.startswith("@@"):
                break
            for prefix in ("--- a/", "+++ b/"):
                if line.startswith(prefix):
                    sections[line[len(prefix):]] = chunk
    return sections


def patch_sections(d, name):
    with open(os.path.join(d, name), encoding="utf-8", newline="") as f:
        return _diff_sections(f.read())
