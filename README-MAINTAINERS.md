# Maintainers

本仓库即 [`everkm/publish`](https://github.com/everkm/publish)（`everkm-publish-npm` 仅为本地/历史别名）。

架构细节见 [stuff/km/260621-Plan-everkm-publish-包管理器分发.md](./stuff/km/260621-Plan-everkm-publish-包管理器分发.md)。

## Release

1. **Binary Release** — tag 触发构建并发布 GitHub Release（含 notes）:

   ```bash
   git tag everkm-publish@v0.17.0
   git push origin everkm-publish@v0.17.0
   ```

   等待构建完成，确认 Release 资产与 notes。

2. **CDN + npm + install 脚本 + Homebrew** — semver tag 触发：

   ```bash
   git tag v0.17.0
   git push origin v0.17.0

   # or via Makefile
   make tag TAG=v0.17.0
   ```

   并行触发两个 workflow：

   | Workflow | 职责 |
   |----------|------|
   | **Publish NPM Package** | Release → CDN（含 `install.sh` / `install.ps1`）→ npm publish |
   | **Publish Package Managers** | Homebrew tap |

3. Verify:

   ```bash
   # CDN / latest
   curl -s https://ekmp-assets.everkm.com/pkgs/latest.json | jq .

   # npm
   npm view everkm-publish version

   # curl 安装脚本（Linux / macOS）
   curl -fsSL https://ekmp-assets.everkm.com/install.sh | bash

   # PowerShell 安装脚本（Windows）
   irm https://ekmp-assets.everkm.com/install.ps1 | iex

   # Homebrew（若曾 tap 过旧版，先更新：`brew untap everkm/tap && brew tap everkm/tap`）
   brew tap everkm/tap
   brew trust everkm/tap
   brew install everkm-publish
   ```

### 手动重跑

| 场景 | Actions workflow | 说明 |
|------|------------------|------|
| 仅 CDN / npm | **Publish NPM Package** → `workflow_dispatch` | 可选 `skip_npm`、`force_cdn`（重传 + 刷新七牛缓存） |
| 仅 Homebrew | **Publish Package Managers** → `workflow_dispatch` | 指定 `version`；可选 `skip_homebrew` / `force_homebrew` |

## GitHub Secrets

| Secret | 用途 |
|--------|------|
| `CF_S3_AK` / `CF_S3_SK` | Cloudflare R2 上传 |
| `QINIU_ACCESS_KEY` / `QINIU_SECRET_KEY` | 七牛上传与 CDN 刷新 |
| `GH_TOKEN` | 读取同仓 GitHub Release；push [`everkm/homebrew-tap`](https://github.com/everkm/homebrew-tap)（未设置时读 Release 回退 `GITHUB_TOKEN`） |
| `NPM_TOKEN` | npm publish（见下） |
| `NOTIFY_DAYU_ENDPOINT` | workflow 结束 Telegram 通知（可选） |

### `NPM_TOKEN` 配置

CI 无法输入 authenticator 验证码；若账号启用了 2FA，token **必须**支持自动化发布，否则 `npm publish` 会报 `EOTP`。

在 [npmjs.com](https://www.npmjs.com) → **Access Tokens** 创建 **Granular Access Token**（或 Classic **Automation** token）：

1. **Packages and scopes**：对 `everkm-publish` 授予 **Read and write**（或 all packages）
2. **Security settings**：勾选 **Bypass two-factor authentication (2FA)**
3. 若包归属 npm organization，还需在 **Organizations** 中授权对应 org

将 token 写入仓库 **Settings → Secrets → Actions → `NPM_TOKEN`**。更新后重新跑 workflow 即可。

本地验证 token：

```bash
npm whoami --registry=https://registry.npmjs.org/ --//registry.npmjs.org/:_authToken=YOUR_TOKEN
```

### `GH_TOKEN` 与 Homebrew tap

`GH_TOKEN` 需对 [`everkm/homebrew-tap`](https://github.com/everkm/homebrew-tap) 具备 **write** 权限（org 级 PAT 或 GitHub App）。

Formula 路径：`Formula/everkm-publish.rb`（单文件，`on_macos` / `on_linux`）。

## 脚本与产物

| 文件 | 用途 |
|------|------|
| `scripts/publish-npm-package.py` | CDN 镜像、`latest.json` / `meta.json`（含 sha256）、`install.sh` / `install.ps1` 上传 |
| `scripts/install.sh` | curl 安装脚本（Linux / macOS）→ CDN `install.sh` |
| `scripts/install.ps1` | PowerShell 安装脚本（Windows）→ CDN `install.ps1` |
| `scripts/publish-homebrew.py` | 生成 Formula → push homebrew-tap |
| `.github/workflows/publish-npm.yaml` | CDN + npm |
| `.github/workflows/publish-package-managers.yaml` | Homebrew |

## 用户安装渠道

| 平台 | 命令 |
|------|------|
| Node | `npm i -g everkm-publish` |
| Linux / macOS（curl） | `curl -fsSL https://ekmp-assets.everkm.com/install.sh \| bash` |
| Windows（PowerShell） | `irm https://ekmp-assets.everkm.com/install.ps1 \| iex` |
| macOS / Linux（Homebrew） | `brew tap everkm/tap && brew trust everkm/tap && brew install everkm-publish` |
