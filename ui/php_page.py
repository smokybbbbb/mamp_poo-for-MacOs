"""PHP Versions page — install / start / stop individual PHP versions."""
import shutil
import threading

import customtkinter as ctk

from manager import downloader, server as srv
from manager.config import AppConfig, PHP_VERSIONS, PHP_PORTS, PHP_DIR, save_config


class PhpPage(ctk.CTkFrame):
    def __init__(self, parent, config: AppConfig, on_change=None):
        super().__init__(parent, fg_color="transparent")
        self.config = config
        self.on_change = on_change
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="PHP Versions", font=("", 20, "bold")).pack(
            anchor="w", padx=20, pady=(16, 2))
        ctk.CTkLabel(self, text="PHP แต่ละ version รันเป็น FastCGI process แยกกัน",
                     text_color="gray").pack(anchor="w", padx=20, pady=(0, 12))

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        self.refresh()

    def refresh(self):
        for w in self.scroll.winfo_children():
            w.destroy()
        for ver in PHP_VERSIONS:
            self._row(ver)

    def _row(self, ver: str):
        ready = downloader.is_php_ready(ver)
        running = srv.is_php_running(ver)
        port = PHP_PORTS.get(ver)

        card = ctk.CTkFrame(self.scroll, corner_radius=8, fg_color="#1e2433")
        card.pack(fill="x", pady=4)

        dot_col = "#22c55e" if running else ("#60a5fa" if ready else "#4b5563")
        ctk.CTkLabel(card, text="●", text_color=dot_col,
                     font=("", 14), width=26).grid(row=0, column=0, padx=(12, 4), pady=14)

        ctk.CTkLabel(card, text=f"PHP {ver}", font=("", 13, "bold"),
                     anchor="w").grid(row=0, column=1, sticky="w")
        status_text = "กำลังรัน" if running else ("หยุด" if ready else "ยังไม่ได้ติดตั้ง")
        ctk.CTkLabel(card, text=f"Port {port}  ·  {status_text}",
                     text_color="gray", anchor="w",
                     font=("", 11)).grid(row=1, column=1, sticky="w", pady=(0, 10))

        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.grid(row=0, column=2, rowspan=2, padx=(0, 8))

        if not ready:
            progress = ctk.CTkProgressBar(card, width=130)
            progress.set(0)
            progress.grid(row=0, column=3, rowspan=2, padx=8)
            ctk.CTkButton(btns, text="ติดตั้ง", width=80,
                          command=lambda v=ver, p=progress: self._install(v, p)).pack()
        else:
            if running:
                ctk.CTkButton(btns, text="Stop", width=80,
                              fg_color="#7f1d1d", hover_color="#991b1b",
                              command=lambda v=ver: self._stop(v)).pack(pady=2)
            else:
                ctk.CTkButton(btns, text="Start", width=80,
                              fg_color="#065f46", hover_color="#047857",
                              command=lambda v=ver: self._start(v)).pack(pady=2)
            ctk.CTkButton(btns, text="ลบ", width=80, fg_color="gray40",
                          command=lambda v=ver: self._remove(v)).pack(pady=2)

        card.grid_columnconfigure(1, weight=1)

    def _install(self, ver: str, progress: ctk.CTkProgressBar):
        def run():
            ok = downloader.download_php(ver, lambda p: self.after(0, lambda: progress.set(p)))
            if ok and ver not in (self.config.installed_php or []):
                self.config.installed_php.append(ver)
                save_config(self.config)
            self.after(0, self.refresh)
            if self.on_change:
                self.after(0, self.on_change)
        threading.Thread(target=run, daemon=True).start()

    def _start(self, ver: str):
        ok, msg = srv.start_php(ver)
        self.refresh()

    def _stop(self, ver: str):
        srv.stop_php(ver)
        self.refresh()

    def _remove(self, ver: str):
        srv.stop_php(ver)
        php_dir = PHP_DIR / ver
        if php_dir.exists():
            shutil.rmtree(php_dir)
        if self.config.installed_php and ver in self.config.installed_php:
            self.config.installed_php.remove(ver)
            save_config(self.config)
        self.refresh()
        if self.on_change:
            self.on_change()
