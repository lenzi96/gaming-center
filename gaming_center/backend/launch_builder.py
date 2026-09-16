"""
Linux game launch options builder and tuning profile manager for Gaming Center.

Provides comprehensive support for:
- Performance wrappers (GameMode, MangoHud, Prime-Run, Priority, Core-Pinning)
- Gamescope micro-compositor (Resolution, FSR/NIS scaling, Framerate limiter, HDR)
- Proton / Wine runtime optimizations (NVAPI, DLSS, FSync/ESync, Wine-FSR, Large Address Aware)
- Vulkan / DXVK / VKD3D drivers (DXVK Async, DXR Raytracing, RADV GPL, Audio latency)
- Preset profiles (Max Performance, NVIDIA RTX, AMD Radeon, Gamescope FSR, Retro, Debug)
- Persistent JSON profiles per game (saved in ~/.config/gaming-center/profiles/)
"""
import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class LaunchConfig:
    preset: str = "custom"

    # Performance Wrappers
    use_gamemode: bool = True
    use_mangohud: bool = False
    use_prime_run: bool = False
    use_high_priority: bool = False  # nice -n -10
    cpu_pinning: str = ""             # taskset -c ...

    # Gamescope Compositor
    use_gamescope: bool = False
    gamescope_output_w: int = 2560    # -W
    gamescope_output_h: int = 1440    # -H
    gamescope_render_w: int = 1920    # -w
    gamescope_render_h: int = 1080    # -h
    gamescope_r: int = 144            # -r
    gamescope_mode: str = "fullscreen"  # "fullscreen" (-f), "borderless" (-b), "windowed"
    gamescope_upscale: str = ""       # "", "fsr", "nis", "pixel", "linear"
    gamescope_sharpness: int = 5      # --fsr-sharpness 0-20
    gamescope_hdr: bool = False       # --hdr-enabled

    # Proton / Wine Environment Variables
    env_vars: Dict[str, str] = field(
        default_factory=lambda: {
            "PROTON_ENABLE_NVAPI": "0",
            "PROTON_HIDE_NVIDIA_GPU": "0",
            "PROTON_NO_ESYNC": "0",
            "PROTON_NO_FSYNC": "0",
            "PROTON_ENABLE_WAYLAND": "0",
            "WINE_FULLSCREEN_FSR": "0",
            "WINE_FULLSCREEN_FSR_STRENGTH": "2",
            "PROTON_FORCE_LARGE_ADDRESS_AWARE": "0",
            "PROTON_USE_WINED3D": "0",
            "PROTON_LOG": "0",
            # Vulkan, DXVK, VKD3D & Audio
            "DXVK_ASYNC": "0",
            "DXVK_HUD": "",
            "VKD3D_CONFIG": "",
            "VKD3D_FEATURE_LEVEL": "",
            "RADV_PERFTEST": "",
            "PULSE_LATENCY_MSEC": "",
        }
    )

    # Custom / Wiki arguments passed to the game binary
    custom_args: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LaunchConfig":
        cfg = cls()
        for k, v in data.items():
            if hasattr(cfg, k):
                if k == "env_vars" and isinstance(v, dict):
                    cfg.env_vars.update(v)
                else:
                    setattr(cfg, k, v)
        return cfg


