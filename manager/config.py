import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List

# macOS data directory: ~/Library/Application Support/MampPoo
DATA_DIR = Path.home() / "Library" / "Application Support" / "MampPoo"

APACHE_DIR      = DATA_DIR / "apache"
PHP_DIR         = DATA_DIR / "php"
MARIADB_DIR     = DATA_DIR / "mariadb"       # binary installation
MARIADB_DATA    = DATA_DIR / "mariadb_data"  # actual databases (survives reinstall)
PHPMYADMIN_DIR  = DATA_DIR / "phpmyadmin"
MKCERT_DIR      = DATA_DIR / "mkcert"
CERTS_DIR       = DATA_DIR / "certs"
VHOSTS_DIR      = APACHE_DIR / "conf" / "vhosts"
CONFIG_FILE     = DATA_DIR / "config.json"

PHP_VERSIONS = ["8.5", "8.4", "8.3", "8.2", "8.1", "8.0", "7.4"]

PHP_PORTS = {
    "7.4": 9074,
    "8.0": 9080,
    "8.1": 9081,
    "8.2": 9082,
    "8.3": 9083,
    "8.4": 9084,
    "8.5": 9085,
}

# Detect Apple Silicon vs Intel for mkcert download
import platform
ARCH = "arm64" if platform.machine() == "arm64" else "amd64"

MKCERT_URL = (
    f"https://github.com/FiloSottile/mkcert/releases/download/"
    f"v1.4.4/mkcert-v1.4.4-darwin-{ARCH}"
)
PHPMYADMIN_URL = (
    "https://files.phpmyadmin.net/phpMyAdmin/5.2.1/"
    "phpMyAdmin-5.2.1-all-languages.zip"
)


@dataclass
class VHost:
    domain: str
    root_path: str
    php_version: str
    https_enabled: bool = False
    enabled: bool = True
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


@dataclass
class AppConfig:
    vhosts: List[VHost] = field(default_factory=list)
    http_port: int = 80
    https_port: int = 443
    installed_php: List[str] = field(default_factory=list)
    apache_ready: bool = False
    mariadb_ready: bool = False
    phpmyadmin_ready: bool = False
    mkcert_ready: bool = False
    mariadb_initialized: bool = False


def _ensure_dirs():
    for d in [DATA_DIR, CERTS_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def load_config() -> AppConfig:
    _ensure_dirs()
    if not CONFIG_FILE.exists():
        return AppConfig()
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        vhosts = [VHost(**v) for v in data.get("vhosts", [])]
        return AppConfig(
            vhosts=vhosts,
            http_port=data.get("http_port", 80),
            https_port=data.get("https_port", 443),
            installed_php=data.get("installed_php", []),
            apache_ready=data.get("apache_ready", False),
            mariadb_ready=data.get("mariadb_ready", False),
            phpmyadmin_ready=data.get("phpmyadmin_ready", False),
            mkcert_ready=data.get("mkcert_ready", False),
            mariadb_initialized=data.get("mariadb_initialized", False),
        )
    except Exception:
        return AppConfig()


def save_config(config: AppConfig):
    _ensure_dirs()
    data = {
        "vhosts": [asdict(v) for v in config.vhosts],
        "http_port": config.http_port,
        "https_port": config.https_port,
        "installed_php": config.installed_php,
        "apache_ready": config.apache_ready,
        "mariadb_ready": config.mariadb_ready,
        "phpmyadmin_ready": config.phpmyadmin_ready,
        "mkcert_ready": config.mkcert_ready,
        "mariadb_initialized": config.mariadb_initialized,
    }
    CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
