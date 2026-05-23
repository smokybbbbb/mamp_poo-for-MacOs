"""VHost dialog and Setup/Install dialog."""
import threading
import tkinter as tk
import tkinter.filedialog as fd
from pathlib import Path

import customtkinter as ctk

from manager.config import PHP_VERSIONS, VHost, AppConfig, MARIADB_DATA
from manager import downloader, server as srv, ssl as ssl_mgr


# ─── VHost Dialog ─────────────────────────────────────────────────────────────

class VHostDialog(ctk.CTkToplevel):
    def __init__(self, parent, config: AppConfig, vhost: VHost | None = None, on_save=None):
        super().__init__(parent)
        self.config = config
        self.vhost = vhost
        self.on_save = on_save
        self._edit = vhost is not None

        self.title("Edit Site" if self._edit else "Add New Site")
        self.geometry("520x460")
        self.resizable(False, False)
        self.grab_set()
        self.lift()
        self.attributes("-topmost", True)
        self._build()
        self._center()

    def _center(self):
        self.update_idletasks()
        x = self.master.winfo_rootx() + self.master.winfo_width() // 2 - self.winfo_width() // 2
        y = self.master.winfo_rooty() + self.master.winfo_height() // 2 - self.winfo_height() // 2
        self.geometry(f"+{x}+{y}")

    def _build(self):
        p = {"padx": 24, "pady": 6}
        v = self.vhost

        ctk.CTkLabel(self, text="Domain", anchor="w").pack(fill="x", **p)
        self.domain_var = tk.StringVar(value=v.domain if v else "")
        ctk.CTkEntry(self, textvariable=self.domain_var,
                     placeholder_text="mysite.dev").pack(fill="x", **p)

        ctk.CTkLabel(self, text="Document Root", anchor="w").pack(fill="x", **p)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=6)
        self.root_var = tk.StringVar(value=v.root_path if v else "")
        ctk.CTkEntry(row, textvariable=self.root_var,
                     placeholder_text="C:/Sites/mysite").pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row, text="Browse", width=80, command=self._browse).pack(side="left", padx=(8, 0))

        ctk.CTkLabel(self, text="PHP Version", anchor="w").pack(fill="x", **p)
        installed = set(self.config.installed_php or [])
        choices = [f"PHP {ver}{'  ✓' if ver in installed else '  (ยังไม่ติดตั้ง)'}"
                   for ver in PHP_VERSIONS]
        default = v.php_version if v else (self.config.installed_php[0] if self.config.installed_php else PHP_VERSIONS[0])
        self.php_var = tk.StringVar(
            value=next((c for c in choices if c.startswith(f"PHP {default}")), choices[0])
        )
        ctk.CTkOptionMenu(self, values=choices, variable=self.php_var).pack(fill="x", **p)

        self.https_var = tk.BooleanVar(value=v.https_enabled if v else False)
        ctk.CTkCheckBox(self, text="Enable HTTPS (ต้องติดตั้ง mkcert + Root CA ใน Setup ก่อน)",
                        variable=self.https_var).pack(anchor="w", **p)

        self.status = ctk.CTkLabel(self, text="", text_color="orange")
        self.status.pack(pady=(4, 0))

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=24, pady=(12, 20))
        ctk.CTkButton(btns, text="ยกเลิก", fg_color="gray40",
                      command=self.destroy).pack(side="left")
        ctk.CTkButton(btns, text="บันทึก", command=self._save).pack(side="right")

    def _browse(self):
        path = fd.askdirectory(title="เลือก Document Root")
        if path:
            self.root_var.set(path)

    def _save(self):
        domain = self.domain_var.get().strip()
        root = self.root_var.get().strip()
        php_ver = self.php_var.get().replace("PHP ", "").split()[0]
        https = self.https_var.get()

        if not domain:
            self.status.configure(text="กรุณาใส่ Domain", text_color="red"); return
        if not root:
            self.status.configure(text="กรุณาเลือก Document Root", text_color="red"); return
        if not Path(root).exists():
            self.status.configure(text="ไม่พบ folder นี้", text_color="red"); return
        if https and not downloader.is_mkcert_ready():
            self.status.configure(text="ต้องติดตั้ง mkcert ก่อน", text_color="orange"); return
        if https and not ssl_mgr.is_root_ca_installed():
            self.status.configure(
                text="ต้องกด 'Install mkcert Root CA' ใน Setup ก่อน ไม่งั้น Chrome จะแสดง ERR_CERT_AUTHORITY_INVALID",
                text_color="orange"); return

        # .dev / .app / .page TLDs are HSTS-preloaded — Chrome forces HTTPS always
        tld = domain.rsplit(".", 1)[-1].lower() if "." in domain else ""
        if tld in ("dev", "app", "page") and not https:
            self.status.configure(
                text=f".{tld} ถูก Chrome บังคับ HTTPS เสมอ — กรุณาเปิด Enable HTTPS",
                text_color="orange"); return

        if self._edit:
            self.vhost.domain = domain
            self.vhost.root_path = root
            self.vhost.php_version = php_ver
            self.vhost.https_enabled = https
            result = self.vhost
        else:
            result = VHost(domain=domain, root_path=root,
                           php_version=php_ver, https_enabled=https)

        if self.on_save:
            self.on_save(result)
        self.destroy()