PRESET_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "balanced": {
        "name": "⚡ Standard (Ausgewogen)",
        "description": "Standardeinstellungen mit aktivem GameMode für flüssiges Gaming.",
        "use_gamemode": True,
        "use_mangohud": False,
        "use_prime_run": False,
        "use_high_priority": False,
        "use_gamescope": False,
        "env_vars": {
            "PROTON_ENABLE_NVAPI": "0",
            "PROTON_HIDE_NVIDIA_GPU": "0",
            "PROTON_NO_ESYNC": "0",
            "PROTON_NO_FSYNC": "0",
            "PROTON_ENABLE_WAYLAND": "0",
            "WINE_FULLSCREEN_FSR": "0",
            "PROTON_FORCE_LARGE_ADDRESS_AWARE": "0",
            "PROTON_USE_WINED3D": "0",
            "PROTON_LOG": "0",
            "DXVK_ASYNC": "0",
            "DXVK_HUD": "",
            "VKD3D_CONFIG": "",
            "RADV_PERFTEST": "",
            "PULSE_LATENCY_MSEC": "",
        },
    },
    "max_performance": {
        "name": "🚀 Maximale Performance",
        "description": "GameMode + FSync + asynchrone DXVK Shader-Kompilierung und erhöhte Prozesspriorität.",
        "use_gamemode": True,
        "use_mangohud": False,
        "use_prime_run": False,
        "use_high_priority": True,
        "use_gamescope": False,
        "env_vars": {
            "DXVK_ASYNC": "1",
            "PROTON_NO_ESYNC": "0",
            "PROTON_NO_FSYNC": "0",
            "RADV_PERFTEST": "gpl",
        },
    },
    "nvidia_rtx": {
        "name": "🟢 NVIDIA RTX & DLSS",
        "description": "Schaltet NVAPI für DLSS frei, aktiviert DirectX 12 Raytracing (VKD3D DXR).",
        "use_gamemode": True,
        "use_mangohud": False,
        "use_prime_run": False,
        "use_high_priority": False,
        "use_gamescope": False,
        "env_vars": {
            "PROTON_ENABLE_NVAPI": "1",
            "VKD3D_CONFIG": "dxr11,dxr",
            "PROTON_HIDE_NVIDIA_GPU": "0",
            "DXVK_ASYNC": "1",
        },
    },
    "amd_radeon": {
        "name": "🔴 AMD Radeon Optimiert",
        "description": "Aktiviert RADV GPL (Graphics Pipeline Library) und Wine-FSR Upscaling.",
        "use_gamemode": True,
        "use_mangohud": False,
        "use_prime_run": False,
        "use_high_priority": False,
        "use_gamescope": False,
        "env_vars": {
            "RADV_PERFTEST": "gpl",
            "WINE_FULLSCREEN_FSR": "1",
            "WINE_FULLSCREEN_FSR_STRENGTH": "2",
            "DXVK_ASYNC": "1",
        },
    },
    "gamescope_fsr": {
        "name": "📺 Gamescope FSR Upscaler",
        "description": "Rendert in 1080p und skaliert via Gamescope FSR scharf auf 1440p / 4K Vollbild.",
        "use_gamemode": True,
        "use_mangohud": False,
        "use_gamescope": True,
        "gamescope_output_w": 2560,
        "gamescope_output_h": 1440,
        "gamescope_render_w": 1920,
        "gamescope_render_h": 1080,
        "gamescope_r": 144,
        "gamescope_mode": "fullscreen",
        "gamescope_upscale": "fsr",
        "gamescope_sharpness": 5,
        "env_vars": {
            "DXVK_ASYNC": "1",
        },
    },
    "handheld_battery": {
        "name": "🔋 Akkusparend / Handheld (60 FPS)",
        "description": "Gamescope mit 60 FPS Limiter, 720p Renderauflösung und FSR Upscale.",
        "use_gamemode": True,
        "use_mangohud": True,
        "use_gamescope": True,
        "gamescope_output_w": 1920,
        "gamescope_output_h": 1080,
        "gamescope_render_w": 1280,
        "gamescope_render_h": 720,
        "gamescope_r": 60,
        "gamescope_mode": "fullscreen",
        "gamescope_upscale": "fsr",
        "gamescope_sharpness": 6,
        "env_vars": {
            "DXVK_ASYNC": "1",
        },
    },
    "retro_compat": {
        "name": "🕹️ Retro & 32-Bit Kompatibilität",
        "description": "Large Address Aware (4 GB RAM), WineD3D OpenGL Fallback und deaktiviertes ESync für alte Spiele.",
        "use_gamemode": False,
        "use_mangohud": False,
        "use_gamescope": False,
        "env_vars": {
            "PROTON_FORCE_LARGE_ADDRESS_AWARE": "1",
            "PROTON_USE_WINED3D": "1",
            "PROTON_NO_ESYNC": "1",
            "PROTON_NO_FSYNC": "1",
        },
    },
    "debug_crash": {
        "name": "🔍 Absturz-Diagnose & Logging",
        "description": "Erstellt ein ausführliches Proton-Log unter ~/steam-<appid>.log und blendet das DXVK/MangoHud-Overlay ein.",
        "use_gamemode": False,
        "use_mangohud": True,
        "use_gamescope": False,
        "env_vars": {
            "PROTON_LOG": "1",
            "DXVK_HUD": "fps,frametimes,devinfo",
        },
    },
}


