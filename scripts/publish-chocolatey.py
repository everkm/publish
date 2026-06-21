#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
publish-chocolatey.py

从 everkm/publish Release（或本地 publish-artifacts）读取 windows zip，
打包 everkm-publish.nupkg 并 choco push。

环境变量：
- GH_TOKEN / GITHUB_TOKEN — 读 Release
- CHOCO_API_KEY — push 到 chocolatey.org

用法：
  python3 scripts/publish-chocolatey.py --version 0.17.0
  python3 scripts/publish-chocolatey.py --version 0.17.0 --force

退出码：0 成功，2 跳过，1 失败。
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
NUSPEC_TEMPLATE = REPO_ROOT / "templates" / "chocolatey.nuspec.j2"
PACKAGE_ID = "everkm-publish"
WINDOWS_SUFFIX = "windows-amd64.zip"
EXE_NAME = "everkm-publish.exe"
CHOCO_SOURCE = "https://push.chocolatey.org/"

logger = logging.getLogger("publish-chocolatey")
_pub = None


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(message)s")


def load_publish_module():
    path = Path(__file__).resolve().parent / "publish-npm-package.py"
    spec = importlib.util.spec_from_file_location("publish_npm_package", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get_pub():
    global _pub
    if _pub is None:
        _pub = load_publish_module()
    return _pub


def asset_file_name(version: str) -> str:
    return f"EverkmPublish_{version}_{WINDOWS_SUFFIX}"


def escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def normalize_release_notes(notes: str) -> str:
    cleaned = notes.strip() or f"Release {PACKAGE_ID}"
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", cleaned)
    if len(cleaned) > 4000:
        cleaned = cleaned[:3997] + "..."
    return cleaned


def choco_version_exists(version: str) -> bool:
    url = (
        "https://community.chocolatey.org/api/v2/Packages"
        f"?$filter=Id eq '{PACKAGE_ID}' and Version eq '{version}'"
    )
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return "<entry" in resp.text
    except requests.RequestException as exc:
        logger.warning("[WARN] chocolatey version check failed: %s", exc)
        return False


def ensure_windows_zip(
    version: str,
    work_dir: Path,
    token: str | None,
) -> Path:
    pub = get_pub()
    name = asset_file_name(version)
    local = work_dir / name
    if local.is_file():
        logger.info("[INFO] using cached asset: %s", name)
        return local

    release = pub.fetch_release(
        pub.BINARY_GITHUB_REPO,
        pub.release_tag(version),
        token,
    )
    asset = next(
        (a for a in release.get("assets", []) if a.get("name") == name),
        None,
    )
    if not asset or not asset.get("browser_download_url"):
        raise RuntimeError(f"asset not found in release: {name}")
    logger.info("[INFO] downloading asset: %s", name)
    pub.download_asset(asset["browser_download_url"], local, token)
    return local


def extract_exe(zip_path: Path, dest_exe: Path) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        member = next(
            (n for n in zf.namelist() if n.endswith(EXE_NAME) or n.endswith("everkm-publish.exe")),
            None,
        )
        if not member:
            raise RuntimeError(f"{EXE_NAME} not found in {zip_path.name}")
        dest_exe.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(member) as src, dest_exe.open("wb") as dst:
            shutil.copyfileobj(src, dst)


def render_nuspec(version: str, release_notes: str) -> str:
    template = NUSPEC_TEMPLATE.read_text(encoding="utf-8")
    return template.replace("{{ version }}", version).replace(
        "{{ release_notes }}",
        escape_xml(normalize_release_notes(release_notes)),
    )


def run_choco(args: list[str], *, cwd: Path) -> None:
    if os.name != "nt":
        raise RuntimeError("choco pack/push requires Windows (use windows-latest runner)")
    choco = shutil.which("choco")
    if not choco:
        raise RuntimeError("choco CLI not found in PATH")
    subprocess.run([choco, *args], cwd=str(cwd), check=True)


def publish_chocolatey(version: str, *, force: bool = False) -> int:
    pub = get_pub()
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    api_key = os.environ.get("CHOCO_API_KEY")
    if not api_key:
        raise RuntimeError("CHOCO_API_KEY required for choco push")

    if not force and choco_version_exists(version):
        logger.info("[SKIP] chocolatey package already exists version=%s", version)
        return 2

    release = pub.fetch_release(
        pub.BINARY_GITHUB_REPO,
        pub.release_tag(version),
        token,
    )
    release_notes = release.get("body") or ""

    work_dir = pub.ARTIFACTS_DIR / version
    work_dir.mkdir(parents=True, exist_ok=True)
    zip_path = ensure_windows_zip(version, work_dir, token)

    staging = Path(tempfile.mkdtemp(prefix="choco-everkm-publish-"))
    try:
        tools_dir = staging / "tools"
        tools_dir.mkdir(parents=True, exist_ok=True)
        extract_exe(zip_path, tools_dir / EXE_NAME)

        install_script = REPO_ROOT / "templates" / "chocolateyInstall.ps1"
        shutil.copy2(install_script, tools_dir / "chocolateyInstall.ps1")

        nuspec_path = staging / f"{PACKAGE_ID}.nuspec"
        nuspec_path.write_text(
            render_nuspec(version, release_notes),
            encoding="utf-8",
        )

        run_choco(["pack", nuspec_path.name], cwd=staging)
        nupkg = staging / f"{PACKAGE_ID}.{version}.nupkg"
        if not nupkg.is_file():
            raise RuntimeError(f"nupkg not created: {nupkg.name}")

        push_args = [
            "push",
            nupkg.name,
            "--source",
            CHOCO_SOURCE,
            "--api-key",
            api_key,
        ]
        if force:
            push_args.append("--force")
        run_choco(push_args, cwd=staging)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    logger.info("[INFO] chocolatey package published version=%s", version)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="Semver, e.g. 0.17.0")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force push even if version already exists on chocolatey.org",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    setup_logging(args.verbose)

    try:
        return publish_chocolatey(args.version, force=args.force)
    except Exception:
        logger.exception("[ERROR] failed publishing chocolatey version=%s", args.version)
        return 1


if __name__ == "__main__":
    sys.exit(main())