# ─── Setup Dialog ─────────────────────────────────────────────────────────────

class SetupDialog(ctk.CTkToplevel):
    def __init__(self, parent, config: AppConfig, on_done=None):
        super().__init__(parent)
        self.config = config
        self.on_done = on_done
        self.title("Setup — ติดตั้ง Components")
        self.geometry("640x700")
        self.resizable(False, False)
        self.grab_set()
        self.lift()
        self.attributes("-topmost", True)
        self._rows: dict = {}
        self._build()
        self._center()

    def _center(self):
        self.update_idletasks()
        x = self.master.winfo_rootx() + self.master.winfo_width() // 2 - self.winfo_width() // 2
        y = self.master.winfo_rooty() + self.master.winfo_height() // 2 - self.winfo_height() // 2
        self.geometry(f"+{x}+{y}")

    def _build(self):
        ctk.CTkLabel(self, text="ติดตั้ง Components",
                     font=("", 18, "bold")).pack(pady=(20, 2))
        ctk.CTkLabel(self, text="กด Install ทีละรายการ — ดาวน์โหลดอัตโนมัติ",
                     text_color="gray").pack(pady=(0, 12))

        self.scroll = ctk.CTkScrollableFrame(self, height=460)
        self.scroll.pack(fill="both", expand=True, padx=16)

        self._section("Core (จำเป็น)")
        self._dep_row("apache",     "Apache 2.4",            downloader.is_apache_ready,    downloader.download_apache)
        self._dep_row("mariadb",    "MariaDB 11 (MySQL)",    downloader.is_mariadb_ready,   downloader.download_mariadb)
        self._dep_row("phpmyadmin", "phpMyAdmin 5.2",        downloader.is_phpmyadmin_ready, downloader.download_phpmyadmin)
        self._dep_row("mkcert",     "mkcert (สำหรับ HTTPS)", downloader.is_mkcert_ready,    downloader.download_mkcert)

        self._section("PHP (เลือกอย่างน้อย 1 version)")
        for ver in PHP_VERSIONS:
            self._dep_row(
                f"php_{ver}", f"PHP {ver}",
                lambda v=ver: downloader.is_php_ready(v),
                lambda cb=None, v=ver: downloader.download_php(v, cb),
            )

        # Bottom
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(10, 4))
        self.ca_btn = ctk.CTkButton(
            btn_row, text="🔒 Install mkcert Root CA (ต้องการ admin ครั้งเดียว)",
            command=self._install_ca, fg_color="#1d4ed8",
        )
        self.ca_btn.pack(side="left")

        self.init_db_btn = ctk.CTkButton(
            btn_row, text="🗄 Initialize MariaDB",
            command=self._init_mariadb, fg_color="#065f46",
        )
        self.init_db_btn.pack(side="left", padx=(8, 0))

        ctk.CTkButton(btn_row, text="เสร็จแล้ว ✓", command=self._done).pack(side="right")

        # Error detail box
        self.error_box = ctk.CTkTextbox(self, height=56, font=("Consolas", 10),
                                        fg_color="#1a0a0a", text_color="#fca5a5",
                                        state="disabled")
        self.error_box.pack(fill="x", padx=16, pady=(0, 8))
        self._set_error("")  # hide initially

    def _section(self, title: str):
        ctk.CTkLabel(self.scroll, text=title, font=("", 12, "bold"),
                     anchor="w", text_color="#60a5fa").pack(fill="x", pady=(10, 2), padx=2)

    def _dep_row(self, key: str, label: str, check_fn, install_fn):
        ready = check_fn()
        card = ctk.CTkFrame(self.scroll, fg_color="#1e2433", corner_radius=6)
        card.pack(fill="x", pady=3)

        dot = ctk.CTkLabel(card, text="●",
                           text_color="#22c55e" if ready else "#4b5563",
                           font=("", 13), width=26)
        dot.grid(row=0, column=0, padx=(10, 4), pady=10)

        ctk.CTkLabel(card, text=label, font=("", 12),
                     anchor="w").grid(row=0, column=1, sticky="w", padx=4)

        progress = ctk.CTkProgressBar(card, width=130)
        progress.set(0)

        if ready:
            ctk.CTkLabel(card, text="ติดตั้งแล้ว ✓", text_color="#22c55e",
                         font=("", 11)).grid(row=0, column=2, padx=8)
        else:
            progress.grid(row=0, column=2, padx=8)
            btn = ctk.CTkButton(
                card, text="Install", width=80,
                command=lambda k=key, fn=install_fn, p=progress, d=dot:
                    self._start(k, label, fn, p, d),
            )
            btn.grid(row=0, column=3, padx=(0, 10))
            self._rows[key] = {"dot": dot, "btn": btn, "progress": progress}

        card.grid_columnconfigure(1, weight=1)

    def _start(self, key: str, label: str,
               install_fn, progress: ctk.CTkProgressBar, dot: ctk.CTkLabel):
        row = self._rows.get(key, {})
        if "btn" in row:
            row["btn"].configure(state="disabled", text="กำลังดาวน์โหลด…")
        self._set_error("")

        def run():
            def cb(pct):
                self.after(0, lambda: progress.set(pct))

            result = install_fn(cb)
            # Accept both bool and (bool, str) return types
            if isinstance(result, tuple):
                ok, err = result
            else:
                ok, err = result, ""

            def update():
                dot.configure(text_color="#22c55e" if ok else "#ef4444")
                if "btn" in row:
                    row["btn"].configure(
                        text="✓ Done" if ok else "✗ Retry",
                        fg_color="#1a3a1a" if ok else "#7f1d1d",
                        hover_color="#0d2a0d" if ok else "#991b1b",
                        state="disabled" if ok else "normal",
                        command=(lambda k=key, lb=label, fn=install_fn, p=progress, d=dot:
                                 self._start(k, lb, fn, p, d)) if not ok else None,
                    )
                    if ok:
                        progress.grid_remove()
                if not ok and err:
                    self._set_error(f"[{label}] {err}")

            self.after(0, update)

        threading.Thread(target=run, daemon=True).start()

    def _set_error(self, msg: str):
        self.error_box.configure(state="normal")
        self.error_box.delete("1.0", "end")
        if msg:
            self.error_box.insert("end", msg)
            self.error_box.pack(fill="x", padx=16, pady=(0, 8))
        else:
            self.error_box.pack_forget()
        self.error_box.configure(state="disabled")

    def _init_mariadb(self):
        if not downloader.is_mariadb_ready():
            self._set_error("ต้องติดตั้ง MariaDB ก่อน")
            return
        self.init_db_btn.configure(state="disabled", text="กำลัง initialize…")
        self._set_error("")

        def run():
            ok, msg = srv.initialize_mariadb()
            def update():
                self.init_db_btn.configure(state="normal", text="🗄 Initialize MariaDB")
                if ok:
                    self.config.mariadb_initialized = True
                    self._set_error("")
                else:
                    self._set_error(f"[Initialize MariaDB] {msg}")
            self.after(0, update)

        threading.Thread(target=run, daemon=True).start()

    def _install_ca(self):
        self.ca_btn.configure(state="disabled", text="กำลัง request admin… (กด Yes ใน UAC)")

        def run():
            ok, msg = ssl_mgr.install_root_ca()

            def update():
                if ok:
                    self._set_error("")
                    self.ca_btn.configure(
                        state="normal",
                        text="✓ Root CA installed — ปิด/เปิด Chrome ใหม่",
                        fg_color="#065f46", hover_color="#047857",
                    )
                else:
                    self._set_error(f"[Install Root CA] {msg}")
                    self.ca_btn.configure(
                        state="normal",
                        text="🔒 Install mkcert Root CA (ต้องการ admin ครั้งเดียว)",
                    )
            self.after(0, update)

        threading.Thread(target=run, daemon=True).start()

    def _done(self):
        self.config.installed_php = [v for v in PHP_VERSIONS if downloader.is_php_ready(v)]
        self.config.apache_ready = downloader.is_apache_ready()
        self.config.mariadb_ready = downloader.is_mariadb_ready()
        self.config.phpmyadmin_ready = downloader.is_phpmyadmin_ready()
        self.config.mkcert_ready = downloader.is_mkcert_ready()
        # Reset initialized flag if data dir is missing (MariaDB was re-downloaded)
        if not (MARIADB_DATA / "mysql").exists():
            self.config.mariadb_initialized = False
        if self.on_done:
            self.on_done()
        self.destroy()
