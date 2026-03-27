#!/bin/bash
set -e

echo "============================================"
echo " Icosele Vault — macOS Setup"
echo "============================================"
echo

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "ERROR: Python 3 is not installed."
    echo "Install via: brew install python@3.11"
    exit 1
fi

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "Found Python $PY_VER"

# Check Homebrew
if ! command -v brew &>/dev/null; then
    echo ""
    echo "Homebrew is not installed. Install it first:"
    echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
    echo ""
    exit 1
fi
echo "Found Homebrew"

# Check/install QEMU
if ! command -v qemu-system-x86_64 &>/dev/null; then
    echo "Installing QEMU via Homebrew..."
    brew install qemu
else
    QEMU_VER=$(qemu-system-x86_64 --version | head -1)
    echo "Found $QEMU_VER"
fi

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -q

# Create launcher
echo "Creating launcher..."
cat > /usr/local/bin/icosele-vault << LAUNCHER
#!/bin/bash
cd "$PROJECT_DIR"
source .venv/bin/activate
exec python3 main.py "\$@"
LAUNCHER
chmod +x /usr/local/bin/icosele-vault

# Create data directory
mkdir -p data/vms

echo ""
echo "============================================"
echo " Setup complete!"
echo "============================================"
echo ""
echo "To start: icosele-vault"
echo "Or:       cd $PROJECT_DIR && source .venv/bin/activate && python3 main.py"
echo ""
echo "Apple Silicon (M1/M2/M3/M4) is supported natively via HVF."
