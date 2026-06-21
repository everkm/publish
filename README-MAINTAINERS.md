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

2. **CDN + npm + install.sh + 包管理器** — semver tag 触发：

   ```bash
   git tag v0.17.0
   git push origin v0.17.0

   # or via Makefile
   make tag TAG=v0.17.0
   ```

   并行触发两个 workflow：

   | Workflow | 职责 |
   |----------|------|
   | **Publish NPM Package** | Release → CDN（含 `install.sh`）→ npm publish |
   | **Publish Package Managers** | Homebrew tap + Chocolatey |

3. Verify:

   ```bash
   # CDN / latest
   curl -s https://ekmp-assets.everkm.com/pkgs/latest.json | jq .

   # npm
   npm view everkm-publish version

   # curl 安装脚本（Linux / macOS）
   curl -fsSL https://ekmp-assets.everkm.com/install.sh | bash

   # Homebrew
   brew tap everkm/tap
   brew install everkm-publish

   # Chocolatey（Windows）
   choco install everkm-publish
   ```

### 手动重跑

| 场景 | Actions workflow | 说明 |
|------|------------------|------|
| 仅 CDN / npm | **Publish NPM Package** → `workflow_dispatch` | 可选 `skip_npm`、`force_cdn` |
| 仅 Homebrew / Chocolatey | **Publish Package Managers** → `workflow_dispatch` | 指定 `version`；可选 `skip_homebrew` / `skip_chocolatey` / `force_*` |

## GitHub Secrets

| Secret | 用途 |
|--------|------|
| `CF_S3_AK` / `CF_S3_SK` | Cloudflare R2 上传 |
| `QINIU_ACCESS_KEY` / `QINIU_SECRET_KEY` | 七牛上传与 CDN 刷新 |
| `GH_TOKEN` | 读取同仓 GitHub Release；push [`everkm/homebrew-tap`](https://github.com/everkm/homebrew-tap)（未设置时读 Release 回退 `GITHUB_TOKEN`） |
| `NPM_TOKEN` | npm publish（见下） |
| `CHOCO_API_KEY` | Chocolatey push（未设置时跳过 Chocolatey job） |
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

### `CHOCO_API_KEY` 配置

1. 在 [community.chocolatey.org](https://community.chocolatey.org) 注册账户
2. 确保包 id **`everkm-publish`** 可用（首次 push 前可能需社区审核）
3. 账户设置中生成 API Key，写入 **Settings → Secrets → Actions → `CHOCO_API_KEY`**

Chocolatey job 运行在 `windows-latest`；未配置 secret 时自动 skip，不影响 Homebrew。

### `GH_TOKEN` 与 Homebrew tap

`GH_TOKEN` 需对 [`everkm/homebrew-tap`](https://github.com/everkm/homebrew-tap) 具备 **write** 权限（org 级 PAT 或 GitHub App）。

Formula 路径：`Formula/everkm-publish.rb`（单文件，`on_macos` / `on_linux`）。

## 脚本与产物

| 文件 | 用途 |
|------|------|
| `scripts/publish-npm-package.py` | CDN 镜像、`latest.json` / `meta.json`（含 sha256）、`install.sh` 上传 |
| `scripts/install.sh` | curl 安装脚本 → CDN `install.sh` |
| `scripts/publish-homebrew.py` | 生成 Formula → push homebrew-tap |
| `scripts/publish-chocolatey.py` | 打 nupkg → `choco push` |
| `.github/workflows/publish-npm.yaml` | CDN + npm |
| `.github/workflows/publish-package-managers.yaml` | Homebrew + Chocolatey |

## 用户安装渠道

| 平台 | 命令 |
|------|------|
| Node | `npm i -g everkm-publish` |
| Linux / macOS（curl） | `curl -fsSL https://ekmp-assets.everkm.com/install.sh \| bash` |
| macOS / Linux（Homebrew） | `brew tap everkm/tap && brew install everkm-publish` |
| Windows | `choco install everkm-publish` |
