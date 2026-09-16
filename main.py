#!/usr/bin/env python3
"""Launcher for Gaming Center."""

import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

if any(arg in sys.argv for arg in ("--download-and-install", "-h", "--help")):
    import argparse
    parser = argparse.ArgumentParser(description="Gaming Center")
    parser.add_argument("--download-and-install", action="store_true", help="Download and install release from GitHub")
    parser.add_argument("--version", default="", help="Target release version")
    parser.add_argument("--asset-url", default="", help="Direct asset URL")
    parser.add_argument("--tarball-url", default="", help="Tarball download URL")
    parser.add_argument("--token", default="", help="GitHub PAT token")
    args, _ = parser.parse_known_args()
    if args.download_and_install:
        from gaming_center.backend.updater import download_and_install_release
        sys.exit(download_and_install_release(args.version, args.asset_url, args.tarball_url, args.token))

from gaming_center.app import main

if __name__ == "__main__":
    main()
