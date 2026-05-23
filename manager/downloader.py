"""Install Apache, PHP, MariaDB, phpMyAdmin, mkcert on macOS.

Strategy:
- mkcert, phpMyAdmin: direct download (single binary / zip)
- Apache, PHP, MariaDB: install via Homebrew, then symlink into our
  DATA_DIR so we can manage configs ourselves without touching brew prefix.

Requires Homebrew (https://brew.sh). The installer will offer to install it
on first use.
"""
import os
import re
import secrets
import shutil
import stat
import subprocess
import zipfile
from pathlib import Path
from typing import Callable, Optional

import requests

from manager.config import (
    DATA_DIR, APACHE_DIR, PHP_DIR, MARIADB_DIR, PHPMYADMIN_DIR, MKCERT_DIR,
    MKCERT_URL, PHPMYADMIN_URL, ARCH,
)

_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


# ─── Homebrew helpers ─────────────────────────────────────────────────────────

def _brew_prefix() -> Optional[Path]:
    """Return Homebrew prefix or None if brew not installed."""
    for candidate in ["/opt/homebrew/bin/brew", "/usr/local/bin/brew"]:
        if Path(candidate).exists():
            try:
                r = subprocess.run([candidate, "--prefix"],
                                   capture_output=True, text=True, timeout=5)
                if r.returncode == 0:
                    return Path(r.stdout.strip())
            except Exception:
                pass
    return None


def _brew_install(formula: str, progress_cb=None) -> tuple[bool, str]:
    brew = _brew_prefix()
    if not brew:
        return False, ("Homebrew is required. Install from https://brew.sh "
                       "(open Terminal, paste their one-liner).")
    brew_bin = brew / "bin" / "brew"
    try:
        proc = subprocess.Popen(
            [str(brew_bin), "install", formula],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        # Crude progress: drip 0 → 0.95 over output lines
        progress = 0.0
        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
            if progress_cb and progress < 0.95:
                progress = min(0.95, progress + 0.02)
                progress_cb(progress)
        if proc.returncode != 0:
            return False, f"brew install {formula} failed (exit {proc.returncode})"
        if progress_cb:
            progress_cb(1.0)
        return True, f"{formula} installed via Homebrew"
    except Exception as e:
        return False, str(e)


def _symlink_brew_pkg(formula: str, dest: Path,
                      lookup_subdir: str = "") -> tuple[bool, str]:
    """Create dest as a symlink to the brew installation of `formula`."""
    brew = _brew_prefix()
    if not brew:
        return False, "Homebrew missing"
    src = brew / "opt" / formula
    if lookup_subdir:
        src = src / lookup_subdir
    if not src.exists():
        return False, f"{src} not found after brew install"
    if dest.exists() or dest.is_symlink():
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        else:
            shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.symlink_to(src)
    return True, "linked"


# ─── Download helper ──────────────────────────────────────────────────────────

def _download(url: str, dest: Path,
              progress_cb: Optional[Callable[[float], None]] = None) -> None:
    resp = requests.get(url, stream=True, timeout=120, headers=_HEADERS,
                        allow_redirects=True)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0))
    done = 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(65536):
            f.write(chunk)
            done += len(chunk)
            if progress_cb and total:
                progress_cb(done / total)


