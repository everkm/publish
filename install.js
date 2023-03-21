"use strict";
var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __getProtoOf = Object.getPrototypeOf;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __copyProps = (to, from, except, desc) => {
  if ((from && typeof from === "object") || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, {
          get: () => from[key],
          enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable,
        });
  }
  return to;
};

// lib/npm/node-platform.ts
var fs = require("fs");
var os = require("os");
var path = require("path");

var knownWindowsPackages = {
  //   "win32 arm64": "@esbuild/win32-arm64",
  //   "win32 ia32": "@esbuild/win32-ia32",
  "win32 x64": "@esbuild/win32-x64",
};
var knownUnixlikePackages = {
  //   "android arm64": "@esbuild/android-arm64",
  //   "darwin arm64": "@esbuild/darwin-arm64",
  "darwin x64": "darwin-amd64.tar.gz",
  //   "freebsd arm64": "@esbuild/freebsd-arm64",
  //   "freebsd x64": "@esbuild/freebsd-x64",
  //   "linux arm": "@esbuild/linux-arm",
  //   "linux arm64": "@esbuild/linux-arm64",
  //   "linux ia32": "@esbuild/linux-ia32",
  //   "linux mips64el": "@esbuild/linux-mips64el",
  //   "linux ppc64": "@esbuild/linux-ppc64",
  //   "linux riscv64": "@esbuild/linux-riscv64",
  //   "linux s390x BE": "@esbuild/linux-s390x",
  "linux x64": "linux-amd64.tar.gz",
  //   "linux loong64": "@esbuild/linux-loong64",
  //   "netbsd x64": "@esbuild/netbsd-x64",
  //   "openbsd x64": "@esbuild/openbsd-x64",
  //   "sunos x64": "@esbuild/sunos-x64",
};

// 返回可执行文件信息
function pkgAndSubpathForCurrentPlatform() {
  let pkg;
  let binName;
  let platformKey = `${process.platform} ${os.arch()}`;
  if (platformKey in knownWindowsPackages) {
    pkg = knownWindowsPackages[platformKey];
    binName = "daobox-site.exe";
  } else if (platformKey in knownUnixlikePackages) {
    pkg = knownUnixlikePackages[platformKey];
    binName = "daobox-site.bin";
  } else {
    throw new Error(`Unsupported platform: ${platformKey}`);
  }
  return { pkg, binName };
}

// lib/npm/node-install.ts
var fs2 = require("fs");
var os2 = require("os");
var path2 = require("path");
var zlib = require("zlib");
var AdmZip = require("adm-zip");
var https = require("https");
var http = require("http");
var child_process = require("child_process");
var versionFromPackageJSON = require(path2.join(
  __dirname,
  "package.json"
)).version;
var toPath = path2.join(
  __dirname,
  "bin",
  pkgAndSubpathForCurrentPlatform().binName
);

function validateBinaryVersion(...command) {
  command.push("--version");
  let stdout;
  try {
    stdout = child_process
      .execFileSync(command.shift(), command, {
        // Without this, this install script strangely crashes with the error
        // "EACCES: permission denied, write" but only on Ubuntu Linux when node is
        // installed from the Snap Store. This is not a problem when you download
        // the official version of node. The problem appears to be that stderr
        // (i.e. file descriptor 2) isn't writable?
        //
        // More info:
        // - https://snapcraft.io/ (what the Snap Store is)
        // - https://nodejs.org/dist/ (download the official version of node)
        // - https://github.com/evanw/esbuild/issues/1711#issuecomment-1027554035
        //
        stdio: "pipe",
      })
      .toString()
      .trim()
      .split(" ")[1];
  } catch (err) {
    if (
      os2.platform() === "darwin" &&
      /_SecTrustEvaluateWithError/.test(err + "")
    ) {
      let os3 = "this version of macOS";
      try {
        os3 =
          "macOS " +
          child_process
            .execFileSync("sw_vers", ["-productVersion"])
            .toString()
            .trim();
      } catch {}
      throw new Error(`The "daobox-site" package cannot be installed because ${os3} is too outdated.

The "daobox-site" binary executable can't be run. 
`);
    }
    throw err;
  }

  if (stdout !== versionFromPackageJSON) {
    throw new Error(
      `Expected ${JSON.stringify(
        versionFromPackageJSON
      )} but got ${JSON.stringify(stdout)}`
    );
  }
}

function isYarn() {
  const { npm_config_user_agent } = process.env;
  if (npm_config_user_agent) {
    return /\byarn\//.test(npm_config_user_agent);
  }
  return false;
}

async function downloadBinary(pkg, binName) {
  const fileUrl = `https://assets.daobox.cc/daobox-site/stable/${versionFromPackageJSON}/DaoboxSite_${versionFromPackageJSON}_${pkg}`;
  //   const fileUrl = "http://localhost:8000/daobox/daobox-site";
  const filename = path.join(__dirname, "bin", pkg);

  return new Promise((resolve, reject) => {
    http.get(fileUrl, (response) => {
      const fileStream = fs.createWriteStream(filename);
      response.pipe(fileStream);
      fileStream.on("finish", () => {
        console.log(`File saved as ${filename}`);
        fs2.chmodSync(filename, 493);

        // 解压缩
        if (/\.tar\.gz$/.test(filename)) {
          const readStream = fs.createReadStream(filename);
          const unzip = zlib.createGunzip(); // 创建 gunzip 解压缩流
          const untar = tar.extract(destination); // 创建 tar 解压缩流

          readStream
            .pipe(unzip) // 使用 gunzip 解压缩流
            .pipe(untar) // 使用 tar 解压缩流
            .on("finish", () => {
              console.log("解压缩完成");
              resolve();
            });
        } else if (/\.zip$/.test(filename)) {
          const zip = new AdmZip(filename); // 指定 ZIP 文件路径
          zip.extractAllTo(path.dirname(filename), true); // 解压 ZIP 文件到指定目录
          resolve();
        } else {
          reject(`not support archive package: ${pkg}`);
        }
      });
      fileStream.on("error", (e) => {
        reject(e);
      });
    });
  });
}

async function checkAndPreparePackage() {
  const { pkg, binName } = pkgAndSubpathForCurrentPlatform();
  try {
    await downloadBinary(pkg, binName);
  } catch (e3) {
    // console.error("error", e3);
    throw new Error(`Failed to install package "${pkg}"`);
  }
}

checkAndPreparePackage().then(() => {
  validateBinaryVersion(toPath);
});
