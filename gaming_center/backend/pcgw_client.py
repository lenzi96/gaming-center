"""PCGamingWiki API client for fetching save paths, config locations, fixes, and features."""

import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple


@dataclass
class PCGWDownload:
    title: str
    url: str
    description: str = ""
    source: str = "Direct"  # "GitHub", "NexusMods", "ModDB", "PCGamingWiki", "Archive.org", "Direct"
    is_direct: bool = False
    direct_download_url: Optional[str] = None
    filename: Optional[str] = None
    filesize: Optional[int] = None


@dataclass
class PCGWFix:
    title: str
    description: str
    instructions: str = ""
    fix_type: str = "general"  # "intro", "crash", "performance", "general"
    downloads: List[PCGWDownload] = field(default_factory=list)


@dataclass
class PCGWData:
    page_title: str
    pcgw_url: str
    steam_appid: Optional[str] = None
    save_paths_windows: List[str] = field(default_factory=list)
    save_paths_linux: List[str] = field(default_factory=list)
    config_paths_windows: List[str] = field(default_factory=list)
    config_paths_linux: List[str] = field(default_factory=list)
    features: Dict[str, str] = field(default_factory=dict)
    fixes: List[PCGWFix] = field(default_factory=list)
    command_line_arguments: List[str] = field(default_factory=list)
    downloads: List[PCGWDownload] = field(default_factory=list)
    cached_at: float = field(default_factory=time.time)


