#!/usr/bin/env bash
# Aperio v2 installer. No network, no sudo, no settings rewrite.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="$(python3 -c 'import re,sys; print(re.search(r"__version__ = \"([^\"]+)\"", open(sys.argv[1]).read()).group(1))' "$ROOT/src/aperio/__init__.py")"
PREFIX="${APERIO_PREFIX:-$HOME/.local}"
SKILL_HOME="${APERIO_SKILL_HOME:-$HOME/.claude/skills}"
DO_SKILL=1
DRY_RUN=0
UNINSTALL=0
CHECK=0
UPDATE=0
ROLLBACK=0

usage() {
  cat <<'EOF'
Usage: install.sh [options]

  --prefix DIR     install prefix (default: $HOME/.local)
  --no-skill       do not install the /aperio skill
  --dry-run        print actions without changing anything
  --check          report installed and source versions; no writes
  --update         back up the installed library, then install
  --rollback       restore the most recent update backup
  --uninstall      remove files installed by this script
  -h, --help       show this help
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --prefix) PREFIX="${2:?--prefix needs a directory}"; shift 2 ;;
    --no-skill) DO_SKILL=0; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --check) CHECK=1; shift ;;
    --update) UPDATE=1; shift ;;
    --rollback) ROLLBACK=1; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "install.sh: unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$PREFIX" in
  ""|"/"|".") echo "install.sh: refusing unsafe prefix: $PREFIX" >&2; exit 2 ;;
esac
PREFIX="$(python3 -c 'import os,sys; print(os.path.realpath(os.path.expanduser(sys.argv[1])))' "$PREFIX")"
case "$PREFIX" in
  ""|"/"|".") echo "install.sh: refusing unsafe prefix: $PREFIX" >&2; exit 2 ;;
esac
if [ "$DRY_RUN" -eq 0 ] && [ "$CHECK" -eq 0 ] && [ "$ROLLBACK" -eq 0 ]; then
  mkdir -p "$PREFIX"
fi
LIB="$PREFIX/share/aperio"
BIN="$PREFIX/bin/aperio"
SKILL_DIR="$SKILL_HOME/aperio"
CODEX_SKILL_DIR="$HOME/.codex/skills/aperio"
COMMAND_DIR="$HOME/.claude/commands"
COMMAND_FILE="$COMMAND_DIR/aperio.md"
MARKER="aperio-v2-managed"

if [ "$CHECK" -eq 1 ]; then
  if [ -f "$LIB/VERSION" ]; then
    INSTALLED="$(cat "$LIB/VERSION")"
  else
    INSTALLED="not installed"
  fi
  printf 'installed: %s\n' "$INSTALLED"
  printf 'source:    %s\n' "$VERSION"
  if [ "$INSTALLED" = "$VERSION" ] && [ -x "$BIN" ]; then
    exit 0
  fi
  exit 1
fi

if [ "$ROLLBACK" -eq 1 ]; then
  if [ ! -d "$PREFIX/share" ]; then
    echo "install.sh: no update backup found under $PREFIX/share" >&2
    exit 2
  fi
  BACKUP="$(find "$PREFIX/share" -maxdepth 1 -type d -name 'aperio.backup.*' -print 2>/dev/null | sort | tail -1)"
  if [ -z "$BACKUP" ] || [ ! -f "$BACKUP/$MARKER" ]; then
    echo "install.sh: no valid update backup found under $PREFIX/share" >&2
    exit 2
  fi
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "would: remove $LIB"
    echo "would: restore $BACKUP to $LIB"
    exit 0
  fi
  failed_lib="$LIB.rollback-old.$$"
  rm -rf "$failed_lib"
  if [ -e "$LIB" ] && ! mv "$LIB" "$failed_lib" 2>/dev/null; then
    echo "install.sh: could not move the current $LIB aside" >&2
    exit 2
  fi
  if mv "$BACKUP" "$LIB" 2>/dev/null; then
    rm -rf "$failed_lib"
    echo "rolled back to $(cat "$LIB/VERSION")"
  else
    if [ -e "$failed_lib" ]; then mv "$failed_lib" "$LIB" 2>/dev/null || true; fi
    echo "install.sh: could not restore $BACKUP to $LIB" >&2
    exit 2
  fi
  exit 0
fi

if [ "$DO_SKILL" -eq 1 ] && [ -f "$SKILL_DIR/SKILL.md" ] && [ ! -f "$SKILL_DIR/$MARKER" ]; then
  echo "install.sh: refusing to overwrite existing $SKILL_DIR/SKILL.md" >&2
  echo "Move it aside or use --no-skill." >&2
  exit 2
fi

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf 'would: %s\n' "$*"
  else
    "$@"
  fi
}

write_text() {
  local target="$1" value="$2"
  if [ "$DRY_RUN" -eq 1 ]; then
    printf 'would: write %s\n' "$target"
  else
    mkdir -p "$(dirname "$target")"
    printf '%s\n' "$value" > "$target"
  fi
}

