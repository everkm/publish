"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const https = require("https");
const http = require("http");
const child_process = require("child_process");
const AdmZip = require("adm-zip");

const CDN_COM = "https://ekmp-assets.everkm.com";
const CDN_CN = "https://ekmp-assets.everkm.cn";
const BINARY_RELEASE_REPO = "everkm/publish";
const TIMEOUT_MS = 5000;

const knownWindowsPackages = {
  "win32 x64": "windows-amd64.zip",
};

const knownUnixlikePackages = {
  "darwin arm64": "darwin-universal.zip",
  "darwin x64": "darwin-universal.zip",
  "linux x64": "linux-amd64.zip",
};

const versionFromPackageJSON = require(path.join(__dirname, "package.json"))
  .version;

function pkgAndSubpathForCurrentPlatform() {
  const platformKey = `${process.platform} ${os.arch()}`;
  let pkg;
  let binName;
  if (platformKey in knownWindowsPackages) {
    pkg = knownWindowsPackages[platformKey];
    binName = "everkm-publish.exe";
  } else if (platformKey in knownUnixlikePackages) {
    pkg = knownUnixlikePackages[platformKey];
    binName = "everkm-publish.bin";
  } else {
    throw new Error(`Unsupported platform: ${platformKey}`);
  }
  return { pkg, binName };
}

const { pkg, binName } = pkgAndSubpathForCurrentPlatform();
const toPath = path.join(__dirname, "bin", binName);

function buildDownloadUrls(ver, pkgFile) {
  const fileName = `EverkmPublish_${ver}_${pkgFile}`;
  return [
    `${CDN_COM}/pkgs/${ver}/${fileName}`,
    `https://github.com/${BINARY_RELEASE_REPO}/releases/download/everkm-publish%40v${ver}/${fileName}`,
    `${CDN_CN}/pkgs/${ver}/${fileName}`,
  ];
}

function downloadWithTimeout(url, destPath, timeoutMs) {
  return new Promise((resolve, reject) => {
    const client = url.startsWith("https") ? https : http;

    const req = client.get(url, (res) => {
      if (
        res.statusCode >= 300 &&
        res.statusCode < 400 &&
        res.headers.location
      ) {
        downloadWithTimeout(res.headers.location, destPath, timeoutMs)
          .then(resolve)
          .catch(reject);
        return;
      }
      if (res.statusCode !== 200) {
        reject(new Error(`HTTP ${res.statusCode}`));
        return;
      }
      const file = fs.createWriteStream(destPath);
      res.pipe(file);
      file.on("finish", () => {
        file.close(() => resolve(destPath));
      });
      file.on("error", reject);
    });

    req.on("error", reject);
    req.setTimeout(timeoutMs, () => {
      req.destroy();
      reject(new Error(`timeout after ${timeoutMs}ms`));
    });
  });
}

function removeDirectory(dirPath) {
  if (!fs.existsSync(dirPath)) {
    return;
  }
  for (const entry of fs.readdirSync(dirPath)) {
    const entryPath = path.join(dirPath, entry);
    if (fs.lstatSync(entryPath).isDirectory()) {
      removeDirectory(entryPath);
    } else {
      fs.unlinkSync(entryPath);
    }
  }
  fs.rmdirSync(dirPath);
}

function listFilesRecursive(directory) {
  const files = [];
  for (const entry of fs.readdirSync(directory)) {
    const entryPath = path.join(directory, entry);
    if (fs.statSync(entryPath).isDirectory()) {
      files.push(...listFilesRecursive(entryPath));
    } else {
      files.push(entryPath);
    }
  }
  return files;
}

async function downloadBinary(pkgFile, binFileName) {
  const dest = path.join(__dirname, "bin");
  const zipPath = path.join(dest, pkgFile);
  const urls = buildDownloadUrls(versionFromPackageJSON, pkgFile);

  let lastError;
  for (let i = 0; i < urls.length; i++) {
    const url = urls[i];
    console.log(`[INFO] download source ${i + 1}/${urls.length}: ${url}`);
    try {
      await downloadWithTimeout(url, zipPath, TIMEOUT_MS);
      lastError = null;
      break;
    } catch (err) {
      lastError = err;
      console.warn(
        `[WARN] download source ${i + 1} failed:`,
        err.message || err
      );
    }
  }

  if (lastError) {
    throw lastError;
  }

  const extractDir = path.join(dest, "download");
  fs.mkdirSync(extractDir, { recursive: true });

  const zip = new AdmZip(zipPath);
  zip.extractAllTo(extractDir, true);

  const binFile = path.join(dest, binFileName);
  const files = listFilesRecursive(extractDir);
  const binary = files.find((file) =>
    /^everkm-publish/.test(path.basename(file))
  );
  if (!binary) {
    throw new Error("everkm-publish binary not found in downloaded archive");
  }

  fs.renameSync(binary, binFile);
  removeDirectory(extractDir);
  fs.unlinkSync(zipPath);
  fs.chmodSync(binFile, 0o755);
}

function validateBinaryVersion(binaryPath) {
  let stdout;
  try {
    stdout = child_process
      .execFileSync(binaryPath, ["--version"], { stdio: "pipe" })
      .toString()
      .trim()
      .split(" ")[1];
  } catch (err) {
    if (
      os.platform() === "darwin" &&
      /_SecTrustEvaluateWithError/.test(String(err))
    ) {
      let osVersion = "this version of macOS";
      try {
        osVersion =
          "macOS " +
          child_process
            .execFileSync("sw_vers", ["-productVersion"])
            .toString()
            .trim();
      } catch {}
      throw new Error(
        `The "everkm-publish" package cannot be installed because ${osVersion} is too outdated.\n\nThe "everkm-publish" binary executable can't be run.\n`
      );
    }
    throw err;
  }

  if (stdout !== versionFromPackageJSON) {
    throw new Error(
      `Expected ${JSON.stringify(versionFromPackageJSON)} but got ${JSON.stringify(stdout)}`
    );
  }
}

async function checkAndPreparePackage() {
  try {
    await downloadBinary(pkg, binName);
  } catch (err) {
    console.error("error", err);
    throw new Error(`Failed to install package "${pkg}"`);
  }
}

checkAndPreparePackage().then(() => {
  validateBinaryVersion(toPath);
});
