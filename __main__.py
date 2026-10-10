#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""程序入口 — python -m svn_gui [工作目录]"""

import os
import sys


def main():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt, QTranslator, QLibraryInfo, QLocale
    from .ui import main_window as mw

    app = QApplication(sys.argv)
    app.setApplicationName("SVN")

    # 加载 Qt 自带中文翻译（右键菜单 复制/粘贴/剪切、对话框按钮等）
    translator = QTranslator(app)
    tr_dir = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load(QLocale(), "qtbase", "_", tr_dir):
        app.installTranslator(translator)

    start = None
    for arg in sys.argv[1:]:
        if os.path.isdir(arg):
            start = os.path.abspath(arg)
            break

    win = mw.MainWindow(start)
    app.aboutToQuit.connect(lambda: None)
    win.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
