"""
Intelligent Game Optimizer for Gaming Center.

Analyzes system hardware (GPU, CPU, Steam Deck, installed tools) and game metadata
(PCGamingWiki fixes, 32-bit heuristics, engine characteristics) to automatically
generate and persist optimal launch configurations.
"""

import json
import mmap
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
from .launcher_writer import LauncherWriter


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
class GraphicsApiInfo:
    layer: str = "unknown"             # "vkd3d", "dxvk", "hybrid", "vulkan", "opengl", "unknown"
    directx_versions: List[str] = field(default_factory=list)  # ["12"], ["11"], ["9", "11"], etc.
    label: str = "Unbekannt"           # "VKD3D (DirectX 12)", "DXVK (DirectX 11)", etc.
    badge_text: str = "API: Auto"      # "VKD3D (DX12)", "DXVK (DX11)", "Vulkan", etc.
    color: str = "#94a3b8"             # violet for VKD3D, cyan for DXVK, emerald for Vulkan
    detection_source: str = ""         # "Steam Shadercache", "Spiele-Dateien", "PCGamingWiki"

    @property
    def is_dx12(self) -> bool:
        return self.layer in ("vkd3d", "hybrid") or "12" in self.directx_versions

    @property
    def is_dxvk(self) -> bool:
        return self.layer in ("dxvk", "hybrid") or any(v in ("9", "10", "11") for v in self.directx_versions)


@dataclass
class OptimizationResult:
    app_id: str
    game_name: str
    preset_used: str
    config: LaunchConfig
    api_info: GraphicsApiInfo = field(default_factory=GraphicsApiInfo)
    applied_tweaks: List[str] = field(default_factory=list)
    summary: str = ""
    game: Optional[GameInfo] = None


