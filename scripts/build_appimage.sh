#!/bin/bash
set -e

echo "Building Icosele Vault AppImage..."

# Setup
APP_NAME="IcoseleVault"
APP_DIR="$APP_NAME.AppDir"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Clean previous build
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/usr/bin"
mkdir -p "$APP_DIR/usr/share/applications"
mkdir -p "$APP_DIR/usr/share/icons/hicolor/512x512/apps"

# Copy project files
cp -r app "$APP_DIR/usr/bin/"
cp -r assets "$APP_DIR/usr/bin/"
cp main.py "$APP_DIR/usr/bin/"
cp requirements.txt "$APP_DIR/usr/bin/"

# Copy icon
cp assets/icon512.png "$APP_DIR/usr/share/icons/hicolor/512x512/apps/icosele-vault.png"
cp assets/icon512.png "$APP_DIR/icosele-vault.png"

# Create desktop entry
cat > "$APP_DIR/usr/share/applications/icosele-vault.desktop" << 'EOF'
[Desktop Entry]
Name=Icosele Vault
Comment=The most powerful open source VM manager for Linux
Exec=icosele-vault
Icon=icosele-vault
Type=Application
Categories=System;Utility;
Terminal=false
EOF

cp "$APP_DIR/usr/share/applications/icosele-vault.desktop" "$APP_DIR/icosele-vault.desktop"

# Create AppRun script
cat > "$APP_DIR/AppRun" << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
cd "$HERE/usr/bin"
python3 -m venv .venv --system-site-packages 2>/dev/null || true
source .venv/bin/activate 2>/dev/null || true
pip install -r requirements.txt -q 2>/dev/null || true
exec python3 main.py "$@"
EOF

chmod +x "$APP_DIR/AppRun"

# Download appimagetool if not present
if [ ! -f "appimagetool-x86_64.AppImage" ]; then
    echo "Downloading appimagetool..."
    wget -q "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod +x appimagetool-x86_64.AppImage
fi

# Build AppImage
ARCH=x86_64 ./appimagetool-x86_64.AppImage "$APP_DIR" "$APP_NAME-x86_64.AppImage"

echo "Done! AppImage created: $APP_NAME-x86_64.AppImage"
