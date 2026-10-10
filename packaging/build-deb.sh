#!/bin/bash
# 打包 svn-gui 独立 .deb（内置 PySide6 运行时，裁剪为 Core/Gui/Widgets 子集）
# 用法: ./packaging/build-deb.sh   （在项目根目录执行）
set -euo pipefail

PROJ="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="${1:-1.0.0}"
WORK="$(mktemp -d /tmp/svngui-deb.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

SP="$(python3 -c 'import PySide6, os; print(os.path.dirname(os.path.dirname(PySide6.__file__)))')"
ARCH="$(dpkg --print-architecture)"

# ---------- 1. 应用代码 ----------
ROOT="$WORK/pkgroot/svn-gui"
mkdir -p "$ROOT/usr/lib/svn-gui" "$ROOT/usr/bin" \
         "$ROOT/usr/share/applications" "$ROOT/usr/share/pixmaps" \
         "$ROOT/usr/share/doc/svn-gui" "$ROOT/DEBIAN"
mkdir -p "$WORK/src"
cp -a "$PROJ/core" "$PROJ/ui" "$PROJ/__init__.py" "$PROJ/__main__.py" "$WORK/src/"
find "$WORK/src" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
mv "$WORK/src" "$ROOT/usr/lib/svn-gui/svn_gui"

# ---------- 2. 内置 PySide6（只保留 QtCore/QtGui/QtWidgets/Network） ----------
VENDOR="$ROOT/usr/lib/svn-gui/vendor"
mkdir -p "$VENDOR"
cp -a "$SP/PySide6" "$SP/shiboken6" "$VENDOR"/
cp -a "$SP"/pyside6*_*.dist-info "$SP"/shiboken6-*.dist-info "$VENDOR"/ 2>/dev/null || true

cd "$VENDOR/PySide6"
# 顶层：删除开发工具 / 文档 / 无关绑定模块
rm -rf doc designer assistant linguist lrelease lupdate balsam balsamui \
       qmllint qmlls qmlformat qsb __feature__.pyi _git_pyside_version.py
KEEP="QtCore QtGui QtWidgets QtNetwork"
for f in *.abi3.so; do
  mod="${f%.abi3.so}"
  [[ " $KEEP " == *" $mod "* ]] || rm -f "$f" "${mod}.pyi"
done
rm -f *.pyi libpyside6qml.abi3.so*

# Qt 子目录
cd Qt
rm -rf qml metatypes doc resources
cd plugins
rm -rf sceneparsers assetimporters qmltooling geoservices canbus position sensors \
       texttospeech webview sqldrivers multimedia renderers renderplugins \
       geometryloaders scxmldatamodel designer qmllint vectorimageformats \
       wayland-* egldeviceintegrations platforminputcontexts printsupport generic
rm -f platforms/libqeglfs.so platforms/libqwayland* \
      imageformats/libqpdf.so imageformats/libqsvg.so iconengines/libqsvgicon.so

# 共享库：只留 Core/Gui/Widgets/Network/XcbQpa/DBus/OpenGL/ICU
cd ../lib
KEEP_LIB='libQt6Core libQt6Gui libQt6Widgets libQt6Network libQt6XcbQpa libQt6DBus libQt6OpenGL libicu'
for f in *.so*; do
  base="${f%%.so*}"
  keep=0
  for k in $KEEP_LIB; do [[ "$base" == "$k"* ]] && keep=1; done
  ((keep)) || rm -f "$f"
done
# 去掉 ffmpeg 多余符号链接（libQt6Gui 不直接依赖）
rm -f libavcodec.so* libavformat.so* libavutil.so* libswresample.so* libswscale.so* \
      libQt6FFmpegStub-* libQt6EglFSDeviceIntegration.so* libQt6EglFsKmsSupport.so* 2>/dev/null || true

# ---------- 3. 依赖自检：任何 "not found" 都算失败 ----------
cd "$ROOT"
BAD=0
while IFS= read -r -d '' f; do
  m="$(ldd "$f" 2>/dev/null | awk '/not found/{print $1}')"
  [[ -n "$m" ]] && { echo "MISSING DEP: $f -> $m"; BAD=1; }
done < <(find . -name '*.so*' -type f -print0)
((BAD == 0)) || { echo "依赖检查失败，中止"; exit 1; }

