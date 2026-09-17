"""Cover and art manager for games across Steam, Heroic, and Lutris.

Provides URL resolution, local caching under ~/.cache/gaming-center/covers/,
and background downloading for games without local covers.
"""

import os
import urllib.request
import urllib.error
from typing import Optional, Tuple, List
from PyQt6.QtCore import QObject, pyqtSignal, QRunnable, QThreadPool

from gaming_center.backend.game_scanner import GameInfo


class CoverManager(QObject):
    """Manages game covers, CDN downloads, and disk caching."""

    _instance = None
    cover_downloaded = pyqtSignal(str, str)  # app_id, local_file_path

    @classmethod
    def get_instance(cls) -> "CoverManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        super().__init__()
        self.cache_dir = os.path.expanduser("~/.cache/gaming-center/covers")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.thread_pool = QThreadPool.globalInstance()
        self._pending_downloads = set()

    def get_cached_poster_path(self, platform: str, app_id: str) -> Optional[str]:
        """Returns the local path if a cached poster exists."""
        clean_id = self._clean_id(app_id)
        candidates = [
            os.path.join(self.cache_dir, f"{platform}_{clean_id}_poster.jpg"),
            os.path.join(self.cache_dir, f"{platform}_{clean_id}_poster.png"),
        ]
        for c in candidates:
            if os.path.isfile(c) and os.path.getsize(c) > 0:
                return c
        return None

    def get_cached_banner_path(self, platform: str, app_id: str) -> Optional[str]:
        """Returns the local path if a cached banner exists."""
        clean_id = self._clean_id(app_id)
        candidates = [
            os.path.join(self.cache_dir, f"{platform}_{clean_id}_banner.jpg"),
            os.path.join(self.cache_dir, f"{platform}_{clean_id}_banner.png"),
        ]
        for c in candidates:
            if os.path.isfile(c) and os.path.getsize(c) > 0:
                return c
        return None

    def _clean_id(self, app_id: str) -> str:
        return "".join(c for c in app_id if c.isalnum() or c in ("-", "_"))

    @staticmethod
    def get_steam_poster_urls(appid: str) -> List[str]:
        """Generates candidate Steam CDN URLs for portrait capsule art."""
        if not appid.isdigit():
            return []
        return [
            f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/library_600x900_2x.jpg",
            f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/library_600x900.jpg",
            f"https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/{appid}/library_600x900_2x.jpg",
            f"https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/{appid}/library_600x900.jpg",
            f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/capsule_616x353.jpg",
            f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg",
        ]

    @staticmethod
    def get_steam_banner_urls(appid: str) -> List[str]:
        """Generates candidate Steam CDN URLs for landscape hero / header art."""
        if not appid.isdigit():
            return []
        return [
            f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/library_hero.jpg",
            f"https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/{appid}/library_hero.jpg",
            f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg",
            f"https://cdn.steamstatic.com/steam/apps/{appid}/header.jpg",
        ]

    def download_image_sync(self, urls: List[str], target_path: str) -> Optional[str]:
        """Tries to download the image from the list of URLs in order and save it to target_path."""
        import gaming_center
        headers = {"User-Agent": f"Mozilla/5.0 (X11; Linux x86_64) GamingCenter/{gaming_center.__version__}"}
        for url in urls:
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=6) as response:
                    if response.status == 200:
                        data = response.read()
                        if len(data) > 500:  # Avoid empty or 1x1 tracking pixels
                            tmp_path = target_path + ".tmp"
                            with open(tmp_path, "wb") as f:
                                f.write(data)
                            os.replace(tmp_path, target_path)
                            return target_path
            except Exception:
                continue
        return None

    def fetch_cover_async(self, game: GameInfo):
        """Asynchronously downloads cover for a game in background if missing."""
        if not game.app_id or game.app_id in self._pending_downloads:
            return

        # Check if already cached locally
        cached = self.get_cached_poster_path(game.platform, game.app_id)
        if cached:
            game.poster_image = cached
            self.cover_downloaded.emit(game.app_id, cached)
            return

        urls: List[str] = []
        if game.poster_image and (game.poster_image.startswith("http://") or game.poster_image.startswith("https://")):
            urls.append(game.poster_image)

        if game.platform == "steam" and game.app_id.isdigit():
            urls.extend(self.get_steam_poster_urls(game.app_id))

        if not urls:
            return

        self._pending_downloads.add(game.app_id)
        target_file = os.path.join(self.cache_dir, f"{game.platform}_{self._clean_id(game.app_id)}_poster.jpg")

        worker = _DownloadWorker(urls, target_file, game.app_id, self._on_download_finished)
        self.thread_pool.start(worker)

    def _on_download_finished(self, app_id: str, local_path: Optional[str]):
        self._pending_downloads.discard(app_id)
        if local_path and os.path.isfile(local_path):
            self.cover_downloaded.emit(app_id, local_path)


class _DownloadWorker(QRunnable):
    """Background runnable to download an image without blocking the UI."""

    def __init__(self, urls: List[str], target_path: str, app_id: str, callback):
        super().__init__()
        self.urls = urls
        self.target_path = target_path
        self.app_id = app_id
        self.callback = callback

    def run(self):
        manager = CoverManager.get_instance()
        result = manager.download_image_sync(self.urls, self.target_path)
        self.callback(self.app_id, result)
