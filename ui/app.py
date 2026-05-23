"""Main application window — auto-starts everything on launch."""
import threading
import webbrowser
from pathlib import Path

import customtkinter as ctk
from PIL import Image

from manager import server as srv, downloader
from manager.config import AppConfig, load_config, save_config, DATA_DIR, MARIADB_DATA
from ui.sites_page import SitesPage
from ui.php_page import PhpPage
from ui.dialogs import SetupDialog


APP_NAME = "Mamp Poo"
LOGO_PATH = Path(__file__).resolve().parent.parent / "crab_logo.png"


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("980x680")
        self.minsize(820, 560)
        self.cfg: AppConfig = load_config()
        self._page = "sites"
        self._tray = None
        self._quit_requested = False  # True when user picked "Quit" (not just close)

        # Window icon (PNG via PIL → Tk PhotoImage)
        try:
            if LOGO_PATH.exists():
                import tkinter as tk
                self._icon_img = tk.PhotoImage(file=str(LOGO_PATH))
                self.iconphoto(True, self._icon_img)
        except Exception:
            pass

        self._build()
        self._show_page("sites")
        self.after(600, self._on_launch)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # System tray icon — lets services keep running when window closes
        self._init_tray()

    # ─── Layout ───────────────────────────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── Sidebar ──
        side = ctk.CTkFrame(self, width=210, corner_radius=0, fg_color="#0d1117")
        side.grid(row=0, column=0, rowspan=3, sticky="nsew")
        side.grid_propagate(False)

        # Logo
        if LOGO_PATH.exists():
            try:
                pil_img = Image.open(LOGO_PATH)
                self._sidebar_logo = ctk.CTkImage(light_image=pil_img,
                                                  dark_image=pil_img,
                                                  size=(96, 96))
                ctk.CTkLabel(side, image=self._sidebar_logo,
                             text="").pack(pady=(22, 4))
            except Exception:
                pass

        ctk.CTkLabel(side, text="Mamp Poo", font=("", 22, "bold"),
                     text_color="#fb923c").pack(pady=(0, 0))
        ctk.CTkLabel(side, text="local dev manager", font=("", 10),
                     text_color="#6b7280").pack(pady=(0, 22))

        self._nav_btns = {}
        for label, key in [("Sites", "sites"), ("PHP Versions", "php"), ("Settings", "settings")]:
            b = ctk.CTkButton(side, text=label, anchor="w",
                              fg_color="transparent", hover_color="#1e2d45",
                              text_color="#d1d5db", font=("", 13),
                              command=lambda k=key: self._show_page(k))
            b.pack(fill="x", padx=10, pady=2)
            self._nav_btns[key] = b

        ctk.CTkFrame(side, height=1, fg_color="#1f2937").pack(fill="x", padx=10, pady=14)

        ctk.CTkButton(side, text="⚙  Setup / Install", anchor="w",
                      fg_color="transparent", hover_color="#1e2d45",
                      text_color="#9ca3af", font=("", 12),
                      command=lambda: SetupDialog(self, self.cfg, on_done=self._after_setup)
                      ).pack(fill="x", padx=10, pady=2)

        ctk.CTkButton(side, text="🗄  phpMyAdmin", anchor="w",
                      fg_color="transparent", hover_color="#1e2d45",
                      text_color="#9ca3af", font=("", 12),
                      command=self._open_phpmyadmin,
                      ).pack(fill="x", padx=10, pady=2)

        ctk.CTkButton(side, text="📁  Data Folder", anchor="w",
                      fg_color="transparent", hover_color="#1e2d45",
                      text_color="#9ca3af", font=("", 12),
                      command=lambda: self._open_folder(DATA_DIR),
                      ).pack(fill="x", padx=10, pady=2)

        # ── Top bar ──
        topbar = ctk.CTkFrame(self, height=52, corner_radius=0, fg_color="#161b22")
        topbar.grid(row=0, column=1, sticky="ew")
        topbar.grid_propagate(False)

        # Service status dots — click to toggle individual service
        status_frame = ctk.CTkFrame(topbar, fg_color="transparent")
        status_frame.pack(side="left", padx=16, pady=10)

        self.dot_apache = self._status_dot(status_frame, "Apache",
                                            command=self._toggle_apache)
        self.dot_mariadb = self._status_dot(status_frame, "MariaDB",
                                             command=self._toggle_mariadb)
        self.dot_php = self._status_dot(status_frame, "PHP",
                                         command=self._toggle_php)

        self.main_btn = ctk.CTkButton(
            topbar, text="■ Stop All", width=110,
            fg_color="#7f1d1d", hover_color="#991b1b",
            command=self._toggle_all,
        )
        self.main_btn.pack(side="right", padx=16, pady=10)

        self.status_msg = ctk.CTkLabel(topbar, text="กำลังเริ่มต้น…",
                                       text_color="#6b7280", font=("", 11))
        self.status_msg.pack(side="right", padx=(0, 8))

        # ── Content ──
        self.content = ctk.CTkFrame(self, corner_radius=0, fg_color="#0f1117")
        self.content.grid(row=1, column=1, sticky="nsew")

        # ── Status bar ──
        self.statusbar = ctk.CTkLabel(self, text="", font=("", 10),
                                      text_color="#6b7280", height=22,
                                      fg_color="#0d1117", anchor="w")
        self.statusbar.grid(row=2, column=1, sticky="ew", padx=8)

    def _status_dot(self, parent, label: str, command=None):
        """Status indicator that can be clicked to toggle the service."""
        f = ctk.CTkFrame(parent, fg_color="transparent", cursor="hand2")
        f.pack(side="left", padx=8)
        dot = ctk.CTkLabel(f, text="●", text_color="#4b5563",
                           font=("", 14), cursor="hand2")
        dot.pack(side="left")
        lbl = ctk.CTkLabel(f, text=label, text_color="#6b7280",
                           font=("", 11), cursor="hand2")
        lbl.pack(side="left", padx=(2, 0))
        if command:
            for w in (f, dot, lbl):
                w.bind("<Button-1>", lambda _e: command())
        return dot

    # ─── Navigation ───────────────────────────────────────────────────────────

    def _show_page(self, key: str):
        self._page = key
        for k, b in self._nav_btns.items():
            b.configure(fg_color="#1e2d45" if k == key else "transparent",
                        text_color="white" if k == key else "#d1d5db")
        for w in self.content.winfo_children():
            w.destroy()
        if key == "sites":
            SitesPage(self.content, self.cfg, on_change=self._save_and_refresh).pack(fill="both", expand=True)
        elif key == "php":
            PhpPage(self.content, self.cfg, on_change=self._save_and_refresh).pack(fill="both", expand=True)
        elif key == "settings":
            self._build_settings()

    def _build_settings(self):
        import tkinter as tk
        f = ctk.CTkFrame(self.content, fg_color="transparent")
        f.pack(fill="both", expand=True, padx=24, pady=24)
        ctk.CTkLabel(f, text="Settings", font=("", 20, "bold")).pack(anchor="w", pady=(0, 20))

        def row(lbl, var, ph):
            r = ctk.CTkFrame(f, fg_color="transparent")
            r.pack(fill="x", pady=4)
            ctk.CTkLabel(r, text=lbl, width=140, anchor="w").pack(side="left")
            ctk.CTkEntry(r, textvariable=var, placeholder_text=ph, width=100).pack(side="left")

        http_var = tk.StringVar(value=str(self.cfg.http_port))
        https_var = tk.StringVar(value=str(self.cfg.https_port))
        row("HTTP Port", http_var, "80")
        row("HTTPS Port", https_var, "443")

        ctk.CTkLabel(f,
                     text="หมายเหตุ: Port 80/443 ต้องการสิทธิ์ Administrator\n"
                          "ถ้าไม่ต้องการรัน as Admin ให้เปลี่ยนเป็น 8080/8443",
                     text_color="orange", font=("", 11), justify="left").pack(anchor="w", pady=(6, 16))

        def save():
            try:
                self.cfg.http_port = int(http_var.get())
                self.cfg.https_port = int(https_var.get())
                save_config(self.cfg)
                srv.write_apache_conf(self.cfg)
                self._set_status("บันทึกแล้ว — กด Stop/Start เพื่อใช้งาน")
            except ValueError:
                self._set_status("กรุณาใส่ตัวเลข", "orange")

        btn_row = ctk.CTkFrame(f, fg_color="transparent")
        btn_row.pack(anchor="w", pady=(0, 24), fill="x")
        ctk.CTkButton(btn_row, text="บันทึก Settings", command=save).pack(side="left")

        # ── Desktop shortcut ──
        ctk.CTkFrame(f, height=1, fg_color="#1f2937").pack(fill="x", pady=(0, 20))
        ctk.CTkLabel(f, text="Shortcut", font=("", 15, "bold")).pack(anchor="w", pady=(0, 8))
        ctk.CTkLabel(f,
                     text="สร้าง shortcut บน Desktop เพื่อให้เปิดโปรแกรมได้ด้วยการดับเบิ้ลคลิก\n"
                          "(ไม่ต้องเปิด command line)",
                     text_color="gray", justify="left", font=("", 11)).pack(anchor="w", pady=(0, 10))

        self._shortcut_status = ctk.CTkLabel(f, text="", text_color="gray", font=("", 11))

        ctk.CTkButton(f, text="🖥  สร้าง Desktop Shortcut",
                      command=self._create_shortcut).pack(anchor="w")
        self._shortcut_status.pack(anchor="w", pady=(6, 0))

    def _create_shortcut(self):
        """Create a Desktop alias for the launcher (.command script)."""
        import subprocess
        from pathlib import Path

        script_dir = Path(__file__).parent.parent
        launcher = script_dir / "Mamp Poo.command"
        if not launcher.exists():
            self._shortcut_status.configure(
                text="ไม่พบ Mamp Poo.command ในโฟลเดอร์โปรแกรม",
                text_color="orange")
            return

        desktop = Path.home() / "Desktop"
        target = desktop / "Mamp Poo.command"

        # Symlink the launcher onto the Desktop
        try:
            if target.exists() or target.is_symlink():
                target.unlink()
            target.symlink_to(launcher)
            self._shortcut_status.configure(
                text=f"✓ สร้าง shortcut ที่ Desktop แล้ว",
                text_color="#22c55e")
        except Exception as e:
            self._shortcut_status.configure(
                text=f"สร้าง shortcut ไม่ได้: {e}",
                text_color="orange")

    # ─── Launch / Auto-start ──────────────────────────────────────────────────

    def _on_launch(self):
        """Called after window is ready. Checks deps then auto-starts."""
        missing = (
            not downloader.is_apache_ready() or
            not downloader.is_mariadb_ready() or
            not self.cfg.installed_php
        )
        if missing:
            self._set_status("กรุณาติดตั้ง components ก่อน")
            SetupDialog(self, self.cfg, on_done=self._after_setup)
        else:
            self._start_all_async()

    def _after_setup(self):
        save_config(self.cfg)
        self._save_and_refresh()
        missing = (
            not downloader.is_apache_ready() or
            not downloader.is_mariadb_ready() or
            not self.cfg.installed_php
        )
        if not missing:
            self._start_all_async()

    def _start_all_async(self):
        self._set_status("กำลังเริ่มต้น services…")
        self.main_btn.configure(state="disabled", text="Starting…")

        def run():
            # Auto-reset if data dir was wiped (e.g. after re-downloading MariaDB)
            if self.cfg.mariadb_initialized and not (MARIADB_DATA / "mysql").exists():
                self.cfg.mariadb_initialized = False
                save_config(self.cfg)

            if not self.cfg.mariadb_initialized:
                self.after(0, lambda: self._set_status("กำลัง initialize MariaDB (ครั้งแรก)…"))
                ok, msg = srv.initialize_mariadb()
                if ok:
                    self.cfg.mariadb_initialized = True
                    save_config(self.cfg)
                else:
                    self.after(0, lambda m=msg: self._on_started([f"MariaDB init: {m}"]))
                    return

            errors = srv.start_all(self.cfg)
            self.after(0, lambda: self._on_started(errors))

        threading.Thread(target=run, daemon=True).start()

    def _on_started(self, errors: list):
        self._refresh_dots()
        self.main_btn.configure(state="normal")
        if errors:
            self._set_status("เริ่มต้นบางส่วนไม่ได้: " + " | ".join(errors), "orange")
        else:
            self._set_status("Services ทำงานแล้ว — phpMyAdmin: localhost/phpmyadmin", "#22c55e")
        self._update_main_btn()

    # ─── Stop / Toggle ────────────────────────────────────────────────────────

    def _toggle_all(self):
        if srv.is_apache_running():
            self._set_status("กำลังหยุด services…")
            self.main_btn.configure(state="disabled", text="Stopping…")

            def run():
                srv.stop_all()
                self.after(0, self._after_stop)

            threading.Thread(target=run, daemon=True).start()
        else:
            self._start_all_async()

    def _after_stop(self):
        self._refresh_dots()
        self._update_main_btn()
        self._set_status("หยุดทำงานแล้ว")
        self.main_btn.configure(state="normal")

    # ─── Per-service toggles ─────────────────────────────────────────────────

    def _toggle_mariadb(self):
        if srv.is_mariadb_running():
            self._set_status("กำลังหยุด MariaDB…")
            def run():
                srv.stop_mariadb()
                self.after(0, lambda: (self._refresh_dots(),
                                       self._set_status("MariaDB หยุดแล้ว", "#f59e0b")))
            threading.Thread(target=run, daemon=True).start()
        else:
            self._set_status("กำลังเริ่ม MariaDB…")
            def run():
                # Initialize on first run
                if not self.cfg.mariadb_initialized or not (MARIADB_DATA / "mysql").exists():
                    self.cfg.mariadb_initialized = False
                    save_config(self.cfg)
                    self.after(0, lambda: self._set_status("กำลัง initialize MariaDB…"))
                    ok, msg = srv.initialize_mariadb()
                    if not ok:
                        self.after(0, lambda m=msg: self._set_status(
                            f"MariaDB init failed: {m}", "orange"))
                        return
                    self.cfg.mariadb_initialized = True
                    save_config(self.cfg)
                ok, msg = srv.start_mariadb()
                self.after(0, lambda o=ok, m=msg: (
                    self._refresh_dots(),
                    self._set_status(f"MariaDB: {m}",
                                     "#22c55e" if o else "orange"),
                ))
            threading.Thread(target=run, daemon=True).start()

    def _toggle_apache(self):
        if srv.is_apache_running():
            self._set_status("กำลังหยุด Apache…")
            def run():
                srv.stop_apache()
                self.after(0, lambda: (self._refresh_dots(),
                                       self._update_main_btn(),
                                       self._set_status("Apache หยุดแล้ว", "#f59e0b")))
            threading.Thread(target=run, daemon=True).start()
        else:
            self._set_status("กำลังเริ่ม Apache…")
            def run():
                ok, msg = srv.start_apache(self.cfg)
                self.after(0, lambda o=ok, m=msg: (
                    self._refresh_dots(), self._update_main_btn(),
                    self._set_status(f"Apache: {m}",
                                     "#22c55e" if o else "orange"),
                ))
            threading.Thread(target=run, daemon=True).start()

    def _toggle_php(self):
        # Toggle all installed PHP versions at once
        running = [v for v in (self.cfg.installed_php or [])
                   if srv.is_php_running(v)]
        if running:
            self._set_status("กำลังหยุด PHP…")
            def run():
                srv.stop_all_php()
                self.after(0, lambda: (self._refresh_dots(),
                                       self._set_status("PHP หยุดแล้ว", "#f59e0b")))
            threading.Thread(target=run, daemon=True).start()
        else:
            self._set_status("กำลังเริ่ม PHP…")
            def run():
                needed = {v.php_version for v in self.cfg.vhosts if v.enabled}
                installed = self.cfg.installed_php or []
                if installed and not needed:
                    needed = {installed[0]}
                errors = []
                for v in needed:
                    ok, msg = srv.start_php(v)
                    if not ok:
                        errors.append(f"PHP {v}: {msg}")
                self.after(0, lambda e=errors: (
                    self._refresh_dots(),
                    self._set_status(
                        "PHP started" if not e else " | ".join(e),
                        "#22c55e" if not e else "orange"),
                ))
            threading.Thread(target=run, daemon=True).start()

    def _update_main_btn(self):
        running = srv.is_apache_running()
        self.main_btn.configure(
            text="■ Stop All" if running else "▶ Start All",
            fg_color="#7f1d1d" if running else "#065f46",
            hover_color="#991b1b" if running else "#047857",
            state="normal",
        )

    # ─── Status dots ──────────────────────────────────────────────────────────

    def _refresh_dots(self):
        self.dot_apache.configure(
            text_color="#22c55e" if srv.is_apache_running() else "#4b5563")
        self.dot_mariadb.configure(
            text_color="#22c55e" if srv.is_mariadb_running() else "#4b5563")

        any_php = any(srv.is_php_running(v) for v in self.cfg.installed_php or [])
        self.dot_php.configure(text_color="#22c55e" if any_php else "#4b5563")

        # Refresh every 4 s while window open
        self.after(4000, self._refresh_dots)

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _set_status(self, msg: str, color: str = "#6b7280"):
        self.statusbar.configure(text=f"  {msg}", text_color=color)
        self.status_msg.configure(text=msg, text_color=color)

    def _save_and_refresh(self):
        save_config(self.cfg)
        if self._page in ("sites", "php"):
            self._show_page(self._page)

    def _open_phpmyadmin(self):
        port = self.cfg.http_port
        url = f"http://localhost{'' if port == 80 else f':{port}'}/phpmyadmin"
        webbrowser.open(url)

    @staticmethod
    def _open_folder(path):
        import subprocess
        subprocess.Popen(["open", str(path)])

    # ─── Tray / Background mode ──────────────────────────────────────────────

    def _init_tray(self):
        try:
            from ui.tray import TrayIcon
        except Exception:
            self._tray = None
            return
        try:
            self._tray = TrayIcon(
                logo_path=LOGO_PATH,
                on_show=lambda: self.after(0, self._show_window),
                on_open_pma=lambda: self.after(0, self._open_phpmyadmin),
                on_start_all=lambda: self.after(0, self._start_all_async),
                on_stop_all=lambda: self.after(0, self._stop_all_async),
                on_quit=lambda: self.after(0, self._quit_from_tray),
                is_running=lambda: srv.is_apache_running() or srv.is_mariadb_running(),
            )
            self._tray.start()
        except Exception:
            self._tray = None

    def _show_window(self):
        try:
            self.deiconify()
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _stop_all_async(self):
        def run():
            srv.stop_all()
            self.after(0, self._after_stop)
        threading.Thread(target=run, daemon=True).start()
        self._set_status("กำลังหยุด services…")

    def _quit_from_tray(self):
        """Triggered from tray menu — stop services and fully exit."""
        self._quit_requested = True
        if self._tray:
            self._tray.stop()
        def run():
            srv.stop_all()
            self.after(0, self.destroy)
        threading.Thread(target=run, daemon=True).start()
        self._set_status("กำลังปิด services และออกจากโปรแกรม…")

    def _on_close(self):
        """X button → hide to tray, keep services running.
        Use tray menu → Quit to fully exit."""
        if self._quit_requested or self._tray is None:
            # No tray available (or quit requested) → real shutdown
            def run():
                srv.stop_all()
            threading.Thread(target=run, daemon=True).start()
            self.after(2000, self.destroy)
            self._set_status("กำลังปิด services…")
            return
        # Hide window — services keep running
        self.withdraw()
        try:
            self._tray.notify(
                "Mamp Poo ทำงานต่อใน background",
                "Services ยังทำงานอยู่ — คลิก icon ที่ system tray เพื่อแสดงหน้าต่าง หรือ Quit",
            )
        except Exception:
            pass