class PCGWClient:
    API_URL = "https://www.pcgamingwiki.com/w/api.php"
    USER_AGENT = "GamingCenter/1.0 (Linux; PyQt6) +https://github.com/cachyos"

    def __init__(self, cache_dir: Optional[str] = None):
        if cache_dir is None:
            self.cache_dir = os.path.expanduser("~/.cache/gaming-center/pcgw")
        else:
            self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)

    def _get_cache_path(self, title: str) -> str:
        h = hashlib.sha256(title.strip().lower().encode("utf-8")).hexdigest()[:16]
        safe_name = "".join(c for c in title if c.isalnum() or c in (" ", "_", "-")).rstrip()
        safe_name = safe_name[:40].replace(" ", "_")
        return os.path.join(self.cache_dir, f"{safe_name}_{h}.json")

    def _request_json(self, params: Dict[str, str], timeout: int = 8) -> Optional[Dict[str, Any]]:
        """Makes an HTTP GET request to the MediaWiki API."""
        try:
            params["format"] = "json"
            query_str = urllib.parse.urlencode(params)
            url = f"{self.API_URL}?{query_str}"
            req = urllib.request.Request(url, headers={"User-Agent": self.USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read().decode("utf-8", errors="ignore")
                return json.loads(data)
        except Exception:
            return None

    def search_game(self, query: str) -> List[Tuple[str, str]]:
        """Searches PCGW using OpenSearch. Returns [(title, pcgw_url), ...]."""
        # Clean title (e.g. remove TM, (R), Edition suffixes for better search)
        cleaned = re.sub(r"[™®©]", "", query)
        cleaned = re.sub(r"\(.*?\)", "", cleaned).strip()
        if not cleaned:
            cleaned = query

        params = {
            "action": "opensearch",
            "search": cleaned,
            "limit": "5"
        }
        data = self._request_json(params)
        if not data or len(data) < 4:
            return []

        titles = data[1]
        urls = data[3]
        return list(zip(titles, urls))

    def fetch_game_data(self, page_title: str, force_refresh: bool = False) -> Optional[PCGWData]:
        """Fetches full game data from cache or PCGW API."""
        cache_path = self._get_cache_path(page_title)

        # 1. Check local cache (valid for 7 days)
        if not force_refresh and os.path.isfile(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    cached_dict = json.load(f)
                    # Only use cache if it was created with download link support and cache_version >= 2
                    if "downloads" in cached_dict and cached_dict.get("cache_version", 1) >= 2:
                        cached_dict.pop("cache_version", None)
                        cached_downloads = [PCGWDownload(**dl) for dl in cached_dict.pop("downloads", [])]
                        fixes_raw = cached_dict.pop("fixes", [])
                        fixes = []
                        for fx in fixes_raw:
                            fx_downloads = [PCGWDownload(**dl) for dl in fx.pop("downloads", [])]
                            fixes.append(PCGWFix(downloads=fx_downloads, **fx))
                        return PCGWData(fixes=fixes, downloads=cached_downloads, **cached_dict)
            except Exception:
                pass

        # 2. Fetch from PCGW
        params = {
            "action": "parse",
            "page": page_title,
            "prop": "wikitext|sections",
            "redirects": "1",
        }
        res = self._request_json(params)
        if not res or "parse" not in res:
            return None

        parse_obj = res["parse"]
        real_title = parse_obj.get("title", page_title)
        wikitext = parse_obj.get("wikitext", {}).get("*", "")
        pcgw_url = f"https://www.pcgamingwiki.com/wiki/{urllib.parse.quote(real_title.replace(' ', '_'))}"

        # 3. Parse wikitext
        data = self._parse_wikitext(real_title, pcgw_url, wikitext)

        # 4. Save to cache
        try:
            cache_obj = {
                "cache_version": 2,
                "page_title": data.page_title,
                "pcgw_url": data.pcgw_url,
                "steam_appid": data.steam_appid,
                "save_paths_windows": data.save_paths_windows,
                "save_paths_linux": data.save_paths_linux,
                "config_paths_windows": data.config_paths_windows,
                "config_paths_linux": data.config_paths_linux,
                "features": data.features,
                "fixes": [
                    {
                        "title": fx.title,
                        "description": fx.description,
                        "instructions": fx.instructions,
                        "fix_type": fx.fix_type,
                        "downloads": [
                            {
                                "title": dl.title,
                                "url": dl.url,
                                "description": dl.description,
                                "source": dl.source,
                                "is_direct": dl.is_direct,
                                "direct_download_url": dl.direct_download_url,
                                "filename": dl.filename,
                                "filesize": dl.filesize,
                            }
                            for dl in fx.downloads
                        ]
                    }
                    for fx in data.fixes
                ],
                "command_line_arguments": data.command_line_arguments,
                "downloads": [
                    {
                        "title": dl.title,
                        "url": dl.url,
                        "description": dl.description,
                        "source": dl.source,
                        "is_direct": dl.is_direct,
                        "direct_download_url": dl.direct_download_url,
                        "filename": dl.filename,
                        "filesize": dl.filesize,
                    }
                    for dl in data.downloads
                ],
                "cached_at": time.time(),
            }
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache_obj, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

        return data

    def _clean_wikitext_path(self, raw_path: str) -> str:
        """Converts PCGW path templates into standard environment path strings."""
        path = raw_path
        # {{p|userprofile\Documents}} -> %USERPROFILE%\Documents
        path = re.sub(r"\{\{[pP]\|userprofile\\?([^}]*)\}\}", r"%USERPROFILE%\\\1", path)
        path = re.sub(r"\{\{[pP]\|localappdata\\?([^}]*)\}\}", r"%LOCALAPPDATA%\\\1", path)
        path = re.sub(r"\{\{[pP]\|appdata\\?([^}]*)\}\}", r"%APPDATA%\\\1", path)
        path = re.sub(r"\{\{[pP]\|programdata\\?([^}]*)\}\}", r"%PROGRAMDATA%\\\1", path)
        path = re.sub(r"\{\{[pP]\|documents\\?([^}]*)\}\}", r"%USERPROFILE%\\Documents\\\1", path)
        path = re.sub(r"\{\{[pP]\|userprofile\}\}", "%USERPROFILE%", path)
        path = re.sub(r"\{\{[pP]\|localappdata\}\}", "%LOCALAPPDATA%", path)
        path = re.sub(r"\{\{[pP]\|appdata\}\}", "%APPDATA%", path)
        path = re.sub(r"\{\{[pP]\|game\}\}", "%GAMEDIR%", path)
        # Strip other {{template|...}} or {{...}}
        path = re.sub(r"\{\{[^}]+\}\}", "", path)
        # Strip HTML comments and refs
        path = re.sub(r"<ref[^>]*>.*?</ref>", "", path, flags=re.DOTALL)
        path = re.sub(r"<[^>]+>", "", path)
        # Strip wiki links [[Target|Label]] -> Label
        path = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", path)
        # Clean double slashes / backslashes
        path = path.replace("/", "\\")
        path = re.sub(r"\\+", r"\\", path)
        return path.strip()

    def _clean_wikitext_markup(self, text: str) -> str:
        """Strips wiki formatting, citations and html tags for display."""
        # Remove refs and tags
        text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.DOTALL)
        text = re.sub(r"<ref[^>]*/>", "", text)
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        # Wiki links [[Target|Text]] -> Text
        text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", text)
        # External links [http://url Text] -> Text
        text = re.sub(r"\[https?://[^\s]+ ([^\]]+)\]", r"\1", text)
        text = re.sub(r"\[https?://[^\s]+\]", "", text)
        # Templates
        text = re.sub(r"\{\{[pP]\|([^}]+)\}\}", r"%\1%", text)
        text = re.sub(r"\{\{file\|([^|]+)(?:\|[^}]+)?\}\}", r"\1", text)
        text = re.sub(r"\{\{folder\|([^|]+)(?:\|[^}]+)?\}\}", r"\1", text)
        text = re.sub(r"\{\{code\|([^}]+)\}\}", r"\1", text)
        text = re.sub(r"\{\{ii\}\}", "• ", text)
        text = re.sub(r"\{\{--\}\}", "- ", text)
        text = re.sub(r"\{\{[^}]+\}\}", "", text)
        # Bold / Italics
        text = re.sub(r"'{2,5}", "", text)

        # Clean up lines and bullets
        lines = []
        for line in text.splitlines():
            line_str = line.strip()
            if line_str.startswith("#"):
                line_str = "• " + line_str.lstrip("#").strip()
            elif line_str.startswith("*"):
                line_str = "• " + line_str.lstrip("*").strip()
            if line_str:
                lines.append(line_str)
        return "\n".join(lines)

    def _preprocess_pcgw_paths(self, text: str) -> str:
        """Converts {{p|...}} or {{P|...}} nested templates before splitting on pipes."""
        def repl(m):
            content = m.group(1)
            if "\\" in content:
                parts = content.split("\\", 1)
            elif "/" in content:
                parts = content.split("/", 1)
            else:
                parts = [content]
            key = parts[0].strip().upper()
            sub = ("\\" + parts[1].strip()) if len(parts) > 1 else ""
            return f"%{key}%{sub}"

        return re.sub(r"\{\{[pP]\|([^}]+)\}\}", repl, text)

    def _extract_download_links(self, raw_text: str) -> List[PCGWDownload]:
        """Extracts valid patch, mod, tool, and fix download links from raw wikitext."""
        downloads: List[PCGWDownload] = []
        matches = re.findall(r"\[(https?://[^\s\]]+)(?:\s+([^\]]+))?\]", raw_text)
        direct_exts = (".zip", ".7z", ".rar", ".tar.gz", ".tar.xz", ".exe", ".msi", ".asi", ".dll", ".patch")

        for url, label in matches:
            url = url.strip()
            label = (label or "").strip()
            label = re.sub(r"'{2,5}", "", label)
            label = re.sub(r"<[^>]+>", "", label).strip()

            url_lower = url.lower()
            lbl_lower = label.lower()

            # Filter out non-download pages, discussion forums, social media, Wikipedia
            if any(bad in url_lower for bad in [
                "reddit.com", "discord.gg", "discord.com", "youtube.com", "twitch.tv",
                "twitter.com", "x.com", "en.wikipedia.org", "eurogamer.net", "steamcommunity.com/app",
                "store.steampowered.com", "refurl"
            ]):
                continue

            if "forum" in url_lower or "thread" in url_lower or "topic:" in url_lower or "steamusers" in url_lower:
                continue

            if "pcgamingwiki.com/wiki/" in url_lower:
                continue

            parsed_path = urllib.parse.urlparse(url).path.lower()
            is_direct = any(parsed_path.endswith(ext) for ext in direct_exts) or "/releases/download/" in url_lower

            source = "Direkt"
            if "github.com" in url_lower:
                source = "GitHub"
                is_direct = True
            elif "nexusmods.com" in url_lower:
                source = "NexusMods"
            elif "moddb.com" in url_lower:
                source = "ModDB"
            elif "pcgamingwiki.com" in url_lower:
                source = "PCGamingWiki"
            elif "archive.org" in url_lower:
                source = "Archive.org"
            elif "mediafire.com" in url_lower:
                source = "MediaFire"
            elif "google.com/drive" in url_lower or "drive.google.com" in url_lower:
                source = "Google Drive"

            is_patch = (
                is_direct or
                any(dom in url_lower for dom in [
                    "nexusmods.com", "moddb.com", "pcgamingwiki.com/files/", "archive.org/details/",
                    "mixmods.com", "gtagarage.com", "gtainside.com", "ntcore.com", "reshade.me", "gamebanana.com"
                ]) or
                any(k in lbl_lower for k in ["patch", "mod", "fix", "download", "installer", "tool", "update", "skip", "loader"])
            )

            if not is_patch:
                continue

            title = label if label and label.lower() not in ["here", "hier", "download", "link", "source", "mod", "this mod"] else ""
            if not title:
                if "github.com" in url_lower:
                    parts = url.rstrip("/").split("/")
                    title = parts[-1] if len(parts) >= 2 else "GitHub Patch"
                elif is_direct and parsed_path:
                    title = os.path.basename(parsed_path)
                else:
                    title = f"{source} Patch"

            if not any(dl.url == url for dl in downloads):
                downloads.append(PCGWDownload(
                    title=title,
                    url=url,
                    source=source,
                    is_direct=is_direct
                ))

        return downloads

    def _parse_wikitext(self, page_title: str, pcgw_url: str, text: str) -> PCGWData:
        data = PCGWData(page_title=page_title, pcgw_url=pcgw_url)

        # 1. Steam AppID
        appid_m = re.search(r"\|\s*steam appid\s*=\s*(\d+)", text, re.IGNORECASE)
        if appid_m:
            data.steam_appid = appid_m.group(1)

        # 2. Extract Save & Config Paths
        for line in text.splitlines():
            line_str = line.strip()
            # Game data/saves
            if "{{Game data/saves|" in line_str:
                preprocessed = self._preprocess_pcgw_paths(line_str)
                m = re.search(r"\{\{Game data/saves\|([^|]+)\|(.+)\}\}", preprocessed)
                if m:
                    os_name = m.group(1).strip().lower()
                    raw_paths = m.group(2).split("|")
                    for rp in raw_paths:
                        cleaned = self._clean_wikitext_path(rp)
                        if cleaned:
                            if "windows" in os_name:
                                if cleaned not in data.save_paths_windows:
                                    data.save_paths_windows.append(cleaned)
                            elif "linux" in os_name or "steam play" in os_name:
                                if cleaned not in data.save_paths_linux:
                                    data.save_paths_linux.append(cleaned)

            # Game data/config
            elif "{{Game data/config|" in line_str:
                preprocessed = self._preprocess_pcgw_paths(line_str)
                m = re.search(r"\{\{Game data/config\|([^|]+)\|(.+)\}\}", preprocessed)
                if m:
                    os_name = m.group(1).strip().lower()
                    raw_paths = m.group(2).split("|")
                    for rp in raw_paths:
                        cleaned = self._clean_wikitext_path(rp)
                        if cleaned:
                            if "windows" in os_name:
                                if cleaned not in data.config_paths_windows:
                                    data.config_paths_windows.append(cleaned)
                            elif "linux" in os_name or "steam play" in os_name:
                                if cleaned not in data.config_paths_linux:
                                    data.config_paths_linux.append(cleaned)

        # 3. Features (Video, Audio, Input, Network)
        def _get_val(key_pattern: str) -> Optional[str]:
            m = re.search(r"\|\s*" + key_pattern + r"\s*=\s*([^|\n]+)", text, re.IGNORECASE)
            if m:
                val = m.group(1).strip()
                val = re.sub(r"\{\{[^}]+\}\}", "", val).strip()
                return val
            return None

        uw = _get_val("ultrawidescreen")
        if uw:
            data.features["Ultrawide"] = uw.capitalize()

        hdr = _get_val("hdr")
        if hdr:
            data.features["HDR"] = hdr.capitalize()

        rt = _get_val("ray tracing")
        if rt:
            data.features["Ray Tracing"] = rt.capitalize()

        ctrl = _get_val("controller support")
        if ctrl:
            data.features["Controller"] = ctrl.capitalize()

        cloud = _get_val("cloud sync")
        if cloud:
            data.features["Cloud Saves"] = self._clean_wikitext_markup(cloud)

        ac = _get_val("anti-cheat")
        if ac:
            data.features["Anti-Cheat"] = self._clean_wikitext_markup(ac)

        fps = _get_val("60 fps") or _get_val("120+ fps")
        if fps:
            data.features["High FPS"] = fps.capitalize()

        d3d = _get_val("direct3d versions") or _get_val("directx versions")
        if d3d:
            data.features["Direct3D"] = d3d

        vk = _get_val("vulkan versions")
        if vk and vk.lower() not in ("false", "no"):
            data.features["Vulkan"] = vk

        gl = _get_val("opengl versions")
        if gl and gl.lower() not in ("false", "no"):
            data.features["OpenGL"] = gl

        # 4. Extract Fixes (Fixbox templates with nested braces)
        idx = 0
        while True:
            pos = text.find("{{Fixbox", idx)
            if pos == -1:
                break

            # Section heading prior to Fixbox
            preceding = text[:pos]
            headers = re.findall(r"={2,5}([^=\n]+)={2,5}", preceding)
            section_title = headers[-1].strip() if headers else "Known Fix"

            # Parse matching closing }} handling nesting
            depth = 0
            end_pos = -1
            i = pos
            while i < len(text) - 1:
                if text[i:i+2] == "{{":
                    depth += 1
                    i += 2
                    continue
                elif text[i:i+2] == "}}":
                    depth -= 1
                    if depth == 0:
                        end_pos = i + 2
                        break
                    i += 2
                    continue
                i += 1

            if end_pos == -1:
                idx = pos + 8
                continue

            block = text[pos+8:end_pos-2]
            idx = end_pos

            fix_content = ""
            desc = ""

            fix_match = re.search(r"\|\s*fix\s*=\s*(.*)", block, re.DOTALL)
            if fix_match:
                fix_content = fix_match.group(1).strip()
                before_fix = block[:fix_match.start()]
                desc_m = re.search(r"\|\s*description\s*=\s*([^|]+)", before_fix)
                if desc_m:
                    desc = desc_m.group(1).strip()
            else:
                desc_m = re.search(r"\|\s*description\s*=\s*(.*)", block, re.DOTALL)
                if desc_m:
                    desc = desc_m.group(1).strip()
                    fix_content = desc

            # Extract download links inside Fixbox
            downloads = self._extract_download_links(block)
            for dl in downloads:
                if not any(existing.url == dl.url for existing in data.downloads):
                    data.downloads.append(dl)

            cleaned_instructions = self._clean_wikitext_markup(fix_content)
            cleaned_desc = self._clean_wikitext_markup(desc)
            cleaned_title = self._clean_wikitext_markup(section_title)

            # Classify fix type
            combined_lower = f"{cleaned_title} {cleaned_desc}".lower()
            fix_type = "general"
            if "intro" in combined_lower or "skip" in combined_lower or "movie" in combined_lower or "logo" in combined_lower:
                fix_type = "intro"
            elif "crash" in combined_lower or "freeze" in combined_lower or "launch" in combined_lower or "start" in combined_lower:
                fix_type = "crash"
            elif "fps" in combined_lower or "performance" in combined_lower or "stutter" in combined_lower or "lag" in combined_lower:
                fix_type = "performance"
            elif "widescreen" in combined_lower or "fov" in combined_lower or "ultrawide" in combined_lower:
                fix_type = "video"

            if cleaned_instructions or cleaned_desc or downloads:
                display_title = cleaned_title if cleaned_title != "Fix" else (cleaned_desc or "Known Fix")
                data.fixes.append(PCGWFix(
                    title=display_title,
                    description=cleaned_desc if cleaned_desc != display_title else "",
                    instructions=cleaned_instructions or cleaned_desc,
                    fix_type=fix_type,
                    downloads=downloads
                ))

        # 4b. Extract Essential improvements & Patches sections that have downloads
        ess_match = re.search(r"==\s*(?:Essential improvements|Patches)\s*==.*?(?=\n==[^=]|\Z)", text, re.DOTALL | re.IGNORECASE)
        if ess_match:
            ess_text = ess_match.group(0)
            sub_sections = re.split(r"\n===\s*([^=\n]+)\s*===", ess_text)
            for k in range(1, len(sub_sections), 2):
                sec_raw_title = sub_sections[k].strip()
                sec_content = sub_sections[k+1].strip() if k + 1 < len(sub_sections) else ""
                sec_dls = self._extract_download_links(sec_raw_title + "\n" + sec_content)
                if not sec_dls:
                    continue

                clean_sec_title = self._clean_wikitext_markup(sec_raw_title)
                # Check if already added
                found_fix = None
                for fx in data.fixes:
                    if clean_sec_title.lower() in fx.title.lower() or fx.title.lower() in clean_sec_title.lower():
                        found_fix = fx
                        break

                if found_fix:
                    for dl in sec_dls:
                        if not any(existing.url == dl.url for existing in found_fix.downloads):
                            found_fix.downloads.append(dl)
                else:
                    clean_instructions = self._clean_wikitext_markup(sec_content)
                    data.fixes.append(PCGWFix(
                        title=clean_sec_title,
                        description="Community Patch / Essential Improvement",
                        instructions=clean_instructions,
                        fix_type="performance" if "patch" in clean_sec_title.lower() else "general",
                        downloads=sec_dls
                    ))

                for dl in sec_dls:
                    if not any(existing.url == dl.url for existing in data.downloads):
                        data.downloads.append(dl)

        # 5. Extract Command Line Arguments
        cmd_args = re.findall(r"\{\{arg\|([^}]+)\}\}", text, re.IGNORECASE)
        for arg in cmd_args:
            arg_clean = arg.strip()
            if arg_clean and arg_clean not in data.command_line_arguments:
                data.command_line_arguments.append(arg_clean)

        return data
