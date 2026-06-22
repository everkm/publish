#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
publish-npm-package.py

从 everkm/publish GitHub Release 拉取全部资产，镜像至 R2 / 七牛（pkgs/{ver}/），
生成 pkgs/latest.json 与 pkgs/{ver}/meta.json（含上游 Release notes），
上传 install.sh（Linux / macOS）与 install.ps1（Windows）。

环境变量：
- GH_TOKEN / GITHUB_TOKEN — 读 everkm/publish Release
- CF_S3_AK / CF_S3_SK — Cloudflare R2
- QINIU_ACCESS_KEY / QINIU_SECRET_KEY — 七牛上传 + cdnrefresh
- R2_ENDPOINT（可选）

用法：
  python3 scripts/publish-npm-package.py --version 0.16.15
  python3 scripts/publish-npm-package.py --version 0.16.15 --skip-cdn
  python3 scripts/publish-npm-package.py --version 0.16.15 --force-cdn

退出码：0 成功（workflow 继续 npm publish），2 跳过 npm，1 失败。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import mimetypes
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import boto3
import qiniu.config
import requests
from botocore.exceptions import ClientError
from qiniu import Auth, put_file_v2

qiniu.config.set_default(connection_timeout=120, connection_retries=5)

QINIU_RETRYABLE_STATUS = frozenset({502, 503, 504, 573, 579, 599})

CDN_COM = "https://ekmp-assets.everkm.com"
CDN_CN = "https://ekmp-assets.everkm.cn"
R2_BUCKET = "ekmp-assets"
R2_ENDPOINT = os.environ.get(
    "R2_ENDPOINT",
    "https://0348638eaf8921e9cbdad2df98ea51f2.r2.cloudflarestorage.com",
)
BINARY_GITHUB_REPO = "everkm/publish"
NPM_PACKAGE_NAME = "everkm-publish"

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = REPO_ROOT / "publish-artifacts"
INSTALL_SH = REPO_ROOT / "scripts" / "install.sh"
INSTALL_PS1 = REPO_ROOT / "scripts" / "install.ps1"

logger = logging.getLogger("publish-npm-package")


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(message)s")


def release_tag(version: str) -> str:
    return f"everkm-publish@v{version}"


def github_headers(token: str | None) -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_release(github_repo: str, tag: str, token: str | None) -> dict[str, Any]:
    url = f"https://api.github.com/repos/{github_repo}/releases/tags/{tag}"
    resp = requests.get(url, headers=github_headers(token), timeout=60)
    if resp.status_code == 404:
        raise RuntimeError(
            f"release not found: {github_repo} tag={tag} "
            f"(ensure everkm/publish Release is ready before tagging this repo)"
        )
    resp.raise_for_status()
    release = resp.json()
    if release.get("draft"):
        raise RuntimeError(f"release is draft: {github_repo} tag={tag}")
    return release


def make_s3_client() -> Any:
    ak = os.environ.get("CF_S3_AK") or os.environ.get("AWS_ACCESS_KEY_ID")
    sk = os.environ.get("CF_S3_SK") or os.environ.get("AWS_SECRET_ACCESS_KEY")
    if not ak or not sk:
        return None
    return boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=ak,
        aws_secret_access_key=sk,
        region_name="auto",
    )


def object_exists(s3_client: Any, key: str) -> bool:
    try:
        s3_client.head_object(Bucket=R2_BUCKET, Key=key)
        return True
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def content_type_for_key(key: str) -> str:
    content_type, _ = mimetypes.guess_type(key)
    return content_type or "application/octet-stream"


def upload_r2(s3_client: Any, local_path: Path, key: str) -> None:
    s3_client.upload_file(
        str(local_path),
        R2_BUCKET,
        key,
        ExtraArgs={"ContentType": content_type_for_key(key)},
    )


def upload_qiniu(
    local_path: Path,
    key: str,
    *,
    max_attempts: int = 3,
) -> None:
    ak = os.environ.get("QINIU_ACCESS_KEY")
    sk = os.environ.get("QINIU_SECRET_KEY")
    if not ak or not sk:
        raise RuntimeError("QINIU_ACCESS_KEY / QINIU_SECRET_KEY required for upload")
    auth = Auth(ak, sk)
    token = auth.upload_token(R2_BUCKET, key)
    last_status: int | None = None

    for attempt in range(1, max_attempts + 1):
        _, info = put_file_v2(
            token,
            key,
            str(local_path),
            bucket_name=R2_BUCKET,
        )
        if info.status_code == 200:
            return
        last_status = info.status_code
        if info.status_code not in QINIU_RETRYABLE_STATUS or attempt == max_attempts:
            break
        delay = min(30, 2 ** attempt)
        logger.warning(
            "[WARN] qiniu upload attempt %d/%d failed key=%s status=%s, retry in %ds",
            attempt,
            max_attempts,
            key,
            info.status_code,
            delay,
        )
        time.sleep(delay)

    raise RuntimeError(
        f"qiniu upload failed key={key} status={last_status} "
        f"after {max_attempts} attempts"
    )