class LaunchOptionBuilder:
    @staticmethod
    def apply_preset(config: LaunchConfig, preset_key: str) -> LaunchConfig:
        """Applies a preset dictionary to the given configuration."""
        if preset_key not in PRESET_DEFINITIONS:
            return config

        preset = PRESET_DEFINITIONS[preset_key]
        config.preset = preset_key

        for k, v in preset.items():
            if k == "name" or k == "description":
                continue
            if k == "env_vars" and isinstance(v, dict):
                # Reset all to 0/empty first if applying balanced
                if preset_key == "balanced":
                    for ek in config.env_vars:
                        config.env_vars[ek] = "0" if ek.startswith("PROTON_") or ek == "DXVK_ASYNC" or ek == "WINE_FULLSCREEN_FSR" else ""
                config.env_vars.update(v)
            elif hasattr(config, k):
                setattr(config, k, v)

        return config

    @staticmethod
    def build_command_line(config: LaunchConfig, base_placeholder: str = "%command%") -> str:
        """Constructs the complete Linux shell command line string."""
        parts: List[str] = []

        # 1. Environment variables
        for k, v in config.env_vars.items():
            if v and v != "0":
                parts.append(f"{k}={v}")

        # 2. Priority & Core-Pinning wrappers
        if config.use_high_priority:
            parts.append("nice -n -10")

        if config.cpu_pinning.strip():
            parts.append(f"taskset -c {config.cpu_pinning.strip()}")

        # 3. Prime-run (Hybrid GPU) wrapper
        if config.use_prime_run:
            parts.append("prime-run")

        # 4. Gamescope micro-compositor
        if config.use_gamescope:
            gs = ["gamescope"]
            if config.gamescope_output_w and config.gamescope_output_h:
                gs.append(f"-W {config.gamescope_output_w} -H {config.gamescope_output_h}")
            if config.gamescope_render_w and config.gamescope_render_h:
                gs.append(f"-w {config.gamescope_render_w} -h {config.gamescope_render_h}")
            if config.gamescope_r:
                gs.append(f"-r {config.gamescope_r}")
            if config.gamescope_mode == "fullscreen":
                gs.append("-f")
            elif config.gamescope_mode == "borderless":
                gs.append("-b")
            if config.gamescope_upscale:
                gs.append(f"-F {config.gamescope_upscale}")
                if config.gamescope_upscale == "fsr" and config.gamescope_sharpness:
                    gs.append(f"--fsr-sharpness {config.gamescope_sharpness}")
            if config.gamescope_hdr:
                gs.append("--hdr-enabled")
            gs.append("--")
            parts.append(" ".join(gs))

        # 5. GameMode wrapper
        if config.use_gamemode:
            parts.append("gamemoderun")

        # 6. MangoHud wrapper
        if config.use_mangohud:
            parts.append("mangohud")

        # 7. Base command placeholder (%command% in Steam)
        parts.append(base_placeholder)

        # 8. Custom arguments / Wiki flags passed to the game binary
        if config.custom_args:
            clean_args = " ".join(arg.strip() for arg in config.custom_args if arg.strip())
            if clean_args:
                parts.append(clean_args)

        return " ".join(parts)

    @staticmethod
    def get_profiles_dir() -> Path:
        p = Path.home() / ".config" / "gaming-center" / "profiles"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @classmethod
    def save_profile(cls, app_id: str, config: LaunchConfig) -> None:
        """Saves a game's launch configuration to disk."""
        if not app_id:
            return
        target = cls.get_profiles_dir() / f"{app_id}.json"
        try:
            with open(target, "w", encoding="utf-8") as f:
                json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    @classmethod
    def load_profile(cls, app_id: str) -> LaunchConfig:
        """Loads a game's launch configuration from disk or returns default."""
        if not app_id:
            return LaunchConfig()
        target = cls.get_profiles_dir() / f"{app_id}.json"
        if target.exists():
            try:
                with open(target, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return LaunchConfig.from_dict(data)
            except Exception:
                pass
        return LaunchConfig()

    @staticmethod
    def launch_game(game_info: Any, config: LaunchConfig) -> Tuple[bool, str]:
        """
        Launches the game directly from Gaming Center.
        For Steam games, uses steam steam://rungameid/<id> or starts directly.
        """
        try:
            platform = getattr(game_info, "platform", "steam")
            app_id = getattr(game_info, "app_id", "")
            executable = getattr(game_info, "executable", "")
            install_dir = getattr(game_info, "install_dir", "")

            if platform == "steam" and app_id:
                # Steam URL launch
                cmd = ["steam", f"steam://rungameid/{app_id}"]
                subprocess.Popen(cmd, start_new_session=True)
                return True, f"Steam-Spiel {game_info.name} wird über Steam gestartet..."

            elif platform == "heroic" and app_id:
                cmd = ["heroic", "--launch-game", app_id]
                subprocess.Popen(cmd, start_new_session=True)
                return True, f"Heroic-Spiel {game_info.name} wird gestartet..."

            elif executable and os.path.exists(executable):
                # Build custom wrapper execution
                full_cmd_str = LaunchOptionBuilder.build_command_line(config, base_placeholder=f'"{executable}"')
                subprocess.Popen(full_cmd_str, shell=True, cwd=install_dir or None, start_new_session=True)
                return True, f"{game_info.name} wird direkt ausgeführt..."

            return False, "Keine passende Startmethode oder ausführbare Datei gefunden."
        except Exception as e:
            return False, f"Fehler beim Starten des Spiels: {str(e)}"
