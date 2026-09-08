#!/usr/bin/env bash
#
# DEPRECATED. See docs/howto-patches.md.

echo "dev/patch.sh is deprecated — see docs/howto-patches.md." >&2

if [[ -n "${1:-}" ]]; then
  echo >&2
  echo "To regenerate '${1}', edit its commit, then run ./dev/export.sh." >&2
fi

exit 2
