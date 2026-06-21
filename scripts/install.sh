#!/usr/bin/env bash
# everkm-publish curl installer (Linux x64 + macOS)
# Usage:
#   curl -fsSL https://ekmp-assets.everkm.com/install.sh | bash
#   curl -fsSL https://ekmp-assets.everkm.com/install.sh | bash -s -- --version 0.17.0
#   EVERKM_PUBLISH_VERSION=0.17.0 curl -fsSL ... | bash

set -euo pipefail

CDN_COM="https://ekmp-assets.everkm.com"
CDN_CN="https://ekmp-assets.everkm.cn"
BINARY_RELEASE_REPO="everkm/publish"
INSTALL_DIR="${INSTALL_DIR:-${HOME}/.local/bin}"

REQUESTED_VERSION="${EVERKM_PUBLISH_VERSION:-}"

info() { printf '[INFO] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*" >&2; }
fatal() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fatal "missing required command: $1"
}

detect_platform() {
  local os arch
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  arch="$(uname -m)"

  case "$os" in
    darwin)
      PKG_SUFFIX="darwin-universal.zip"
      BIN_SRC="everkm-publish.bin"
      ;;
    linux)
      case "$arch" in
        x86_64 | amd64)
          PKG_SUFFIX="linux-amd64.zip"
          BIN_SRC="everkm-publish.bin"
          ;;
        *)
          fatal "unsupported linux architecture: $arch (supported: x86_64)"
          ;;
      esac
      ;;
    mingw* | msys* | cygwin* | windows*)
      fatal "Windows is not supported by this script. Use: choco install everkm-publish"
      ;;
    *)
      fatal "unsupported OS: $os (Linux/macOS only; Windows: choco install everkm-publish)"
      ;;
  esac
}

parse_args() {
  while [ $# -gt 0 ]; do
    case "$1" in
      --version)
        [ $# -ge 2 ] || fatal "--version requires a value"
        REQUESTED_VERSION="$2"
        shift 2
        ;;
      --prefix)
        [ $# -ge 2 ] || fatal "--prefix requires a value"
        INSTALL_DIR="$2"
        shift 2
        ;;
      -h | --help)
        cat <<'EOF'
everkm-publish installer

Usage:
  curl -fsSL https://ekmp-assets.everkm.com/install.sh | bash
  curl -fsSL https://ekmp-assets.everkm.com/install.sh | bash -s -- --version 0.17.0
  curl -fsSL https://ekmp-assets.everkm.com/install.sh | bash -s -- --prefix ~/.local/bin

Environment:
  EVERKM_PUBLISH_VERSION   Pin semver (same as --version)
  INSTALL_DIR              Install directory (default: ~/.local/bin)
EOF
        exit 0
        ;;
      *)
        fatal "unknown argument: $1"
        ;;
    esac
  done
}

http_get() {
  local url="$1"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL --proto '=https' --tlsv1.2 "$url"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- "$url"
  else
    fatal "curl or wget is required"
  fi
}

http_download() {
  local url="$1" dest="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL --proto '=https' --tlsv1.2 -o "$dest" "$url" || return 1
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$dest" "$url" || return 1
  else
    fatal "curl or wget is required"
  fi
}

resolve_version() {
  if [ -n "$REQUESTED_VERSION" ]; then
    VERSION="$REQUESTED_VERSION"
    info "using requested version: $VERSION"
    return
  fi
  info "resolving latest version from $CDN_COM/pkgs/latest.json"
  VERSION="$(http_get "$CDN_COM/pkgs/latest.json" | grep -o '"version"[[:space:]]*:[[:space:]]*"[^"]*"' | head -n1 | sed 's/.*"\([^"]*\)"$/\1/')"
  [ -n "$VERSION" ] || fatal "failed to parse version from latest.json"
  info "latest version: $VERSION"
}

asset_name() {
  printf 'EverkmPublish_%s_%s' "$VERSION" "$PKG_SUFFIX"
}

