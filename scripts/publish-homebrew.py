#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
publish-homebrew.py

从 everkm/publish Release（或本地 publish-artifacts）读取 darwin/linux zip，
生成 Formula 并 push 到 everkm/homebrew-tap。

环境变量：
- GH_TOKEN / GITHUB_TOKEN — 读 Release、push homebrew-tap

用法：
  python3 scripts/publish-homebrew.py --version 0.17.0
  python3 scripts/publish-homebrew.py --version 0.17.0 --force

退出码：0 成功，2 跳过，1 失败。
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FORMULA_TEMPLATE = REPO_ROOT / "templates" / "homebrew-formula.rb.j2"
HOMEBREW_TAP_REPO = "everkm/homebrew-tap"
DARWIN_SUFFIX = "darwin-universal.zip"
LINUX_SUFFIX = "linux-amd64.zip"

logger = logging.getLogger("publish-homebrew")
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


def asset_file_name(version: str, suffix: str) -> str:
    return f"EverkmPublish_{version}_{suffix}"


def release_asset_url(version: str, asset_name: str) -> str:
    pub = get_pub()
    return (
        f"https://github.com/{pub.BINARY_GITHUB_REPO}/releases/download/"
        f"everkm-publish%40v{version}/{asset_name}"
    )


def render_formula(
    version: str,
    darwin_url: str,
    darwin_sha256: str,
    linux_url: str,
    linux_sha256: str,
) -> str:
    template = FORMULA_TEMPLATE.read_text(encoding="utf-8")
    return (
        template.replace("{{ version }}", version)
        .replace("{{ darwin_url }}", darwin_url)
        .replace("{{ darwin_sha256 }}", darwin_sha256)
        .replace("{{ linux_url }}", linux_url)
        .replace("{{ linux_sha256 }}", linux_sha256)
    )


def ensure_zip_local(
    version: str,
    suffix: str,
    work_dir: Path,
    token: str | None,
) -> tuple[Path, str]:
    pub = get_pub()
    name = asset_file_name(version, suffix)
    local = work_dir / name
    if local.is_file():
        logger.info("[INFO] using cached asset: %s", name)
        return local, pub.file_sha256(local)

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
    return local, pub.file_sha256(local)


def formula_has_version(formula_path: Path, version: str) -> bool:
    if not formula_path.is_file():
        return False
    return f'version "{version}"' in formula_path.read_text(encoding="utf-8")


def publish_homebrew(version: str, *, force: bool = False) -> int:
    pub = get_pub()
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GH_TOKEN / GITHUB_TOKEN required")

    work_dir = pub.ARTIFACTS_DIR / version
    work_dir.mkdir(parents=True, exist_ok=True)

    darwin_name = asset_file_name(version, DARWIN_SUFFIX)
    linux_name = asset_file_name(version, LINUX_SUFFIX)

    _, darwin_sha = ensure_zip_local(version, DARWIN_SUFFIX, work_dir, token)
    _, linux_sha = ensure_zip_local(version, LINUX_SUFFIX, work_dir, token)

    formula = render_formula(
        version,
        release_asset_url(version, darwin_name),
        darwin_sha,
        release_asset_url(version, linux_name),
        linux_sha,
    )

    tmp = Path(tempfile.mkdtemp(prefix="homebrew-tap-"))
    try:
        clone_url = f"https://x-access-token:{token}@github.com/{HOMEBREW_TAP_REPO}.git"
        subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, str(tmp)],
            check=True,
            capture_output=True,
            text=True,
        )

        formula_dir = tmp / "Formula"
        formula_dir.mkdir(exist_ok=True)
        formula_path = formula_dir / "everkm-publish.rb"

        if not force and formula_has_version(formula_path, version):
            logger.info("[SKIP] formula already at version=%s", version)
            return 2

        formula_path.write_text(formula, encoding="utf-8")

        subprocess.run(
            ["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"],
            cwd=tmp,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "github-actions[bot]"],
            cwd=tmp,
            check=True,
        )
        subprocess.run(["git", "add", "Formula/everkm-publish.rb"], cwd=tmp, check=True)

        diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=tmp)
        if diff.returncode == 0:
            logger.info("[SKIP] no formula changes version=%s", version)
            return 2

        subprocess.run(
            ["git", "commit", "-m", f"everkm-publish {version}"],
            cwd=tmp,
            check=True,
        )
        subprocess.run(["git", "push", "origin", "HEAD"], cwd=tmp, check=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    logger.info("[INFO] homebrew formula published version=%s", version)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="Semver, e.g. 0.17.0")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force update even if formula version already exists",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    setup_logging(args.verbose)

    try:
        return publish_homebrew(args.version, force=args.force)
    except Exception:
        logger.exception("[ERROR] failed publishing homebrew version=%s", args.version)
        return 1


if __name__ == "__main__":
    sys.exit(main())
