"""Start/stop Apache, PHP-FPM/CGI, and MariaDB processes (macOS)."""
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, Optional

from manager.config import (
    APACHE_DIR, PHP_DIR, MARIADB_DIR, MARIADB_DATA, PHPMYADMIN_DIR,
    CERTS_DIR, VHOSTS_DIR, DATA_DIR,
    PHP_PORTS, PHP_VERSIONS, AppConfig, VHost,
)

# ─── Process handles ──────────────────────────────────────────────────────────
_apache_proc: Optional[subprocess.Popen] = None
_php_procs: Dict[str, subprocess.Popen] = {}
_mariadb_proc: Optional[subprocess.Popen] = None


def _run(cmd, cwd=None) -> subprocess.Popen:
    return subprocess.Popen(
        cmd, cwd=cwd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def _run_wait(cmd, cwd=None, timeout=15) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return -1, "timeout"
    except Exception as e:
        return -1, str(e)


# ─── MariaDB ──────────────────────────────────────────────────────────────────

def _write_mariadb_ini():
    MARIADB_DATA.mkdir(parents=True, exist_ok=True)
    ini = MARIADB_DIR / "my.cnf"
    ini.write_text(
        "[mysqld]\n"
        f"basedir={MARIADB_DIR}\n"
        f"datadir={MARIADB_DATA}\n"
        "port=3306\n"
        "character-set-server=utf8mb4\n"
        "collation-server=utf8mb4_unicode_ci\n"
        "sql_mode=NO_ENGINE_SUBSTITUTION\n"
        "[client]\nport=3306\n",
        encoding="utf-8",
    )


def initialize_mariadb() -> tuple[bool, str]:
    mysqld = MARIADB_DIR / "bin" / "mysqld"
    mysql_install = MARIADB_DIR / "bin" / "mysql_install_db"
    if not mysqld.exists():
        return False, "MariaDB not downloaded"

    if MARIADB_DATA.exists():
        shutil.rmtree(MARIADB_DATA)
    MARIADB_DATA.mkdir(parents=True)
    _write_mariadb_ini()

    if mysql_install.exists():
        cmd = [str(mysql_install),
               f"--basedir={MARIADB_DIR}",
               f"--datadir={MARIADB_DATA}",
               "--auth-root-authentication-method=normal"]
    else:
        cmd = [str(mysqld), "--initialize-insecure",
               f"--basedir={MARIADB_DIR}",
               f"--datadir={MARIADB_DATA}"]
    code, msg = _run_wait(cmd, cwd=str(MARIADB_DIR / "bin"), timeout=120)
    if not (MARIADB_DATA / "mysql").exists():
        return False, (msg[-600:] if msg else "Initialization produced no mysql/ dir")
    return True, "ok"


def start_mariadb() -> tuple[bool, str]:
    global _mariadb_proc
    if is_mariadb_running():
        return True, "already running"
    mysqld = MARIADB_DIR / "bin" / "mysqld"
    if not mysqld.exists():
        return False, "MariaDB not downloaded"
    if not (MARIADB_DATA / "mysql").exists():
        return False, "MariaDB not initialized — open Setup and click Initialize"
    _write_mariadb_ini()
    ini = MARIADB_DIR / "my.cnf"
    try:
        _mariadb_proc = _run(
            [str(mysqld), f"--defaults-file={ini}"],
            cwd=str(MARIADB_DIR / "bin"),
        )
        time.sleep(2.5)
        if _mariadb_proc.poll() is not None:
            err = _mariadb_proc.stderr.read().decode(errors="replace")[-600:]
            return False, err or "MariaDB exited immediately"
        return True, "ok"
    except Exception as e:
        return False, str(e)


def stop_mariadb() -> bool:
    global _mariadb_proc
    mysqladmin = MARIADB_DIR / "bin" / "mysqladmin"
    if mysqladmin.exists():
        _run_wait([str(mysqladmin), "-u", "root", "--protocol=TCP",
                   "--connect-timeout=3", "shutdown"], timeout=8)
    if _mariadb_proc:
        try:
            _mariadb_proc.terminate()
            _mariadb_proc.wait(timeout=5)
        except Exception:
            pass
        _mariadb_proc = None
    return True


def is_mariadb_running() -> bool:
    return _mariadb_proc is not None and _mariadb_proc.poll() is None


# ─── PHP-CGI ──────────────────────────────────────────────────────────────────
# On macOS we DON'T need an FCGI proxy — Apache's mod_proxy_fcgi handles
# SCRIPT_FILENAME correctly with Unix paths.

def start_php(version: str) -> tuple[bool, str]:
    if version in _php_procs and _php_procs[version].poll() is None:
        return True, "already running"

    php_cgi = PHP_DIR / version / "bin" / "php-cgi"
    if not php_cgi.exists():
        return False, f"PHP {version} not installed"
    port = PHP_PORTS.get(version)
    if not port:
        return False, "Unknown version"

    try:
        proc = _run([str(php_cgi), "-b", f"127.0.0.1:{port}"],
                    cwd=str(PHP_DIR / version))
        time.sleep(0.5)
        if proc.poll() is not None:
            err = proc.stderr.read().decode(errors="replace")[-300:]
            return False, err or "exited immediately"
        _php_procs[version] = proc
        return True, f"port {port}"
    except Exception as e:
        return False, str(e)


def stop_php(version: str) -> bool:
    proc = _php_procs.pop(version, None)
    if proc:
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            pass
    return True


def stop_all_php():
    for v in list(_php_procs):
        stop_php(v)


def is_php_running(version: str) -> bool:
    p = _php_procs.get(version)
    return p is not None and p.poll() is None


# ─── Apache ───────────────────────────────────────────────────────────────────

def start_apache(config: AppConfig = None) -> tuple[bool, str]:
    global _apache_proc
    if is_apache_running():
        return True, "already running"
    httpd = APACHE_DIR / "bin" / "httpd"
    if not httpd.exists():
        return False, "Apache not downloaded"
    write_apache_conf(config)
    try:
        _apache_proc = _run([str(httpd), "-d", str(APACHE_DIR), "-DFOREGROUND"],
                            cwd=str(APACHE_DIR / "bin"))
        time.sleep(1.2)
        if _apache_proc.poll() is not None:
            err = _apache_proc.stderr.read().decode(errors="replace")[-600:]
            return False, err or "Apache exited immediately"
        return True, "ok"
    except Exception as e:
        return False, str(e)


def stop_apache() -> bool:
    global _apache_proc
    httpd = APACHE_DIR / "bin" / "httpd"
    try:
        _run_wait([str(httpd), "-d", str(APACHE_DIR), "-k", "stop"], timeout=5)
    except Exception:
        pass
    if _apache_proc:
        try:
            _apache_proc.terminate()
            _apache_proc.wait(timeout=5)
        except Exception:
            pass
        _apache_proc = None
    return True


def reload_apache(config: AppConfig = None) -> tuple[bool, str]:
    if not is_apache_running():
        return start_apache(config)
    write_apache_conf(config)
    httpd = APACHE_DIR / "bin" / "httpd"
    code, msg = _run_wait([str(httpd), "-d", str(APACHE_DIR), "-k", "graceful"],
                          timeout=5)
    return code == 0, msg


def is_apache_running() -> bool:
    return _apache_proc is not None and _apache_proc.poll() is None


# ─── Start / Stop all ─────────────────────────────────────────────────────────

def start_all(config: AppConfig) -> list[str]:
    errors = []
    ok, msg = start_mariadb()
    if not ok:
        errors.append(f"MariaDB: {msg}")
    needed = {v.php_version for v in config.vhosts if v.enabled}
    from manager.downloader import is_php_ready
    installed = [ver for ver in PHP_VERSIONS if is_php_ready(ver)]
    needed |= {installed[0]} if installed and not needed else set()
    for ver in needed:
        ok, msg = start_php(ver)
        if not ok:
            errors.append(f"PHP {ver}: {msg}")
    ok, msg = start_apache(config)
    if not ok:
        errors.append(f"Apache: {msg}")
    return errors


def stop_all():
    stop_apache()
    stop_all_php()
    stop_mariadb()


# ─── Apache config generation ─────────────────────────────────────────────────

def write_apache_conf(config: AppConfig = None):
    if not APACHE_DIR.exists():
        return
    VHOSTS_DIR.mkdir(parents=True, exist_ok=True)
    logs_dir = APACHE_DIR / "logs"
    logs_dir.mkdir(exist_ok=True)

    apache_root = str(APACHE_DIR)
    pma_root = str(PHPMYADMIN_DIR)

    from manager.downloader import is_php_ready
    pma_php_port = next(
        (PHP_PORTS[v] for v in PHP_VERSIONS if is_php_ready(v)),
        9085,
    )

    http_port = config.http_port if config else 80
    https_port = config.https_port if config else 443

    has_ssl = config and any(v.https_enabled for v in config.vhosts if v.enabled)
    ssl_listen = f"Listen {https_port}" if has_ssl else ""
    ssl_modules = """\
LoadModule ssl_module modules/mod_ssl.so
LoadModule socache_shmcb_module modules/mod_socache_shmcb.so""" if has_ssl else ""
    ssl_global = """\
SSLSessionCache "shmcb:logs/ssl_scache(512000)"
SSLSessionCacheTimeout 300""" if has_ssl else ""

    httpd_conf = f"""ServerRoot "{apache_root}"
Listen {http_port}
{ssl_listen}

LoadModule mpm_event_module modules/mod_mpm_event.so
LoadModule actions_module modules/mod_actions.so
LoadModule alias_module modules/mod_alias.so
LoadModule auth_basic_module modules/mod_auth_basic.so
LoadModule authn_core_module modules/mod_authn_core.so
LoadModule authn_file_module modules/mod_authn_file.so
LoadModule authz_core_module modules/mod_authz_core.so
LoadModule authz_host_module modules/mod_authz_host.so
LoadModule authz_user_module modules/mod_authz_user.so
LoadModule autoindex_module modules/mod_autoindex.so
LoadModule dir_module modules/mod_dir.so
LoadModule env_module modules/mod_env.so
LoadModule filter_module modules/mod_filter.so
LoadModule headers_module modules/mod_headers.so
LoadModule log_config_module modules/mod_log_config.so
LoadModule mime_module modules/mod_mime.so
LoadModule proxy_module modules/mod_proxy.so
LoadModule proxy_fcgi_module modules/mod_proxy_fcgi.so
LoadModule rewrite_module modules/mod_rewrite.so
LoadModule setenvif_module modules/mod_setenvif.so
{ssl_modules}

ServerAdmin admin@localhost
ServerName localhost:80

<Directory />
    AllowOverride none
    Require all denied
</Directory>

DocumentRoot "{apache_root}/htdocs"
<Directory "{apache_root}/htdocs">
    Options Indexes FollowSymLinks
    AllowOverride All
    Require all granted
</Directory>

DirectoryIndex index.php index.html index.htm

TypesConfig conf/mime.types
ErrorLog "logs/error.log"
LogLevel warn
CustomLog "logs/access.log" common

{ssl_global}

# phpMyAdmin (built-in) — on macOS, SetHandler works correctly with Unix paths
<VirtualHost *:{http_port}>
    ServerName localhost
    DocumentRoot "{apache_root}/htdocs"

    Alias /phpmyadmin "{pma_root}"
    <Directory "{pma_root}">
        Options FollowSymLinks
        AllowOverride All
        Require all granted
        DirectoryIndex index.php
        <FilesMatch "\\.php$">
            SetHandler "proxy:fcgi://127.0.0.1:{pma_php_port}"
        </FilesMatch>
    </Directory>
</VirtualHost>

IncludeOptional conf/vhosts/*.conf
"""
    (APACHE_DIR / "conf" / "httpd.conf").write_text(httpd_conf, encoding="utf-8")

    if config:
        for f in VHOSTS_DIR.glob("*.conf"):
            f.unlink()
        for vhost in config.vhosts:
            if vhost.enabled:
                write_vhost_conf(vhost, http_port, https_port)


def write_vhost_conf(vhost: VHost, http_port: int = 80, https_port: int = 443):
    VHOSTS_DIR.mkdir(parents=True, exist_ok=True)
    root = str(Path(vhost.root_path))
    php_port = PHP_PORTS.get(vhost.php_version, 9085)

    http_block = f"""\
<VirtualHost *:{http_port}>
    ServerName {vhost.domain}
    DocumentRoot "{root}"

    <Directory "{root}">
        Options Indexes FollowSymLinks ExecCGI
        AllowOverride All
        Require all granted
    </Directory>

    DirectoryIndex index.php index.html index.htm

    <FilesMatch "\\.php$">
        SetHandler "proxy:fcgi://127.0.0.1:{php_port}"
    </FilesMatch>

    ErrorLog "logs/{vhost.domain}-error.log"
    CustomLog "logs/{vhost.domain}-access.log" common
</VirtualHost>
"""
    https_block = ""
    if vhost.https_enabled:
        cert = str(CERTS_DIR / f"{vhost.domain}.pem")
        key = str(CERTS_DIR / f"{vhost.domain}-key.pem")
        https_block = f"""
<VirtualHost *:{https_port}>
    ServerName {vhost.domain}
    DocumentRoot "{root}"

    SSLEngine on
    SSLCertificateFile    "{cert}"
    SSLCertificateKeyFile "{key}"

    <Directory "{root}">
        Options Indexes FollowSymLinks
        AllowOverride All
        Require all granted
    </Directory>

    DirectoryIndex index.php index.html index.htm

    <FilesMatch "\\.php$">
        SetHandler "proxy:fcgi://127.0.0.1:{php_port}"
    </FilesMatch>
</VirtualHost>
"""
    (VHOSTS_DIR / f"{vhost.domain}.conf").write_text(
        http_block + https_block, encoding="utf-8")


def remove_vhost_conf(domain: str):
    (VHOSTS_DIR / f"{domain}.conf").unlink(missing_ok=True)
