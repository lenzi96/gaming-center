"""Path resolver to translate PCGW Windows paths to Linux Proton/Wine prefixes."""

import glob
import os
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple
from .game_scanner import GameInfo


@dataclass
class ResolvedPath:
    original: str
    resolved_path: str
    folder_path: str
    exists: bool
    path_type: str  # "save" or "config"
    label: str = ""


class PathResolver:
    """Translates PCGamingWiki path expressions into actual Linux file paths."""

    @staticmethod
    def resolve_paths(game: GameInfo, raw_paths: List[str], path_type: str = "save") -> List[ResolvedPath]:
        results: List[ResolvedPath] = []
        seen_folders = set()
        for raw in raw_paths:
            res = PathResolver.resolve_single_path(game, raw, path_type)
            if res:
                if res.folder_path not in seen_folders:
                    seen_folders.add(res.folder_path)
                    results.append(res)

        # Also check Steam cloud save directory if it's a Steam game
        if game.platform == "steam" and game.app_id.isdigit():
            cloud_path = PathResolver.find_steam_cloud_path(game.app_id)
            if cloud_path and os.path.isdir(cloud_path) and cloud_path not in seen_folders:
                seen_folders.add(cloud_path)
                results.append(ResolvedPath(
                    original="Steam Cloud (Remote)",
                    resolved_path=cloud_path,
                    folder_path=cloud_path,
                    exists=True,
                    path_type="save",
                    label="Steam Cloud Cache"
                ))

        # Sort: existing folders first
        results.sort(key=lambda r: not r.exists)
        return results

    @staticmethod
    def find_steam_cloud_path(appid: str) -> Optional[str]:
        """Finds Steam cloud saves in ~/.local/share/Steam/userdata/<user>/<appid>/remote."""
        home = os.path.expanduser("~")
        candidates = [
            os.path.join(home, ".local/share/Steam/userdata"),
            os.path.join(home, ".steam/steam/userdata"),
            os.path.join(home, ".var/app/com.valvesoftware.Steam/.local/share/Steam/userdata"),
        ]
        for base in candidates:
            if not os.path.isdir(base):
                continue
            for user_id in os.listdir(base):
                p = os.path.join(base, user_id, appid, "remote")
                if os.path.isdir(p):
                    return p
        return None

    @staticmethod
    def resolve_single_path(game: GameInfo, raw_win_path: str, path_type: str) -> Optional[ResolvedPath]:
        if not raw_win_path:
            return None

        # Clean wildcards or filenames at the end
        clean_target = raw_win_path.replace("/", "\\")
        has_file_target = False
        last_part = clean_target.split("\\")[-1]
        if "*" in last_part or "." in last_part:
            has_file_target = True

        # Check if game has a Proton / Wine prefix
        resolved = None
        if game.has_prefix:
            resolved = PathResolver._resolve_in_prefix(game.prefix_dir, clean_target)

        # If no prefix or not found, check install directory (%GAMEDIR%)
        if not resolved and "%GAMEDIR%" in clean_target and game.install_dir:
            sub = clean_target.replace("%GAMEDIR%", "").strip("\\")
            resolved = os.path.join(game.install_dir, sub.replace("\\", "/"))

        # Check native Linux home directory candidates
        if not resolved or not os.path.exists(resolved):
            native_cand = PathResolver._resolve_native(game.name, clean_target)
            if native_cand and os.path.exists(native_cand):
                resolved = native_cand

        if not resolved:
            # Fallback path representation even if not yet created on disk
            if game.prefix_dir:
                resolved = os.path.join(
                    game.prefix_dir, "drive_c", "users", "steamuser",
                    clean_target.replace("%USERPROFILE%", "")
                                .replace("%APPDATA%", "AppData/Roaming")
                                .replace("%LOCALAPPDATA%", "AppData/Local")
                                .strip("\\").replace("\\", "/")
                )
            else:
                resolved = clean_target

        if os.path.isdir(resolved):
            folder = resolved
            exists = True
        elif has_file_target or os.path.isfile(resolved):
            folder = os.path.dirname(resolved)
            exists = os.path.isdir(folder)
        else:
            folder = resolved
            exists = os.path.exists(resolved)

        # Label
        label = "Wine/Proton Prefix"
        if "%GAMEDIR%" in raw_win_path:
            label = "Installationsordner"
        elif "AppData" in raw_win_path or "%APPDATA%" in raw_win_path:
            label = "AppData Roaming"
        elif "LOCALAPPDATA" in raw_win_path:
            label = "AppData Local"
        elif "Documents" in raw_win_path or "Saved Games" in raw_win_path:
            label = "Dokumente / Saved Games"

        return ResolvedPath(
            original=raw_win_path,
            resolved_path=resolved,
            folder_path=folder,
            exists=exists,
            path_type=path_type,
            label=label
        )

    @staticmethod
    def _resolve_in_prefix(prefix_dir: str, win_path: str) -> Optional[str]:
        """Case-insensitively resolves Windows environment paths inside Wine prefix."""
        drive_c = os.path.join(prefix_dir, "drive_c")
        if not os.path.isdir(drive_c):
            return None

        users_dir = os.path.join(drive_c, "users")
        user_root = None
        if os.path.isdir(users_dir):
            users = [u for u in os.listdir(users_dir) if u not in ("Public", "Default")]
            username = "steamuser" if "steamuser" in users else (users[0] if users else "steamuser")
            user_root = os.path.join(users_dir, username)
        else:
            user_root = os.path.join(drive_c, "users", "steamuser")

        path = win_path
        path = path.replace("%USERPROFILE%", user_root)
        path = path.replace("%APPDATA%", os.path.join(user_root, "AppData", "Roaming"))
        path = path.replace("%LOCALAPPDATA%", os.path.join(user_root, "AppData", "Local"))
        path = path.replace("%PROGRAMDATA%", os.path.join(drive_c, "ProgramData"))

        # Traverse path segments case-insensitively
        parts = [p for p in path.split("\\") if p]
        curr = "/"
        for part in parts:
            if curr == "/" and (part.endswith(":") or part == ""):
                continue
            if not os.path.isdir(curr):
                curr = os.path.join(curr, part)
                continue

            # Check direct or case-insensitive or 'My Documents' alias
            try:
                children = os.listdir(curr)
            except Exception:
                curr = os.path.join(curr, part)
                continue

            match = None
            for c in children:
                if c.lower() == part.lower():
                    match = c
                    break

            if not match and part.lower() == "documents":
                for c in children:
                    if c.lower() in ("my documents", "documents"):
                        match = c
                        break

            if match:
                curr = os.path.join(curr, match)
            else:
                curr = os.path.join(curr, part)

        return curr

    @staticmethod
    def _resolve_native(game_name: str, win_path: str) -> Optional[str]:
        """Looks for common Linux native save locations in ~/.local/share or ~/.config."""
        home = os.path.expanduser("~")
        candidates = [
            os.path.join(home, ".local", "share", game_name),
            os.path.join(home, ".config", game_name),
            os.path.join(home, ".local", "share", game_name.lower().replace(" ", "_")),
            os.path.join(home, ".config", game_name.lower().replace(" ", "_")),
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        return None
