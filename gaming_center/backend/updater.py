"""
Update manager and release installer for Gaming Center.

Provides GitHub releases integration, semantic version comparison (via vercmp or fallback),
silent background checks, token-authenticated requests, and 1-click self-updating.
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import List, Optional

from PyQt6.QtCore import QSettings, QThread, pyqtSignal

import gaming_center

DEFAULT_GITHUB_REPO = "lenzi96/gaming-center"


@dataclass
class UpdateInfo:
    app_installed: str = gaming_center.__version__
    app_remote: str = gaming_center.__version__
    app_has_update: bool = False

    github_repo: Optional[str] = None
    github_release_url: Optional[str] = None
    github_tarball_url: Optional[str] = None
    github_asset_api_url: Optional[str] = None
    github_release_notes: Optional[str] = None
    github_auth_error: bool = False
    github_error_message: Optional[str] = None

    check_error: Optional[str] = None
    checked_at: Optional[datetime.datetime] = None


def get_source_root() -> str:
    """Returns root directory of Gaming Center project or package."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_github_repo() -> str:
    """Retrieves configured or git-detected GitHub repository ('owner/repo')."""
    settings = QSettings("GamingCenter", "GamingCenter")
    custom = str(settings.value("updater/github_repo", "")).strip()
    if custom:
        return custom

    source_dir = get_source_root()
    try:
        res = subprocess.run(
            ["git", "-C", source_dir, "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            url = res.stdout.strip()
            m = re.search(r"github\.com[:/]([^/]+)/([^/\.]+)", url)
            if m:
                repo = f"{m.group(1)}/{m.group(2)}"
                return repo[:-4] if repo.endswith(".git") else repo
    except Exception:
        pass
    return DEFAULT_GITHUB_REPO


def set_github_repo(repo_str: str) -> None:
    """Saves configured GitHub repository and updates git remote origin if in git repo."""
    repo_clean = repo_str.strip()
    m = re.search(r"github\.com[:/]([^/]+)/([^/\.]+)", repo_clean)
    if m:
        repo_clean = f"{m.group(1)}/{m.group(2)}"
        if repo_clean.endswith(".git"):
            repo_clean = repo_clean[:-4]

    settings = QSettings("GamingCenter", "GamingCenter")
    settings.setValue("updater/github_repo", repo_clean)

    source_dir = get_source_root()
    if os.path.isdir(os.path.join(source_dir, ".git")) and repo_clean:
        target_url = f"https://github.com/{repo_clean}.git"
        check_rem = subprocess.run(["git", "-C", source_dir, "remote"], capture_output=True, text=True, check=False)
        if "origin" in check_rem.stdout:
            subprocess.run(["git", "-C", source_dir, "remote", "set-url", "origin", target_url], check=False)
        else:
            subprocess.run(["git", "-C", source_dir, "remote", "add", "origin", target_url], check=False)


def get_github_token() -> Optional[str]:
    """Retrieves GitHub personal access token from QSettings, env, or ~/.git-credentials."""
    settings = QSettings("GamingCenter", "GamingCenter")
    token = str(settings.value("updater/github_token", "")).strip()
    if token:
        return token

    env_token = os.environ.get("GITHUB_TOKEN", "").strip() or os.environ.get("GH_TOKEN", "").strip()
    if env_token:
        return env_token

    # Check ~/.git-credentials
    git_cred_path = os.path.expanduser("~/.git-credentials")
    if os.path.exists(git_cred_path):
        try:
            with open(git_cred_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if "github.com" in line:
                        m = re.search(r":([^@:]+)@github\.com", line)
                        if m:
                            tok = m.group(1).strip()
                            if tok.startswith("github_pat_") or tok.startswith("ghp_"):
                                return tok
        except Exception:
            pass

    # Check config file in user config directory
    cfg_token_path = os.path.expanduser("~/.config/gaming-center/token")
    if os.path.exists(cfg_token_path):
        try:
            with open(cfg_token_path, "r", encoding="utf-8") as f:
                t = f.read().strip()
                if t:
                    return t
        except Exception:
            pass

    return None


def set_github_token(token_str: str) -> None:
    """Saves configured GitHub personal access token in QSettings."""
    settings = QSettings("GamingCenter", "GamingCenter")
    settings.setValue("updater/github_token", token_str.strip())


def compare_versions(v1: str, v2: str) -> int:
    """Uses vercmp if available, else standard fallback. Returns -1 if v1 < v2, 0 if equal, 1 if v1 > v2."""
    v1_clean = v1.lstrip("v").strip()
    v2_clean = v2.lstrip("v").strip()

    if shutil.which("vercmp"):
        try:
            res = subprocess.run(
                ["vercmp", v1_clean, v2_clean],
                capture_output=True,
                text=True,
                check=False,
            )
            return int(res.stdout.strip())
        except Exception:
            pass

    parts1 = [int(p) for p in re.findall(r"\d+", v1_clean)]
    parts2 = [int(p) for p in re.findall(r"\d+", v2_clean)]
    # Pad shorter version
    max_len = max(len(parts1), len(parts2))
    parts1.extend([0] * (max_len - len(parts1)))
    parts2.extend([0] * (max_len - len(parts2)))
    return (parts1 > parts2) - (parts1 < parts2)


class UpdateCheckerWorker(QThread):
    finished = pyqtSignal(UpdateInfo)

    def run(self):
        info = UpdateInfo()
        info.app_installed = gaming_center.__version__
        info.checked_at = datetime.datetime.now()

        gh_repo = get_github_repo()
        gh_token = get_github_token()
        info.github_repo = gh_repo

        if not gh_repo:
            info.check_error = "Kein GitHub-Repository hinterlegt."
            self.finished.emit(info)
            return

        try:
            gh_url = f"https://api.github.com/repos/{gh_repo}/releases/latest"
            headers = {
                "User-Agent": f"gaming-center/{info.app_installed}",
                "Accept": "application/vnd.github+json",
            }
            if gh_token:
                headers["Authorization"] = f"Bearer {gh_token}"

            req = urllib.request.Request(gh_url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode())
                    tag = data.get("tag_name", "").lstrip("v").strip()
                    if tag:
                        info.app_remote = tag
                        info.github_release_url = data.get("html_url", "")
                        info.github_release_notes = data.get("body", "")
                        for asset in data.get("assets", []):
                            name = asset.get("name", "")
                            if name.endswith((".tar.gz", ".zip")):
                                info.github_tarball_url = asset.get("browser_download_url", "")
                                info.github_asset_api_url = asset.get("url", "")
                                break

                        # If no explicit asset tarball, GitHub provides the source tarball
                        if not info.github_tarball_url:
                            info.github_tarball_url = data.get("tarball_url", "")

                        cmp_res = compare_versions(info.app_installed, info.app_remote)
                        info.app_has_update = cmp_res < 0

        except urllib.error.HTTPError as err:
            if err.code in (401, 403, 404):
                info.github_auth_error = True
                if not gh_token:
                    info.github_error_message = (
                        "Repository ist privat oder nicht gefunden. Bitte GitHub-Token hinterlegen oder Repo auf 'Public' stellen."
                    )
                else:
                    info.github_error_message = f"GitHub-Fehler {err.code}: Token ungültig oder unzureichende Rechte."
            else:
                info.github_error_message = f"GitHub HTTP-Fehler {err.code}"
            info.check_error = info.github_error_message
        except Exception as err:
            info.github_error_message = f"Netzwerkfehler: {str(err)}"
            info.check_error = info.github_error_message

        self.finished.emit(info)


@dataclass
class UpdateStep:
    name: str
    command: List[str]
    description: str


class BatchUpdateWorker(QThread):
    step_started = pyqtSignal(int, int, str)       # current_idx, total_steps, title
    output_line = pyqtSignal(str)                  # streamed line
    all_completed = pyqtSignal(bool, str)          # success, summary

    def __init__(self, steps: List[UpdateStep]):
        super().__init__()
        self.steps = steps
        self.process: Optional[subprocess.Popen] = None
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=1)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass

    def run(self):
        total = len(self.steps)
        if total == 0:
            self.all_completed.emit(True, "Keine anstehenden Updates.")
            return

        all_success = True
        failed_steps = []

        for idx, step in enumerate(self.steps, start=1):
            if self._is_cancelled:
                self.output_line.emit("\n[!] Vorgang durch Benutzer abgebrochen.")
                self.all_completed.emit(False, "Aktualisierung abgebrochen.")
                return

            self.step_started.emit(idx, total, step.name)
            self.output_line.emit(f"\n=======================================================")
            self.output_line.emit(f"[{idx}/{total}] {step.name}")
            self.output_line.emit(f"Befehl: {' '.join(step.command)}")
            self.output_line.emit(f"=======================================================\n")

            env = os.environ.copy()
            source_root = get_source_root()
            if "PYTHONPATH" in env and env["PYTHONPATH"]:
                env["PYTHONPATH"] = f"{source_root}:{env['PYTHONPATH']}"
            else:
                env["PYTHONPATH"] = source_root

            try:
                self.process = subprocess.Popen(
                    step.command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                    env=env,
                )

                if self.process.stdout:
                    for line in iter(self.process.stdout.readline, ""):
                        if self._is_cancelled:
                            break
                        self.output_line.emit(line.rstrip())

                self.process.wait()
                ret = self.process.returncode if self.process else 1

                if ret != 0:
                    all_success = False
                    failed_steps.append(step.name)
                    self.output_line.emit(f"\n[✗] Schritt '{step.name}' mit Statuscode {ret} beendet.")
                else:
                    self.output_line.emit(f"\n[✓] Schritt '{step.name}' erfolgreich abgeschlossen.")

            except Exception as exc:
                all_success = False
                failed_steps.append(step.name)
                self.output_line.emit(f"\n[✗] Fehler bei '{step.name}': {exc}")

        if all_success:
            summary = "Gaming Center wurde erfolgreich aktualisiert."
        else:
            summary = f"Einige Schritte schlugen fehl: {', '.join(failed_steps)}"

        self.all_completed.emit(all_success, summary)


def download_and_install_release(
    version: str = "",
    asset_url: str = "",
    tarball_url: str = "",
    token: str = "",
) -> int:
    """
    Downloads GitHub release tarball, extracts it to /tmp, and executes install.sh.
    Supports both public repositories and private repositories with token authentication.
    """
    repo = get_github_repo() or DEFAULT_GITHUB_REPO
    token = token.strip() if token else (get_github_token() or "")

    # Always fetch latest live asset url directly from GitHub API when token is present or URLs missing
    if token or not (asset_url or tarball_url):
        try:
            tag_slug = (
                f"tags/v{version}"
                if version and not version.startswith("v")
                else (f"tags/{version}" if version else "latest")
            )
            api_rel = f"https://api.github.com/repos/{repo}/releases/{tag_slug}"
            headers = {
                "User-Agent": "gaming-center",
                "Accept": "application/vnd.github+json",
            }
            if token:
                headers["Authorization"] = f"Bearer {token}"

            req = urllib.request.Request(api_rel, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                version = data.get("tag_name", "").lstrip("v").strip() or version
                for asset in data.get("assets", []):
                    if asset.get("name", "").endswith((".tar.gz", ".zip")):
                        asset_url = asset.get("url", "")
                        tarball_url = asset.get("browser_download_url", "")
                        break
                if not tarball_url:
                    tarball_url = data.get("tarball_url", "")
        except Exception as e:
            if not (asset_url or tarball_url):
                print(f"[FEHLER] Konnte Release-Informationen von GitHub nicht abrufen: {e}")
                return 1

    print("=======================================================")
    print("  Gaming Center - Automatischer Release-Updater        ")
    print("=======================================================")
    print(f"Ziel-Version : v{version if version else 'latest'}")
    print(f"Repository   : {repo}")
    print(f"Token aktiv  : {'Ja' if token else 'Nein (Öffentliches Repo)'}")
    print("-------------------------------------------------------")

    tmp_dir = tempfile.mkdtemp(prefix="gaming_center_update_")
    tar_path = os.path.join(tmp_dir, f"gaming-center-v{version}.tar.gz")
    unpack_dir = os.path.join(tmp_dir, "unpacked")

    try:
        download_url = asset_url if (token and asset_url) else tarball_url
        if not download_url:
            download_url = f"https://github.com/{repo}/releases/download/v{version}/gaming-center-v{version}.tar.gz"

        print("[1/4] Lade Release-Paket herunter...")
        curl_bin = shutil.which("curl")
        download_ok = False

        if curl_bin:
            curl_cmd = [curl_bin, "-sSL", "-f"]
            if token:
                curl_cmd.extend(["-H", f"Authorization: Bearer {token}"])
            curl_cmd.extend(["-H", "Accept: application/octet-stream", download_url, "-o", tar_path])
            res = subprocess.run(curl_cmd, check=False)
            if res.returncode == 0 and os.path.exists(tar_path) and os.path.getsize(tar_path) > 1000:
                download_ok = True

        if not download_ok:
            class NoAuthRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    new_req = super().redirect_request(req, fp, code, msg, headers, newurl)
                    if new_req and "Authorization" in new_req.headers:
                        del new_req.headers["Authorization"]
                    return new_req

            opener = urllib.request.build_opener(NoAuthRedirect)
            headers = {"User-Agent": "Gaming-Center"}
            if token and "api.github.com" in download_url:
                headers["Authorization"] = f"Bearer {token}"
                headers["Accept"] = "application/octet-stream"
            req = urllib.request.Request(download_url, headers=headers)
            try:
                with opener.open(req, timeout=30) as resp, open(tar_path, "wb") as out_f:
                    shutil.copyfileobj(resp, out_f)
                if os.path.exists(tar_path) and os.path.getsize(tar_path) > 1000:
                    download_ok = True
            except Exception as e:
                print(f"[Hinweis] urllib Download: {e}")

        if not download_ok:
            print("[FEHLER] Herunterladen des Release-Archivs fehlgeschlagen.")
            print("Hinweis: Falls das Repository privat ist, stelle sicher, dass ein gültiges Token hinterlegt ist.")
            return 1

        size_mb = os.path.getsize(tar_path) / (1024 * 1024)
        print(f"✓ Download erfolgreich ({size_mb:.2f} MB)")

        print("[2/4] Entpacke Archiv...")
        os.makedirs(unpack_dir, exist_ok=True)
        res_tar = subprocess.run(["tar", "-xzf", tar_path, "-C", unpack_dir], check=False)
        if res_tar.returncode != 0:
            print("[FEHLER] Archiv konnte nicht entpackt werden.")
            return 1
        print("✓ Entpacken abgeschlossen.")

        # Find install.sh inside unpacked folder
        installer_path = None
        for root, dirs, files in os.walk(unpack_dir):
            if "install.sh" in files:
                installer_path = os.path.join(root, "install.sh")
                break

        if not installer_path:
            print("[FEHLER] install.sh im entpackten Release-Archiv nicht gefunden.")
            return 1

        print(f"[3/4] Führe Installation aus ({installer_path})...")
        os.chmod(installer_path, 0o755)
        res_inst = subprocess.run(["bash", installer_path], check=False)
        if res_inst.returncode != 0:
            print(f"[FEHLER] Installation schlug fehl mit Exit-Code {res_inst.returncode}")
            return res_inst.returncode

        print("[4/4] Bereinige temporäre Dateien...")
        print(f"✓ Gaming Center wurde erfolgreich auf v{version} aktualisiert!")
        return 0

    finally:
        try:
            shutil.rmtree(tmp_dir)
        except Exception:
            pass


if __name__ == "__main__":
    if any(arg in sys.argv for arg in ("--download-and-install", "-h", "--help")):
        import argparse

        parser = argparse.ArgumentParser(description="Gaming Center Release Installer")
        parser.add_argument("--download-and-install", action="store_true")
        parser.add_argument("--version", default="")
        parser.add_argument("--asset-url", default="")
        parser.add_argument("--tarball-url", default="")
        parser.add_argument("--token", default="")
        args, _ = parser.parse_known_args()
        if args.download_and_install:
            sys.exit(
                download_and_install_release(args.version, args.asset_url, args.tarball_url, args.token)
            )
