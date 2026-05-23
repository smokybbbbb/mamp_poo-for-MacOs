"""Sites page — list and manage vhosts."""
import webbrowser
import tkinter as tk

import customtkinter as ctk

from manager import server as srv, ssl as ssl_mgr, hosts as hosts_mgr
from manager.config import AppConfig, VHost, save_config
from manager.downloader import is_php_ready
from ui.dialogs import VHostDialog


class SitesPage(ctk.CTkFrame):
    def __init__(self, parent, config: AppConfig, on_change=None):
        super().__init__(parent, fg_color="transparent")
        self.config = config
        self.on_change = on_change
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=20, pady=(16, 8))
        ctk.CTkLabel(hdr, text="Sites", font=("", 20, "bold")).pack(side="left")
        ctk.CTkButton(hdr, text="+ Add Site", width=100,
                      command=self._add_site).pack(side="right")

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        self.refresh()

    def refresh(self):
        for w in self.scroll.winfo_children():
            w.destroy()
        if not self.config.vhosts:
            ctk.CTkLabel(self.scroll,
                         text="ยังไม่มี Site — กด '+ Add Site' เพื่อเพิ่ม",
                         text_color="gray").pack(pady=60)
            return
        for vh in self.config.vhosts:
            self._card(vh)

    def _card(self, vh: VHost):
        php_ok = is_php_ready(vh.php_version)
        running = srv.is_apache_running() and srv.is_php_running(vh.php_version)
        dot_col = "#22c55e" if running else ("#f97316" if php_ok else "#ef4444")

        card = ctk.CTkFrame(self.scroll, corner_radius=10, fg_color="#1e2433")
        card.pack(fill="x", pady=5)

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(12, 8))

        ctk.CTkLabel(top, text="●", text_color=dot_col, font=("", 16),
                     width=22).pack(side="left")

        info = ctk.CTkFrame(top, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True, padx=(4, 0))

        name_row = ctk.CTkFrame(info, fg_color="transparent")
        name_row.pack(fill="x")
        ctk.CTkLabel(name_row, text=vh.domain,
                     font=("", 15, "bold")).pack(side="left")
        self._badge(name_row, f"PHP {vh.php_version}",
                    "#1e3a5f" if php_ok else "#3a1a1a",
                    "#7dd3fc" if php_ok else "#fca5a5")
        if vh.https_enabled:
            self._badge(name_row, "HTTPS", "#065f46", "#34d399")
        if not php_ok:
            self._badge(name_row, "PHP not installed", "#3a1a1a", "#fca5a5")

        ctk.CTkLabel(info, text=vh.root_path, text_color="gray",
                     font=("", 11)).pack(anchor="w")

        btns = ctk.CTkFrame(top, fg_color="transparent")
        btns.pack(side="right")

        proto = "https" if vh.https_enabled else "http"
        port = self.config.https_port if vh.https_enabled else self.config.http_port
        suffix = f":{port}" if port not in (80, 443) else ""
        url = f"{proto}://{vh.domain}{suffix}"

        ctk.CTkButton(btns, text="Open", width=60,
                      command=lambda u=url: webbrowser.open(u)).pack(side="left", padx=2)
        ctk.CTkButton(btns, text="Edit", width=60, fg_color="gray40",
                      command=lambda v=vh: self._edit(v)).pack(side="left", padx=2)
        ctk.CTkButton(btns, text="Delete", width=70,
                      fg_color="#7f1d1d", hover_color="#991b1b",
                      command=lambda v=vh: self._delete(v)).pack(side="left", padx=2)

    @staticmethod
    def _badge(parent, text, bg, fg):
        tk.Label(parent, text=f" {text} ", bg=bg, fg=fg,
                 font=("Segoe UI", 9, "bold"), padx=4, pady=1
                 ).pack(side="left", padx=(6, 0))

    def _add_site(self):
        def on_save(vh: VHost):
            self.config.vhosts.append(vh)
            self._apply(vh)
        VHostDialog(self, self.config, on_save=on_save)

    def _edit(self, vh: VHost):
        old_domain, old_https = vh.domain, vh.https_enabled

        def on_save(updated: VHost):
            if old_domain != updated.domain:
                hosts_mgr.remove_domain(old_domain)
                srv.remove_vhost_conf(old_domain)
            if old_https and not updated.https_enabled:
                ssl_mgr.remove_cert(old_domain)
            self._apply(updated)

        VHostDialog(self, self.config, vhost=vh, on_save=on_save)

    def _delete(self, vh: VHost):
        dlg = ctk.CTkInputDialog(
            text=f"พิมพ์ '{vh.domain}' เพื่อยืนยันการลบ:",
            title="ลบ Site")
        if dlg.get_input() != vh.domain:
            return
        hosts_mgr.remove_domain(vh.domain)
        ssl_mgr.remove_cert(vh.domain)
        srv.remove_vhost_conf(vh.domain)
        self.config.vhosts = [v for v in self.config.vhosts if v.id != vh.id]
        save_config(self.config)
        srv.reload_apache(self.config)
        self.refresh()
        if self.on_change:
            self.on_change()

    def _apply(self, vh: VHost):
        srv.write_vhost_conf(vh, self.config.http_port, self.config.https_port)
        if vh.https_enabled and not ssl_mgr.cert_exists(vh.domain):
            ssl_mgr.generate_cert(vh.domain)
        hosts_mgr.add_domain(vh.domain)
        save_config(self.config)
        if is_php_ready(vh.php_version) and srv.is_apache_running():
            srv.start_php(vh.php_version)
        srv.reload_apache(self.config)
        self.refresh()
        if self.on_change:
            self.on_change()
