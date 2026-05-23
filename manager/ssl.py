"""SSL certificate management via mkcert (macOS)."""
import os
import subprocess
from pathlib import Path
from manager.config import MKCERT_DIR, CERTS_DIR

_MKCERT = MKCERT_DIR / "mkcert"


def _caroot() -> Path | None:
    if not _MKCERT.exists():
        return None
    try:
        r = subprocess.run([str(_MKCERT), "-CAROOT"],
                           capture_output=True, text=True, timeout=5)
        path = r.stdout.strip()
        return Path(path) if path else None
    except Exception:
        return None


def is_root_ca_installed() -> bool:
    """Check if mkcert's root CA is in the macOS keychain."""
    caroot = _caroot()
    if not caroot:
        return False
    root_pem = caroot / "rootCA.pem"
    if not root_pem.exists():
        return False
    # `security find-certificate -c "mkcert ..."` returns 0 if found.
    try:
        r = subprocess.run(
            ["security", "find-certificate", "-c", "mkcert",
             "/Library/Keychains/System.keychain"],
            capture_output=True, text=True, timeout=10,
        )
        return r.returncode == 0
    except Exception:
        return False


def install_root_ca() -> tuple[bool, str]:
    if not _MKCERT.exists():
        return False, "mkcert not installed"
    if is_root_ca_installed():
        return True, "Root CA already installed"

    # mkcert -install needs sudo to write to System.keychain.
    # Run via osascript so the password prompt is a normal macOS dialog.
    cmd = f"{str(_MKCERT)!r} -install"
    osa = (
        f'do shell script "{cmd.replace(chr(34), chr(92)+chr(34))}" '
        f'with administrator privileges'
    )
    try:
        r = subprocess.run(["osascript", "-e", osa],
                           capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return False, "Timed out waiting for password"
    except Exception as e:
        return False, str(e)

    if is_root_ca_installed():
        return True, "Root CA installed successfully"
    return False, (r.stderr or r.stdout or "Install failed — did you enter the password?").strip()


def generate_cert(domain: str) -> tuple[bool, str]:
    if not _MKCERT.exists():
        return False, "mkcert not installed"
    CERTS_DIR.mkdir(parents=True, exist_ok=True)
    cert = CERTS_DIR / f"{domain}.pem"
    key = CERTS_DIR / f"{domain}-key.pem"
    try:
        r = subprocess.run(
            [str(_MKCERT), "-cert-file", str(cert), "-key-file", str(key), domain],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0:
            return True, f"Cert created for {domain}"
        return False, (r.stderr or r.stdout).strip()
    except Exception as e:
        return False, str(e)


def cert_exists(domain: str) -> bool:
    return (CERTS_DIR / f"{domain}.pem").exists() and \
           (CERTS_DIR / f"{domain}-key.pem").exists()


def remove_cert(domain: str):
    (CERTS_DIR / f"{domain}.pem").unlink(missing_ok=True)
    (CERTS_DIR / f"{domain}-key.pem").unlink(missing_ok=True)
