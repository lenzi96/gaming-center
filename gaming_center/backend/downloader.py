"""Multi-threaded background downloader for game patches, mods, and fixes.

Includes GitHub API release asset resolution and secure archive extraction.
"""

import os
import re
import time
import urllib.parse
import urllib.request
import zipfile
import tarfile
from typing import Optional, Tuple, List, Dict
from PyQt6.QtCore import QThread, pyqtSignal


class GitHubReleaseResolver:
    """Resolves GitHub repository URLs to direct latest release asset URLs."""

    @staticmethod
    def is_github_repo_or_release(url: str) -> bool:
        u = url.lower()
        return "github.com" in u and not any(bad in u for bad in ["/issues", "/pulls", "/wiki"])

    @staticmethod
    def resolve_latest_asset(url: str, timeout: int = 5) -> Optional[Dict[str, any]]:
        """Queries GitHub API to find the latest release and its primary download asset.

        Returns dict with: {download_url, filename, size, tag_name} or None.
        """
        m = re.search(r"github\.com/([^/]+)/([^/]+)", url)
        if not m:
            return None

        owner = m.group(1)
        repo = m.group(2).rstrip("/")
        # If repo has .git, strip it
        if repo.endswith(".git"):
            repo = repo[:-4]

        api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
        req = urllib.request.Request(
            api_url,
            headers={
                "User-Agent": "GamingCenter/1.0 (Linux; x86_64)",
                "Accept": "application/vnd.github.v3+json"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json_loads(resp.read().decode("utf-8"))

            assets = data.get("assets", [])
            tag_name = data.get("tag_name", "latest")

            if assets:
                # Prefer zip, 7z, tar.gz, exe
                best_asset = assets[0]
                for a in assets:
                    name = a.get("name", "").lower()
                    if name.endswith((".zip", ".7z", ".tar.gz", ".exe", ".asi", ".dll")):
                        best_asset = a
                        break

                return {
                    "download_url": best_asset.get("browser_download_url"),
                    "filename": best_asset.get("name"),
                    "size": best_asset.get("size", 0),
                    "tag_name": tag_name
                }
            else:
                # Fallback to source zipball
                return {
                    "download_url": data.get("zipball_url"),
                    "filename": f"{repo}-{tag_name}.zip",
                    "size": 0,
                    "tag_name": tag_name
                }
        except Exception:
            return None


def json_loads(s: str):
    import json
    return json.loads(s)


class DownloadWorker(QThread):
    """Background download worker with chunk streaming, speed calculation, and progress updates."""

    started = pyqtSignal(str, int)                      # filename, total_bytes
    progress = pyqtSignal(int, int, int, str, str)      # downloaded_bytes, total_bytes, percent, speed_str, eta_str
    finished = pyqtSignal(str)                          # saved_file_path
    error = pyqtSignal(str)                             # error_message
    cancelled = pyqtSignal()                            # download_cancelled

    CHUNK_SIZE = 64 * 1024  # 64 KB

    def __init__(self, url: str, dest_dir: str, custom_filename: Optional[str] = None):
        super().__init__()
        self.url = url
        self.dest_dir = dest_dir
        self.custom_filename = custom_filename
        self._is_cancelled = False

    def cancel(self):
        """Cancels the active download."""
        self._is_cancelled = True

    def run(self):
        os.makedirs(self.dest_dir, exist_ok=True)

        req = urllib.request.Request(
            self.url,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                "Accept": "*/*"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                total_bytes = int(response.headers.get("Content-Length", 0))

                # Determine filename
                filename = self.custom_filename
                if not filename:
                    # Try Content-Disposition
                    cd = response.headers.get("Content-Disposition", "")
                    cd_match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';\r\n]+)', cd, re.IGNORECASE)
                    if cd_match:
                        filename = urllib.parse.unquote(cd_match.group(1).strip())

                if not filename:
                    # Fallback to URL path basename
                    parsed_path = urllib.parse.urlparse(response.geturl() or self.url).path
                    base = os.path.basename(parsed_path)
                    filename = urllib.parse.unquote(base) if base else "download.zip"

                # Sanitize filename
                filename = re.sub(r'[\\/*?:"<>|]', "_", filename)
                final_path = os.path.join(self.dest_dir, filename)
                part_path = final_path + ".part"

                self.started.emit(filename, total_bytes)

                downloaded_bytes = 0
                start_time = time.time()
                last_update_time = start_time
                last_downloaded_bytes = 0

                with open(part_path, "wb") as f:
                    while True:
                        if self._is_cancelled:
                            f.close()
                            if os.path.exists(part_path):
                                os.remove(part_path)
                            self.cancelled.emit()
                            return

                        chunk = response.read(self.CHUNK_SIZE)
                        if not chunk:
                            break

                        f.write(chunk)
                        downloaded_bytes += len(chunk)

                        now = time.time()
                        if now - last_update_time >= 0.15 or (total_bytes > 0 and downloaded_bytes == total_bytes):
                            elapsed = now - last_update_time
                            bytes_diff = downloaded_bytes - last_downloaded_bytes
                            speed_bps = (bytes_diff / elapsed) if elapsed > 0 else 0
                            speed_str = self._format_speed(speed_bps)

                            percent = int((downloaded_bytes / total_bytes) * 100) if total_bytes > 0 else 0
                            eta_str = ""
                            if speed_bps > 0 and total_bytes > downloaded_bytes:
                                remaining_sec = int((total_bytes - downloaded_bytes) / speed_bps)
                                eta_str = self._format_eta(remaining_sec)

                            self.progress.emit(downloaded_bytes, total_bytes, percent, speed_str, eta_str)
                            last_update_time = now
                            last_downloaded_bytes = downloaded_bytes

                # Rename .part to final
                if os.path.exists(final_path):
                    try:
                        os.remove(final_path)
                    except Exception:
                        pass
                os.rename(part_path, final_path)

                self.finished.emit(final_path)

        except Exception as e:
            self.error.emit(str(e))

    def _format_speed(self, bytes_per_sec: float) -> str:
        if bytes_per_sec >= 1024 * 1024:
            return f"{bytes_per_sec / (1024 * 1024):.1f} MB/s"
        elif bytes_per_sec >= 1024:
            return f"{bytes_per_sec / 1024:.0f} KB/s"
        else:
            return f"{bytes_per_sec:.0f} B/s"

    def _format_eta(self, seconds: int) -> str:
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds // 60}m {seconds % 60}s"
        else:
            return f"{seconds // 3600}h {(seconds % 3600) // 60}m"


class ArchiveExtractor:
    """Safe archive extractor preventing path traversal attacks (Zip Slip)."""

    @staticmethod
    def is_supported_archive(path: str) -> bool:
        lower = path.lower()
        return lower.endswith((".zip", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz", ".tar"))

    @staticmethod
    def extract(archive_path: str, dest_dir: str) -> Tuple[bool, str, List[str]]:
        """Extracts supported archive into dest_dir safely.

        Returns (success: bool, message: str, extracted_files: list).
        """
        if not os.path.isfile(archive_path):
            return False, "Archivdatei existiert nicht.", []

        dest_dir = os.path.abspath(dest_dir)
        os.makedirs(dest_dir, exist_ok=True)
        extracted = []

        try:
            if zipfile.is_zipfile(archive_path):
                with zipfile.ZipFile(archive_path, "r") as z:
                    for member in z.infolist():
                        target_path = os.path.abspath(os.path.join(dest_dir, member.filename))
                        # Prevent Zip Slip directory traversal
                        if not target_path.startswith(dest_dir + os.sep) and target_path != dest_dir:
                            continue
                        z.extract(member, dest_dir)
                        extracted.append(target_path)
                return True, f"{len(extracted)} Dateien erfolgreich entpackt.", extracted

            elif tarfile.is_tarfile(archive_path):
                with tarfile.open(archive_path, "r:*") as t:
                    for member in t.getmembers():
                        target_path = os.path.abspath(os.path.join(dest_dir, member.name))
                        if not target_path.startswith(dest_dir + os.sep) and target_path != dest_dir:
                            continue
                        t.extract(member, dest_dir)
                        extracted.append(target_path)
                return True, f"{len(extracted)} Dateien erfolgreich entpackt.", extracted

            else:
                return False, "Dateiformat wird für automatische Entpackung nicht unterstützt.", []

        except Exception as e:
            return False, f"Fehler beim Entpacken: {str(e)}", []
