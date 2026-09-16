"""Linux game launch options builder for Steam, Heroic, and Wine."""

from dataclasses import dataclass, field
from typing import List, Dict


@dataclass
class LaunchConfig:
    use_gamemode: bool = True
    use_mangohud: bool = False
    
    # Gamescope
    use_gamescope: bool = False
    gamescope_w: int = 2560
    gamescope_h: int = 1440
    gamescope_r: int = 144
    gamescope_fullscreen: bool = True
    gamescope_upscale: str = ""  # "", "fsr", "nis"

    # Environment variables
    env_vars: Dict[str, str] = field(default_factory=lambda: {
        "PROTON_ENABLE_NVAPI": "0",
        "DXVK_ASYNC": "0",
        "PROTON_NO_ESYNC": "0",
        "PROTON_NO_FSYNC": "0",
        "WINE_FULLSCREEN_FSR": "0",
        "RADV_PERFTEST": "",
    })

    # Custom arguments passed to the game binary
    custom_args: List[str] = field(default_factory=list)


class LaunchOptionBuilder:
    @staticmethod
    def build_command_line(config: LaunchConfig, base_placeholder: str = "%command%") -> str:
        parts: List[str] = []

        # 1. Environment variables
        for k, v in config.env_vars.items():
            if v and v != "0":
                parts.append(f"{k}={v}")

        # 2. Gamescope wrapper
        if config.use_gamescope:
            gs = [f"gamescope -W {config.gamescope_w} -H {config.gamescope_h} -r {config.gamescope_r}"]
            if config.gamescope_fullscreen:
                gs.append("-f")
            if config.gamescope_upscale:
                gs.append(f"-F {config.gamescope_upscale}")
            gs.append("--")
            parts.append(" ".join(gs))

        # 3. GameMode wrapper
        if config.use_gamemode:
            parts.append("gamemoderun")

        # 4. MangoHud wrapper
        if config.use_mangohud:
            parts.append("mangohud")

        # 5. Base command placeholder
        parts.append(base_placeholder)

        # 6. Custom and PCGW arguments
        if config.custom_args:
            parts.append(" ".join(config.custom_args))

        return " ".join(parts)
