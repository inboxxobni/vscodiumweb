import argparse
import os

from .importer import import_stack
from .exporter import export_stack
from .rebase import rebase_abort, rebase_continue, rebase_redo, rebase_start, rebase_status
from .verify import verify_tree


def main(argv):
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo", default="vscode")
    common.add_argument("--patches", default="patches")
    common.add_argument("--quality", default=os.environ.get("VSCODE_QUALITY", ""))
    common.add_argument("--os", dest="os_name", default=os.environ.get("OS_NAME", ""))
    parser = argparse.ArgumentParser(description="VSCodium patch stack: import, export, rebase")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("import", parents=[common])
    sub.add_parser("verify", parents=[common])
    p = sub.add_parser("export", parents=[common])
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-verify", action="store_true")
    p = sub.add_parser("rebase", parents=[common])
    p.add_argument("onto", nargs="?", help="commit or tag to replay the patches onto "
                                            "(default: upstream/<quality>.json)")
    p.add_argument("--continue", dest="cont", action="store_true", help="go on after resolving a conflict")
    p.add_argument("--skip", nargs="?", const="", metavar="PATCH",
                   help="drop the current patch (or the named pending one) and go on")
    p.add_argument("--redo", action="store_true", help="undo the last applied patch and apply it again")
    p.add_argument("--abort", action="store_true", help="restore vscode/ as it was before the rebase")
    p.add_argument("--status", action="store_true")
    p.add_argument("--until", metavar="PATCH", help="stop after this patch")
    p.add_argument("--reject", action="store_true",
                   help="leave conflicts as .rej files instead of conflict markers "
                        "(default when git config vscodium.conflicts is reject)")
    p.add_argument("-f", "--force", action="store_true", help="with --abort: discard unexported patches")
    args = parser.parse_args(argv)

    if args.command == "import":
        import_stack(args.repo, args.patches, args.quality, args.os_name)
    elif args.command == "verify":
        verify_tree(args.repo)
    elif args.command == "export":
        export_stack(args.repo, args.patches, dry_run=args.dry_run, verify=not args.no_verify)
    elif args.status:
        rebase_status(args.repo)
    elif args.abort:
        rebase_abort(args.repo, args.force or os.environ.get("VSCODIUM_FORCE_RESET") == "1")
    elif args.redo:
        rebase_redo(args.repo)
    elif args.cont or args.skip is not None:
        rebase_continue(args.repo, args.until, skip=args.skip)
    else:
        rebase_start(args.repo, args.patches, args.onto, args.quality, args.os_name, args.until, args.reject)