BACKUP=""
restore_update() {
  status=$?
  if [ -n "$BACKUP" ] && [ -d "$BACKUP" ]; then
    failed_lib="$LIB.failed-restore.$$"
    rm -rf "$failed_lib"
    if [ -e "$LIB" ] && ! mv "$LIB" "$failed_lib" 2>/dev/null; then
      echo "update failed; could not move the partial $LIB aside" >&2
    elif mv "$BACKUP" "$LIB" 2>/dev/null; then
      rm -rf "$failed_lib"
      echo "update failed; restored $LIB from backup" >&2
    else
      if [ -e "$failed_lib" ]; then mv "$failed_lib" "$LIB" 2>/dev/null || true; fi
      echo "update failed; could not restore $LIB from backup" >&2
    fi
  fi
  exit "$status"
}
if [ "$UPDATE" -eq 1 ] && [ -f "$LIB/$MARKER" ]; then
  BACKUP="$LIB.backup.$(date -u +%Y%m%dT%H%M%SZ).$$.$RANDOM"
  run cp -R "$LIB" "$BACKUP"
  if [ "$DRY_RUN" -eq 0 ]; then
    # keep the 5 newest backups (incl. the just-created one, which is excluded
    # from the candidate list); --rollback restores the newest one
    find "$PREFIX/share" -maxdepth 1 -type d -name 'aperio.backup.*' \
      ! -path "$BACKUP" -print 2>/dev/null \
      | sort -r | tail -n +5 | while IFS= read -r old_backup; do
          rm -rf "$old_backup"
        done
  fi
  trap restore_update ERR
fi

if [ "$UNINSTALL" -eq 1 ]; then
  if [ -f "$LIB/$MARKER" ]; then
    run rm -rf "$LIB"
    if [ "$DRY_RUN" -eq 0 ]; then echo "removed $LIB"; fi
  else
    echo "not removing $LIB: marker missing"
  fi
  if [ -f "$BIN" ] && grep -q "Aperio v2" "$BIN" 2>/dev/null; then
    run rm -f "$BIN"
    if [ "$DRY_RUN" -eq 0 ]; then echo "removed $BIN"; fi
  fi
  if [ "$DO_SKILL" -eq 1 ] && [ -f "$SKILL_DIR/$MARKER" ]; then
    run rm -f "$SKILL_DIR/SKILL.md" "$SKILL_DIR/VERSION" "$SKILL_DIR/$MARKER"
    if [ "$DRY_RUN" -eq 0 ]; then rmdir "$SKILL_DIR" 2>/dev/null || true; echo "removed Aperio files in $SKILL_DIR"; fi
  fi
  if [ "$DO_SKILL" -eq 1 ] && [ -f "$CODEX_SKILL_DIR/$MARKER" ]; then
    run rm -f "$CODEX_SKILL_DIR/SKILL.md" "$CODEX_SKILL_DIR/VERSION" "$CODEX_SKILL_DIR/$MARKER"
    if [ "$DRY_RUN" -eq 0 ]; then rmdir "$CODEX_SKILL_DIR" 2>/dev/null || true; echo "removed Aperio files in $CODEX_SKILL_DIR"; fi
  fi
  if [ "$DO_SKILL" -eq 1 ] && [ -f "$COMMAND_FILE" ] && grep -q "Aperio v2" "$COMMAND_FILE" 2>/dev/null; then
    run rm -f "$COMMAND_FILE"
    if [ "$DRY_RUN" -eq 0 ]; then echo "removed $COMMAND_FILE"; fi
  fi
  exit 0
fi

run mkdir -p "$LIB" "$PREFIX/bin"
run rm -rf "$LIB/aperio"
run cp -R "$ROOT/src/aperio" "$LIB/aperio"
if [ "$DRY_RUN" -eq 0 ]; then
  find "$LIB/aperio" -type d -name __pycache__ -prune -exec rm -rf {} +
  find "$LIB/aperio" -type f -name '*.pyc' -delete
fi
write_text "$LIB/VERSION" "$VERSION"
write_text "$LIB/$MARKER" "$MARKER"
run chmod 755 "$PREFIX/bin"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "would: write $BIN"
else
  cat > "$PREFIX/bin/.aperio-wrapper.tmp" <<'EOF'
#!/usr/bin/env python3
"""Aperio v2 launcher. Installed by install.sh."""
import sys
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "share" / "aperio"))
from aperio.cli import main
raise SystemExit(main())
EOF
  mv "$PREFIX/bin/.aperio-wrapper.tmp" "$BIN"
  chmod 755 "$BIN"
fi

if [ "$DO_SKILL" -eq 1 ]; then
  run mkdir -p "$SKILL_DIR"
  run cp "$ROOT/skill/aperio/SKILL.md" "$SKILL_DIR/SKILL.md"
  write_text "$SKILL_DIR/VERSION" "$VERSION"
  write_text "$SKILL_DIR/$MARKER" "$MARKER"
  if [ -f "$COMMAND_FILE" ] && grep -q "Aperio v2" "$COMMAND_FILE" 2>/dev/null; then
    run rm -f "$COMMAND_FILE"
    if [ "$DRY_RUN" -eq 0 ]; then echo "removed legacy $COMMAND_FILE"; fi
  fi
  if [ -d "$HOME/.codex" ]; then
    CODEX_DIR="$HOME/.codex/skills/aperio"
    run mkdir -p "$CODEX_DIR"
    run cp "$ROOT/skill/aperio/SKILL.md" "$CODEX_DIR/SKILL.md"
    write_text "$CODEX_DIR/VERSION" "$VERSION"
    write_text "$CODEX_DIR/$MARKER" "$MARKER"
  fi
fi

if [ "$DRY_RUN" -eq 1 ]; then
  echo "dry run: no files changed"
  exit 0
fi
trap - ERR
echo "installed Aperio $VERSION"
echo "  binary: $BIN"
if [ "$DO_SKILL" -eq 1 ]; then
  echo "  skill:  $SKILL_DIR"
fi
case ":$PATH:" in
  *":$PREFIX/bin:"*) ;;
  *) echo "  note: add $PREFIX/bin to PATH" ;;
esac
