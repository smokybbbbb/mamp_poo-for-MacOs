"""System tray icon for Mamp Poo.

Lets the app keep running (and serving requests) after the window is closed.
Right-click the tray icon → Show, Open phpMyAdmin, Stop/Start All, Quit.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from PIL import Image
import pystray


class TrayIcon:
    def __init__(
        self,
        logo_path: Path,
        on_show: Callable[[], None],
        on_open_pma: Callable[[], None],
        on_start_all: Callable[[], None],
        on_stop_all: Callable[[], None],
        on_quit: Callable[[], None],
        is_running: Callable[[], bool],
    ):
        self._on_show = on_show
        self._on_open_pma = on_open_pma
        self._on_start_all = on_start_all
        self._on_stop_all = on_stop_all
        self._on_quit = on_quit
        self._is_running = is_running

        try:
            image = Image.open(logo_path).convert("RGBA")
        except Exception:
            # Fallback: orange square
            image = Image.new("RGBA", (64, 64), (251, 146, 60, 255))

        # Resize to typical tray icon size
        image = image.resize((64, 64), Image.LANCZOS)

        menu = pystray.Menu(
            pystray.MenuItem(
                "Show Window",
                lambda _icon, _item: self._safe_call(self._on_show),
                default=True,  # double-click default action
            ),
            pystray.MenuItem(
                "Open phpMyAdmin",
                lambda _icon, _item: self._safe_call(self._on_open_pma),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda _item: "■ Stop All Services" if self._is_running()
                              else "▶ Start All Services",
                lambda _icon, _item: self._toggle(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Quit Mamp Poo",
                lambda _icon, _item: self._safe_call(self._on_quit),
            ),
        )
        self._icon = pystray.Icon(
            "mamp_poo", image, "Mamp Poo — local dev manager", menu,
        )
        self._thread: threading.Thread | None = None

    def _safe_call(self, fn: Callable[[], None]):
        try:
            fn()
        except Exception:
            pass

    def _toggle(self):
        if self._is_running():
            self._safe_call(self._on_stop_all)
        else:
            self._safe_call(self._on_start_all)

    def start(self):
        """Run the tray icon in a background thread."""
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop and remove the tray icon."""
        try:
            self._icon.visible = False
            self._icon.stop()
        except Exception:
            pass

    def notify(self, title: str, message: str):
        try:
            self._icon.notify(message, title)
        except Exception:
            pass
