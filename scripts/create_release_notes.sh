#!/usr/bin/env bash
# Write a markdown release note for each deployable component (and optional shared).
#
#   ./scripts/create_release_notes.sh
#   ./scripts/create_release_notes.sh api ui maf
#   BASE=v1.0.0 ./scripts/create_release_notes.sh
#   OUT_DIR=./filechange_20260828_041422 ./scripts/create_release_notes.sh
#
# Default output: dist/release-notes/<YYYYMMDD_HHMMSS>/
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

folder_for() {
  case "$1" in
    ui) echo UI ;;
    api) echo ipp_agentic_api ;;
    document) echo document-processing-mcp ;;
    voice) echo voice_enable_mcp ;;
    maf) echo central-agentic-flow ;;
    shared) echo "" ;;
    *) return 1 ;;
  esac
}

label_for() {
  case "$1" in
    ui) echo "UI (Gradio)" ;;
    api) echo "ipp_agentic_api (gateway API)" ;;
    document) echo "document-processing-mcp" ;;
    voice) echo "voice_enable_mcp" ;;
    maf) echo "central-agentic-flow (MAF)" ;;
    shared) echo "shared (docs, scripts, samples, prompts)" ;;
    *) echo "$1" ;;
  esac
}

resolve_name() {
  key="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  case "$key" in
    ui|ui-app) echo ui ;;
    api|ip_api|ip-api|ipp_agentic_api|ipp-agentic-api) echo api ;;
    document|document-processing-mcp|document-mcp) echo document ;;
    voice|voice_enable_mcp|voice-mcp) echo voice ;;
    maf|central-agentic-flow|central_agentic_flow) echo maf ;;
    shared|root|docs|scripts) echo shared ;;
    *) echo "Unknown component: $1" >&2; return 2 ;;
  esac
}

pyproject_version() {
  local file="$1"
  if [[ -f "$file" ]]; then
    sed -n 's/^version = "\([^"]*\)".*/\1/p' "$file" | head -n 1
  fi
}

NAMES=""
if [[ $# -eq 0 ]] || [[ "${1:-}" == "all" ]]; then
  NAMES="ui api document voice maf shared"
else
  for arg in "$@"; do
    NAMES="$NAMES $(resolve_name "$arg")"
  done
fi

STAMP="${STAMP:-$(date '+%Y%m%d_%H%M%S')}"
OUT_DIR="${OUT_DIR:-$ROOT/dist/release-notes/$STAMP}"
mkdir -p "$OUT_DIR"

IN_GIT=0
if git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  IN_GIT=1
fi

BRANCH=""
HEAD=""
BASE_REF="${BASE:-}"
if [[ "$IN_GIT" -eq 1 ]]; then
  BRANCH="$(git -C "$ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  HEAD="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || true)"
  if [[ -z "$BASE_REF" ]]; then
    BASE_REF="$(git -C "$ROOT" describe --tags --abbrev=0 2>/dev/null || true)"
  fi
  if [[ -z "$BASE_REF" ]] && git -C "$ROOT" rev-parse --verify origin/main >/dev/null 2>&1; then
    BASE_REF="origin/main"
  fi
  if [[ -z "$BASE_REF" ]] && git -C "$ROOT" rev-parse --verify main >/dev/null 2>&1; then
    BASE_REF="main"
  fi
fi

write_component() {
  local name="$1"
  local folder
  folder="$(folder_for "$name")"
  local label
  label="$(label_for "$name")"
  local outfile="$OUT_DIR/${name}.md"
  local version=""
  local pathspec=()

  if [[ "$name" == "shared" ]]; then
    version="$(pyproject_version "$ROOT/pyproject.toml")"
    pathspec=(docs scripts samples prompts postman README.md .env.example uv.lock pyproject.toml)
  else
    version="$(pyproject_version "$ROOT/$folder/pyproject.toml")"
    pathspec=("$folder")
  fi

  {
    echo "# Release notes — $label"
    echo
    echo "| Field | Value |"
    echo "|-------|-------|"
    echo "| Generated | $(date '+%Y-%m-%d %H:%M:%S %z') |"
    echo "| Stamp | $STAMP |"
    echo "| Component | \`$name\` |"
    if [[ -n "$folder" ]]; then
      echo "| Folder | \`$folder/\` |"
    fi
    echo "| Version (pyproject) | ${version:-n/a} |"
    if [[ "$IN_GIT" -eq 1 ]]; then
      echo "| Branch | \`${BRANCH:-n/a}\` |"
      echo "| HEAD | \`${HEAD:-n/a}\` |"
      echo "| Compare from | \`${BASE_REF:-n/a}\` |"
    else
      echo "| Git | not a git work tree |"
    fi
    echo
    echo "## Summary"
    echo
    echo "Changes for this component since the compare ref (tags / origin/main / main), plus uncommitted files."
    echo

    if [[ "$IN_GIT" -eq 1 ]]; then
      echo "## Commits"
      echo
      if [[ -n "$BASE_REF" ]] && git -C "$ROOT" rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
        local log
        log="$(git -C "$ROOT" log --pretty=format:'- `%h` %ad %s' --date=short "${BASE_REF}..HEAD" -- "${pathspec[@]}" || true)"
        if [[ -n "$log" ]]; then
          echo "$log"
        else
          echo "_No commits in range for these paths._"
        fi
      else
        local log
        log="$(git -C "$ROOT" log -20 --pretty=format:'- `%h` %ad %s' --date=short -- "${pathspec[@]}" || true)"
        if [[ -n "$log" ]]; then
          echo "$log"
        else
          echo "_No commits for these paths._"
        fi
      fi
      echo
      echo "## Files changed (committed range)"
      echo
      if [[ -n "$BASE_REF" ]] && git -C "$ROOT" rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
        local files
        files="$(git -C "$ROOT" diff --name-status "${BASE_REF}...HEAD" -- "${pathspec[@]}" || true)"
        if [[ -n "$files" ]]; then
          echo '```'
          echo "$files"
          echo '```'
        else
          echo "_None._"
        fi
      else
        echo "_No compare ref; skipped._"
      fi
      echo
      echo "## Uncommitted (staged, unstaged, untracked)"
      echo
      local dirty
      dirty="$(git -C "$ROOT" status --short -- "${pathspec[@]}" || true)"
      if [[ -n "$dirty" ]]; then
        echo '```'
        echo "$dirty"
        echo '```'
      else
        echo "_Clean._"
      fi
    else
      echo "## Files in folder"
      echo
      echo '```'
      if [[ "$name" == "shared" ]]; then
        printf '%s\n' "${pathspec[@]}"
      else
        find "$ROOT/$folder" -type f \
          ! -path '*/.venv/*' ! -path '*/__pycache__/*' ! -path '*/dist/*' \
          ! -path '*/.git/*' | sed "s|^$ROOT/||" | sort
      fi
      echo '```'
    fi
    echo
  } > "$outfile"
  echo "Wrote $outfile"
}

INDEX="$OUT_DIR/INDEX.md"
{
  echo "# Release notes index"
  echo
  echo "Generated $(date '+%Y-%m-%d %H:%M:%S %z')  "
  echo "Stamp: \`$STAMP\`  "
  echo "Output: \`$OUT_DIR\`"
  echo
  echo "| Component | File |"
  echo "|-----------|------|"
} > "$INDEX"

for name in $NAMES; do
  write_component "$name"
  echo "| $(label_for "$name") | [\`$name.md\`]($name.md) |" >> "$INDEX"
done

echo
echo "Release notes: $OUT_DIR"
echo "Index: $INDEX"
