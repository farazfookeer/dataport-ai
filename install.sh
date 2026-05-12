#!/usr/bin/env bash
#
# Dataport AI for Tableau — one-time installer for macOS and Linux.
#
# Run this once: ./install.sh
# It will set up everything and create a double-clickable launcher.
#

set -e
cd "$(dirname "$0")"

# ──────────────────────────── helpers ────────────────────────────

bold()   { printf "\033[1m%s\033[0m\n" "$1"; }
green()  { printf "\033[32m%s\033[0m\n" "$1"; }
red()    { printf "\033[31m%s\033[0m\n" "$1"; }
yellow() { printf "\033[33m%s\033[0m\n" "$1"; }
hr()     { printf "──────────────────────────────────────────────\n"; }

# ──────────────────────────── banner ─────────────────────────────

clear
bold "📊 Dataport AI for Tableau — Setup"
hr
echo "This installer will:"
echo "  1. Check that Python 3.10+ is available"
echo "  2. Create an isolated Python environment in ./.venv"
echo "  3. Install the dependencies (~200MB, takes 1–2 minutes)"
echo "  4. Create a double-clickable launcher: 'Dataport AI.command'"
echo
echo "You only need to run this once."
hr
echo

# ──────────────────────────── Python check ───────────────────────

if ! command -v python3 >/dev/null 2>&1; then
    red "✗ Python 3 not found."
    echo
    echo "Install it from https://python.org/downloads (pick the latest 3.11 or 3.12)"
    echo "then run this script again."
    exit 1
fi

PY_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
PY_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    red "✗ Python ${PY_MAJOR}.${PY_MINOR} is too old (need 3.10+)."
    echo "Install a newer Python from https://python.org/downloads"
    exit 1
fi

green "✓ Python ${PY_MAJOR}.${PY_MINOR} detected"

# ──────────────────────────── venv ───────────────────────────────

if [ ! -d ".venv" ]; then
    echo "→ Creating Python environment in .venv/ ..."
    python3 -m venv .venv
fi
green "✓ Virtual environment ready"

# ──────────────────────────── install deps ───────────────────────

echo "→ Installing dependencies (this takes a minute) ..."
.venv/bin/pip install --quiet --upgrade pip
if ! .venv/bin/pip install --quiet -e . ; then
    red "✗ Dependency installation failed."
    echo "Run the following to see the full error:"
    echo "  .venv/bin/pip install -e ."
    exit 1
fi
green "✓ Dependencies installed"

# ──────────────────────────── launcher ───────────────────────────

LAUNCHER="Dataport AI.command"
cat > "$LAUNCHER" <<'LAUNCHER_EOF'
#!/usr/bin/env bash
# Double-click me to launch the Dataport AI for Tableau.
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "⚠  First-time setup wasn't completed. Run ./install.sh first."
    read -p "Press Enter to close..."
    exit 1
fi

clear
.venv/bin/python -m src.tui
RC=$?

if [ "$RC" != "0" ]; then
    echo
    echo "The app exited with code $RC."
    read -p "Press Enter to close..."
fi
LAUNCHER_EOF
chmod +x "$LAUNCHER"
green "✓ Created '$LAUNCHER' (double-click to launch)"

# ──────────────────────────── done ───────────────────────────────

hr
bold "🎉 All set!"
echo
echo "Next steps:"
echo
yellow "  1. Get an Anthropic API key"
echo "     → https://console.anthropic.com/settings/keys"
echo "     (sign up, then 'Create Key'. Dataport AI needs this to"
echo "      generate data stories from your spreadsheets.)"
echo
yellow "  2. Launch the app"
echo "     → Double-click 'Dataport AI.command' in this folder"
echo
yellow "  3. (Optional) Drop CSV/Excel files into the 'samples' folder"
echo "     so they show up easily in the file picker."
echo
hr
