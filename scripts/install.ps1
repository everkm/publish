#requires -Version 5.1
# everkm-publish Windows installer
# Usage:
#   irm https://ekmp-assets.everkm.com/install.ps1 | iex
#   $env:EVERKM_PUBLISH_VERSION='0.17.0'; irm https://ekmp-assets.everkm.com/install.ps1 | iex

$ErrorActionPreference = 'Stop'

$CDN_COM = 'https://ekmp-assets.everkm.com'
$CDN_CN = 'https://ekmp-assets.everkm.cn'
$BINARY_RELEASE_REPO = 'everkm/publish'
$PKG_SUFFIX = 'windows-amd64.zip'
$BIN_NAME = 'everkm-publish.exe'

if (-not $env:INSTALL_DIR) {
    $env:INSTALL_DIR = Join-Path $env:USERPROFILE '.local\bin'
}
$InstallDir = $env:INSTALL_DIR

$RequestedVersion = $env:EVERKM_PUBLISH_VERSION
$ResolvedVersion = $null

function Write-Info([string]$Message) {
    Write-Host "[INFO] $Message"
}

function Write-Warn([string]$Message) {
    Write-Warning $Message
}

function Write-Fatal([string]$Message) {
    Write-Error "[ERROR] $Message"
    exit 1
}

function Ensure-Tls12 {
    if ([Net.ServicePointManager]::SecurityProtocol -band [Net.SecurityProtocolType]::Tls12) {
        return
    }
    [Net.ServicePointManager]::SecurityProtocol = `
        [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
}

function Invoke-HttpGet([string]$Url) {
    Ensure-Tls12
    return (Invoke-WebRequest -Uri $Url -UseBasicParsing).Content
}

function Invoke-HttpDownload([string]$Url, [string]$Dest) {
    Ensure-Tls12
    Invoke-WebRequest -Uri $Url -OutFile $Dest -UseBasicParsing
}

function Resolve-Version {
    if ($RequestedVersion) {
        $script:ResolvedVersion = $RequestedVersion
        Write-Info "using requested version: $ResolvedVersion"
        return
    }
    Write-Info "resolving latest version from $CDN_COM/pkgs/latest.json"
    $json = Invoke-HttpGet "$CDN_COM/pkgs/latest.json" | ConvertFrom-Json
    if (-not $json.version) {
        Write-Fatal 'failed to parse version from latest.json'
    }
    $script:ResolvedVersion = [string]$json.version
    Write-Info "latest version: $ResolvedVersion"
}

function Get-AssetName {
    return "EverkmPublish_${ResolvedVersion}_${PKG_SUFFIX}"
}

function Get-DownloadUrls([string]$Asset) {
    return @(
        "$CDN_COM/pkgs/$ResolvedVersion/$Asset"
        "https://github.com/$BINARY_RELEASE_REPO/releases/download/everkm-publish%40v$ResolvedVersion/$Asset"
        "$CDN_CN/pkgs/$ResolvedVersion/$Asset"
    )
}

function Get-ExpectedSha256 {
    $asset = Get-AssetName
    $metaUrl = "$CDN_COM/pkgs/$ResolvedVersion/meta.json"
    Write-Info "reading checksums from $metaUrl"
    $meta = Invoke-HttpGet $metaUrl | ConvertFrom-Json
    foreach ($entry in $meta.assets) {
        if ($entry.name -eq $asset) {
            if ($entry.sha256) {
                return [string]$entry.sha256
            }
            break
        }
    }
    Write-Fatal "sha256 not found in meta.json for asset: $asset"
}

function Download-Zip([string]$Dest) {
    $asset = Get-AssetName
    $urls = Get-DownloadUrls $asset
    for ($i = 0; $i -lt $urls.Count; $i++) {
        $url = $urls[$i]
        Write-Info "download source $($i + 1)/$($urls.Count): $url"
        try {
            Invoke-HttpDownload $url $Dest
            return
        } catch {
            Write-Warn "download failed: $url"
        }
    }
    Write-Fatal "all download sources failed for $asset"
}

function Test-Sha256([string]$File, [string]$Expected) {
    $actual = (Get-FileHash -Path $File -Algorithm SHA256).Hash.ToLowerInvariant()
    $expectedNorm = $Expected.ToLowerInvariant()
    if ($actual -ne $expectedNorm) {
        Write-Fatal "sha256 mismatch: expected $expectedNorm got $actual"
    }
    Write-Info 'sha256 verified'
}

function Install-Binary([string]$ZipPath) {
    $extractDir = Join-Path ([System.IO.Path]::GetTempPath()) ("everkm-publish.{0}" -f [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $extractDir -Force | Out-Null
    try {
        Expand-Archive -Path $ZipPath -DestinationPath $extractDir -Force
        $binPath = Join-Path $extractDir $BIN_NAME
        if (-not (Test-Path -LiteralPath $binPath)) {
            $binPath = Get-ChildItem -Path $extractDir -Recurse -Filter $BIN_NAME |
                Select-Object -First 1 -ExpandProperty FullName
        }
        if (-not $binPath) {
            Write-Fatal "$BIN_NAME not found in archive"
        }
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
        $destBin = Join-Path $InstallDir 'everkm-publish.exe'
        Copy-Item -LiteralPath $binPath -Destination $destBin -Force
        Write-Info "installed: $destBin"
        return $destBin
    } finally {
        Remove-Item -LiteralPath $extractDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Show-PathHint {
    $paths = ($env:Path -split ';') | Where-Object { $_ -ne '' }
    foreach ($entry in $paths) {
        if ($entry -eq $InstallDir) {
            return
        }
    }
    Write-Warn "$InstallDir is not in PATH"
    Write-Host "Add to your user PATH (PowerShell):"
    Write-Host "  [Environment]::SetEnvironmentVariable('Path', `"$InstallDir;`$env:Path`", 'User')"
}

function Test-Install([string]$DestBin) {
    if (-not (Test-Path -LiteralPath $DestBin)) {
        Write-Fatal "binary not found: $DestBin"
    }
    Write-Info 'verifying installation...'
    & $DestBin --version
}

Resolve-Version
$expectedSha = Get-ExpectedSha256
$work = Join-Path ([System.IO.Path]::GetTempPath()) ("everkm-publish-install.{0}" -f [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work -Force | Out-Null
try {
    $zip = Join-Path $work (Get-AssetName)
    Download-Zip $zip
    Test-Sha256 $zip $expectedSha
    $destBin = Install-Binary $zip
    Show-PathHint
    Test-Install $destBin
    Write-Info "everkm-publish $ResolvedVersion installed successfully"
} finally {
    Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
}