def upload_file_both(
    s3_client: Any,
    local_path: Path,
    key: str,
    *,
    skip_if_exists: bool = False,
) -> None:
    if skip_if_exists and object_exists(s3_client, key):
        logger.info("[INFO] R2 cache hit, skip R2 upload: %s", key)
    else:
        logger.info("[INFO] uploading to R2: %s", key)
        upload_r2(s3_client, local_path, key)
    logger.info("[INFO] uploading to Qiniu: %s", key)
    upload_qiniu(local_path, key)


def pkg_key(version: str, asset_name: str) -> str:
    return f"pkgs/{version}/{asset_name}"


def asset_download_urls(version: str, asset_name: str) -> list[str]:
    return [
        f"{CDN_COM}/pkgs/{version}/{asset_name}",
        (
            f"https://github.com/{BINARY_GITHUB_REPO}/releases/download/"
            f"everkm-publish%40v{version}/{asset_name}"
        ),
        f"{CDN_CN}/pkgs/{version}/{asset_name}",
    ]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_latest_json(
    version: str,
    tag: str,
    notes: str,
    asset_names: list[str],
    asset_sha256: dict[str, str] | None = None,
) -> dict[str, Any]:
    assets = []
    for name in asset_names:
        entry: dict[str, Any] = {
            "name": name,
            "download_urls": asset_download_urls(version, name),
        }
        if asset_sha256 and name in asset_sha256:
            entry["sha256"] = asset_sha256[name]
        assets.append(entry)
    return {
        "version": version,
        "tag": tag,
        "notes": notes,
        "assets": assets,
    }


def download_asset(
    url: str,
    dest: Path,
    token: str | None,
    *,
    max_attempts: int = 3,
) -> None:
    headers = github_headers(token)
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            with requests.get(
                url, headers=headers, timeout=(30, 600), stream=True
            ) as resp:
                resp.raise_for_status()
                tmp = dest.with_suffix(dest.suffix + ".part")
                with tmp.open("wb") as f:
                    for chunk in resp.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
                tmp.replace(dest)
            return
        except requests.RequestException as exc:
            last_error = exc
            if dest.exists():
                dest.unlink()
            part = dest.with_suffix(dest.suffix + ".part")
            if part.exists():
                part.unlink()
            if attempt < max_attempts:
                logger.warning(
                    "[WARN] download attempt %d/%d failed: %s",
                    attempt,
                    max_attempts,
                    exc,
                )
            else:
                break

    raise RuntimeError(f"download failed after {max_attempts} attempts: {url}") from last_error


def npm_version_exists(version: str) -> bool:
    url = f"https://registry.npmjs.org/{NPM_PACKAGE_NAME}/{version}"
    try:
        resp = requests.get(url, timeout=30)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def latest_json_version(s3_client: Any) -> str | None:
    latest_key = "pkgs/latest.json"
    try:
        resp = s3_client.get_object(Bucket=R2_BUCKET, Key=latest_key)
        data = json.loads(resp["Body"].read())
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in ("404", "NoSuchKey", "NotFound"):
            return None
        raise
    except (json.JSONDecodeError, TypeError):
        return None
    version = data.get("version")
    return version if isinstance(version, str) and version else None


def cdn_assets_complete(s3_client: Any, version: str, asset_names: list[str]) -> bool:
    if not asset_names:
        return False
    for name in asset_names:
        if not object_exists(s3_client, pkg_key(version, name)):
            return False
    if not object_exists(s3_client, pkg_key(version, "meta.json")):
        return False
    if latest_json_version(s3_client) != version:
        return False
    return True


def cdn_refresh_urls(version: str, asset_names: list[str]) -> None:
    urls = [f"{CDN_CN}/pkgs/{version}/{name}" for name in asset_names]
    urls.append(f"{CDN_CN}/pkgs/{version}/meta.json")
    urls.append(f"{CDN_CN}/pkgs/latest.json")
    urls.append(f"{CDN_CN}/install.sh")
    urls.append(f"{CDN_CN}/pkgs/{version}/install.sh")
    urls.append(f"{CDN_CN}/install.ps1")
    urls.append(f"{CDN_CN}/pkgs/{version}/install.ps1")
    ak = os.environ.get("QINIU_ACCESS_KEY")
    sk = os.environ.get("QINIU_SECRET_KEY")
    if not ak or not sk:
        logger.warning("[WARN] skip cdnrefresh: QINIU credentials missing")
        return
    refresh_file = Path(tempfile.gettempdir()) / "cdn-refresh-pkgs.txt"
    refresh_file.write_text("\n".join(urls) + "\n", encoding="utf-8")
    subprocess.run(["qshell", "account", ak, sk, "ekmp", "-w"], check=True)
    subprocess.run(["qshell", "cdnrefresh", "-i", str(refresh_file)], check=True)


