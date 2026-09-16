"""Savegame backup and restoration manager."""

import os
import shutil
import tarfile
import time
from dataclasses import dataclass
from typing import List, Optional
from PyQt6.QtCore import QObject, pyqtSignal


@dataclass
class BackupInfo:
    file_path: str
    file_name: str
    game_id: str
    timestamp: float
    size_bytes: int
    note: str = ""

    @property
    def formatted_date(self) -> str:
        return time.strftime("%d.%m.%Y %H:%M:%S", time.localtime(self.timestamp))

    @property
    def formatted_size(self) -> str:
        kb = self.size_bytes / 1024
        if kb > 1024:
            return f"{kb / 1024:.2f} MB"
        return f"{kb:.0f} KB"


class SavegameManager(QObject):
    backup_created = pyqtSignal(object)  # BackupInfo
    backup_restored = pyqtSignal(str)   # file_path
    backup_deleted = pyqtSignal(str)

    def __init__(self, base_backup_dir: Optional[str] = None):
        super().__init__()
        if base_backup_dir is None:
            self.base_dir = os.path.expanduser("~/.local/share/gaming-center/backups")
        else:
            self.base_dir = base_backup_dir
        os.makedirs(self.base_dir, exist_ok=True)

    def get_game_backup_dir(self, game_id: str) -> str:
        safe_id = "".join(c for c in game_id if c.isalnum() or c in ("_", "-"))
        d = os.path.join(self.base_dir, safe_id)
        os.makedirs(d, exist_ok=True)
        return d

    def list_backups(self, game_id: str) -> List[BackupInfo]:
        """Lists all existing backups for a game sorted newest first."""
        d = self.get_game_backup_dir(game_id)
        results: List[BackupInfo] = []
        if not os.path.isdir(d):
            return results

        for fname in os.listdir(d):
            if fname.endswith(".tar.gz"):
                fpath = os.path.join(d, fname)
                try:
                    stat = os.stat(fpath)
                    # Expected format: backup_YYYYMMDD_HHMMSS[_note].tar.gz
                    note = ""
                    parts = fname.replace(".tar.gz", "").split("_", 3)
                    if len(parts) >= 4:
                        note = parts[3].replace("_", " ")

                    results.append(BackupInfo(
                        file_path=fpath,
                        file_name=fname,
                        game_id=game_id,
                        timestamp=stat.st_mtime,
                        size_bytes=stat.st_size,
                        note=note
                    ))
                except Exception:
                    pass

        results.sort(key=lambda b: b.timestamp, reverse=True)
        return results

    def create_backup(self, game_id: str, source_path: str, note: str = "") -> Optional[BackupInfo]:
        """Creates a timestamped .tar.gz archive of source_path."""
        if not os.path.exists(source_path):
            return None

        game_dir = self.get_game_backup_dir(game_id)
        ts_str = time.strftime("%Y%m%d_%H%M%S")
        clean_note = "".join(c for c in note if c.isalnum() or c in ("_", "-")).strip()
        if clean_note:
            fname = f"backup_{ts_str}_{clean_note}.tar.gz"
        else:
            fname = f"backup_{ts_str}.tar.gz"

        out_path = os.path.join(game_dir, fname)

        try:
            with tarfile.open(out_path, "w:gz") as tar:
                if os.path.isdir(source_path):
                    # Arcname stores folder name
                    arcname = os.path.basename(os.path.normpath(source_path))
                    tar.add(source_path, arcname=arcname)
                else:
                    tar.add(source_path, arcname=os.path.basename(source_path))

            stat = os.stat(out_path)
            info = BackupInfo(
                file_path=out_path,
                file_name=fname,
                game_id=game_id,
                timestamp=stat.st_mtime,
                size_bytes=stat.st_size,
                note=note
            )
            self.backup_created.emit(info)
            return info
        except Exception as e:
            if os.path.exists(out_path):
                try:
                    os.remove(out_path)
                except Exception:
                    pass
            return None

    def restore_backup(self, backup_file: str, target_dir: str) -> bool:
        """Extracts backup archive into target directory."""
        if not os.path.isfile(backup_file):
            return False

        try:
            with tarfile.open(backup_file, "r:gz") as tar:
                # Security check against path traversal
                for member in tar.getmembers():
                    if member.name.startswith("/") or ".." in member.name:
                        return False
                tar.extractall(path=target_dir)
            self.backup_restored.emit(backup_file)
            return True
        except Exception:
            return False

    def delete_backup(self, backup_file: str) -> bool:
        """Deletes a backup file."""
        if os.path.isfile(backup_file):
            try:
                os.remove(backup_file)
                self.backup_deleted.emit(backup_file)
                return True
            except Exception:
                pass
        return False
