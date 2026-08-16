#!/usr/bin/env python3
"""
Rotorflight Lua EdgeTX Suite Updater / Installer
A desktop utility to download, install, and update the Rotorflight Lua suite for EdgeTX radios.
"""

import os
import sys
import json
import shutil
import zipfile
import threading
import platform
import re
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import List, Dict, Optional, Tuple

APP_TITLE = "Rotorflight EdgeTX Suite Updater"
APP_VERSION = "1.0.0"
DEFAULT_REPO = "rotorflight/rotorflight-lua-edgetx-suite"
GITHUB_API_RELEASES = f"https://api.github.com/repos/{DEFAULT_REPO}/releases"


class RadioDetector:
    """Helper to detect connected EdgeTX SD cards / radio drives across OS platforms."""

    @staticmethod
    def is_likely_radio_root(path: str) -> Tuple[bool, int]:
        if not os.path.isdir(path):
            return False, 0

        score = 0
        scripts_dir = os.path.join(path, "SCRIPTS")
        sounds_dir = os.path.join(path, "SOUNDS")
        widgets_dir = os.path.join(path, "WIDGETS")
        radio_dir = os.path.join(path, "RADIO")

        if os.path.isfile(os.path.join(path, "radio.cpuid")):
            score += 10
        if os.path.isfile(os.path.join(path, "sdcard.cpuid")):
            score += 10
        if os.path.isfile(os.path.join(path, "flash.cpuid")):
            score += 8
        if os.path.isfile(os.path.join(radio_dir, "radio.yml")) or os.path.isfile(os.path.join(radio_dir, "radio.bin")):
            score += 8
        if os.path.isdir(os.path.join(scripts_dir, "TOOLS")):
            score += 5
        if os.path.isdir(scripts_dir):
            score += 3
        if os.path.isdir(widgets_dir):
            score += 2
        if os.path.isdir(sounds_dir):
            score += 2

        is_radio = score >= 5 or (os.path.isdir(scripts_dir) and (os.path.isdir(widgets_dir) or os.path.isdir(sounds_dir)))
        return is_radio, score

    @classmethod
    def get_candidate_drives(cls) -> List[Tuple[str, str, int]]:
        candidates = []
        system = platform.system()

        if system == "Windows":
            import string
            for letter in string.ascii_uppercase:
                drive = f"{letter}:\\"
                if os.path.exists(drive):
                    try:
                        is_radio, score = cls.is_likely_radio_root(drive)
                        label = f"{drive} (Radio SD Card)" if is_radio else f"{drive}"
                        candidates.append((drive, label, score))
                    except Exception:
                        pass
        elif system == "Darwin":  # macOS
            volumes = "/Volumes"
            if os.path.exists(volumes):
                for item in os.listdir(volumes):
                    path = os.path.join(volumes, item)
                    if os.path.isdir(path):
                        is_radio, score = cls.is_likely_radio_root(path)
                        label = f"{item} (Radio)" if is_radio else item
                        candidates.append((path, label, score))
        else:  # Linux
            search_paths = ["/media", "/run/media", "/mnt"]
            for base in search_paths:
                if os.path.exists(base):
                    for root, dirs, _ in os.walk(base):
                        for d in dirs:
                            path = os.path.join(root, d)
                            is_radio, score = cls.is_likely_radio_root(path)
                            if is_radio:
                                candidates.append((path, f"{d} (Radio)", score))

        # Sort highest score first
        candidates.sort(key=lambda x: x[2], reverse=True)
        return candidates


class RFSuiteUpdaterApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("640x580")
        self.root.minsize(580, 520)

        # Apply icon if exists
        self._set_icon()

        # State
        self.selected_repo = tk.StringVar(value=DEFAULT_REPO)
        self.releases_data = []
        self.local_builds = []
        self.selected_drive = tk.StringVar()
        self.selected_release_tag = tk.StringVar()
        self.selected_language = tk.StringVar(value="de")
        self.include_prereleases = tk.BooleanVar(value=True)
        self.preserve_settings = tk.BooleanVar(value=True)
        self.local_zip_path = tk.StringVar()
        self.is_local_mode = tk.BooleanVar(value=False)

        self._configure_styles()
        self._build_ui()

        # Initial background scan
        self.root.after(100, self.refresh_drives)
        self.root.after(200, self.fetch_releases_async)

    def _set_icon(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        ico_path = os.path.join(base_dir, "updater.ico")
        if os.path.isfile(ico_path):
            try:
                self.root.iconbitmap(ico_path)
            except Exception:
                pass

    def _configure_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        # Palette
        bg_dark = "#1e1e24"
        card_bg = "#2b2d3a"
        fg_text = "#e6e6e6"
        accent = "#0078d4"
        accent_hover = "#106ebe"
        success_color = "#107c41"

        self.root.configure(bg=bg_dark)

        style.configure("TFrame", background=bg_dark)
        style.configure("Card.TFrame", background=card_bg, relief="flat")
        style.configure("TLabel", background=bg_dark, foreground=fg_text, font=("Segoe UI", 9))
        style.configure("Card.TLabel", background=card_bg, foreground=fg_text, font=("Segoe UI", 9))
        style.configure("CardTitle.TLabel", background=card_bg, foreground="#60cdff", font=("Segoe UI", 10, "bold"))
        style.configure("Header.TLabel", background=bg_dark, foreground="#ffffff", font=("Segoe UI", 13, "bold"))
        style.configure("SubHeader.TLabel", background=bg_dark, foreground="#aaaaaa", font=("Segoe UI", 8))
        
        style.configure("TCheckbutton", background=card_bg, foreground=fg_text, font=("Segoe UI", 9))
        style.map("TCheckbutton", background=[("active", card_bg)])

        style.configure("TButton", font=("Segoe UI", 9), padding=5)
        style.configure("Accent.TButton", background=accent, foreground="#ffffff", font=("Segoe UI", 10, "bold"), padding=6)
        style.map("Accent.TButton", background=[("active", accent_hover), ("disabled", "#444444")])

        style.configure("Success.TButton", background=success_color, foreground="#ffffff", font=("Segoe UI", 10, "bold"), padding=6)

        style.configure("TCombobox", font=("Segoe UI", 9))
        style.configure("Horizontal.TProgressbar", background=accent, troughcolor="#333333")

    def _build_ui(self):
        # Header container
        header_frame = ttk.Frame(self.root, padding=(16, 10, 16, 4))
        header_frame.pack(fill="x")

        title_lbl = ttk.Label(header_frame, text=APP_TITLE, style="Header.TLabel")
        title_lbl.pack(anchor="w")

        subtitle_lbl = ttk.Label(header_frame, text="Easily install and update Rotorflight Lua scripts on your EdgeTX radio", style="SubHeader.TLabel")
        subtitle_lbl.pack(anchor="w", pady=(2, 0))

        # Main container
        main_frame = ttk.Frame(self.root, padding=(16, 4, 16, 12))
        main_frame.pack(fill="both", expand=True)

        # 1. Drive Selection Card
        self._build_drive_card(main_frame)

        # 2. Release & Language Selection Card
        self._build_release_card(main_frame)

        # 3. Actions & Progress Card
        self._build_actions_card(main_frame)

        # 4. Status and Log Card
        self._build_log_card(main_frame)

    def _build_drive_card(self, parent):
        card = ttk.Frame(parent, style="Card.TFrame", padding=12)
        card.pack(fill="x", pady=4)

        header_row = ttk.Frame(card, style="Card.TFrame")
        header_row.pack(fill="x", pady=(0, 6))

        title = ttk.Label(header_row, text="1. Select Radio SD Card / Target Drive", style="CardTitle.TLabel")
        title.pack(side="left")

        self.installed_ver_lbl = ttk.Label(header_row, text="Installed: Unknown", style="Card.TLabel", foreground="#888888")
        self.installed_ver_lbl.pack(side="right")

        drive_row = ttk.Frame(card, style="Card.TFrame")
        drive_row.pack(fill="x")

        self.drive_combo = ttk.Combobox(drive_row, textvariable=self.selected_drive, state="normal", width=35)
        self.drive_combo.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.drive_combo.bind("<<ComboboxSelected>>", self._on_drive_selected)
        self.drive_combo.bind("<Return>", self._on_drive_selected)
        self.drive_combo.bind("<FocusOut>", self._on_drive_selected)

        browse_btn = ttk.Button(drive_row, text="Browse...", command=self._browse_drive, width=10)
        browse_btn.pack(side="left", padx=(0, 4))

        refresh_btn = ttk.Button(drive_row, text="🔄", command=self.refresh_drives, width=3)
        refresh_btn.pack(side="left")

    def _build_release_card(self, parent):
        card = ttk.Frame(parent, style="Card.TFrame", padding=12)
        card.pack(fill="x", pady=4)

        title = ttk.Label(card, text="2. Select Release Version & Language", style="CardTitle.TLabel")
        title.pack(anchor="w", pady=(0, 6))

        # Repository config row
        repo_row = ttk.Frame(card, style="Card.TFrame")
        repo_row.pack(fill="x", pady=(0, 4))

        lbl_repo = ttk.Label(repo_row, text="Repo:", style="Card.TLabel", width=10)
        lbl_repo.pack(side="left")

        self.repo_entry = ttk.Entry(repo_row, textvariable=self.selected_repo, font=("Segoe UI", 9))
        self.repo_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.repo_entry.bind("<Return>", lambda e: self.fetch_releases_async())

        # Version selection row
        rel_row = ttk.Frame(card, style="Card.TFrame")
        rel_row.pack(fill="x", pady=(0, 4))

        lbl_rel = ttk.Label(rel_row, text="Version:", style="Card.TLabel", width=10)
        lbl_rel.pack(side="left")

        self.release_combo = ttk.Combobox(rel_row, textvariable=self.selected_release_tag, state="readonly")
        self.release_combo.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.release_combo.bind("<<ComboboxSelected>>", self._on_release_selected)

        ref_rel_btn = ttk.Button(rel_row, text="🔄", command=self.fetch_releases_async, width=3)
        ref_rel_btn.pack(side="left")

        lang_row = ttk.Frame(card, style="Card.TFrame")
        lang_row.pack(fill="x", pady=(0, 4))

        lbl_lang = ttk.Label(lang_row, text="Language:", style="Card.TLabel", width=10)
        lbl_lang.pack(side="left")

        self.lang_combo = ttk.Combobox(lang_row, textvariable=self.selected_language, state="readonly", width=15)
        self.lang_combo["values"] = self._get_fallback_languages()
        self.lang_combo.pack(side="left", padx=(0, 10))

        prerelease_chk = ttk.Checkbutton(
            lang_row, 
            text="Include Pre-Releases", 
            variable=self.include_prereleases,
            command=self._update_release_list
        )
        prerelease_chk.pack(side="left", padx=(10, 0))

        # Local ZIP alternative
        local_row = ttk.Frame(card, style="Card.TFrame")
        local_row.pack(fill="x", pady=(2, 0))

        self.local_chk = ttk.Checkbutton(
            local_row,
            text="Install from Local ZIP File instead of GitHub",
            variable=self.is_local_mode,
            command=self._on_toggle_local_mode
        )
        self.local_chk.pack(side="left")

        self.local_browse_btn = ttk.Button(local_row, text="Select ZIP...", command=self._browse_local_zip, state="disabled")
        self.local_browse_btn.pack(side="left", padx=(10, 0))

        self.local_file_lbl = ttk.Label(card, textvariable=self.local_zip_path, style="Card.TLabel", foreground="#888888", font=("Segoe UI", 8))
        self.local_file_lbl.pack(anchor="w", pady=(2, 0))

    def _build_actions_card(self, parent):
        card = ttk.Frame(parent, style="Card.TFrame", padding=12)
        card.pack(fill="x", pady=4)

        opt_row = ttk.Frame(card, style="Card.TFrame")
        opt_row.pack(fill="x", pady=(0, 6))

        preserve_chk = ttk.Checkbutton(
            opt_row,
            text="Preserve User Settings (preferences.ini & custom themes)",
            variable=self.preserve_settings
        )
        preserve_chk.pack(side="left")

        btn_row = ttk.Frame(card, style="Card.TFrame")
        btn_row.pack(fill="x")

        self.install_btn = ttk.Button(
            btn_row, 
            text="Install / Update RFSuite", 
            style="Accent.TButton",
            command=self.start_install_async
        )
        self.install_btn.pack(fill="x")

        self.progress_bar = ttk.Progressbar(card, style="Horizontal.TProgressbar", mode="indeterminate")
        self.progress_bar.pack(fill="x", pady=(6, 0))

    def _build_log_card(self, parent):
        card = ttk.Frame(parent, style="Card.TFrame", padding=10)
        card.pack(fill="both", expand=True, pady=(4, 0))

        status_row = ttk.Frame(card, style="Card.TFrame")
        status_row.pack(fill="x", pady=(0, 4))

        self.status_lbl = ttk.Label(status_row, text="Ready", style="Card.TLabel", font=("Segoe UI", 9, "bold"))
        self.status_lbl.pack(side="left")

        self.log_text = tk.Text(
            card, 
            bg="#18181c", 
            fg="#cccccc", 
            insertbackground="#ffffff",
            relief="flat", 
            height=5, 
            font=("Consolas", 8),
            wrap="word"
        )
        self.log_text.pack(fill="both", expand=True)

        scrollbar = ttk.Scrollbar(self.log_text, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

    def log(self, message: str):
        def _append():
            self.log_text.insert("end", message + "\n")
            self.log_text.see("end")
        self.root.after(0, _append)

    def set_status(self, text: str, is_error: bool = False):
        def _set():
            self.status_lbl.configure(text=text, foreground="#ff5555" if is_error else "#ffffff")
        self.root.after(0, _set)

    def _on_toggle_local_mode(self):
        if self.is_local_mode.get():
            self.local_browse_btn.configure(state="normal")
            self.release_combo.configure(state="disabled")
        else:
            self.local_browse_btn.configure(state="disabled")
            self.release_combo.configure(state="readonly")

    def _browse_local_zip(self):
        filename = filedialog.askopenfilename(
            title="Select RFSuite Install ZIP",
            filetypes=[("Zip files", "*.zip"), ("All files", "*.*")]
        )
        if filename:
            self.local_zip_path.set(filename)
            self.log(f"Selected local ZIP: {filename}")

    def refresh_drives(self):
        self.log("Scanning for EdgeTX radio drives...")
        candidates = RadioDetector.get_candidate_drives()
        options = []
        best_path = None

        # Check local simulator directory as candidate as well
        script_dir = os.path.dirname(os.path.abspath(__file__))
        repo_root = os.path.abspath(os.path.join(script_dir, "..", "..", ".."))
        sim_dir = os.path.join(repo_root, "simulator")
        if os.path.isdir(sim_dir):
            options.append(sim_dir)

        for path, label, score in candidates:
            if path not in options:
                options.append(path)
            if score >= 5 and best_path is None:
                best_path = path

        self.drive_combo["values"] = options
        if best_path:
            self.selected_drive.set(best_path)
            self.log(f"Auto-detected Radio SD Card at: {best_path}")
            self._check_installed_version(best_path)
        elif options:
            self.selected_drive.set(options[0])
            self._check_installed_version(options[0])
        else:
            self.selected_drive.set("")
            self.installed_ver_lbl.configure(text="Installed: No drive selected")

    def _browse_drive(self):
        directory = filedialog.askdirectory(title="Select Radio SD Card or Simulator Root Folder")
        if directory:
            self.selected_drive.set(directory)
            self._on_drive_selected(None)

    def _on_drive_selected(self, _event):
        path = self.selected_drive.get().strip()
        if path:
            self._check_installed_version(path)

    def _check_installed_version(self, root_path: str):
        if not root_path or not os.path.exists(root_path):
            self.installed_ver_lbl.configure(text="Installed: Invalid path", foreground="#aaaaaa")
            return

        candidates = [
            os.path.join(root_path, "SCRIPTS", "TOOLS", "rfsuite-core", "lib", "version.lua"),
            os.path.join(root_path, "SCRIPTS", "TOOLS", "rfsuite", "lib", "version.lua"),
            os.path.join(root_path, "src", "rfsuite", "lib", "version.lua")
        ]

        for ver_file in candidates:
            if os.path.isfile(ver_file):
                try:
                    with open(ver_file, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    m_maj = re.search(r"M\.MAJOR\s*=\s*(\d+)", content)
                    m_min = re.search(r"M\.MINOR\s*=\s*(\d+)", content)
                    m_pat = re.search(r"M\.PATCH\s*=\s*(\d+)", content)
                    if m_maj and m_min and m_pat:
                        ver_str = f"v{m_maj.group(1)}.{m_min.group(1)}.{m_pat.group(1)}"
                        self.installed_ver_lbl.configure(text=f"Installed: {ver_str}", foreground="#55ff55")
                        self.log(f"Detected installed version on target: {ver_str}")
                        return
                except Exception:
                    pass

        self.installed_ver_lbl.configure(text="Installed: None or Unknown", foreground="#aaaaaa")

    def _scan_local_dist_builds(self) -> List[Dict]:
        """Find locally compiled ZIP packages in dist/ to allow testing without GitHub release."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        repo_root = os.path.abspath(os.path.join(script_dir, "..", "..", ".."))
        dist_dir = os.path.join(repo_root, "dist")
        
        builds = []
        if os.path.isdir(dist_dir):
            for f in os.listdir(dist_dir):
                if f.endswith(".zip"):
                    full_p = os.path.join(dist_dir, f)
                    # Pattern: rfsuite-radio-install-v0.0.2_de.zip
                    m_lang = re.search(r"_([a-z]{2})\.zip$", f)
                    lang = m_lang.group(1) if m_lang else "de"
                    m_ver = re.search(r"v([0-9]+\.[0-9]+\.[0-9]+)", f)
                    ver = m_ver.group(1) if m_ver else "local"
                    builds.append({
                        "tag_name": f"Local: {f}",
                        "name": f"Local Build (v{ver} - {lang})",
                        "prerelease": False,
                        "is_local_dist": True,
                        "local_path": full_p,
                        "assets": [{
                            "name": f,
                            "browser_download_url": None,
                            "local_path": full_p
                        }]
                    })
        return builds

    def fetch_releases_async(self):
        repo = self.selected_repo.get().strip() or DEFAULT_REPO
        self.set_status(f"Fetching branches & releases from GitHub ({repo})...")
        self.progress_bar.start(10)

        def _fetch():
            releases = []
            branches = []
            
            # 1. Fetch Branches from GitHub
            try:
                branches_url = f"https://api.github.com/repos/{repo}/branches"
                req_b = urllib.request.Request(branches_url, headers={"User-Agent": "RFSuite-EdgeTX-Updater"})
                with urllib.request.urlopen(req_b, timeout=8) as resp_b:
                    b_data = json.loads(resp_b.read().decode("utf-8"))
                    if isinstance(b_data, list):
                        for b in b_data:
                            b_name = b.get("name", "")
                            branches.append({
                                "tag_name": f"Branch: {b_name}",
                                "name": f"Branch: {b_name} (Latest Live Code)",
                                "prerelease": True,
                                "is_branch": True,
                                "branch_name": b_name,
                                "download_url": f"https://github.com/{repo}/archive/refs/heads/{b_name}.zip",
                                "assets": []
                            })
            except Exception as e:
                self.log(f"Notice: GitHub branches query for {repo}: {e}")

            # 2. Fetch Releases from GitHub
            try:
                rel_url = f"https://api.github.com/repos/{repo}/releases"
                req_r = urllib.request.Request(rel_url, headers={"User-Agent": "RFSuite-EdgeTX-Updater"})
                with urllib.request.urlopen(req_r, timeout=8) as resp_r:
                    r_data = json.loads(resp_r.read().decode("utf-8"))
                    if isinstance(r_data, list):
                        for r in r_data:
                            r["tag_name"] = f"Release: {r.get('tag_name', '')}"
                            r["is_branch"] = False
                            releases.append(r)
            except Exception as e:
                self.log(f"Notice: GitHub releases query for {repo}: {e}")

            # 3. Local dist ZIPs
            local_builds = self._scan_local_dist_builds()

            # Combine: Branches first, then Releases, then Local builds
            self.releases_data = branches + releases + local_builds

            if not self.releases_data:
                self.log(f"No branches or releases found on GitHub repo '{repo}'.")
                self.root.after(0, lambda: self.set_status(f"No versions found for {repo}.", is_error=True))
            else:
                self.log(f"Loaded {len(branches)} branch(es), {len(releases)} release(s), {len(local_builds)} local package(s).")
                self.root.after(0, lambda: self.set_status(f"Ready ({len(self.releases_data)} options available)"))

            self.root.after(0, self._update_release_list)
            self.root.after(0, self.progress_bar.stop)

        threading.Thread(target=_fetch, daemon=True).start()

    def _update_release_list(self):
        show_prereleases = self.include_prereleases.get()
        filtered = []
        for r in self.releases_data:
            if r.get("is_branch"):
                if show_prereleases:
                    filtered.append(r)
            elif r.get("prerelease"):
                if show_prereleases:
                    filtered.append(r)
            else:
                filtered.append(r)

        options = [r.get("tag_name", "") for r in filtered if r.get("tag_name")]
        self.release_combo["values"] = options
        if options:
            self.release_combo.current(0)
            self._on_release_selected(None)
        else:
            self.selected_release_tag.set("")

    def _get_fallback_languages(self) -> List[str]:
        """Scans the local repository i18n directory if available, or returns default languages."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        repo_root = os.path.abspath(os.path.join(script_dir, "..", "..", ".."))
        i18n_dir = os.path.join(repo_root, "src", "rfsuite", "i18n")
        if os.path.isdir(i18n_dir):
            langs = [f[:-4].lower() for f in os.listdir(i18n_dir) if f.endswith(".lua") and f != "init.lua"]
            if langs:
                return sorted(list(set(langs)))
        return ["de", "en"]

    def _detect_languages_for_selection(self, rel: Optional[Dict]) -> List[str]:
        """Automatically detects available languages for the selected branch, release, or local build."""
        if not rel:
            return self._get_fallback_languages()

        # 1. From local dist build or release assets
        assets = rel.get("assets", [])
        if assets:
            languages_found = []
            for asset in assets:
                name = asset.get("name", "")
                m = re.search(r"[-_]([a-z]{2})\.zip$", name, re.IGNORECASE)
                if m:
                    languages_found.append(m.group(1).lower())
            if languages_found:
                return sorted(list(set(languages_found)))

        # 2. From GitHub branch: query GitHub contents API for src/rfsuite/i18n
        if rel.get("is_branch"):
            branch_name = rel.get("branch_name", "master")
            repo = self.selected_repo.get().strip() or DEFAULT_REPO
            try:
                contents_url = f"https://api.github.com/repos/{repo}/contents/src/rfsuite/i18n?ref={branch_name}"
                req = urllib.request.Request(contents_url, headers={"User-Agent": "RFSuite-EdgeTX-Updater"})
                with urllib.request.urlopen(req, timeout=6) as resp:
                    items = json.loads(resp.read().decode("utf-8"))
                    if isinstance(items, list):
                        langs = [
                            f["name"][:-4].lower() 
                            for f in items 
                            if f.get("name", "").endswith(".lua") and f.get("name") != "init.lua"
                        ]
                        if langs:
                            return sorted(list(set(langs)))
            except Exception as e:
                self.log(f"Notice: Detecting branch languages via API ({branch_name}): {e}")

        # 3. Fallback to local files in repo
        return self._get_fallback_languages()

    def _on_release_selected(self, _event):
        sel = self.selected_release_tag.get().strip()
        if not sel:
            return
        
        rel = next((r for r in self.releases_data if r.get("tag_name") == sel), None)
        available_langs = self._detect_languages_for_selection(rel)
        
        self.lang_combo["values"] = available_langs
        if self.selected_language.get() not in available_langs:
            if "de" in available_langs:
                self.selected_language.set("de")
            elif "en" in available_langs:
                self.selected_language.set("en")
            elif available_langs:
                self.selected_language.set(available_langs[0])

    def start_install_async(self):
        target_root = self.selected_drive.get().strip()
        if not target_root or not os.path.exists(target_root):
            messagebox.showerror("Error", "Please select a valid Radio SD Card target folder.")
            return

        selected_lang = self.selected_language.get().strip() or "de"

        if self.is_local_mode.get():
            zip_path = self.local_zip_path.get().strip()
            if not zip_path or not os.path.isfile(zip_path):
                messagebox.showerror("Error", "Please choose an existing local ZIP file.")
                return
            download_url = None
            is_branch = False
        else:
            sel_tag = self.selected_release_tag.get().strip()
            if not sel_tag:
                messagebox.showerror("Error", "Please select a version or branch.")
                return

            rel = next((r for r in self.releases_data if r.get("tag_name") == sel_tag), None)
            if not rel:
                messagebox.showerror("Error", "Selected version was not found.")
                return

            if rel.get("is_branch"):
                download_url = rel.get("download_url")
                zip_path = None
                is_branch = True
            elif rel.get("is_local_dist"):
                zip_path = rel.get("local_path")
                download_url = None
                is_branch = False
            else:
                # Find matching language asset from release
                assets = rel.get("assets", [])
                matched_asset = None

                for a in assets:
                    name = a.get("name", "")
                    if f"_{selected_lang}.zip" in name or f"-{selected_lang}.zip" in name:
                        matched_asset = a
                        break

                if not matched_asset:
                    for a in assets:
                        if a.get("name", "").endswith(".zip"):
                            matched_asset = a
                            break

                if not matched_asset:
                    messagebox.showerror("Error", f"No installation ZIP asset found in {sel_tag} for language '{selected_lang}'.")
                    return

                download_url = matched_asset.get("browser_download_url")
                zip_path = None
                is_branch = False

        self.install_btn.configure(state="disabled")
        self.progress_bar.start(10)
        self.set_status("Installation in progress...")

        threading.Thread(
            target=self._run_installer_worker,
            args=(target_root, download_url, zip_path, is_branch, selected_lang),
            daemon=True
        ).start()

    def _run_installer_worker(self, target_root: str, download_url: Optional[str], local_zip_path: Optional[str], is_branch: bool, language: str):
        import tempfile
        temp_dir = tempfile.mkdtemp(prefix="rfsuite_updater_")

        try:
            # Step 1: Obtain ZIP
            if download_url:
                zip_dest = os.path.join(temp_dir, "package.zip")
                self.log(f"Downloading from: {download_url}...")
                self.set_status("Downloading package from GitHub...")
                req = urllib.request.Request(download_url, headers={"User-Agent": "RFSuite-EdgeTX-Updater"})
                with urllib.request.urlopen(req, timeout=30) as resp, open(zip_dest, "wb") as f_out:
                    shutil.copyfileobj(resp, f_out)
                self.log("Download complete.")
            else:
                zip_dest = local_zip_path
                self.log(f"Using local package: {zip_dest}")

            # Step 2: Unzip to staging
            extract_dir = os.path.join(temp_dir, "extracted")
            os.makedirs(extract_dir, exist_ok=True)
            self.set_status("Extracting archive...")
            self.log("Extracting package contents...")

            with zipfile.ZipFile(zip_dest, "r") as zf:
                zf.extractall(extract_dir)

            # Step 3: Determine if this is a pre-packaged ZIP (SCRIPTS/WIDGETS) or Source Repo (src/)
            # Find the root folder inside extract_dir
            candidate_roots = [extract_dir]
            for d in os.listdir(extract_dir):
                full_d = os.path.join(extract_dir, d)
                if os.path.isdir(full_d):
                    candidate_roots.append(full_d)

            src_repo_root = None
            packaged_root = None

            for cr in candidate_roots:
                if os.path.exists(os.path.join(cr, "src", "main.lua")) or os.path.exists(os.path.join(cr, "src", "rfsuite")):
                    src_repo_root = cr
                    break
                elif os.path.exists(os.path.join(cr, "SCRIPTS", "TOOLS")):
                    packaged_root = cr
                    break

            stage_out_dir = os.path.join(temp_dir, "stage_out")
            os.makedirs(stage_out_dir, exist_ok=True)

            if src_repo_root:
                # It's a source code archive (e.g. from GitHub branch) -> package and inline translations on the fly
                self.log(f"Building radio package on-the-fly for language '{language}'...")
                self.set_status(f"Compiling & inlining translations ({language})...")
                self._package_source_tree(src_repo_root, stage_out_dir, language)
            elif packaged_root:
                stage_out_dir = packaged_root
            else:
                raise RuntimeError("Invalid package structure: Neither 'src' source tree nor 'SCRIPTS' folder found.")

            # Step 4: Backup user preferences if enabled
            pref_backup_path = None
            if self.preserve_settings.get():
                target_user_pref = os.path.join(target_root, "SCRIPTS", "TOOLS", "rfsuite.user", "preferences.ini")
                if os.path.isfile(target_user_pref):
                    self.log("Backing up existing user preferences (preferences.ini)...")
                    pref_backup_path = os.path.join(temp_dir, "preferences.ini.bak")
                    shutil.copy2(target_user_pref, pref_backup_path)

            # Step 5: Clean old core directory to avoid orphan files
            self.set_status("Deploying files to radio SD card...")
            target_tools = os.path.join(target_root, "SCRIPTS", "TOOLS")
            target_core = os.path.join(target_tools, "rfsuite-core")
            legacy_core = os.path.join(target_tools, "rfsuite")

            if os.path.isdir(target_core):
                self.log("Cleaning previous rfsuite-core installation...")
                shutil.rmtree(target_core, ignore_errors=True)

            if os.path.isdir(legacy_core):
                self.log("Cleaning legacy rfsuite directory...")
                shutil.rmtree(legacy_core, ignore_errors=True)

            # Step 6: Copy new files to target
            self.log(f"Copying files to target: {target_root}")
            for item in os.listdir(stage_out_dir):
                src_item = os.path.join(stage_out_dir, item)
                dst_item = os.path.join(target_root, item)
                if os.path.isdir(src_item):
                    self._merge_copy_tree(src_item, dst_item)
                else:
                    os.makedirs(os.path.dirname(dst_item), exist_ok=True)
                    shutil.copy2(src_item, dst_item)

            # Step 7: Restore user preferences if backed up
            if pref_backup_path and os.path.isfile(pref_backup_path):
                self.log("Restoring preserved user preferences...")
                dst_user_dir = os.path.join(target_root, "SCRIPTS", "TOOLS", "rfsuite.user")
                os.makedirs(dst_user_dir, exist_ok=True)
                shutil.copy2(pref_backup_path, os.path.join(dst_user_dir, "preferences.ini"))

            self.log("✅ Installation completed successfully!")
            self.set_status("Installation complete! ✅")
            self.root.after(0, lambda: self._check_installed_version(target_root))
            self.root.after(0, lambda: messagebox.showinfo("Success", f"Rotorflight Lua EdgeTX Suite ({language}) was successfully installed!"))

        except Exception as e:
            self.log(f"❌ Error during installation: {e}")
            self.set_status(f"Installation failed: {e}", is_error=True)
            self.root.after(0, lambda: messagebox.showerror("Installation Failed", str(e)))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            self.root.after(0, self.progress_bar.stop)
            self.root.after(0, lambda: self.install_btn.configure(state="normal"))

    def _package_source_tree(self, repo_root: str, stage_out: str, lang: str):
        """Stages raw source code from a branch archive into EdgeTX structure with translation inlining."""
        src_root = os.path.join(repo_root, "src")
        src_core = os.path.join(src_root, "rfsuite")
        src_widgets = os.path.join(src_root, "widgets", "rfsuite")
        src_user = os.path.join(src_root, "rfsuite.user")
        src_audio = os.path.join(src_core, "audio")

        staging_tools = os.path.join(stage_out, "SCRIPTS", "TOOLS")
        staging_core = os.path.join(staging_tools, "rfsuite-core")
        staging_widgets = os.path.join(stage_out, "WIDGETS", "rfsuite")
        staging_sounds = os.path.join(stage_out, "SOUNDS", "rf")
        staging_user = os.path.join(staging_tools, "rfsuite.user")

        os.makedirs(staging_core, exist_ok=True)
        os.makedirs(staging_widgets, exist_ok=True)
        os.makedirs(staging_sounds, exist_ok=True)
        os.makedirs(staging_user, exist_ok=True)

        # Copy core files
        for item in os.listdir(src_core):
            if item in ["audio", "i18n"]:
                continue
            s = os.path.join(src_core, item)
            d = os.path.join(staging_core, item)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)

        # Copy init.lua
        os.makedirs(os.path.join(staging_core, "i18n"), exist_ok=True)
        init_src = os.path.join(src_core, "i18n", "init.lua")
        if os.path.isfile(init_src):
            shutil.copy2(init_src, os.path.join(staging_core, "i18n", "init.lua"))

        # Copy tool entrypoint
        shutil.copy2(os.path.join(src_root, "main.lua"), os.path.join(staging_tools, "rfsuite.lua"))

        # Copy widgets
        if os.path.isdir(src_widgets):
            shutil.copytree(src_widgets, staging_widgets, dirs_exist_ok=True)

        # Copy user default config
        if os.path.isdir(src_user):
            shutil.copytree(src_user, staging_user, dirs_exist_ok=True)

        # Copy sounds
        if os.path.isdir(src_audio):
            for pack_lang in ["en", "de"]:
                p_src = os.path.join(src_audio, pack_lang, "default")
                if not os.path.isdir(p_src):
                    p_src = os.path.join(src_audio, pack_lang)
                if os.path.isdir(p_src):
                    for sub in ["adj", "app", "evt", "stat", "gov"]:
                        s_sub = os.path.join(p_src, sub)
                        if os.path.isdir(s_sub):
                            shutil.copytree(s_sub, os.path.join(staging_sounds, pack_lang, sub), dirs_exist_ok=True)

            for wav in ["beep.wav", "multibeep.wav", "warn.wav", "alarm.wav"]:
                w_p = os.path.join(src_audio, wav)
                if os.path.isfile(w_p):
                    shutil.copy2(w_p, staging_sounds)

        # Generate theme index
        self._generate_theme_index(staging_core, staging_user)

        # Precompile and resolve i18n in-process without spawning subprocesses
        lang_file = os.path.join(src_core, "i18n", f"{lang}.lua")
        fallback_file = os.path.join(src_core, "i18n", "en.lua")
        
        self.log(f"Precompiling i18n tags for {lang}...")
        self._precompile_i18n_dir(staging_tools)
        self._precompile_i18n_dir(staging_widgets)

        if os.path.isfile(lang_file):
            self.log(f"Resolving translations with {lang}.lua...")
            self._resolve_i18n_dir(staging_tools, lang_file, fallback_file if lang != "en" else None, lang)
            self._resolve_i18n_dir(staging_widgets, lang_file, fallback_file if lang != "en" else None, lang)

    def _precompile_i18n_dir(self, root_dir: str):
        """In-process i18n precompilation converting UI text macros to @i18n(...)@ tags."""
        for root, _, files in os.walk(root_dir):
            for file in files:
                if not file.endswith(".lua"):
                    continue
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read()
                except Exception:
                    continue

                changed = False

                def encode_fallback(s):
                    return s.replace('|', '__PIPE__').replace(')', '__RPAREN__').replace('(', '__LPAREN__').replace(',', '__COMMA__').replace('@', '__AT__')

                # 1. Find pageT / Common.pageT prefix
                m_prefix = re.search(r'(?:pageT|Common\.pageT)\s*\(\s*["\']([^"\']+)["\']\s*\)', content)
                prefix = m_prefix.group(1) if m_prefix else None

                if not prefix:
                    m_keyprefix = re.search(r'keyPrefix\s*=\s*["\']([^"\']+)["\']', content)
                    if m_keyprefix:
                        prefix = m_keyprefix.group(1)
                        if prefix.startswith("app.pages."):
                            prefix = prefix[10:]

                if prefix:
                    full_prefix = f"app.pages.{prefix}"
                    pattern = r'\b(?:pageText|t)\s*\(\s*(?:i18n|nil)\s*,\s*["\']([^"\']+)["\'](?:\s*,\s*(["\'])(.*?)\2)?\s*\)'
                    def sub_pagetext(m):
                        k = m.group(1)
                        if m.group(3) is not None:
                            fb = encode_fallback(m.group(3))
                            return f'"@i18n({full_prefix}.{k}|{fb})@"'
                        return f'"@i18n({full_prefix}.{k})@"'
                    new_content, count = re.subn(pattern, sub_pagetext, content)
                    if count > 0:
                        content = new_content
                        changed = True

                    def sub_commont(m):
                        page_key = m.group(1)
                        k = m.group(2)
                        if m.group(4) is not None:
                            fb = encode_fallback(m.group(4))
                            return f'"@i18n(app.pages.{page_key}.{k}|{fb})@"'
                        return f'"@i18n(app.pages.{page_key}.{k})@"'
                    pattern_common = r'\bCommon\.t\s*\(\s*i18n\s*,\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\'](?:\s*,\s*(["\'])(.*?)\3)?\s*\)'
                    new_content, count = re.subn(pattern_common, sub_commont, content)
                    if count > 0:
                        content = new_content
                        changed = True

                    m_fallback = re.search(r'fallback\s*=\s*\{(.*?)\}', content, re.DOTALL)
                    if m_fallback:
                        fallback_block = m_fallback.group(1)
                        strings = re.findall(r'(["\'])(.*?)\1', fallback_block)
                        new_block = fallback_block
                        for idx, (quote, string) in enumerate(strings):
                            fb = encode_fallback(string)
                            tag = f'"@i18n({full_prefix}.help_p{idx+1}|{fb})@"'
                            new_block = new_block.replace(f'{quote}{string}{quote}', tag, 1)
                        content = content.replace(fallback_block, new_block, 1)
                        changed = True

                if file == "header.lua":
                    pattern_header = r'\bt\s*\(\s*["\']([^"\']+)["\']\s*,\s*(["\'])(.*?)\2\s*\)'
                    def sub_header(m):
                        k = m.group(1)
                        fb = encode_fallback(m.group(3))
                        return f'"@i18n(app.actions.{k}|{fb})@"'
                    new_content, count = re.subn(pattern_header, sub_header, content)
                    if count > 0:
                        content = new_content
                        changed = True

                pattern_widget_t_and_t = r'\(?\s*\(?\s*\bt\s+and\s+t\s*\(\s*["\']([^"\']+)["\']\s*\)\s*\)?\s*\)?\s*or\s*(["\'])(.*?)\2'
                def sub_widget_t_and_t(m):
                    k = m.group(1)
                    fb = encode_fallback(m.group(3))
                    return f'"@i18n({k}|{fb})@"'
                new_content, count = re.subn(pattern_widget_t_and_t, sub_widget_t_and_t, content)
                if count > 0:
                    content = new_content
                    changed = True

                pattern_widget_t = r'\bt\s*\(\s*["\'](widgets\.dashboard\.[^"\']+)["\']\s*,\s*(["\'])(.*?)\2\s*\)'
                def sub_widget_t(m):
                    k = m.group(1)
                    fb = encode_fallback(m.group(3))
                    return f'"@i18n({k}|{fb})@"'
                new_content, count = re.subn(pattern_widget_t, sub_widget_t, content)
                if count > 0:
                    content = new_content
                    changed = True

                pattern_i18n_full = r'\b(?:[a-zA-Z0-9_]+\.)?i18n\s+and\s+(?:[a-zA-Z0-9_]+\.)?i18n\.t\s+and\s+(?:[a-zA-Z0-9_]+\.)?i18n\.t\s*\(\s*["\']([^"\']+)["\']\s*\)\s*or\s*(["\'])(.*?)\2'
                def sub_i18n_full(m):
                    k = m.group(1)
                    fb = encode_fallback(m.group(3))
                    return f'"@i18n({k}|{fb})@"'
                new_content, count = re.subn(pattern_i18n_full, sub_i18n_full, content)
                if count > 0:
                    content = new_content
                    changed = True

                pattern_i18n_t = r'\b(?:[a-zA-Z0-9_]+\.)?i18n\.t\s*\(\s*["\']([^"\']+)["\']\s*\)'
                new_content, count = re.subn(pattern_i18n_t, lambda m: f'"@i18n({m.group(1)})@"', content)
                if count > 0:
                    content = new_content
                    changed = True

                if file == "splash.lua":
                    new_content, count = re.subn(r'["\']Please wait for telemetry["\']', r'"@i18n(widgets.dashboard.please_wait_for_telemetry)@"', content)
                    if count > 0:
                        content = new_content
                        changed = True

                if file == "runtime.lua":
                    new_content, count = re.subn(r'self\.statusLine\s+or\s+["\']Please wait\.\.\.["\']', r'self.statusLine or "@i18n(widgets.dashboard.please_wait_for_telemetry)@"', content)
                    if count > 0:
                        content = new_content
                        changed = True

                if changed:
                    try:
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                    except Exception:
                        pass

    def _resolve_i18n_dir(self, root_dir: str, lang_lua_path: str, fallback_lua_path: Optional[str], lang_code: str):
        """In-process resolution of @i18n(...)@ tags using the Lua language table."""
        translations = self._load_lua_i18n_table(lang_lua_path)
        fallback = self._load_lua_i18n_table(fallback_lua_path) if fallback_lua_path and os.path.isfile(fallback_lua_path) else None

        tag_regex = re.compile(
            r'@i18n\(\s*([^)@,]+?)\s*(?:,\s*(upper|lower))?\s*\)'
            r'((?::[a-z_]+(?:\([^@]*?\))?)*)@',
            flags=re.IGNORECASE
        )

        def _coerce_atom(s: str):
            try:
                return int(s)
            except ValueError:
                try:
                    return float(s)
                except ValueError:
                    if s.lower() in ('true', 'false'):
                        return s.lower() == 'true'
                    return s

        def _parse_chain(chain: str):
            if not chain:
                return []
            out = []
            for seg in filter(None, chain.split(':')):
                m = re.match(r'([a-z_][a-z0-9_]*)\s*(?:\((.*)\))?$', seg, flags=re.IGNORECASE)
                if not m:
                    continue
                name, argstr = m.group(1).lower(), (m.group(2) or '').strip()
                args = []
                if argstr:
                    import shlex
                    parts = []
                    current = ''
                    depth = 0
                    for ch in argstr:
                        if ch == '(':
                            depth += 1
                            current += ch
                        elif ch == ')':
                            depth = max(0, depth - 1)
                            current += ch
                        elif ch == ',' and depth == 0:
                            parts.append(current.strip())
                            current = ''
                        else:
                            current += ch
                    if current.strip():
                        parts.append(current.strip())
                    for p in parts:
                        parsed = shlex.split(p) if p else []
                        if len(parsed) == 1:
                            args.append(_coerce_atom(parsed[0]))
                        elif len(parsed) == 0:
                            args.append('')
                        else:
                            args.append(_coerce_atom(' '.join(parsed)))
                out.append((name, args, {}))
            return out

        def _upperfirst(s: str) -> str:
            return s[:1].upper() + s[1:].lower() if s else s

        def _truncate(s: str, n: int, ellipsis: Optional[str] = None) -> str:
            if n < 0: 
                return s
            if len(s) <= n:
                return s
            if ellipsis:
                if n <= len(ellipsis):
                    return ellipsis[:n]
                return s[: n - len(ellipsis)] + ellipsis
            return s[:n]

        def _collapse_ws(s: str) -> str:
            return re.sub(r'\s+', ' ', s).strip()

        def _slice(s: str, start: int, end: Optional[int] = None) -> str:
            return s[start:end]

        def _ensure_char(c: str) -> str:
            return c[0] if isinstance(c, str) and c else ' '

        transforms = {
            'upper': lambda s: s.upper(),
            'lower': lambda s: s.lower(),
            'upperfirst': _upperfirst,
            'capitalize': lambda s: s[:1].upper() + s[1:],
            'title': lambda s: s.title(),
            'swapcase': lambda s: s.swapcase(),
            'trim': lambda s: s.strip(),
            'ltrim': lambda s: s.lstrip(),
            'rtrim': lambda s: s.rstrip(),
            'collapse_ws': _collapse_ws,
            'truncate': lambda s, n, ellipsis=None: _truncate(s, int(n), ellipsis),
            'slice': _slice,
            'padleft': lambda s, width, char=' ': s.rjust(int(width), _ensure_char(char)),
            'padright': lambda s, width, char=' ': s.ljust(int(width), _ensure_char(char)),
            'center': lambda s, width, char=' ': s.center(int(width), _ensure_char(char)),
            'replace': lambda s, old, new, count=None: s.replace(str(old), str(new), int(count) if count is not None else -1),
            'remove': lambda s, pattern: re.sub(str(pattern), '', s),
            'keep': lambda s, pattern: ' '.join(re.findall(str(pattern), s)),
            'strip_prefix': lambda s, p: s[len(p):] if s.startswith(str(p)) else s,
            'strip_suffix': lambda s, p: s[:-len(p)] if len(p) and s.endswith(str(p)) else s,
            'prefix': lambda s, p: str(p) + s,
            'suffix': lambda s, p: s + str(p),
            'escape_html': lambda s: html.escape(s, quote=True),
            'escape_json': lambda s: s.replace('\\', '\\\\').replace('"', r'\"'),
        }

        def _apply_pipeline(s: str, basic_mod: Optional[str], chain: str) -> str:
            if basic_mod:
                fn = transforms.get(basic_mod.lower())
                if fn:
                    s = fn(s)
            for name, args, _ in _parse_chain(chain):
                fn = transforms.get(name)
                if fn:
                    try:
                        s = fn(s, *args)
                    except Exception:
                        pass
            return s

        def _resolve_key(tree: dict, dotted: str):
            node = tree
            for part in dotted.split('.'):
                if not isinstance(node, dict) or part not in node:
                    return None
                node = node[part]
            if isinstance(node, dict):
                if 'translation' in node and isinstance(node['translation'], (str, int, float)):
                    return str(node['translation'])
                if 'english' in node and isinstance(node['english'], (str, int, float)):
                    return str(node['english'])
                return None
            if node is None:
                return None
            return str(node)

        def _get_esc_fallback(key: str) -> Optional[str]:
            parts = key.split('.')
            if len(parts) < 6:
                return None
            param = parts[5]
            lookup = {
                "beacondelay": "Beacon Delay",
                "beaconstrength": "Beacon Strength",
                "beepstrength": "Beep Strength",
                "brakeonstop": "Brake On Stop",
                "demagcompensation": "Demag Compensation",
                "motordirection": "Motor Direction",
                "motortiming": "Motor Timing",
                "temperatureprotection": "Temperature Protection",
                "ppmcenterthrottle": "PPM Center Throttle",
                "ppmmaxthrottle": "PPM Max Throttle",
                "ppmminthrottle": "PPM Min Throttle",
                "startuppower": "Startup Power",
                "waitingforesc": "Waiting for ESC...",
                "brakingmode": "Braking Mode",
                "brakingstrength": "Braking Strength",
                "dithering": "Dithering",
                "forceedtarm": "Force DShot Arm",
                "ledcontrol": "LED Control",
                "lowrpmpowerprotection": "Low RPM Power Protection",
                "maxstartuppower": "Max Startup Power",
                "minstartuppower": "Min Startup Power",
                "powerrating": "Power Rating",
                "pwmfrequency": "PWM Frequency",
                "rampuppower": "Rampup Power",
                "rampupstartpower": "Rampup Start Power",
                "startupbeep": "Startup Beep",
                "threshold48to24": "Threshold 48 to 24",
                "threshold96to48": "Threshold 96 to 48",
                "extra_msg_save": "Save successful"
            }
            if param in lookup:
                return lookup[param]
            if '_' in param:
                return ' '.join(w.capitalize() for w in param.split('_'))
            return param.capitalize()

        esc_fallbacks = {
            "app.modules.esc_tools.mfg.blheli_s.name": "BLHeli_S",
            "app.modules.esc_tools.mfg.bluejay.name": "Bluejay",
            "app.modules.esc_tools.mfg.flrtr.name": "Flyrotor",
            "app.modules.esc_tools.mfg.hw5.name": "Hobbywing",
            "app.modules.esc_tools.mfg.omp.name": "OMP",
            "app.modules.esc_tools.mfg.scorp.name": "Scorpion",
            "app.modules.esc_tools.mfg.xdfly.name": "XDFly",
            "app.modules.esc_tools.mfg.yge.name": "YGE",
            "app.modules.esc_tools.mfg.ztw.name": "ZTW",
            "app.modules.esc_tools.mfg.blheli_s.waitingforesc": "Waiting for ESC...",
            "app.modules.esc_tools.mfg.bluejay.waitingforesc": "Waiting for ESC...",
            "app.modules.esc_tools.mfg.blheli_s.basic": "Basic",
            "app.modules.esc_tools.mfg.blheli_s.advanced": "Advanced",
            "app.modules.esc_tools.mfg.blheli_s.input": "Input",
            "app.modules.esc_tools.mfg.bluejay.beacon": "Beacon",
            "app.modules.esc_tools.mfg.bluejay.brake": "Brake",
            "app.modules.esc_tools.mfg.bluejay.general": "General",
            "app.modules.esc_tools.mfg.bluejay.other": "Other",
            "app.modules.esc_tools.mfg.flrtr.advanced": "Advanced",
            "app.modules.esc_tools.mfg.flrtr.basic": "Basic",
            "app.modules.esc_tools.mfg.flrtr.governor": "Governor",
            "app.modules.esc_tools.mfg.flrtr.other": "Other",
            "app.modules.esc_tools.mfg.hw5.advanced": "Advanced",
            "app.modules.esc_tools.mfg.hw5.basic": "Basic",
            "app.modules.esc_tools.mfg.hw5.rotation": "Rotation",
            "app.modules.esc_tools.mfg.omp.advanced": "Advanced",
            "app.modules.esc_tools.mfg.omp.basic": "Basic",
            "app.modules.esc_tools.mfg.omp.governor": "Governor",
            "app.modules.esc_tools.mfg.scorp.advanced": "Advanced",
            "app.modules.esc_tools.mfg.scorp.basic": "Basic",
            "app.modules.esc_tools.mfg.scorp.limits": "Limits",
            "app.modules.esc_tools.mfg.xdfly.advanced": "Advanced",
            "app.modules.esc_tools.mfg.xdfly.basic": "Basic",
            "app.modules.esc_tools.mfg.xdfly.governor": "Governor",
            "app.modules.esc_tools.mfg.yge.advanced": "Advanced",
            "app.modules.esc_tools.mfg.yge.basic": "Basic",
            "app.modules.esc_tools.mfg.yge.other": "Other",
            "app.modules.esc_tools.mfg.ztw.advanced": "Advanced",
            "app.modules.esc_tools.mfg.ztw.basic": "Basic",
            "app.modules.esc_tools.mfg.ztw.governor": "Governor",
            "api.ESC_PARAMETERS_HW5.tbl_disabled": "Disabled",
            "api.ESC_PARAMETERS_HW5.tbl_autocalculate": "Auto-Calculate",
            "api.ESC_PARAMETERS_HW5.tbl_normal": "Normal",
            "api.ESC_PARAMETERS_HW5.tbl_reverse": "Reverse",
            "api.ESC_PARAMETERS_HW5.tbl_cw": "CW",
            "api.ESC_PARAMETERS_HW5.tbl_ccw": "CCW",
            "api.ESC_PARAMETERS_HW5.tbl_proportional": "Proportional",
        }

        def _sub_tag(m):
            key = m.group(1).strip()
            basic_mod = m.group(2)
            chain = m.group(3) or ''

            inline_fallback = None
            if '|' in key:
                key, inline_fallback = key.split('|', 1)
                inline_fallback = (inline_fallback
                                   .replace('__PIPE__', '|')
                                   .replace('__RPAREN__', ')')
                                   .replace('__LPAREN__', '(')
                                   .replace('__COMMA__', ',')
                                   .replace('__AT__', '@'))

            # Aliases
            if key.startswith("app.pages.setup_controls."):
                key = "app.modules.controls." + key[len("app.pages.setup_controls."):]
            elif key == "app.modules.esc_tools.name":
                key = "app.modules.esc_motors.esc_tools"
            elif key == "widgets.governor.THR-OFF":
                key = "widgets.governor.THROFF"

            resolved = _resolve_key(translations, key) if translations else None
            if resolved is None and fallback:
                resolved = _resolve_key(fallback, key)

            if resolved is None:
                esc_fb = _get_esc_fallback(key)
                if esc_fb is not None:
                    resolved = esc_fb
                elif key in esc_fallbacks:
                    resolved = esc_fallbacks[key]
                elif inline_fallback is not None:
                    resolved = inline_fallback
                else:
                    return m.group(0)

            # Apply transform pipeline
            resolved = _apply_pipeline(str(resolved), basic_mod, chain)

            # Sanitize for Lua string insertion
            resolved = resolved.replace("\r\n", "\n").replace("\r", "\n")
            resolved = resolved.replace("\n", r"\n")
            resolved = resolved.replace('"', r'\"')
            return resolved

        for root, _, files in os.walk(root_dir):
            for file in files:
                if not file.endswith(".lua"):
                    continue
                fpath = os.path.join(root, file)
                try:
                    with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                        text = f.read()
                except Exception:
                    continue

                new_text, count = tag_regex.subn(_sub_tag, text)
                if "@i18n_language@" in new_text:
                    new_text = new_text.replace("@i18n_language@", lang_code)
                    count += 1

                if count > 0:
                    try:
                        with open(fpath, 'w', encoding='utf-8') as f:
                            f.write(new_text)
                    except Exception:
                        pass

    def _load_lua_i18n_table(self, path_str: str) -> dict:
        """Parses a Lua return { ... } dictionary into Python dict."""
        if not path_str or not os.path.isfile(path_str):
            return {}
        try:
            import codecs
            with open(path_str, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
                
            json_str = ""
            for line in lines:
                line = re.sub(r'--.*$', '', line)
                stripped = line.strip()
                if not stripped:
                    continue
                    
                if stripped == "return {":
                    json_str += "{\n"
                    continue
                    
                m = re.match(r'^(?:\[\s*["\']([a-zA-Z0-9_]+)["\']\s*\]|([a-zA-Z0-9_]+))\s*=\s*\{\s*$', stripped)
                if m:
                    key = m.group(1) or m.group(2)
                    json_str += f'"{key}": {{\n'
                    continue
                    
                m = re.match(r'^(?:\[\s*["\']([a-zA-Z0-9_]+)["\']\s*\]|([a-zA-Z0-9_]+))\s*=\s*(.*?),?$', stripped)
                if m:
                    key = m.group(1) or m.group(2)
                    val = m.group(3).strip()
                    
                    # If val is a table on a single line, e.g. { name = "Flight Tuning" }
                    if val.startswith('{') and val.endswith('}'):
                        val_content = val[1:-1].strip()
                        int_m = re.match(r'^(?:\[\s*["\']([a-zA-Z0-9_]+)["\']\s*\]|([a-zA-Z0-9_]+))\s*=\s*["\'](.*?)["\']$', val_content)
                        if int_m:
                            int_key = int_m.group(1) or int_m.group(2)
                            val = f'{{"{int_key}": "{int_m.group(3)}"}}'
                    elif (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                        inner = val[1:-1]
                        raw_bytes = inner.encode('utf-8', errors='replace')
                        try:
                            decoded_bytes, _ = codecs.escape_decode(raw_bytes)
                            val_str = decoded_bytes.decode('utf-8', errors='replace')
                        except Exception:
                            val_str = inner
                        val = json.dumps(val_str, ensure_ascii=False)
                        
                    json_str += f'"{key}": {val},\n'
                    continue
                    
                if stripped == "}" or stripped == "}," or stripped == "};":
                    json_str += "},\n"
                    continue
                    
                json_str += line

            json_str = re.sub(r',\s*([\]}])', r'\1', json_str)
            json_str = re.sub(r',\s*$', '', json_str)
            
            return json.loads(json_str)
        except Exception as e:
            self.log(f"Notice: Lua i18n parsing error on {path_str}: {e}")
            return {}

    def _generate_theme_index(self, target_core_dir: str, target_user_dir: str):
        entries = []
        sys_themes = os.path.join(target_core_dir, "widgets", "dashboard", "themes")
        if os.path.isdir(sys_themes):
            for d in os.listdir(sys_themes):
                init_f = os.path.join(sys_themes, d, "init.lua")
                if os.path.isfile(init_f):
                    with open(init_f, "r", encoding="utf-8", errors="ignore") as f:
                        c = f.read()
                    name_m = re.search(r'name\s*=\s*"([^"]+)"', c)
                    config_m = re.search(r'configure\s*=\s*"([^"]+)"', c)
                    stand_m = re.search(r"standalone\s*=\s*(true|false)", c)
                    if name_m:
                        entries.append({
                            "name": name_m.group(1),
                            "source": "system",
                            "folder": d,
                            "configure": config_m.group(1) if config_m else None,
                            "standalone": stand_m.group(1) == "true" if stand_m else False
                        })

        out_file = os.path.join(target_core_dir, "app", "pages", "settings", "dashboard", "theme_index.lua")
        os.makedirs(os.path.dirname(out_file), exist_ok=True)
        lines = ["return {"]
        for e in entries:
            safe_name = e["name"].replace("\\", "\\\\").replace('"', '\\"')
            safe_folder = e["folder"].replace("\\", "\\\\").replace('"', '\\"')
            cfg_val = f'"{e["configure"]}"' if e["configure"] else "nil"
            stand_val = "true" if e["standalone"] else "false"
            lines.append(f'  {{ name = "{safe_name}", source = "{e["source"]}", folder = "{safe_folder}", configure = {cfg_val}, standalone = {stand_val} }},')
        lines.append("}\n")
        with open(out_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def _merge_copy_tree(self, src: str, dst: str):
        """Recursively copy src directory to dst, overwriting existing files."""
        os.makedirs(dst, exist_ok=True)
        for item in os.listdir(src):
            s = os.path.join(src, item)
            d = os.path.join(dst, item)
            if os.path.isdir(s):
                self._merge_copy_tree(s, d)
            else:
                shutil.copy2(s, d)


def main():
    root = tk.Tk()
    app = RFSuiteUpdaterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
