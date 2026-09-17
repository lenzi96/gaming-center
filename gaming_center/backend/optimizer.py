"""
Intelligent Game Optimizer for Gaming Center.

Analyzes system hardware (GPU, CPU, Steam Deck, installed tools) and game metadata
(PCGamingWiki fixes, 32-bit heuristics, engine characteristics) to automatically
generate and persist optimal launch configurations.
"""

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .game_scanner import GameInfo
from .launch_builder import LaunchConfig, LaunchOptionBuilder
from .pcgw_client import PCGWClient, PCGWData


@dataclass
class SystemHardwareInfo:
    gpu_vendor: str = "unknown"  # "amd", "nvidia", "intel", "unknown"
    gpu_name: str = "Unbekannte GPU"
    cpu_name: str = "Unbekannte CPU"
    cpu_threads: int = 4
    has_gamemode: bool = False
    has_mangohud: bool = False
    has_gamescope: bool = False
    has_primerun: bool = False
    is_steam_deck: bool = False
    screen_res: str = "1920x1080"
    screen_hz: int = 60

    @property
    def vendor_display(self) -> str:
        if self.gpu_vendor == "amd":
            return "AMD Radeon"
        elif self.gpu_vendor == "nvidia":
            return "NVIDIA GeForce"
        elif self.gpu_vendor == "intel":
            return "Intel Arc / Xe"
        return "Standard / Generisch"


@dataclass
class OptimizationResult:
    app_id: str
    game_name: str
    preset_used: str
    config: LaunchConfig
    applied_tweaks: List[str] = field(default_factory=list)
    summary: str = ""


