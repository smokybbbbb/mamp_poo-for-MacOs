"""macOS /etc/hosts manager — elevates via osascript (system password prompt)."""
import subprocess
import tempfile
from pathlib import Path

HOSTS_FILE = Path("/etc/hosts")
MARKER = "# MampPoo"


def _read_hosts() -> str:
    try:
        return HOSTS_FILE.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _managed_domains() -> list[str]:
    domains = []
    in_block = False
    for line in _read_hosts().splitlines():
        if line.strip() == f"{MARKER} BEGIN":
            in_block = True; continue
        if line.strip() == f"{MARKER} END":
            in_block = False; continue
        if in_block and line.strip() and not line.startswith("#"):
            parts = line.split()
            if len(parts) >= 2:
                domains.append(parts[1])
    return domains


def _build_hosts_content(domains: list[str]) -> str:
    original = _read_hosts()
    cleaned, in_block = [], False
    for line in original.splitlines():
        if line.strip() == f"{MARKER} BEGIN": in_block = True; continue
        if line.strip() == f"{MARKER} END":   in_block = False; continue
        if not in_block:
            cleaned.append(line)
    if domains:
        block = [f"{MARKER} BEGIN"]
        for d in domains:
            block.append(f"127.0.0.1  {d}")
        block.append(f"{MARKER} END")
        return "\n".join(cleaned).rstrip() + "\n\n" + "\n".join(block) + "\n"
    return "\n".join(cleaned).rstrip() + "\n"


def _write_hosts_elevated(content: str) -> tuple[bool, str]:
    """Write hosts file using sudo via osascript (shows GUI password prompt)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                     delete=False, encoding="utf-8") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    # osascript "do shell script ... with administrator privileges" pops the
    # standard macOS authentication dialog.
    shell = f"cp {tmp_path!r} /etc/hosts && chmod 644 /etc/hosts"
    osa = (
        f'do shell script "{shell.replace(chr(34), chr(92)+chr(34))}" '
        f'with administrator privileges'
    )
    try:
        r = subprocess.run(
            ["osascript", "-e", osa],
            capture_output=True, text=True, timeout=60,
        )
        Path(tmp_path).unlink(missing_ok=True)
        if r.returncode != 0:
            return False, (r.stderr or "Authentication cancelled").strip()
        return True, "hosts updated"
    except subprocess.TimeoutExpired:
        Path(tmp_path).unlink(missing_ok=True)
        return False, "Timed out waiting for password"
    except Exception as e:
        Path(tmp_path).unlink(missing_ok=True)
        return False, str(e)


def add_domain(domain: str) -> tuple[bool, str]:
    current = _managed_domains()
    if domain not in current:
        current.append(domain)
    return _write_hosts_elevated(_build_hosts_content(current))


def remove_domain(domain: str) -> tuple[bool, str]:
    current = _managed_domains()
    if domain in current:
        current.remove(domain)
    return _write_hosts_elevated(_build_hosts_content(current))


def sync_domains(domains: list[str]) -> tuple[bool, str]:
    return _write_hosts_elevated(_build_hosts_content(list(set(domains))))


def domain_in_hosts(domain: str) -> bool:
    return domain in _managed_domains()