# ---------- 4. 桌面入口 / 启动器 / 元数据 ----------
cat > "$WORK/svn-gui-launcher" <<EOF
#!/bin/sh
# svn-gui: 使用内置 PySide6 (/usr/lib/svn-gui/vendor)
APP_DIR=/usr/lib/svn-gui
exec python3 -c "import sys; sys.path.insert(0, '\$APP_DIR/vendor'); sys.path.insert(0, '\$APP_DIR'); sys.argv[0]='svn-gui'; import runpy; runpy.run_module('svn_gui', run_name='__main__')" "\$@"
EOF
install -m 755 "$WORK/svn-gui-launcher" "$ROOT/usr/bin/svn-gui"

cat > "$ROOT/usr/share/applications/svn-gui.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=SVN GUI
Comment=PySide6-based graphical SVN client
Exec=svn-gui
Icon=svn-gui
Terminal=false
Categories=Development;RevisionControl;
EOF
install -m 644 "$WORK/svn-gui-launcher" /dev/null 2>/dev/null || true
# 图标：优先项目内 icon.png，否则占位
ICON=""
for c in "$PROJ/packaging/icon.png" "$PROJ/icon.png"; do [[ -f "$c" ]] && ICON="$c" && break; done
if [[ -z "$ICON" ]]; then
  QT_QPA_PLATFORM=offscreen python3 - <<PYEOF
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QGuiApplication
import sys
app = QGuiApplication(sys.argv)
pm = QPixmap(128, 128); pm.fill(QColor("#2d333b"))
p = QPainter(pm); p.setPen(QColor("#e5534b"))
f = QFont(); f.setPixelSize(84); f.setBold(True); p.setFont(f)
p.drawText(pm.rect(), 0x0084, "SV"); p.end()
pm.save("$WORK/icon.png", "PNG")
PYEOF
  ICON="$WORK/icon.png"
fi
install -m 644 "$ICON" "$ROOT/usr/share/pixmaps/svn-gui.png"

cat > "$ROOT/usr/share/doc/svn-gui/copyright" <<'EOF'
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: svn-gui
Source: local
Files: *
Copyright: 2025 tko
License: MIT
Permission is hereby granted, free of charge, to any person obtaining a copy
 of this software and associated documentation files (the "Software"), to deal
 in the Software without restriction, including without limitation the rights
 to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 copies of the Software, and to permit persons to whom the Software is
 furnished to do so, subject to the following conditions:
 .
 The above copyright notice and this permission notice shall be included in
 all copies or substantial portions of the Software.
 .
 THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 THE SOFTWARE.
EOF
cp "$PROJ/README.md" "$ROOT/usr/share/doc/svn-gui/README.md"
gzip -9n < "$PROJ/packaging/changelog" > "$ROOT/usr/share/doc/svn-gui/changelog.gz" 2>/dev/null || true

# 字节码预编译 + DEBIAN 元数据
python3 -m compileall -q "$ROOT/usr/lib/svn-gui/svn_gui" >/dev/null 2>&1 || true
SIZE="$(du -sk "$ROOT/usr" | cut -f1)"
cat > "$ROOT/DEBIAN/control" <<EOF
Package: svn-gui
Version: $VERSION
Section: devel
Priority: optional
Architecture: $ARCH
Installed-Size: $SIZE
Depends: python3 (>= 3.10), subversion, libgl1, libegl1, libxkbcommon0, libxkbcommon-x11-0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-randr0, libxcb-render-util0, libxcb-shape0, libxcb-xinerama0, libxcb-xkb1, libxcb-cursor0, libfontconfig1, libdbus-1-3, libglib2.0-0
Maintainer: tko <tko@localhost>
Description: PySide6 图形化 SVN 客户端
 基于 PySide6 (Qt6) 的 SVN 可视化客户端：工作副本状态、提交、
 diff 查看器、blame、冲突解决、分支/合并、深浅色主题。
 内置裁剪版 PySide6 运行时，无需 pip 安装。
EOF
cat > "$ROOT/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
#DEBHELPER#
exit 0
EOF
chmod 755 "$ROOT/DEBIAN/postinst"

# ---------- 5. 构建 ----------
OUT="$PROJ/svn-gui_${VERSION}_${ARCH}.deb"
cd "$WORK/pkgroot" && fakeroot dpkg-deb --build --root-owner-group svn-gui "$OUT"
echo "完成: $OUT ($(du -h "$OUT" | cut -f1))"