class GameOptimizer:
    _cached_hw: Optional[SystemHardwareInfo] = None
    _cached_api: Dict[str, GraphicsApiInfo] = {}

    @classmethod
    def detect_graphics_api(
        cls,
        game: GameInfo,
        pcgw_data: Optional[PCGWData] = None,
        force_refresh: bool = False,
    ) -> GraphicsApiInfo:
        """
        Detects whether a game uses VKD3D (DirectX 12), DXVK (DirectX 9/10/11),
        Hybrid (both), or Vulkan Native.
        Uses a high-performance multi-tier inspection:
        1. In-memory cache lookup
        2. Steam Shadercache inspection (all Steam library locations)
        3. Passed or locally cached PCGamingWiki metadata
        4. Targeted binary/DLL and Agility SDK inspection (mmap + PE search)
        5. Wine/Proton prefix logs and config overrides
        6. Engine & retro heuristics
        """
        cache_key = f"{game.app_id}_{game.install_dir}"
        if not force_refresh and pcgw_data is None and cache_key in cls._cached_api:
            return cls._cached_api[cache_key]

        api_info: Optional[GraphicsApiInfo] = None

        # 1. Check Steam Shadercache (Highest confidence for already-run games)
        if game.app_id:
            possible_sc_dirs = [
                Path.home() / ".local/share/Steam/steamapps/shadercache" / game.app_id,
                Path.home() / ".steam/steam/steamapps/shadercache" / game.app_id,
                Path.home() / ".steam/root/steamapps/shadercache" / game.app_id,
            ]
            if game.install_dir:
                try:
                    p = Path(game.install_dir)
                    for parent in p.parents:
                        if parent.name == "common" and parent.parent.name == "steamapps":
                            sc_cand = parent.parent / "shadercache" / game.app_id
                            if sc_cand not in possible_sc_dirs:
                                possible_sc_dirs.append(sc_cand)
                            break
                except Exception:
                    pass

            for sc in possible_sc_dirs:
                if sc.is_dir():
                    try:
                        vkd3d_dir = sc / "VKD3D_shader_cache"
                        has_vkd3d = vkd3d_dir.is_dir() and any(f.is_file() and f.stat().st_size > 0 for f in vkd3d_dir.iterdir())
                        dxvk_dir = sc / "DXVK_state_cache"
                        has_dxvk = dxvk_dir.is_dir() and any(f.is_file() and f.stat().st_size > 0 for f in dxvk_dir.iterdir())

                        if has_vkd3d and has_dxvk:
                            api_info = GraphicsApiInfo(
                                layer="hybrid",
                                directx_versions=["11", "12"],
                                label="Hybrid (DX11 DXVK & DX12 VKD3D)",
                                badge_text="DX11/DX12 Hybrid",
                                color="#f59e0b",
                                detection_source="Steam Shadercache",
                            )
                            break
                        elif has_vkd3d:
                            api_info = GraphicsApiInfo(
                                layer="vkd3d",
                                directx_versions=["12"],
                                label="VKD3D (DirectX 12)",
                                badge_text="VKD3D (DX12)",
                                color="#a855f7",
                                detection_source="Steam VKD3D Shadercache",
                            )
                            break
                        elif has_dxvk:
                            api_info = GraphicsApiInfo(
                                layer="dxvk",
                                directx_versions=["11"],
                                label="DXVK (DirectX 9-11)",
                                badge_text="DXVK (DX11)",
                                color="#38bdf8",
                                detection_source="Steam DXVK Shadercache",
                            )
                            break
                    except Exception:
                        pass

        # 2. Check PCGamingWiki Data (Passed object or local JSON cache)
        if not api_info:
            d3d_ver: Optional[str] = None
            vk_ver: Optional[str] = None
            if pcgw_data and getattr(pcgw_data, "features", None):
                d3d_ver = pcgw_data.features.get("Direct3D")
                vk_ver = pcgw_data.features.get("Vulkan")
            else:
                # Fast check of local PCGW disk cache (~0.5ms)
                cache_dir = os.path.expanduser("~/.cache/gaming-center/pcgw")
                if os.path.isdir(cache_dir):
                    try:
                        for fname in os.listdir(cache_dir):
                            if fname.endswith(".json"):
                                fpath = os.path.join(cache_dir, fname)
                                try:
                                    with open(fpath, "r", encoding="utf-8") as fp:
                                        cdata = json.load(fp)
                                        if (game.app_id and cdata.get("steam_appid") == game.app_id) or cdata.get("page_title", "").lower() == game.name.lower():
                                            feats = cdata.get("features", {})
                                            d3d_ver = feats.get("Direct3D")
                                            vk_ver = feats.get("Vulkan")
                                            break
                                except Exception:
                                    pass
                    except Exception:
                        pass

            if d3d_ver:
                has_12 = "12" in d3d_ver
                has_9_11 = any(v in d3d_ver for v in ("9", "10", "11"))
                if has_12 and has_9_11:
                    api_info = GraphicsApiInfo(
                        layer="hybrid",
                        directx_versions=["11", "12"],
                        label="Hybrid (DX11 DXVK & DX12 VKD3D)",
                        badge_text="DX11/DX12 Hybrid",
                        color="#f59e0b",
                        detection_source="PCGamingWiki",
                    )
                elif has_12:
                    api_info = GraphicsApiInfo(
                        layer="vkd3d",
                        directx_versions=["12"],
                        label="VKD3D (DirectX 12)",
                        badge_text="VKD3D (DX12)",
                        color="#a855f7",
                        detection_source="PCGamingWiki (D3D12)",
                    )
                elif "9" in d3d_ver:
                    api_info = GraphicsApiInfo(
                        layer="dxvk",
                        directx_versions=["9"],
                        label="DXVK (DirectX 9)",
                        badge_text="DXVK (DX9)",
                        color="#06b6d4",
                        detection_source="PCGamingWiki (D3D9)",
                    )
                else:
                    api_info = GraphicsApiInfo(
                        layer="dxvk",
                        directx_versions=["11"],
                        label="DXVK (DirectX 11)",
                        badge_text="DXVK (DX11)",
                        color="#38bdf8",
                        detection_source="PCGamingWiki (D3D11)",
                    )
            elif vk_ver and vk_ver.lower() not in ("false", "no"):
                api_info = GraphicsApiInfo(
                    layer="vulkan",
                    directx_versions=[],
                    label="Vulkan Native",
                    badge_text="Vulkan Native",
                    color="#10b981",
                    detection_source="PCGamingWiki (Vulkan)",
                )

        # 3. Targeted Game Directory & Executable Inspection
        if not api_info and game.install_dir and os.path.isdir(game.install_dir):
            cand_names = {"bin", "bin64", "bin32", "bin_ship", "binaries", "win64", "win32", "x64", "x86", "retailclient", "game"}
            cand_dirs = [game.install_dir]
            try:
                for entry in os.scandir(game.install_dir):
                    if entry.is_dir():
                        en = entry.name.lower()
                        if en in cand_names:
                            cand_dirs.append(entry.path)
                        try:
                            for sub in os.scandir(entry.path):
                                if sub.is_dir():
                                    sn = sub.name.lower()
                                    if sn in cand_names:
                                        cand_dirs.append(sub.path)
                                    try:
                                        for sub2 in os.scandir(sub.path):
                                            if sub2.is_dir() and sub2.name.lower() in cand_names:
                                                cand_dirs.append(sub2.path)
                                    except Exception:
                                        pass
                        except Exception:
                            pass
            except Exception:
                pass

            has_agility = False
            has_fg = False
            has_dxvk_cache = False
            has_vulkan_file = False
            has_ue5 = False
            exe_candidates: List[Tuple[int, str]] = []

            for d in cand_dirs:
                if os.path.isdir(d):
                    try:
                        for f in os.listdir(d):
                            fl = f.lower()
                            if fl in ("d3d12core.dll", "d3d12sdklayers.dll"):
                                has_agility = True
                            elif fl in ("amd_fidelityfx_dx12.dll", "ffx_backend_dx12_x64.dll", "nvngx_dlssg.dll", "sl.dlss_g.dll"):
                                has_fg = True
                            elif fl.endswith(".dxvk-cache"):
                                has_dxvk_cache = True
                            elif fl in ("vulkan-1.dll", "libvulkan.so"):
                                has_vulkan_file = True
                            elif fl == "psoversion.txt" or "ue5" in fl:
                                has_ue5 = True

                            if fl.endswith(".exe") and not any(x in fl for x in ("crash", "report", "unins", "setup", "redist", "prereq", "installer", "update", "vcredist", "dxsetup", "cef", "epicwebhelper")):
                                p = os.path.join(d, f)
                                try:
                                    sz = os.path.getsize(p)
                                    if sz > 100_000:
                                        exe_candidates.append((sz, p))
                                except Exception:
                                    pass
                    except Exception:
                        pass

            # Agility SDK or Frame Generation DLLs are 100% DirectX 12
            if has_agility or has_fg:
                api_info = GraphicsApiInfo(
                    layer="vkd3d",
                    directx_versions=["12"],
                    label="VKD3D (DirectX 12)",
                    badge_text="VKD3D (DX12)",
                    color="#a855f7",
                    detection_source="Spiele-Dateien (Agility/FG)",
                )

            # Inspect primary game binary using fast memory-mapping
            if not api_info and exe_candidates:
                exe_candidates.sort(key=lambda x: x[0], reverse=True)
                d3d12_root = False
                d3d12_dev = False
                d3d11_dev = False
                d3d9_dev = False
                vk_dev = False

                for sz, p in exe_candidates[:2]:
                    try:
                        with open(p, "rb") as fp:
                            with mmap.mmap(fp.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                                if mm.find(b"D3D12SDKVersion") != -1 or mm.find(b"D3D12SerializeRootSignature") != -1:
                                    d3d12_root = True
                                if mm.find(b"D3D12CreateDevice") != -1:
                                    d3d12_dev = True
                                if mm.find(b"D3D11CreateDevice") != -1:
                                    d3d11_dev = True
                                if mm.find(b"Direct3DCreate9") != -1:
                                    d3d9_dev = True
                                if mm.find(b"vkCreateInstance") != -1:
                                    vk_dev = True
                    except Exception:
                        pass

                if d3d12_root:
                    api_info = GraphicsApiInfo(
                        layer="vkd3d",
                        directx_versions=["12"],
                        label="VKD3D (DirectX 12)",
                        badge_text="VKD3D (DX12)",
                        color="#a855f7",
                        detection_source="Spiele-Executable (Agility SDK)",
                    )
                elif d3d12_dev and (d3d11_dev or d3d9_dev):
                    if has_ue5:
                        api_info = GraphicsApiInfo(
                            layer="vkd3d",
                            directx_versions=["12"],
                            label="VKD3D (DirectX 12)",
                            badge_text="VKD3D (DX12)",
                            color="#a855f7",
                            detection_source="Spiele-Dateien (UE5 Engine)",
                        )
                    else:
                        api_info = GraphicsApiInfo(
                            layer="hybrid",
                            directx_versions=["11", "12"],
                            label="Hybrid (DX11 DXVK & DX12 VKD3D)",
                            badge_text="DX11/DX12 Hybrid",
                            color="#f59e0b",
                            detection_source="Spiele-Executable (D3D11/12)",
                        )
                elif d3d12_dev:
                    api_info = GraphicsApiInfo(
                        layer="vkd3d",
                        directx_versions=["12"],
                        label="VKD3D (DirectX 12)",
                        badge_text="VKD3D (DX12)",
                        color="#a855f7",
                        detection_source="Spiele-Executable (D3D12)",
                    )
                elif d3d11_dev:
                    api_info = GraphicsApiInfo(
                        layer="dxvk",
                        directx_versions=["11"],
                        label="DXVK (DirectX 11)",
                        badge_text="DXVK (DX11)",
                        color="#38bdf8",
                        detection_source="Spiele-Executable (D3D11)",
                    )
                elif d3d9_dev:
                    api_info = GraphicsApiInfo(
                        layer="dxvk",
                        directx_versions=["9"],
                        label="DXVK (DirectX 9)",
                        badge_text="DXVK (DX9)",
                        color="#06b6d4",
                        detection_source="Spiele-Executable (D3D9)",
                    )
                elif vk_dev or has_vulkan_file:
                    api_info = GraphicsApiInfo(
                        layer="vulkan",
                        directx_versions=[],
                        label="Vulkan Native",
                        badge_text="Vulkan Native",
                        color="#10b981",
                        detection_source="Spiele-Executable (Vulkan)",
                    )

            if not api_info and has_dxvk_cache:
                api_info = GraphicsApiInfo(
                    layer="dxvk",
                    directx_versions=["11"],
                    label="DXVK (DirectX 11)",
                    badge_text="DXVK (DX11)",
                    color="#38bdf8",
                    detection_source="Spiele-Dateien (.dxvk-cache)",
                )

        # 4. Check Proton Prefix Runtime Logs if available
        if not api_info:
            prefix_paths = []
            if getattr(game, "prefix_dir", None):
                prefix_paths.append(Path(game.prefix_dir))
            if game.app_id:
                prefix_paths.extend([
                    Path.home() / f".local/share/Steam/steamapps/compatdata/{game.app_id}/pfx",
                    Path.home() / f".steam/steam/steamapps/compatdata/{game.app_id}/pfx",
                ])
                if game.install_dir:
                    try:
                        p = Path(game.install_dir)
                        for parent in p.parents:
                            if parent.name == "common" and parent.parent.name == "steamapps":
                                prefix_paths.append(parent.parent / "compatdata" / game.app_id / "pfx")
                                break
                    except Exception:
                        pass

            for pfx in prefix_paths:
                if pfx.is_dir():
                    try:
                        d12_log = pfx / "d3d12.log"
                        d11_log = pfx / "d3d11.log"
                        if d12_log.is_file() and d12_log.stat().st_size > 0:
                            api_info = GraphicsApiInfo("vkd3d", ["12"], "VKD3D (DirectX 12)", "VKD3D (DX12)", "#a855f7", "Proton Prefix (d3d12.log)")
                            break
                        elif d11_log.is_file() and d11_log.stat().st_size > 0:
                            api_info = GraphicsApiInfo("dxvk", ["11"], "DXVK (DirectX 11)", "DXVK (DX11)", "#38bdf8", "Proton Prefix (d3d11.log)")
                            break
                    except Exception:
                        pass

        # 5. Fallback heuristics: Retro -> DX9, Modern -> DXVK DX11
        if not api_info:
            if cls._is_likely_retro_game(game):
                api_info = GraphicsApiInfo(
                    layer="dxvk",
                    directx_versions=["9"],
                    label="DXVK (DirectX 9 / Retro)",
                    badge_text="DXVK (DX9)",
                    color="#06b6d4",
                    detection_source="Retro-Erkennung",
                )
            else:
                api_info = GraphicsApiInfo(
                    layer="dxvk",
                    directx_versions=["11"],
                    label="DXVK (DirectX 11 / Standard)",
                    badge_text="DXVK (DX11)",
                    color="#38bdf8",
                    detection_source="Standard-Erkennung",
                )

        cls._cached_api[cache_key] = api_info
        return api_info

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
        force_refresh: bool = False,
    ) -> OptimizationResult:
        """
        Creates an optimized LaunchConfig for the specified game and saves it to disk.
        """
        if hw is None:
            hw = cls.detect_hardware(force_refresh=force_refresh)

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

        # 2. Graphics API (DXVK vs VKD3D) & GPU-Specific Optimization
        api_info = cls.detect_graphics_api(game, pcgw_data, force_refresh=force_refresh)

        if hw.is_steam_deck or mode == "handheld":
            config.preset = "handheld_battery"
            LaunchOptionBuilder.apply_preset(config, "handheld_battery")
            applied_tweaks.append("🔋 Handheld-Preset: 60 FPS Cap + Gamescope 720p/FSR")

        elif api_info.layer == "vkd3d":
            applied_tweaks.append(f"🟣 Grafik-API erkannt: {api_info.label} ({api_info.detection_source})")
            if hw.gpu_vendor == "nvidia":
                config.preset = "nvidia_rtx"
                LaunchOptionBuilder.apply_preset(config, "nvidia_rtx")
                config.env_vars["PROTON_ENABLE_NVAPI"] = "1"
                applied_tweaks.append("🟢 NVIDIA RTX: DLSS & Reflex aktiviert (PROTON_ENABLE_NVAPI=1)")
            elif hw.gpu_vendor == "amd":
                config.preset = "amd_radeon"
                LaunchOptionBuilder.apply_preset(config, "amd_radeon")
                config.env_vars["RADV_PERFTEST"] = "gpl"
                applied_tweaks.append("🔴 AMD RADV: GPL Pipeline-Compiler für DX12 aktiv (RADV_PERFTEST=gpl)")
            else:
                config.preset = "max_performance" if mode == "performance" else "balanced"
                LaunchOptionBuilder.apply_preset(config, config.preset)

            config.env_vars["VKD3D_CONFIG"] = "dxr11,dxr"
            config.env_vars["DXVK_ASYNC"] = "0"
            config.env_vars["WINE_FULLSCREEN_FSR"] = "0"
            applied_tweaks.append("🎮 VKD3D DirectX 12 DXR freigeschaltet (VKD3D_CONFIG=dxr11,dxr)")

        elif api_info.layer == "dxvk":
            applied_tweaks.append(f"🔷 Grafik-API erkannt: {api_info.label} ({api_info.detection_source})")
            if hw.gpu_vendor == "amd":
                config.preset = "amd_radeon"
                LaunchOptionBuilder.apply_preset(config, "amd_radeon")
                config.env_vars["RADV_PERFTEST"] = "gpl"
                config.env_vars["WINE_FULLSCREEN_FSR"] = "1"
                config.env_vars["WINE_FULLSCREEN_FSR_STRENGTH"] = "2"
                applied_tweaks.append("🔴 AMD RADV: GPL Shader Pipeline aktiv (RADV_PERFTEST=gpl)")
                applied_tweaks.append("✨ Wine-FSR Skalierung vorbereitet (WINE_FULLSCREEN_FSR=1)")
            elif hw.gpu_vendor == "nvidia":
                config.preset = "nvidia_rtx"
                LaunchOptionBuilder.apply_preset(config, "nvidia_rtx")
                config.env_vars["PROTON_ENABLE_NVAPI"] = "1"
                applied_tweaks.append("🟢 NVIDIA RTX: DLSS & Reflex aktiviert (PROTON_ENABLE_NVAPI=1)")
            else:
                config.preset = "max_performance" if mode == "performance" else "balanced"
                LaunchOptionBuilder.apply_preset(config, config.preset)

            config.env_vars["DXVK_ASYNC"] = "1"
            config.env_vars["VKD3D_CONFIG"] = ""
            applied_tweaks.append("⚡ DXVK Async Shader-Kompilierung aktiviert (DXVK_ASYNC=1)")

        elif api_info.layer == "hybrid":
            applied_tweaks.append(f"🔶 Grafik-API erkannt: {api_info.label} ({api_info.detection_source})")
            if hw.gpu_vendor == "amd":
                config.preset = "amd_radeon"
                LaunchOptionBuilder.apply_preset(config, "amd_radeon")
                config.env_vars["RADV_PERFTEST"] = "gpl"
                config.env_vars["WINE_FULLSCREEN_FSR"] = "1"
                config.env_vars["WINE_FULLSCREEN_FSR_STRENGTH"] = "2"
            elif hw.gpu_vendor == "nvidia":
                config.preset = "nvidia_rtx"
                LaunchOptionBuilder.apply_preset(config, "nvidia_rtx")
                config.env_vars["PROTON_ENABLE_NVAPI"] = "1"
            else:
                config.preset = "max_performance" if mode == "performance" else "balanced"
                LaunchOptionBuilder.apply_preset(config, config.preset)

            config.env_vars["DXVK_ASYNC"] = "1"
            config.env_vars["VKD3D_CONFIG"] = "dxr11,dxr"
            applied_tweaks.append("⚡ DXVK Async & VKD3D DXR aktiviert für Hybrid DX11/DX12")

        elif api_info.layer == "vulkan":
            applied_tweaks.append(f"🟢 Grafik-API erkannt: {api_info.label} (Native Vulkan-Engine)")
            config.preset = "max_performance" if mode == "performance" else "balanced"
            LaunchOptionBuilder.apply_preset(config, config.preset)
            config.env_vars["DXVK_ASYNC"] = "0"
            config.env_vars["VKD3D_CONFIG"] = ""
            config.env_vars["WINE_FULLSCREEN_FSR"] = "0"

        else:
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

        summary = f"{len(applied_tweaks)} Optimierungen für {game.name} ({api_info.label}) angewendet."
        return OptimizationResult(
            app_id=game.app_id,
            game_name=game.name,
            preset_used=config.preset,
            config=config,
            api_info=api_info,
            applied_tweaks=applied_tweaks,
            summary=summary,
            game=game,
        )

    @classmethod
    def optimize_batch(
        cls,
        games: List[GameInfo],
        pcgw_client: Optional[PCGWClient] = None,
        mode: str = "performance",
        progress_cb: Optional[Callable[[int, int, str], None]] = None,
        apply_to_launcher: bool = False,
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
                if apply_to_launcher:
                    try:
                        cmd_line = LaunchOptionBuilder.build_command_line(res.config, base_placeholder="%command%")
                        ok, msg = LauncherWriter.write_launch_options(game, cmd_line)
                        if ok:
                            res.applied_tweaks.append("📥 Startoptionen direkt in Launcher übertragen")
                    except Exception:
                        pass
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