def publish(
    version: str,
    *,
    skip_cdn: bool = False,
    force_cdn: bool = False,
) -> int:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    tag = release_tag(version)

    release = fetch_release(BINARY_GITHUB_REPO, tag, token)
    notes = release.get("body") or ""
    assets = release.get("assets") or []
    if not assets:
        raise RuntimeError(f"no assets in release {BINARY_GITHUB_REPO} tag={tag}")

    asset_names = [a["name"] for a in assets if a.get("name")]
    logger.info(
        "[INFO] release=%s tag=%s assets=%d",
        BINARY_GITHUB_REPO,
        tag,
        len(asset_names),
    )

    s3_client = None if skip_cdn else make_s3_client()
    if not skip_cdn and s3_client is None:
        raise RuntimeError("CF_S3_AK / CF_S3_SK required for CDN upload")

    if (
        not skip_cdn
        and not force_cdn
        and npm_version_exists(version)
        and cdn_assets_complete(s3_client, version, asset_names)
    ):
        logger.info(
            "[SKIP] version=%s already on npm and CDN complete",
            version,
        )
        return 2

    work_dir = ARTIFACTS_DIR / version
    work_dir.mkdir(parents=True, exist_ok=True)

    for asset in assets:
        name = asset.get("name")
        url = asset.get("browser_download_url")
        if not name or not url:
            continue
        local_path = work_dir / name
        logger.info("[INFO] downloading asset: %s", name)
        download_asset(url, local_path, token)

    if not skip_cdn:
        asset_sha256: dict[str, str] = {}
        for name in asset_names:
            local_path = work_dir / name
            if not local_path.is_file():
                raise RuntimeError(f"downloaded asset missing: {name}")
            asset_sha256[name] = file_sha256(local_path)
            upload_file_both(
                s3_client,
                local_path,
                pkg_key(version, name),
                skip_if_exists=not force_cdn,
            )

        if not INSTALL_SH.is_file():
            raise RuntimeError(f"install script missing: {INSTALL_SH}")
        if not INSTALL_PS1.is_file():
            raise RuntimeError(f"install script missing: {INSTALL_PS1}")
        upload_file_both(
            s3_client,
            INSTALL_SH,
            "install.sh",
            skip_if_exists=not force_cdn,
        )
        upload_file_both(
            s3_client,
            INSTALL_SH,
            pkg_key(version, "install.sh"),
            skip_if_exists=not force_cdn,
        )
        upload_file_both(
            s3_client,
            INSTALL_PS1,
            "install.ps1",
            skip_if_exists=not force_cdn,
        )
        upload_file_both(
            s3_client,
            INSTALL_PS1,
            pkg_key(version, "install.ps1"),
            skip_if_exists=not force_cdn,
        )

        meta = build_latest_json(version, tag, notes, asset_names, asset_sha256)

        meta_path = work_dir / "meta.json"
        with meta_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
            f.write("\n")
        upload_file_both(
            s3_client,
            meta_path,
            pkg_key(version, "meta.json"),
            skip_if_exists=not force_cdn,
        )

        latest_path = work_dir / "latest.json"
        with latest_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
            f.write("\n")
        upload_file_both(
            s3_client,
            latest_path,
            "pkgs/latest.json",
            skip_if_exists=False,
        )
        cdn_refresh_urls(version, asset_names)

    logger.info("[INFO] publish complete version=%s", version)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="Semver, e.g. 0.16.15")
    parser.add_argument(
        "--skip-cdn",
        action="store_true",
        help="Skip R2/Qiniu upload (dry-run download only)",
    )
    parser.add_argument(
        "--force-cdn",
        action="store_true",
        help="Force re-upload CDN objects and refresh Qiniu cache",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    setup_logging(args.verbose)

    try:
        return publish(
            args.version,
            skip_cdn=args.skip_cdn,
            force_cdn=args.force_cdn,
        )
    except Exception:
        logger.exception("[ERROR] failed publishing version=%s", args.version)
        return 1


if __name__ == "__main__":
    sys.exit(main())
