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

usage() {
  cat <<'EOF'
Usage: install.sh [options]

  --prefix DIR     install prefix (default: $HOME/.local)
  --no-skill       do not install the /aperio skill
  --dry-run        print actions without changing anything
  --uninstall      remove files installed by this script
  -h, --help       show this help
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --prefix) PREFIX="${2:?--prefix needs a directory}"; shift 2 ;;
    --no-skill) DO_SKILL=0; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "install.sh: unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$PREFIX" in
  ""|"/"|".") echo "install.sh: refusing unsafe prefix: $PREFIX" >&2; exit 2 ;;
esac
if [ "$DRY_RUN" -eq 0 ]; then
  mkdir -p "$PREFIX"
  PREFIX="$(cd "$PREFIX" && pwd)"
else
  PREFIX="$(cd "$PREFIX" 2>/dev/null && pwd || printf '%s' "$PREFIX")"
fi
LIB="$PREFIX/share/aperio"
BIN="$PREFIX/bin/aperio"
SKILL_DIR="$SKILL_HOME/aperio"
COMMAND_DIR="$HOME/.claude/commands"
COMMAND_FILE="$COMMAND_DIR/aperio.md"
MARKER="aperio-v2-managed"

if [ "$DO_SKILL" -eq 1 ] && [ -f "$COMMAND_FILE" ] && ! grep -q "Aperio v2" "$COMMAND_FILE" 2>/dev/null; then
  echo "install.sh: refusing to overwrite existing $COMMAND_FILE" >&2
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

if [ "$UNINSTALL" -eq 1 ]; then
  if [ -f "$LIB/$MARKER" ]; then
    run rm -rf "$LIB"
    echo "removed $LIB"
  else
    echo "not removing $LIB: marker missing"
  fi
  if [ -f "$BIN" ] && grep -q "Aperio v2" "$BIN" 2>/dev/null; then
    run rm -f "$BIN"
    echo "removed $BIN"
  fi
  if [ "$DO_SKILL" -eq 1 ] && [ -f "$SKILL_DIR/$MARKER" ]; then
    run rm -rf "$SKILL_DIR"
    echo "removed $SKILL_DIR"
  fi
  if [ "$DO_SKILL" -eq 1 ] && [ -f "$COMMAND_FILE" ] && grep -q "Aperio v2" "$COMMAND_FILE" 2>/dev/null; then
    run rm -f "$COMMAND_FILE"
    echo "removed $COMMAND_FILE"
  fi
  exit 0
fi

run mkdir -p "$LIB" "$PREFIX/bin"
run rm -rf "$LIB/aperio"
run cp -R "$ROOT/src/aperio" "$LIB/aperio"
write_text "$LIB/VERSION" "$VERSION"
write_text "$LIB/$MARKER" "$MARKER"
run chmod 755 "$PREFIX/bin"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "would: write $BIN"
else
  cat > "$PREFIX/bin/.aperio-wrapper.tmp" <<EOF
#!/usr/bin/env python3
"""Aperio v2 launcher. Installed by install.sh."""
import sys
sys.path.insert(0, "$LIB")
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
  run mkdir -p "$COMMAND_DIR"
  run cp "$ROOT/commands/aperio.md" "$COMMAND_FILE"
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
echo "installed Aperio $VERSION"
echo "  binary: $BIN"
if [ "$DO_SKILL" -eq 1 ]; then
  echo "  skill:  $SKILL_DIR"
fi
case ":$PATH:" in
  *":$PREFIX/bin:"*) ;;
  *) echo "  note: add $PREFIX/bin to PATH" ;;
esac