lookup_sha256() {
  local meta_url asset meta
  asset="$(asset_name)"
  meta_url="$CDN_COM/pkgs/$VERSION/meta.json"
  info "reading checksums from $meta_url"
  meta="$(http_get "$meta_url")"
  EXPECTED_SHA256="$(printf '%s\n' "$meta" | sed -n "/\"name\": \"${asset}\"/,/}/p" | grep '"sha256"' | head -n1 | sed 's/.*"sha256"[[:space:]]*:[[:space:]]*"\([a-f0-9]*\)".*/\1/')"
  [ -n "$EXPECTED_SHA256" ] || fatal "sha256 not found in meta.json for asset: $asset"
}

build_download_urls() {
  local asset="$1"
  URLS=(
    "$CDN_COM/pkgs/$VERSION/$asset"
    "https://github.com/$BINARY_RELEASE_REPO/releases/download/everkm-publish%40v$VERSION/$asset"
    "$CDN_CN/pkgs/$VERSION/$asset"
  )
}

download_zip() {
  local asset dest i url
  asset="$(asset_name)"
  dest="$1"
  build_download_urls "$asset"
  for i in "${!URLS[@]}"; do
    url="${URLS[$i]}"
    info "download source $((i + 1))/${#URLS[@]}: $url"
    if http_download "$url" "$dest"; then
      return 0
    fi
    warn "download failed: $url"
  done
  fatal "all download sources failed for $asset"
}

sha256_file() {
  local file="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$file" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$file" | awk '{print $1}'
  else
    fatal "sha256sum or shasum is required"
  fi
}

verify_sha256() {
  local file="$1" actual
  actual="$(sha256_file "$file")"
  if [ "$actual" != "$EXPECTED_SHA256" ]; then
    fatal "sha256 mismatch: expected $EXPECTED_SHA256 got $actual"
  fi
  info "sha256 verified"
}

extract_and_install() {
  local zip="$1"
  local extract_dir dest_bin bin_path
  need_cmd unzip
  extract_dir="$(mktemp -d "${TMPDIR:-/tmp}/everkm-publish.XXXXXX")"
  unzip -oq "$zip" -d "$extract_dir"
  dest_bin="$INSTALL_DIR/everkm-publish"
  mkdir -p "$INSTALL_DIR"
  bin_path="$extract_dir/everkm-publish.bin"
  if [ ! -f "$bin_path" ]; then
    bin_path="$(find "$extract_dir" -type f \( -name 'everkm-publish.bin' -o -name 'everkm-publish' \) | head -n1)"
    [ -n "$bin_path" ] || fatal "everkm-publish binary not found in archive"
  fi
  cp "$bin_path" "$dest_bin"
  chmod +x "$dest_bin"
  rm -rf "$extract_dir"
  info "installed: $dest_bin"
}

path_hint() {
  case ":$PATH:" in
    *":$INSTALL_DIR:"*) return ;;
  esac
  warn "$INSTALL_DIR is not in PATH"
  printf 'Add to your shell profile:\n  export PATH="%s:$PATH"\n' "$INSTALL_DIR"
}

verify_install() {
  local dest_bin="$INSTALL_DIR/everkm-publish"
  [ -x "$dest_bin" ] || fatal "binary not executable: $dest_bin"
  info "verifying installation..."
  "$dest_bin" --version
}

main() {
  parse_args "$@"
  detect_platform
  resolve_version
  lookup_sha256

  local work zip
  work="$(mktemp -d "${TMPDIR:-/tmp}/everkm-publish-install.XXXXXX")"
  trap "rm -rf '$work'" EXIT
  zip="$work/$(asset_name)"

  download_zip "$zip"
  verify_sha256 "$zip"
  extract_and_install "$zip"
  path_hint
  verify_install
  info "everkm-publish $VERSION installed successfully"
}

main "$@"
