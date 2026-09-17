"""Game scanner module for Steam, Heroic, Lutris, and custom Linux games."""

import glob
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from PyQt6.QtCore import QObject, pyqtSignal


@dataclass
class GameInfo:
    app_id: str
    name: str
    platform: str  # "steam", "heroic", "lutris", "custom"
    install_dir: str = ""
    executable: str = ""
    prefix_dir: str = ""
    banner_image: Optional[str] = None
    poster_image: Optional[str] = None
    last_played: int = 0
    size_mb: int = 0
    library_path: str = ""

    @property
    def has_prefix(self) -> bool:
        return bool(self.prefix_dir and os.path.isdir(self.prefix_dir))

    @property
    def formatted_size(self) -> str:
        if self.size_mb >= 1024:
            return f"{self.size_mb / 1024:.1f} GB"
        return f"{self.size_mb} MB"


class GameScanner(QObject):
    scan_started = pyqtSignal()
    game_found = pyqtSignal(object)  # GameInfo
    scan_finished = pyqtSignal(list) # List[GameInfo]

    EXCLUDE_KEYWORDS = [
        "steamworks",
        "proton",
        "steam linux runtime",
        "steam controller configs",
        "soundtrack",
        "steamvr",
        "redistributables",
    ]

    def __init__(self):
        super().__init__()
        self.games: List[GameInfo] = []

    def scan_all(self) -> List[GameInfo]:
        """Scan all platforms synchronously."""
        self.scan_started.emit()
        self.games = []

        # 1. Scan Steam
        steam_games = self.scan_steam()
        self.games.extend(steam_games)

        # 2. Scan Heroic
        heroic_games = self.scan_heroic()
        self.games.extend(heroic_games)

        # 3. Scan Lutris
        lutris_games = self.scan_lutris()
        self.games.extend(lutris_games)

        # 4. Scan Custom
        custom_games = self.scan_custom()
        self.games.extend(custom_games)

        # Sort: recently played first, then alphabetically
        self.games.sort(key=lambda g: (-g.last_played, g.name.lower()))

        for g in self.games:
            self.game_found.emit(g)

        self.scan_finished.emit(self.games)
        return self.games

    def get_steam_libraries(self) -> List[str]:
        """Finds all configured Steam library folders across the system."""
        libraries = set()
        home = os.path.expanduser("~")
        candidates = [
            os.path.join(home, ".local/share/Steam"),
            os.path.join(home, ".steam/steam"),
            os.path.join(home, ".steam/root"),
            os.path.join(home, ".var/app/com.valvesoftware.Steam/.local/share/Steam"),  # Flatpak
        ]

        for cand in candidates:
            vdf_path = os.path.join(cand, "steamapps", "libraryfolders.vdf")
            if os.path.isfile(vdf_path):
                libraries.add(cand)
                try:
                    with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            m = re.search(r'"path"\s+"([^"]+)"', line)
                            if m:
                                lib_dir = m.group(1).replace("\\\\", "/")
                                if os.path.isdir(lib_dir):
                                    libraries.add(lib_dir)
                except Exception:
                    pass

        return sorted(list(libraries))

    def _find_steam_art(
        self, appid: str, steam_cache_dirs: List[str], steam_root_dirs: Optional[List[str]] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """Finds local cover art in Steam appcache, userdata grid, or cached covers."""
        poster = None
        banner = None

        # 1. Search modern appcache/librarycache/<appid>/ (subdirectories with sha1 hash)
        for cache_dir in steam_cache_dirs:
            if not os.path.isdir(cache_dir):
                continue

            app_dir = os.path.join(cache_dir, appid)
            if os.path.isdir(app_dir):
                try:
                    with os.scandir(app_dir) as entries:
                        for entry in entries:
                            if entry.is_dir():
                                try:
                                    with os.scandir(entry.path) as sub_entries:
                                        for sub in sub_entries:
                                            name = sub.name.lower()
                                            if not poster and ("capsule" in name or "600x900" in name):
                                                poster = sub.path
                                            elif not banner and ("hero" in name or "header" in name) and "blur" not in name:
                                                banner = sub.path
                                            if poster and banner:
                                                break
                                except Exception:
                                    pass
                            elif entry.is_file():
                                name = entry.name.lower()
                                if not poster and ("capsule" in name or "600x900" in name):
                                    poster = entry.path
                                elif not banner and ("hero" in name or "header" in name) and "blur" not in name:
                                    banner = entry.path
                            if poster and banner:
                                break
                except Exception:
                    pass

            if poster and banner:
                return poster, banner

            # Flat candidates directly inside cache_dir
            if not poster:
                for cand in [
                    os.path.join(cache_dir, f"{appid}_library_600x900.jpg"),
                    os.path.join(cache_dir, f"{appid}_library_capsule.jpg"),
                    os.path.join(cache_dir, appid, "library_600x900.jpg"),
                    os.path.join(cache_dir, appid, "library_capsule.jpg"),
                ]:
                    if os.path.isfile(cand):
                        poster = cand
                        break

            if not banner:
                for cand in [
                    os.path.join(cache_dir, f"{appid}_header.jpg"),
                    os.path.join(cache_dir, f"{appid}_library_hero.jpg"),
                    os.path.join(cache_dir, appid, "header.jpg"),
                ]:
                    if os.path.isfile(cand):
                        banner = cand
                        break

            if poster and banner:
                return poster, banner

        # 2. Search Steam userdata/<user_id>/config/grid/
        if steam_root_dirs:
            for s_root in steam_root_dirs:
                userdata_dir = os.path.join(s_root, "userdata")
                if not os.path.isdir(userdata_dir):
                    continue
                try:
                    with os.scandir(userdata_dir) as u_entries:
                        for u_entry in u_entries:
                            if u_entry.is_dir():
                                grid_dir = os.path.join(u_entry.path, "config", "grid")
                                if os.path.isdir(grid_dir):
                                    if not poster:
                                        for ext in ["p.jpg", "p.png", "_portrait.png", "_portrait.jpg"]:
                                            cand = os.path.join(grid_dir, f"{appid}{ext}")
                                            if os.path.isfile(cand):
                                                poster = cand
                                                break
                                    if not banner:
                                        for ext in ["_hero.jpg", "_hero.png", ".jpg", ".png"]:
                                            cand = os.path.join(grid_dir, f"{appid}{ext}")
                                            if os.path.isfile(cand):
                                                banner = cand
                                                break
                except Exception:
                    pass

        # 3. Check ~/.cache/gaming-center/covers/
        cache_center = os.path.expanduser("~/.cache/gaming-center/covers")
        if not poster:
            for ext in [".jpg", ".png"]:
                cand = os.path.join(cache_center, f"steam_{appid}_poster{ext}")
                if os.path.isfile(cand) and os.path.getsize(cand) > 0:
                    poster = cand
                    break
        if not banner:
            for ext in [".jpg", ".png"]:
                cand = os.path.join(cache_center, f"steam_{appid}_banner{ext}")
                if os.path.isfile(cand) and os.path.getsize(cand) > 0:
                    banner = cand
                    break

        return poster, banner

    def _find_steam_prefix(self, appid: str, libraries: List[str], game_library: str) -> str:
        """Finds the Proton prefix (compatdata/<appid>/pfx) for a Steam game."""
        # 1. First check in the library where the game itself is installed
        cand = os.path.join(game_library, "steamapps", "compatdata", appid, "pfx")
        if os.path.isdir(cand):
            return cand

        # 2. Check in all other library folders (Steam often places prefixes in ~/.local/share/Steam)
        for lib in libraries:
            cand = os.path.join(lib, "steamapps", "compatdata", appid, "pfx")
            if os.path.isdir(cand):
                return cand

        return ""

    def scan_steam(self) -> List[GameInfo]:
        """Scans all Steam games across libraries."""
        games: List[GameInfo] = []
        libraries = self.get_steam_libraries()
        if not libraries:
            return games

        home = os.path.expanduser("~")
        cache_dirs = [
            os.path.join(home, ".local/share/Steam/appcache/librarycache"),
            os.path.join(home, ".steam/steam/appcache/librarycache"),
            os.path.join(home, ".var/app/com.valvesoftware.Steam/.local/share/Steam/appcache/librarycache"),
        ]
        steam_roots = [
            os.path.join(home, ".local/share/Steam"),
            os.path.join(home, ".steam/steam"),
            os.path.join(home, ".var/app/com.valvesoftware.Steam/.local/share/Steam"),
        ]

        seen_appids = set()

        for lib in libraries:
            steamapps = os.path.join(lib, "steamapps")
            if not os.path.isdir(steamapps):
                continue

            manifests = glob.glob(os.path.join(steamapps, "appmanifest_*.acf"))
            for mf_path in manifests:
                try:
                    with open(mf_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()

                    appid_m = re.search(r'"appid"\s+"(\d+)"', content)
                    name_m = re.search(r'"name"\s+"([^"]+)"', content)
                    dir_m = re.search(r'"installdir"\s+"([^"]+)"', content)
                    last_played_m = re.search(r'"LastPlayed"\s+"(\d+)"', content)
                    size_m = re.search(r'"SizeOnDisk"\s+"(\d+)"', content)

                    if not (appid_m and name_m):
                        continue

                    appid = appid_m.group(1)
                    name = name_m.group(1)

                    # Filter out tools, runtimes, soundtracks
                    name_lower = name.lower()
                    if any(ex in name_lower for ex in self.EXCLUDE_KEYWORDS):
                        continue
                    if appid in seen_appids:
                        continue
                    seen_appids.add(appid)

                    install_sub = dir_m.group(1) if dir_m else ""
                    install_dir = os.path.join(steamapps, "common", install_sub) if install_sub else ""
                    last_played = int(last_played_m.group(1)) if last_played_m else 0
                    size_mb = int(int(size_m.group(1)) / (1024 * 1024)) if size_m else 0

                    poster, banner = self._find_steam_art(appid, cache_dirs, steam_roots)
                    prefix = self._find_steam_prefix(appid, libraries, lib)

                    games.append(GameInfo(
                        app_id=appid,
                        name=name,
                        platform="steam",
                        install_dir=install_dir,
                        prefix_dir=prefix,
                        banner_image=banner,
                        poster_image=poster,
                        last_played=last_played,
                        size_mb=size_mb,
                        library_path=lib
                    ))
                except Exception:
                    continue

        return games

    def scan_heroic(self) -> List[GameInfo]:
        """Scans Heroic Games Launcher (GOG, Epic Games)."""
        games: List[GameInfo] = []
        home = os.path.expanduser("~")
        cache_center = os.path.expanduser("~/.cache/gaming-center/covers")
        
        # 1. GOG Games
        gog_file = os.path.join(home, ".config/heroic/gog_store/installed.json")
        if os.path.isfile(gog_file):
            try:
                with open(gog_file, "r", encoding="utf-8", errors="ignore") as f:
                    data = json.load(f)
                    installed = data.get("installed", [])
                    for item in installed:
                        app_name = str(item.get("appName") or item.get("id") or "")
                        title = item.get("title", app_name)
                        install_dir = item.get("install_path", "")
                        prefix = ""
                        cfg_file = os.path.join(home, f".config/heroic/GamesConfig/{app_name}.json")
                        if os.path.isfile(cfg_file):
                            try:
                                with open(cfg_file, "r") as cf:
                                    cdata = json.load(cf)
                                    prefix = cdata.get("winePrefix", "")
                            except Exception:
                                pass

                        clean_id = "".join(c for c in app_name if c.isalnum() or c in ("-", "_"))
                        poster = item.get("image")
                        banner = None
                        for ext in [".jpg", ".png"]:
                            cand = os.path.join(cache_center, f"heroic_{clean_id}_poster{ext}")
                            if os.path.isfile(cand):
                                poster = cand
                                break
                        for ext in [".jpg", ".png"]:
                            cand = os.path.join(cache_center, f"heroic_{clean_id}_banner{ext}")
                            if os.path.isfile(cand):
                                banner = cand
                                break

                        games.append(GameInfo(
                            app_id=f"heroic_gog_{app_name}",
                            name=title,
                            platform="heroic",
                            install_dir=install_dir,
                            prefix_dir=prefix,
                            banner_image=banner,
                            poster_image=poster,
                            size_mb=0
                        ))
            except Exception:
                pass

        # 2. Legendary (Epic Games)
        legendary_file = os.path.join(home, ".config/heroic/legendaryConfig/legendary/installed.json")
        legendary_art_cache = {}
        legendary_lib_file = os.path.join(home, ".config/heroic/store_cache/legendary_library.json")
        if os.path.isfile(legendary_lib_file):
            try:
                with open(legendary_lib_file, "r", encoding="utf-8", errors="ignore") as f:
                    ldata = json.load(f)
                    for litem in ldata.get("library", []):
                        aname = litem.get("app_name")
                        if aname:
                            legendary_art_cache[aname] = (litem.get("art_square"), litem.get("art_cover"))
            except Exception:
                pass

        if os.path.isfile(legendary_file):
            try:
                with open(legendary_file, "r", encoding="utf-8", errors="ignore") as f:
                    data = json.load(f)
                    for app_name, item in data.items():
                        title = item.get("title", app_name)
                        install_dir = item.get("install_path", "")
                        prefix = ""
                        cfg_file = os.path.join(home, f".config/heroic/GamesConfig/{app_name}.json")
                        if os.path.isfile(cfg_file):
                            try:
                                with open(cfg_file, "r") as cf:
                                    cdata = json.load(cf)
                                    prefix = cdata.get("winePrefix", "")
                            except Exception:
                                pass

                        clean_id = "".join(c for c in app_name if c.isalnum() or c in ("-", "_"))
                        poster = None
                        banner = None

                        # Check local cover cache
                        for ext in [".jpg", ".png"]:
                            cand = os.path.join(cache_center, f"heroic_{clean_id}_poster{ext}")
                            if os.path.isfile(cand):
                                poster = cand
                                break
                        for ext in [".jpg", ".png"]:
                            cand = os.path.join(cache_center, f"heroic_{clean_id}_banner{ext}")
                            if os.path.isfile(cand):
                                banner = cand
                                break

                        # Check legendary library cache art
                        if app_name in legendary_art_cache:
                            l_poster, l_banner = legendary_art_cache[app_name]
                            if not poster and l_poster:
                                poster = l_poster
                            if not banner and l_banner:
                                banner = l_banner

                        games.append(GameInfo(
                            app_id=f"heroic_epic_{app_name}",
                            name=title,
                            platform="heroic",
                            install_dir=install_dir,
                            prefix_dir=prefix,
                            banner_image=banner,
                            poster_image=poster,
                            size_mb=0
                        ))
            except Exception:
                pass

        return games

    def scan_lutris(self) -> List[GameInfo]:
        """Scans Lutris SQLite database."""
        games: List[GameInfo] = []
        home = os.path.expanduser("~")
        pga_db = os.path.join(home, ".local/share/lutris/pga.db")
        if not os.path.isfile(pga_db):
            return games

        lutris_dirs = [
            os.path.join(home, ".local/share/lutris"),
            os.path.join(home, ".var/app/net.lutris.Lutris/data/lutris"),
        ]
        cache_center = os.path.expanduser("~/.cache/gaming-center/covers")

        try:
            conn = sqlite3.connect(pga_db)
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, slug, runner, directory, installed FROM games WHERE installed = 1")
            for row in cursor.fetchall():
                gid, name, slug, runner, directory, installed = row
                if not name:
                    continue
                
                # Check runner and prefix
                prefix = ""
                cfg_path = os.path.join(home, f".config/lutris/games/{slug}-{gid}.yml")
                if os.path.isfile(cfg_path):
                    try:
                        with open(cfg_path, "r", encoding="utf-8", errors="ignore") as f:
                            for line in f:
                                if "prefix:" in line:
                                    prefix = line.split("prefix:", 1)[1].strip().strip("'\"")
                                    break
                    except Exception:
                        pass

                # Resolve coverart and banners
                poster = None
                banner = None
                for ldir in lutris_dirs:
                    if not poster:
                        for ext in [".jpg", ".png"]:
                            cand = os.path.join(ldir, "coverart", f"{slug}{ext}")
                            if os.path.isfile(cand):
                                poster = cand
                                break
                    if not banner:
                        for ext in [".jpg", ".png"]:
                            cand = os.path.join(ldir, "banners", f"{slug}{ext}")
                            if os.path.isfile(cand):
                                banner = cand
                                break

                # Check local cache
                if not poster:
                    for ext in [".jpg", ".png"]:
                        cand = os.path.join(cache_center, f"lutris_{gid}_poster{ext}")
                        if os.path.isfile(cand):
                            poster = cand
                            break

                games.append(GameInfo(
                    app_id=f"lutris_{gid}",
                    name=name,
                    platform="lutris",
                    install_dir=directory or "",
                    prefix_dir=prefix,
                    banner_image=banner,
                    poster_image=poster,
                    size_mb=0
                ))
            conn.close()
        except Exception:
            pass

        return games

    def scan_custom(self) -> List[GameInfo]:
        """Loads user-added custom games from config."""
        games: List[GameInfo] = []
        cfg_path = os.path.expanduser("~/.config/gaming-center/custom_games.json")
        if os.path.isfile(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        games.append(GameInfo(
                            app_id=item.get("app_id", ""),
                            name=item.get("name", "Custom Game"),
                            platform="custom",
                            install_dir=item.get("install_dir", ""),
                            executable=item.get("executable", ""),
                            prefix_dir=item.get("prefix_dir", ""),
                            banner_image=item.get("banner_image"),
                            poster_image=item.get("poster_image"),
                        ))
            except Exception:
                pass
        return games
