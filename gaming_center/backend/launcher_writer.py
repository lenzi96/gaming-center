"""
Launcher Writer for Gaming Center.

Provides safe, direct persistence of game launch options into launcher configuration files:
- Steam: userdata/<account_id>/config/localconfig.vdf
- Heroic Games Launcher: ~/.config/heroic/GamesConfig/<app_name>.json
- Lutris: ~/.config/lutris/games/<slug>-<id>.yml
"""

import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from .game_scanner import GameInfo


class LauncherWriter:
    @staticmethod
    def is_steam_running() -> bool:
        """Checks if the Steam client process is currently running."""
        try:
            res = subprocess.run(["pgrep", "-x", "steam"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return res.returncode == 0
        except Exception:
            return False

    @staticmethod
    def get_steam_localconfig_paths() -> List[str]:
        """Finds all localconfig.vdf files across Steam libraries and user accounts."""
        paths = set()
        home = Path.home()
        candidates = [
            home / ".local/share/Steam/userdata",
            home / ".steam/steam/userdata",
            home / ".steam/root/userdata",
            home / ".var/app/com.valvesoftware.Steam/.local/share/Steam/userdata",
        ]

        for cand in candidates:
            if cand.is_dir():
                for p in cand.glob("*/config/localconfig.vdf"):
                    if p.is_file():
                        paths.add(str(p.resolve()))

        return sorted(list(paths))

    @classmethod
    def read_current_launcher_options(cls, game: GameInfo) -> Optional[str]:
        """Reads what launch options are currently configured in the game's launcher."""
        if not game:
            return None

        platform = (game.platform or "steam").lower()

        if platform == "steam":
            return cls._read_steam_launch_options(game.app_id)
        elif platform == "heroic":
            return cls._read_heroic_launch_options(game.app_id)
        elif platform == "lutris":
            return cls._read_lutris_launch_options(game.app_id)

        return None

    @classmethod
    def write_launch_options(cls, game: GameInfo, command_line: str) -> Tuple[bool, str]:
        """
        Writes the generated launch command string directly into the game's launcher config.
        Returns (success: bool, message: str).
        """
        if not game:
            return False, "Kein Spiel ausgewählt."

        platform = (game.platform or "steam").lower()

        if platform == "steam":
            return cls._write_steam_launch_options(game.app_id, command_line)
        elif platform == "heroic":
            return cls._write_heroic_launch_options(game.app_id, command_line)
        elif platform == "lutris":
            return cls._write_lutris_launch_options(game.app_id, command_line)

        return False, f"Plattform '{platform}' wird für direktes Schreiben nicht unterstützt."

    @classmethod
    def clear_launcher_options(cls, game: GameInfo) -> Tuple[bool, str]:
        """Removes custom launch options from the game's launcher configuration."""
        if not game:
            return False, "Kein Spiel ausgewählt."

        platform = (game.platform or "steam").lower()

        if platform == "steam":
            return cls._write_steam_launch_options(game.app_id, "")
        elif platform == "heroic":
            return cls._write_heroic_launch_options(game.app_id, "")
        elif platform == "lutris":
            return cls._write_lutris_launch_options(game.app_id, "")

        return False, f"Plattform '{platform}' wird nicht unterstützt."

    # -------------------------------------------------------------------------
    # Steam Implementation (localconfig.vdf)
    # -------------------------------------------------------------------------

    @classmethod
    def _read_steam_launch_options(cls, app_id: str) -> Optional[str]:
        if not app_id:
            return None

        for vdf_path in cls.get_steam_localconfig_paths():
            try:
                data = cls._load_vdf(vdf_path)
                if not data:
                    continue

                app_entry = cls._navigate_steam_apps_dict(data, app_id, create_if_missing=False)
                if app_entry and isinstance(app_entry, dict):
                    for k, v in app_entry.items():
                        if k.lower() == "launchoptions":
                            return str(v)
            except Exception:
                pass

        return None

    @classmethod
    def _write_steam_launch_options(cls, app_id: str, command_line: str) -> Tuple[bool, str]:
        if not app_id:
            return False, "Ungültige Steam App-ID."

        vdf_paths = cls.get_steam_localconfig_paths()
        if not vdf_paths:
            return False, "Keine Steam 'localconfig.vdf' im System gefunden."

        modified_count = 0
        for vdf_path in vdf_paths:
            try:
                data = cls._load_vdf(vdf_path)
                if data is None:
                    continue

                app_entry = cls._navigate_steam_apps_dict(data, app_id, create_if_missing=True)
                if app_entry is None or not isinstance(app_entry, dict):
                    continue

                if command_line.strip():
                    app_entry["LaunchOptions"] = command_line.strip()
                else:
                    to_del = [k for k in app_entry if k.lower() == "launchoptions"]
                    for k in to_del:
                        del app_entry[k]

                bak_path = vdf_path + ".bak"
                if not os.path.exists(bak_path):
                    shutil.copy2(vdf_path, bak_path)

                cls._save_vdf_atomic(vdf_path, data)
                modified_count += 1
            except Exception as e:
                return False, f"Fehler beim Schreiben von Steam VDF ({os.path.basename(vdf_path)}): {e}"

        if modified_count == 0:
            return False, "Konnte Konfiguration in Steam-Dateien nicht anwenden."

        msg = "Startoptionen erfolgreich in Steam eingetragen!"
        if cls.is_steam_running():
            msg += "\n\n⚠️ Hinweis: Steam ist aktuell geöffnet! Bitte starte Steam neu, damit die geänderten Startoptionen aktiv werden."
        return True, msg

    @staticmethod
    def _navigate_steam_apps_dict(data: Dict[str, Any], app_id: str, create_if_missing: bool = False) -> Optional[Dict[str, Any]]:
        """Navigates to UserLocalConfigStore -> Software -> Valve -> Steam -> apps -> <app_id>."""
        def _get_or_create(parent: Dict[str, Any], key_candidates: List[str]) -> Optional[Dict[str, Any]]:
            for k in key_candidates:
                if k in parent and isinstance(parent[k], dict):
                    return parent[k]
            if create_if_missing:
                first_k = key_candidates[0]
                parent[first_k] = {}
                return parent[first_k]
            return None

        store = _get_or_create(data, ["UserLocalConfigStore", "userlocalconfigstore"])
        if store is None:
            return None

        software = _get_or_create(store, ["Software", "software"])
        if software is None:
            return None

        valve = _get_or_create(software, ["Valve", "valve"])
        if valve is None:
            return None

        steam = _get_or_create(valve, ["Steam", "steam"])
        if steam is None:
            return None

        apps = _get_or_create(steam, ["apps", "Apps"])
        if apps is None:
            return None

        return _get_or_create(apps, [str(app_id)])

    @staticmethod
    def _load_vdf(path: str) -> Optional[Dict[str, Any]]:
        """Loads a VDF file using the vdf package with fallback."""
        try:
            import vdf
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return vdf.load(f)
        except Exception:
            pass

        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
            return LauncherWriter._simple_vdf_parse(text)
        except Exception:
            return None

    @staticmethod
    def _save_vdf_atomic(path: str, data: Dict[str, Any]):
        """Serializes and writes VDF atomically."""
        dir_name = os.path.dirname(path)
        with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding="utf-8") as tf:
            tmp_name = tf.name
            try:
                import vdf
                vdf.dump(data, tf, pretty=True)
            except Exception:
                content = LauncherWriter._simple_vdf_dump(data)
                tf.write(content)

        os.replace(tmp_name, path)

    @staticmethod
    def _simple_vdf_parse(text: str) -> Dict[str, Any]:
        """Simple recursive VDF parser fallback."""
        tokens = re.findall(r'"([^"]*)"|([{}])', text)
        stack: List[Dict[str, Any]] = [{}]
        key = None

        for str_val, brace in tokens:
            if brace == "{":
                new_dict: Dict[str, Any] = {}
                if key:
                    stack[-1][key] = new_dict
                    key = None
                stack.append(new_dict)
            elif brace == "}":
                if len(stack) > 1:
                    stack.pop()
            elif str_val is not None:
                if key is None:
                    key = str_val
                else:
                    stack[-1][key] = str_val
                    key = None

        return stack[0]

    @staticmethod
    def _simple_vdf_dump(data: Dict[str, Any], indent: int = 0) -> str:
        """Simple VDF serializer fallback."""
        lines: List[str] = []
        tabs = "\t" * indent
        for k, v in data.items():
            if isinstance(v, dict):
                lines.append(f'{tabs}"{k}"')
                lines.append(f'{tabs}{{')
                lines.append(LauncherWriter._simple_vdf_dump(v, indent + 1))
                lines.append(f'{tabs}}}')
            else:
                escaped_v = str(v).replace('"', '\\"')
                lines.append(f'{tabs}"{k}"\t\t"{escaped_v}"')
        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # Heroic Games Launcher Implementation
    # -------------------------------------------------------------------------

    @classmethod
    def _get_heroic_app_name(cls, app_id: str) -> str:
        """Extracts the actual Heroic appName from app_id."""
        if app_id.startswith("heroic_gog_"):
            return app_id[len("heroic_gog_"):]
        elif app_id.startswith("heroic_epic_"):
            return app_id[len("heroic_epic_"):]
        elif app_id.startswith("heroic_"):
            return app_id[len("heroic_"):]
        return app_id

    @classmethod
    def _read_heroic_launch_options(cls, app_id: str) -> Optional[str]:
        app_name = cls._get_heroic_app_name(app_id)
        cfg_path = os.path.expanduser(f"~/.config/heroic/GamesConfig/{app_name}.json")
        if not os.path.isfile(cfg_path):
            return None

        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                args = data.get("launchArguments", "").strip()
                wrapper = " ".join(data.get("wrapperOptions", [])) if isinstance(data.get("wrapperOptions"), list) else str(data.get("wrapperOptions", ""))
                auto_exec = data.get("autoExec", "").strip()

                parts = []
                if wrapper.strip():
                    parts.append(wrapper.strip())
                if auto_exec:
                    parts.append(auto_exec)
                if args:
                    parts.append(args)
                return " ".join(parts) if parts else None
        except Exception:
            return None

    @classmethod
    def _write_heroic_launch_options(cls, app_id: str, command_line: str) -> Tuple[bool, str]:
        app_name = cls._get_heroic_app_name(app_id)
        cfg_dir = os.path.expanduser("~/.config/heroic/GamesConfig")
        os.makedirs(cfg_dir, exist_ok=True)
        cfg_path = os.path.join(cfg_dir, f"{app_name}.json")

        data: Dict[str, Any] = {}
        if os.path.isfile(cfg_path):
            try:
                bak_path = cfg_path + ".bak"
                if not os.path.exists(bak_path):
                    shutil.copy2(cfg_path, bak_path)

                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}

        cmd = command_line.strip()
        if cmd:
            if "%command%" in cmd:
                before, after = cmd.split("%command%", 1)
                data["autoExec"] = before.strip()
                data["launchArguments"] = after.strip()
            else:
                data["autoExec"] = cmd
        else:
            data.pop("autoExec", None)
            data.pop("launchArguments", None)

        try:
            with tempfile.NamedTemporaryFile("w", dir=cfg_dir, delete=False, encoding="utf-8") as tf:
                tmp_name = tf.name
                json.dump(data, tf, indent=2, ensure_ascii=False)
            os.replace(tmp_name, cfg_path)
            return True, "Startoptionen erfolgreich im Heroic Games Launcher hinterlegt!"
        except Exception as e:
            return False, f"Fehler beim Schreiben der Heroic-Konfiguration: {e}"

    # -------------------------------------------------------------------------
    # Lutris Implementation
    # -------------------------------------------------------------------------

    @classmethod
    def _read_lutris_launch_options(cls, app_id: str) -> Optional[str]:
        slug_id = app_id[len("lutris_"):] if app_id.startswith("lutris_") else app_id
        lutris_dir = os.path.expanduser("~/.config/lutris/games")
        if not os.path.isdir(lutris_dir):
            return None

        for yml_file in glob.glob(os.path.join(lutris_dir, f"*-{slug_id}.yml")):
            try:
                with open(yml_file, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    m = re.search(r"^\s*args:\s*(.+)$", content, re.MULTILINE)
                    if m:
                        return m.group(1).strip().strip("'\"")
            except Exception:
                pass
        return None

    @classmethod
    def _write_lutris_launch_options(cls, app_id: str, command_line: str) -> Tuple[bool, str]:
        slug_id = app_id[len("lutris_"):] if app_id.startswith("lutris_") else app_id
        lutris_dir = os.path.expanduser("~/.config/lutris/games")
        if not os.path.isdir(lutris_dir):
            return False, "Lutris-Konfigurationsordner nicht gefunden."

        matches = glob.glob(os.path.join(lutris_dir, f"*-{slug_id}.yml"))
        if not matches:
            return False, f"Lutris-Konfigurationsdatei für Spiel ID '{slug_id}' nicht gefunden."

        target_file = matches[0]
        try:
            bak_path = target_file + ".bak"
            if not os.path.exists(bak_path):
                shutil.copy2(target_file, bak_path)

            with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            cmd_clean = command_line.replace("%command%", "").strip()
            args_set = False
            new_lines = []

            for line in lines:
                if re.match(r"^\s*args:\s*", line):
                    if cmd_clean:
                        new_lines.append(f"  args: '{cmd_clean}'\n")
                        args_set = True
                else:
                    new_lines.append(line)
                    if re.match(r"^game:\s*", line) and cmd_clean and not args_set:
                        new_lines.append(f"  args: '{cmd_clean}'\n")
                        args_set = True

            with tempfile.NamedTemporaryFile("w", dir=lutris_dir, delete=False, encoding="utf-8") as tf:
                tmp_name = tf.name
                tf.writelines(new_lines)
            os.replace(tmp_name, target_file)

            return True, "Startoptionen erfolgreich in Lutris hinterlegt!"
        except Exception as e:
            return False, f"Fehler beim Schreiben der Lutris-Konfiguration: {e}"