def _is_valid_zip(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            if f.read(2) != b"PK":
                return False
        with zipfile.ZipFile(path) as zf:
            return len(zf.namelist()) > 0
    except Exception:
        return False


# ─── Apache (via Homebrew httpd) ──────────────────────────────────────────────

def download_apache(progress_cb=None) -> tuple[bool, str]:
    ok, msg = _brew_install("httpd", progress_cb)
    if not ok:
        return ok, msg
    ok, msg = _symlink_brew_pkg("httpd", APACHE_DIR)
    if not ok:
        return ok, msg
    # Ensure conf dir is writable (brew links a read-only formula dir; copy
    # the conf out so we can rewrite httpd.conf freely).
    target_conf = APACHE_DIR / "conf"
    if target_conf.is_symlink() or not target_conf.exists():
        brew = _brew_prefix()
        src_conf = brew / "etc" / "httpd"
        if src_conf.exists():
            # Move into a writable location inside our APPSUPPORT
            real_conf = DATA_DIR / "apache_conf"
            if real_conf.exists():
                shutil.rmtree(real_conf)
            shutil.copytree(src_conf, real_conf)
            # Replace APACHE_DIR/conf symlink with our writable dir
            # (httpd was linked to brew opt; we need a custom layout)
            # The simplest: drop a wrapper APACHE_DIR with our own structure
    return True, "ok"


def is_apache_ready() -> bool:
    return (APACHE_DIR / "bin" / "httpd").exists()


# ─── PHP (via Homebrew shivammathur/php tap or php@X.Y formulae) ──────────────

def download_php(version: str, progress_cb=None) -> tuple[bool, str]:
    # Try the official php@X.Y formula first (e.g. php@8.3)
    formula = f"php@{version}"
    ok, msg = _brew_install(formula, progress_cb)
    if not ok:
        # Fall back to shivammathur tap for older/newer versions
        brew = _brew_prefix()
        if brew:
            brew_bin = brew / "bin" / "brew"
            try:
                subprocess.run([str(brew_bin), "tap", "shivammathur/php"],
                               capture_output=True, timeout=30)
            except Exception:
                pass
            ok, msg = _brew_install(f"shivammathur/php/php@{version}", progress_cb)
        if not ok:
            return False, msg
    ok, msg = _symlink_brew_pkg(formula, PHP_DIR / version)
    if not ok:
        return False, msg
    _setup_php_ini(version)
    return True, f"PHP {version} installed via Homebrew"


def _setup_php_ini(version: str):
    """Find php.ini under the brew prefix and patch sane defaults."""
    php_dir = PHP_DIR / version
    # Brew's php@X.Y typically has php.ini at: <prefix>/etc/php/X.Y/php.ini
    brew = _brew_prefix()
    if not brew:
        return
    candidates = [
        brew / "etc" / "php" / version / "php.ini",
        php_dir / "lib" / "php.ini",
    ]
    ini = next((p for p in candidates if p.exists()), None)
    if not ini:
        return
    text = ini.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r'^\s*display_errors\s*=.*$', 'display_errors = Off',
                  text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r'^\s*display_startup_errors\s*=.*$',
                  'display_startup_errors = Off',
                  text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r'^\s*error_reporting\s*=.*$',
                  'error_reporting = E_ALL & ~E_DEPRECATED & ~E_STRICT & ~E_NOTICE',
                  text, flags=re.MULTILINE | re.IGNORECASE)
    try:
        ini.write_text(text, encoding="utf-8")
    except PermissionError:
        pass  # brew-installed ini may be read-only; user-level override needed


def is_php_ready(version: str) -> bool:
    return (PHP_DIR / version / "bin" / "php-cgi").exists()


# ─── MariaDB (via Homebrew) ───────────────────────────────────────────────────

def download_mariadb(progress_cb=None) -> tuple[bool, str]:
    ok, msg = _brew_install("mariadb", progress_cb)
    if not ok:
        return ok, msg
    return _symlink_brew_pkg("mariadb", MARIADB_DIR)


def is_mariadb_ready() -> bool:
    return (MARIADB_DIR / "bin" / "mysqld").exists()


# ─── phpMyAdmin (direct download) ─────────────────────────────────────────────

def download_phpmyadmin(progress_cb=None) -> tuple[bool, str]:
    zip_path = DATA_DIR / "_phpmyadmin.zip"
    try:
        _download(PHPMYADMIN_URL, zip_path, progress_cb)
        if not _is_valid_zip(zip_path):
            zip_path.unlink(missing_ok=True)
            return False, "Downloaded file is not a valid zip"
        tmp = DATA_DIR / "_pma_tmp"
        if tmp.exists():
            shutil.rmtree(tmp)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp)
        extracted = next(p for p in tmp.iterdir() if p.is_dir())
        if PHPMYADMIN_DIR.exists():
            shutil.rmtree(PHPMYADMIN_DIR)
        shutil.move(str(extracted), str(PHPMYADMIN_DIR))
        shutil.rmtree(tmp, ignore_errors=True)
        zip_path.unlink(missing_ok=True)
        _write_phpmyadmin_config()
        return True, "ok"
    except Exception as e:
        zip_path.unlink(missing_ok=True)
        return False, str(e)


def _write_phpmyadmin_config():
    secret = secrets.token_hex(16)
    cfg = f"""<?php
declare(strict_types=1);
$cfg['blowfish_secret'] = '{secret}';
$i = 0;
$i++;
$cfg['Servers'][$i]['auth_type']       = 'cookie';
$cfg['Servers'][$i]['host']            = '127.0.0.1';
$cfg['Servers'][$i]['port']            = '3306';
$cfg['Servers'][$i]['compress']        = false;
$cfg['Servers'][$i]['AllowNoPassword'] = true;
$cfg['UploadDir'] = '';
$cfg['SaveDir']   = '';
$cfg['TempDir']   = sys_get_temp_dir();
"""
    (PHPMYADMIN_DIR / "config.inc.php").write_text(cfg, encoding="utf-8")


def is_phpmyadmin_ready() -> bool:
    return (PHPMYADMIN_DIR / "index.php").exists()


# ─── mkcert (direct binary download) ──────────────────────────────────────────

def download_mkcert(progress_cb=None) -> tuple[bool, str]:
    try:
        MKCERT_DIR.mkdir(parents=True, exist_ok=True)
        out = MKCERT_DIR / "mkcert"
        _download(MKCERT_URL, out, progress_cb)
        # Make executable
        out.chmod(out.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return True, "ok"
    except Exception as e:
        return False, str(e)


def is_mkcert_ready() -> bool:
    return (MKCERT_DIR / "mkcert").exists()
