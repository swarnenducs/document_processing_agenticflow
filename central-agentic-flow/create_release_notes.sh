#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT="$(cd "$HERE/.." && pwd)"
if [[ -f "$PARENT/scripts/create_release_notes.sh" ]]; then
  exec "$PARENT/scripts/create_release_notes.sh" maf "$@"
fi
echo "Monorepo helper missing. Run from the combined repo: scripts/create_release_notes.sh maf" >&2
exit 1
