<!-- order: 36 -->

# How to work on the patches

VSCodium is VS Code plus the patches in `patches/`. In the `vscode/` clone made by `./dev/build.sh`, each patch is a git commit: edit them with git, then run `./dev/export.sh` to write them back. Build flags and prerequisites are in [howto-build.md](howto-build.md); what each patch does is in [patches.md](patches.md).

## Table of Contents

- [Layout](#layout)
- [Commands](#commands)
- [Modify a Patch](#patch-modify)
- [Add a Patch](#patch-add)
- [Remove a Patch](#patch-remove)
- [Update to a New VS Code](#patch-rebase)
  - [Resolve a Conflict](#patch-conflict)
  - [Recover](#patch-recover)
- [Normalize](#patch-normalize)
- [Tooling](#tooling)

## <a id="layout"></a>Layout

- `refs/vscodium/base` is the VS Code commit the patches apply to, the patches are the commits on top of it in apply order, and `refs/vscodium/head` is the last commit `patches/` reproduces
- the directories apply in order: `patches/`, `patches/insider/` (`VSCODE_QUALITY=insider`), `patches/<os>/` (`OS_NAME`), `patches/user/`
- each directory's `.patches` file lists its files in apply order; export rewrites it, and a `.patch` or `.json` file it does not list fails the import
- `NN-name.patch` is a git mailbox (`git format-patch`), applied with `git am --3way`
- `NN-name.json` lists paths to remove, `[{"action": "remove", "paths": [...]}]`, without storing their content
- the commit subject names the file: `[00-foo] description` exports to `00-foo.patch` in the directory it came from (`patches/` for a new commit), `[linux/00-foo]` to `patches/linux/` (from a clone built with `OS_NAME=linux`, export refuses it otherwise), `[user/foo]` and untagged commits to `patches/user/`
- binary changes go in `src/<quality>/`; export refuses them
- `patches/<os>/client/` and `patches/<os>/reh/[<arch>/]` (linux, alpine) are not in the stack: `build/<os>/package_*.sh` apply them to the build output
- `*.patch.yet` and `*.patch.no` are not in the stack either: `00-update-disable.patch.yet` is applied to the build tree when `DISABLE_UPDATE=yes`, `.no` files are parked; update them by hand

## <a id="commands"></a>Commands

- `./dev/build.sh`: clone VS Code and import the stack ([flags](howto-build.md#flags))
- `./dev/export.sh [--dry-run] [--no-verify]`: write the commits to `patches/`; `--dry-run` only reports drift, `--no-verify` skips the re-import check
- `./dev/rebase.sh [<VS Code tag or commit>] [--until <patch>] [--reject]`: replay the stack onto a commit (default: `upstream/<quality>.json`, or the clone's base when no stack is imported, as after a failed build)
- `./dev/rebase.sh --status | --continue | --skip [<patch>] | --redo | --abort [-f]`
- `./dev/verify.sh`: list the source imports the stack broke (a file or a `package.json` dependency a patch removed that other files still import)
- `./dev/normalize.sh`: re-export every OS of the current quality

The build leaves the branding (`!!APP_NAME!!` substituted, `product.json`, `src/<quality>/`) uncommitted on top of the stack; `git -C vscode reset --hard HEAD` drops it. Export reads the commits, not the tree.

## <a id="patch-modify"></a>Modify a Patch

- `git -C vscode log --oneline refs/vscodium/base..` lists the stack; the subject tag is the patch file
- edit in `vscode/`, `git -C vscode add` the files, then `git -C vscode commit --fixup <commit of the patch>`
- `git -C vscode -c sequence.editor=: rebase -i --autosquash refs/vscodium/base`
- `./dev/export.sh`
- to test: `./dev/build.sh -s` (`-is` on an insider clone), then `npm run watch` and `./scripts/code.sh` in `vscode/`

`git rebase -i` here is plain git: a conflict has markers, no `.rej`, and ends with `git rebase --continue`. The `.rej` files and `./dev/rebase.sh --continue` below belong to `./dev/rebase.sh` only. `git -C vscode apply ../patches/helper/settings.patch` turns off format on save while you edit; do not commit it.

## <a id="patch-add"></a>Add a Patch

- commit with the subject `[00-area-what-it-does] description`; `./dev/export.sh` writes `patches/00-area-what-it-does.patch`
- a commit tagged `[NN-name.json]` must only `git rm` files; it is written as `patches/NN-name.json`

## <a id="patch-remove"></a>Remove a Patch

- drop the commit with `git rebase -i refs/vscodium/base`, then `./dev/export.sh` deletes the file and updates `.patches`

## <a id="patch-rebase"></a>Update to a New VS Code

Rebase on the clone of the previous version, before changing `upstream/<quality>.json`, so git has both versions for the 3-way merge. When `./dev/build.sh` fails on a stale patch, its message prints the command to run. To skip the 3-way merge and get only `.rej` files, no markers, start with `--reject`, or set `git config vscodium.conflicts reject` once (in this repository or `--global`); the mode is fixed when the rebase starts.

- `./dev/rebase.sh <VS Code tag or commit>`
- on a conflict, resolve it (below) and `./dev/rebase.sh --continue`
- when it finishes: `./dev/export.sh`, then `./dev/verify.sh`
- repeat for the other OSes from the same machine, `OS_NAME` only picks the directory: `OS_NAME=<os> ./dev/rebase.sh <VS Code tag or commit>`, then `./dev/export.sh`
- point `upstream/<quality>.json` at the new commit (the rebase reminds you)
- insider, on the `insider` branch: `./dev/rebase.sh <commit>` with the latest commit (`curl -s https://update.code.visualstudio.com/api/update/darwin/insider/0000000000000000000000000000000000000000 | jq -r .version`), `./dev/export.sh`, then `./dev/build.sh -il` re-clones at whatever is latest by then and writes it to `upstream/insider.json`; rebase again if a newer one landed
- the finish report also checks the `client/` and `reh/` patches; they are plain diffs, fix a broken one by hand

`.json` patches never conflict: paths gone upstream are dropped and reported. `./dev/export.sh` works mid-rebase: it writes the patches rebased so far and leaves the pending ones untouched.

### <a id="patch-conflict"></a>Resolve a Conflict

The rebase stops on the first patch that does not apply and lists the files:

- resolve each file and `git add` it; `git rm` a file that is gone; with `--reject`, delete each `.rej` once its hunks are in
- `./dev/rebase.sh --continue` (not `git am --continue`) commits the resolution under the patch's name
- rerere is on: a conflict you already resolved is replayed and only needs review
- `--skip` drops the patch, `--redo` undoes the last applied or skipped patch and applies it again, `--until <patch>` (also with `--continue`) stops after that patch, `Ctrl-C` pauses between patches

### <a id="patch-recover"></a>Recover

- `./dev/rebase.sh --status`: applied, skipped and pending patches
- `./dev/rebase.sh --abort`, while the rebase is running: put `vscode/` and `patches/` back; once a patch has been rebased it asks for `-f`, which discards the rebased commits and the patches exported mid-rebase
- the state and a backup of `patches/` are in `vscode/.git/vscodium-rebase/`
- `./dev/build.sh -f` (`VSCODIUM_FORCE_RESET=1`) drops uncommitted edits, commits past `refs/vscodium/head` and a rebase in progress

## <a id="patch-normalize"></a>Normalize

`./dev/normalize.sh` rewrites the patches of every OS in the canonical format. Run it on a clone of the quality's base (without the prefix on a stable clone); it leaves `vscode/` on the last OS it exported, and the next `./dev/build.sh -s` (`-is` for insider) re-imports yours:

```bash
VSCODE_QUALITY=insider ./dev/normalize.sh
```

## <a id="tooling"></a>Tooling

`dev/{export,rebase,verify,normalize}.sh` run `python3 dev/lib/stack`, `./dev/build.sh` imports through `patches.sh`. `dev/lib/git.py` and `dev/lib/patches.py` are Electron's patch tooling (MIT, see `dev/lib/NOTICE`). The package reads as a pipeline: `layout.py` (which directories apply, in what order), `patchfile.py` (the `.patch` and `.json` formats and the subject tag), `apply.py` (one patch to one commit), then `importer.py` and `exporter.py`; the rebase is `state.py`, `conflicts.py` and `rebase.py`; `verify.py` is the import check, `repo.py` the git plumbing and `cli.py` the arguments.
