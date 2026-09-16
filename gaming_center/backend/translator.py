"""High-performance translation service for translating PCGW guides to German.

Uses instant local offline dictionary for common gaming fixes,
and fast MyMemory API with extended quota & persistent disk cache for custom guides.
"""

import html
import json
import os
import re
import threading
import urllib.parse
import urllib.request
from typing import Optional, Dict, Tuple
from .pcgw_client import PCGWFix


class Translator:
    COMMON_TERMS: Dict[str, str] = {
        # Titles & Issues
        "Skip intro videos": "Intro-Videos überspringen",
        "Skip intro videos on start-up": "Intro-Videos beim Start überspringen",
        "Skip startup videos": "Startvideos überspringen",
        "Skip loading screen narration videos": "Ladebildschirm-Videos überspringen",
        "Skip REDlauncher on start-up": "REDlauncher beim Start überspringen",
        "Bypass REDlauncher or GOG Galaxy": "REDlauncher oder GOG Galaxy umgehen",
        "Field of view (FOV)": "Sichtfeld (FOV) anpassen",
        "Field of view": "Sichtfeld (FOV)",
        "Widescreen resolution": "Breitbild-Auflösung anpassen",
        "Ultrawide support": "Ultrawide-Unterstützung",
        "Borderless window": "Randloser Fenstermodus",
        "Borderless fullscreen": "Randloses Vollbild",
        "Windowed mode": "Fenstermodus",
        "Disable motion blur": "Bewegungsunschärfe deaktivieren",
        "Disable depth of field": "Tiefenschärfe deaktivieren",
        "Disable film grain": "Filmkorn deaktivieren",
        "Disable chromatic aberration": "Chromatische Aberration deaktivieren",
        "Disable mouse acceleration": "Mausbeschleunigung deaktivieren",
        "Disable mouse smoothing": "Mausglättung deaktivieren",
        "Mouse smoothing": "Mausglättung",
        "High frame rate": "Hohe Bildrate (60+ FPS)",
        "Unlock framerate": "Bildrate freischalten (FPS-Lock aufheben)",
        "Uncap framerate": "Bildrate freischalten",
        "Change in-game cinematic framerate": "Bildrate von Zwischensequenzen anpassen",
        "Fix crash on startup": "Absturz beim Starten beheben",
        "Crash on startup": "Absturz beim Starten",
        "Game crashes on launch": "Spiel stürzt beim Start ab",
        "Audio crackling / stuttering": "Audio-Knistern / Ruckeln beheben",
        "Audio stuttering": "Audio-Stottern beheben",
        "Stuttering fix": "Ruckeln beheben",
        "Microstuttering": "Mikroruckler beheben",
        "Black screen on launch": "Schwarzer Bildschirm beim Start",
        "Controller not detected": "Controller wird nicht erkannt",
        "Controller support": "Controller-Unterstützung",
        "Increase text size": "Textgröße anpassen",
        "Enable developer console": "Entwickler-Konsole aktivieren",
        "Enable console": "Konsole aktivieren",
        "Adjust AMD SMT setting": "AMD SMT-Einstellung anpassen",
        "Use RoboCop intro skip": "RoboCop Intro-Skip verwenden",
        "Use Skip Movies mod": "Skip Movies Mod verwenden",
        "Edit user.settings config file": "Konfigurationsdatei user.settings bearbeiten",
        "Edit user.settings or dx12user.settings config file": "Konfigurationsdatei user.settings oder dx12user.settings bearbeiten",
        "Modify user.settings file": "user.settings Datei anpassen",
        "Modify general.ini file": "general.ini Datei anpassen",
        "Edit Engine.ini config file": "Konfigurationsdatei Engine.ini bearbeiten",
        "Tested on Steam version of the game": "Auf der Steam-Version des Spiels getestet",
    }

    def __init__(self, cache_file: Optional[str] = None):
        self._lock = threading.Lock()
        if cache_file is None:
            cache_dir = os.path.expanduser("~/.cache/gaming-center")
            os.makedirs(cache_dir, exist_ok=True)
            self.cache_file = os.path.join(cache_dir, "translations_de.json")
        else:
            self.cache_file = cache_file

        self.cache: Dict[str, str] = {}
        self._load_cache()

    def _load_cache(self):
        if os.path.isfile(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    with self._lock:
                        self.cache = json.load(f)
            except Exception:
                with self._lock:
                    self.cache = {}

    def _save_cache(self):
        try:
            with self._lock:
                cache_copy = dict(self.cache)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_copy, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _is_code_or_path(self, line: str) -> bool:
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            return True
        if re.match(r"^[A-Za-z0-9_\-.]+\s*=\s*[A-Za-z0-9_\"\'\-./]+$", s):
            return True
        if s.startswith("-") or s.startswith("--"):
            return True
        if s.startswith("%") and s.count("%") >= 2 and len(s) < 80:
            return True
        return False

    def translate_query(self, query: str, src: str = "en", tgt: str = "de") -> str:
        clean_q = query.strip()
        if not clean_q or len(clean_q) < 2:
            return query

        # 1. Check instant offline dictionary
        if clean_q in self.COMMON_TERMS:
            return self.COMMON_TERMS[clean_q]

        # 2. Check local persistent disk cache
        with self._lock:
            if clean_q in self.cache:
                return self.cache[clean_q]

        # 3. Check code or path
        if self._is_code_or_path(clean_q):
            return query

        # 4. Protect INI sections and key=value pairs before translating
        placeholders = {}
        counter = 0

        def repl_sec(m):
            nonlocal counter
            ph = f"XYZSEC{counter}XYZ"
            placeholders[ph] = m.group(0)
            counter += 1
            return ph

        def repl_kv(m):
            nonlocal counter
            ph = f"XYZKV{counter}XYZ"
            placeholders[ph] = m.group(0)
            counter += 1
            return ph

        s_to_translate = re.sub(r"\[[A-Za-z0-9_./\- ]+\]", repl_sec, clean_q)
        s_to_translate = re.sub(r"^[A-Za-z0-9_.\-]+=[A-Za-z0-9_./\- ]+$", repl_kv, s_to_translate, flags=re.MULTILINE)

        # 5. Fast Google Chrome Extension API (instant, 0 rate limit)
        url_google = "https://clients5.google.com/translate_a/t?" + urllib.parse.urlencode({
            "client": "dict-chrome-ex",
            "sl": src,
            "tl": tgt,
            "q": s_to_translate[:3000]
        })
        req = urllib.request.Request(url_google, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
        try:
            with urllib.request.urlopen(req, timeout=4) as resp:
                raw = resp.read().decode("utf-8")
                data = json.loads(raw)
                if isinstance(data, list) and data:
                    res = data[0] if isinstance(data[0], str) else data[0][0]
                    res = html.unescape(res)
                    for ph, orig in placeholders.items():
                        res = res.replace(ph, orig)
                    with self._lock:
                        self.cache[clean_q] = res
                    self._save_cache()
                    return res
        except Exception:
            pass

        # 6. Fallback: MyMemory API with extended quota
        url_mymemory = "https://api.mymemory.translated.net/get?" + urllib.parse.urlencode({
            "q": clean_q[:450],
            "langpair": f"{src}|{tgt}",
            "de": "gaming-center-linux@cachyos.org"
        })
        req_mm = urllib.request.Request(url_mymemory, headers={"User-Agent": "GamingCenter/1.0"})
        try:
            with urllib.request.urlopen(req_mm, timeout=4) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                translated = data.get("responseData", {}).get("translatedText", "")
                if translated and not translated.startswith("MYMEMORY WARNING"):
                    res = html.unescape(translated)
                    for ph, orig in placeholders.items():
                        res = res.replace(ph, orig)
                    with self._lock:
                        self.cache[clean_q] = res
                    self._save_cache()
                    return res
        except Exception:
            pass

        return query

    def translate_text(self, text: str, src: str = "en", tgt: str = "de") -> str:
        if not text:
            return ""

        clean = text.strip()
        with self._lock:
            if clean in self.cache:
                return self.cache[clean]

        # Fast block translation (preserves bullets, lines, formatting in 1 request)
        res = self.translate_query(clean, src=src, tgt=tgt)
        return res if res else text

    def translate_fix_fast(self, fix: PCGWFix) -> Tuple[PCGWFix, bool]:
        """Fast offline lookup using built-in dictionary and disk cache with zero network latency.
        Returns (PCGWFix, is_fully_translated).
        """
        clean_title = fix.title.strip()
        clean_desc = fix.description.strip() if fix.description else ""
        clean_inst = fix.instructions.strip() if fix.instructions else ""

        with self._lock:
            title_de = self.COMMON_TERMS.get(clean_title) or self.cache.get(clean_title) or ""
            desc_de = self.COMMON_TERMS.get(clean_desc) or self.cache.get(clean_desc) or ""
            inst_de = self.cache.get(clean_inst) or ""

        fully_done = bool(
            (not clean_title or title_de) and
            (not clean_desc or desc_de) and
            (not clean_inst or inst_de)
        )

        return PCGWFix(
            title=title_de if title_de else fix.title,
            description=desc_de if desc_de else (fix.description if not clean_inst else ""),
            instructions=inst_de, # empty string means translation pending
            fix_type=fix.fix_type,
            downloads=fix.downloads
        ), fully_done

    def translate_fix(self, fix: PCGWFix) -> PCGWFix:
        clean_title = fix.title.strip()
        clean_desc = fix.description.strip() if fix.description else ""
        clean_inst = fix.instructions.strip() if fix.instructions else ""

        title_de = self.translate_query(clean_title) if clean_title else ""
        desc_de = self.translate_query(clean_desc) if clean_desc else ""
        inst_de = self.translate_text(clean_inst) if clean_inst else ""

        return PCGWFix(
            title=title_de or fix.title,
            description=desc_de or fix.description,
            instructions=inst_de or fix.instructions,
            fix_type=fix.fix_type,
            downloads=fix.downloads
        )

