"""Mamp Poo — entry point.  Just run: python main.py"""
import importlib.util
import subprocess
import sys

REQUIRED = [
    ("customtkinter", "customtkinter"),
    ("requests",      "requests"),
    ("PIL",           "Pillow"),
    ("pystray",       "pystray"),
]


def _ensure_packages():
    missing = [pkg for mod, pkg in REQUIRED if importlib.util.find_spec(mod) is None]
    if missing:
        print(f"Installing packages: {', '.join(missing)} …")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet"] + missing
        )
        print("Done.\n")


if __name__ == "__main__":
    _ensure_packages()

    import customtkinter as ctk
    from ui.app import App

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    app = App()
    app.mainloop()
