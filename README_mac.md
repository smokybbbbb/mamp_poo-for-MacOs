# Mamp Poo — macOS edition

Local development server manager for macOS (Intel + Apple Silicon).

---

## ⚠️ Status: starting template

โครงสร้างถูก adapt จาก Windows version แล้ว แต่**ยังไม่ได้ test บน Mac จริง**
ต้องไปลอง run และอาจต้องปรับเพิ่มเติม โดยเฉพาะส่วน Homebrew integration

---

## Requirements

- **macOS 11+** (Intel หรือ Apple Silicon)
- **Python 3.10+** — มากับ macOS หรือ `brew install python@3.12`
- **[Homebrew](https://brew.sh)** — ใช้ติดตั้ง Apache/PHP/MariaDB (single source of truth)
- พื้นที่ดิสก์ ~500MB

---

## ความต่างจาก Windows version

| ส่วน | Windows | macOS |
|---|---|---|
| **Data dir** | `%APPDATA%\LocalDevManager\` | `~/Library/Application Support/MampPoo/` |
| **hosts file** | `C:\Windows\System32\drivers\etc\hosts` (UAC) | `/etc/hosts` (osascript + password) |
| **mkcert install** | PowerShell `Start-Process RunAs` | `osascript ... administrator privileges` |
| **Apache/PHP/MariaDB** | Download zip จาก Apache Lounge / php.net | Install via `brew install httpd php@X.Y mariadb` |
| **FCGI proxy** | ✅ จำเป็น (Windows path bug) | ❌ ไม่ต้องใช้ (Unix paths ทำงานปกติ) |
| **Launcher** | `Mamp Poo.vbs` | `Mamp Poo.command` |
| **Tray icon** | Windows system tray | macOS menu bar (pystray ใช้ได้บนทั้งสอง) |
| **Build** | `.exe` ด้วย PyInstaller | `.app` bundle ด้วย PyInstaller |

---

## วิธีรันครั้งแรก

```bash
cd "Mamp Poo (macOS folder)"

# Install Homebrew if not yet — paste this in Terminal:
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python deps
python3 -m pip install -r requirements.txt

# Run
python3 main.py
# OR double-click "Mamp Poo.command"
```

ครั้งแรกแอปจะเปิด Setup Dialog — กด Install ทีละอัน
แอปจะรัน `brew install httpd / php@X.Y / mariadb` ให้อัตโนมัติ

---

## Build เป็น .app

```bash
chmod +x build_app.sh
./build_app.sh
```

ผลลัพธ์: `dist/Mamp Poo.app` ลากไปใส่ `/Applications` ได้เลย

---

## สิ่งที่อาจต้องปรับเมื่อเทสจริง

1. **Homebrew formula symlink layout** — ตอน `_symlink_brew_pkg` อาจต้องปรับให้ตรงกับโครงสร้างจริงของ brew
   - `brew --prefix httpd` ใช้ตอน start Apache
   - `brew --prefix php@8.3` มี `bin/php-cgi` ไหม

2. **php.ini path** — โดย default brew วางที่ `<prefix>/etc/php/X.Y/php.ini` แต่บางเวอร์ชั่นใช้ `/usr/local/etc/php/X.Y/`

3. **MariaDB initialization** — บน macOS อาจต้องใช้ `mariadb-install-db` (script ของ brew) แทน `mysql_install_db`

4. **Apache binding port 80** — macOS ไม่ต้อง admin เพราะ port < 1024 ก็ยังต้อง root
   → แนะนำให้ user เปลี่ยน port เป็น **8080/8443** ใน Settings

5. **Tray icon บน macOS** — pystray จะใช้ NSStatusBar แต่บางครั้ง icon ไม่ขึ้น ต้องปรับขนาดเป็น 22x22 หรือ template image

6. **Code signing** — ถ้าจะ distribute `.app` ให้คนอื่นต้อง sign ด้วย Apple Developer ID มิฉะนั้น Gatekeeper จะบล็อก

---

## ไฟล์ที่แตกต่างจาก Windows

- `manager/config.py` — paths
- `manager/hosts.py` — `/etc/hosts` + osascript
- `manager/ssl.py` — mkcert via osascript
- `manager/server.py` — Unix paths, no FCGI proxy, no STARTUPINFO
- `manager/downloader.py` — Homebrew-based installer
- `Mamp Poo.command` — shell launcher
- `build_app.sh` — PyInstaller for macOS

**ไม่เปลี่ยน** จาก Windows version: `ui/*.py`, `main.py`, `crab_logo.png`