class GameOptimizer:
    _cached_hw: Optional[SystemHardwareInfo] = None

    @classmethod
    def detect_hardware(cls, force_refresh: bool = False) -> SystemHardwareInfo:
        """Detects system hardware, GPU, CPU, display and available Linux gaming tools."""
        if cls._cached_hw is not None and not force_refresh:
            return cls._cached_hw

        hw = SystemHardwareInfo()

        # 1. CPU detection
        try:
            with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "model name" in line:
                        hw.cpu_name = line.split(":", 1)[1].strip()
                        break
        except Exception:
            pass

        hw.cpu_threads = os.cpu_count() or 4

        # 2. GPU detection
        gpu_detected = False
        # Try /sys/class/drm
        drm_path = Path("/sys/class/drm")
        if drm_path.exists():
            for card in drm_path.glob("card[0-9]/device"):
                vendor_file = card / "vendor"
                if vendor_file.exists():
                    try:
                        v_id = vendor_file.read_text().strip().lower()
                        if "0x1002" in v_id:
                            hw.gpu_vendor = "amd"
                            gpu_detected = True
                        elif "0x10de" in v_id:
                            hw.gpu_vendor = "nvidia"
                            gpu_detected = True
                        elif "0x8086" in v_id:
                            hw.gpu_vendor = "intel"
                            gpu_detected = True
                    except Exception:
                        pass

        # Try lspci for exact GPU name
        try:
            out = subprocess.check_output(["lspci"], text=True, stderr=subprocess.DEVNULL)
            for line in out.splitlines():
                if any(x in line for x in ["VGA compatible controller", "3D controller", "Display controller"]):
                    parts = line.split(":", 2)
                    if len(parts) >= 3:
                        name = parts[2].strip()
                        hw.gpu_name = name
                        name_low = name.lower()
                        if not gpu_detected:
                            if "amd" in name_low or "radeon" in name_low or "advanced micro" in name_low:
                                hw.gpu_vendor = "amd"
                                gpu_detected = True
                            elif "nvidia" in name_low or "geforce" in name_low:
                                hw.gpu_vendor = "nvidia"
                                gpu_detected = True
                            elif "intel" in name_low or "arc" in name_low:
                                hw.gpu_vendor = "intel"
                                gpu_detected = True
                        # If we found discrete GPU, prioritize it over integrated
                        if "nvidia" in name_low or "radeon" in name_low:
                            break
        except Exception:
            pass

        # 3. Available Gaming Tools
        hw.has_gamemode = shutil.which("gamemoderun") is not None
        hw.has_mangohud = shutil.which("mangohud") is not None
        hw.has_gamescope = shutil.which("gamescope") is not None
        hw.has_primerun = shutil.which("prime-run") is not None

        # 4. Steam Deck detection
        try:
            prod_name = Path("/sys/devices/virtual/dmi/id/product_name")
            if prod_name.exists():
                text = prod_name.read_text().strip().lower()
                if "jupiter" in text or "galileo" in text or "steam deck" in text:
                    hw.is_steam_deck = True
        except Exception:
            pass
        if os.environ.get("SteamDeck") == "1":
            hw.is_steam_deck = True

        # 5. Display Resolution fallback
        try:
            xrandr_out = subprocess.check_output(["xrandr", "--current"], text=True, stderr=subprocess.DEVNULL)
            for line in xrandr_out.splitlines():
                if " connected" in line and "primary" in line:
                    match = re.search(r"(\d{3,4})x(\d{3,4})\+(\d+)\+(\d+)", line)
                    if match:
                        hw.screen_res = f"{match.group(1)}x{match.group(2)}"
                    break
        except Exception:
            pass

        cls._cached_hw = hw
        return hw

    @classmethod
    def optimize_game(
        cls,
        game: GameInfo,
        pcgw_data: Optional[PCGWData] = None,
        hw: Optional[SystemHardwareInfo] = None,
        mode: str = "performance",  # "performance", "balanced", "handheld"
    ) -> OptimizationResult:
        """
        Creates an optimized LaunchConfig for the specified game and saves it to disk.
        """
        if hw is None:
            hw = cls.detect_hardware()

        applied_tweaks: List[str] = []
        config = LaunchConfig()

        # 1. Performance Wrappers
        if hw.has_gamemode:
            config.use_gamemode = True
            applied_tweaks.append("⚡ GameMode aktiv (gamemoderun)")
        else:
            config.use_gamemode = False

        if mode == "performance" and hw.cpu_threads >= 8:
            config.use_high_priority = True
            applied_tweaks.append("🚀 Erhöhte CPU-Priorität (nice -n -10)")
        else:
            config.use_high_priority = False

        if hw.has_primerun and hw.gpu_vendor == "nvidia":
            config.use_prime_run = True
            applied_tweaks.append("🔋 Prime-Run aktiv (Dedizierte NVIDIA GPU)")

        # 2. GPU & Graphics Engine Optimization
        if hw.is_steam_deck or mode == "handheld":
            config.preset = "handheld_battery"
            LaunchOptionBuilder.apply_preset(config, "handheld_battery")
            applied_tweaks.append("🔋 Handheld-Preset: 60 FPS Cap + Gamescope 720p/FSR")

        elif hw.gpu_vendor == "nvidia":
            config.preset = "nvidia_rtx"
            LaunchOptionBuilder.apply_preset(config, "nvidia_rtx")
            config.env_vars["PROTON_ENABLE_NVAPI"] = "1"
            config.env_vars["VKD3D_CONFIG"] = "dxr11,dxr"
            config.env_vars["DXVK_ASYNC"] = "1"
            applied_tweaks.append("🟢 NVIDIA RTX: DLSS & Reflex aktiviert (PROTON_ENABLE_NVAPI=1)")
            applied_tweaks.append("🎮 DirectX 12 Raytracing freigeschaltet (VKD3D_CONFIG=dxr11,dxr)")
            applied_tweaks.append("⚡ DXVK Async Shader-Kompilierung aktiv (DXVK_ASYNC=1)")

        elif hw.gpu_vendor == "amd":
            config.preset = "amd_radeon"
            LaunchOptionBuilder.apply_preset(config, "amd_radeon")
            config.env_vars["RADV_PERFTEST"] = "gpl"
            config.env_vars["DXVK_ASYNC"] = "1"
            config.env_vars["WINE_FULLSCREEN_FSR"] = "1"
            config.env_vars["WINE_FULLSCREEN_FSR_STRENGTH"] = "2"
            applied_tweaks.append("🔴 AMD Radeon: RADV GPL Shader Pipeline aktiv (RADV_PERFTEST=gpl)")
            applied_tweaks.append("⚡ DXVK Async Shader-Kompilierung aktiv (DXVK_ASYNC=1)")
            applied_tweaks.append("✨ Wine-FSR Skalierung vorbereitet (WINE_FULLSCREEN_FSR=1)")

        else:
            # Intel / Standard
            config.preset = "max_performance" if mode == "performance" else "balanced"
            LaunchOptionBuilder.apply_preset(config, config.preset)
            config.env_vars["DXVK_ASYNC"] = "1"
            applied_tweaks.append("⚡ DXVK Async Shader-Kompilierung aktiv (DXVK_ASYNC=1)")

        # 3. Retro / 32-Bit Heuristics
        is_retro = cls._is_likely_retro_game(game)
        if is_retro:
            config.env_vars["PROTON_FORCE_LARGE_ADDRESS_AWARE"] = "1"
            applied_tweaks.append("🕹️ 32-Bit Schutz: Large Address Aware (4 GB RAM) aktiviert")

        # 4. PCGamingWiki Argumente & Fixes
        if pcgw_data:
            try:
                wiki_args = cls._extract_useful_launch_args(pcgw_data)
                for arg in wiki_args:
                    if arg not in config.custom_args:
                        config.custom_args.append(arg)
                        applied_tweaks.append(f"💡 Wiki-Parameter hinzugefügt: {arg}")
            except Exception as e:
                pass

        # If user has Gamescope installed and screen is high res, configure gamescope resolution
        if hw.has_gamescope and hw.screen_res:
            try:
                w, h = map(int, hw.screen_res.split("x"))
                if w >= 2560 and h >= 1440:
                    config.gamescope_output_w = w
                    config.gamescope_output_h = h
                    config.gamescope_render_w = 1920 if w >= 2560 else w
                    config.gamescope_render_h = 1080 if h >= 1440 else h
            except Exception:
                pass

        # 5. Persist profile to disk
        if game.app_id:
            try:
                LaunchOptionBuilder.save_profile(game.app_id, config)
            except Exception:
                pass

        summary = f"{len(applied_tweaks)} Optimierungen für {game.name} angewendet."
        return OptimizationResult(
            app_id=game.app_id,
            game_name=game.name,
            preset_used=config.preset,
            config=config,
            applied_tweaks=applied_tweaks,
            summary=summary,
        )

    @classmethod
    def optimize_batch(
        cls,
        games: List[GameInfo],
        pcgw_client: Optional[PCGWClient] = None,
        mode: str = "performance",
        progress_cb: Optional[Callable[[int, int, str], None]] = None,
    ) -> List[OptimizationResult]:
        """Optimizes multiple games in batch."""
        hw = cls.detect_hardware()
        results: List[OptimizationResult] = []
        total = len(games)

        for idx, game in enumerate(games):
            if progress_cb:
                try:
                    progress_cb(idx + 1, total, game.name)
                except Exception:
                    pass

            pcgw_data = None
            if pcgw_client:
                try:
                    search_res = pcgw_client.search_game(game.name)
                    if search_res:
                        pcgw_data = pcgw_client.fetch_game_data(search_res[0][0])
                except Exception:
                    pass

            try:
                res = cls.optimize_game(game, pcgw_data=pcgw_data, hw=hw, mode=mode)
                results.append(res)
            except Exception as e:
                import traceback
                traceback.print_exc()

        return results

    @staticmethod
    def _is_likely_retro_game(game: GameInfo) -> bool:
        """Heuristic to detect older / 32-bit titles requiring Large Address Aware."""
        name_lower = game.name.lower()
        classic_keywords = [
            "gothic", "fallout 3", "new vegas", "oblivion", "morrowind",
            "stalker", "s.t.a.l.k.e.r.", "half-life 2", "portal",
            "mass effect", "dragon age", "witcher: enhanced", "san andreas",
            "vice city", "fable", "kotor", "star wars", "bioshock",
            "crysis", "deus ex", "dawn of war", "titan quest",
        ]
        if any(kw in name_lower for kw in classic_keywords):
            return True

        # Check install directory for x86 / 32-bit executables
        if game.install_dir and os.path.isdir(game.install_dir):
            try:
                for root, _, files in os.walk(game.install_dir):
                    for f in files:
                        fl = f.lower()
                        if fl.endswith(".exe") and any(x in fl for x in ["_x86", "_32", "win32", "x86"]):
                            return True
                    # Limit depth to avoid slow scans
                    if root.count(os.sep) - game.install_dir.count(os.sep) >= 2:
                        break
            except Exception:
                pass

        return False

    @staticmethod
    def _extract_useful_launch_args(pcgw_data: PCGWData) -> List[str]:
        """Extracts common recommended launch arguments from PCGW fixes and arguments."""
        if not pcgw_data:
            return []

        candidates = ["-novid", "-skipintro", "-nointro", "--launcher-skip", "-dx11", "-vulkan"]
        found: List[str] = []

        # Check explicit command line arguments if available
        if getattr(pcgw_data, "command_line_arguments", None):
            for arg in pcgw_data.command_line_arguments:
                arg_strip = arg.strip()
                if any(cand == arg_strip.lower() for cand in candidates):
                    if arg_strip not in found:
                        found.append(arg_strip)

        all_text_parts = []
        if getattr(pcgw_data, "fixes", None):
            for fix in pcgw_data.fixes:
                title = getattr(fix, "title", "") or ""
                desc = getattr(fix, "description", "") or ""
                instr = getattr(fix, "instructions", "") or ""
                all_text_parts.append(f"{title} {desc} {instr}")

        all_text = " ".join(all_text_parts).lower()
        for cand in candidates:
            if cand in all_text and cand not in found:
                found.append(cand)

        return found
