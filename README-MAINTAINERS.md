# Maintainers

本仓库即 [`everkm/publish`](https://github.com/everkm/publish)（`everkm-publish-npm` 仅为本地/历史别名）。

## Release

1. **Binary Release** — tag 触发构建并发布 GitHub Release（含 notes）:

   ```bash
   git tag everkm-publish@v0.17.0
   git push origin everkm-publish@v0.17.0
   ```

   等待构建完成，确认 Release 资产与 notes。

2. **CDN + npm** — semver tag 触发 CDN 镜像与 npm publish:

   ```bash
   git tag v0.17.0
   git push origin v0.17.0

   # or via Makefile
   make tag TAG=v0.17.0
   ```

3. Verify:

   ```bash
   curl -s https://ekmp-assets.everkm.com/pkgs/latest.json
   npm view everkm-publish version
   ```

Manual re-run: GitHub Actions → **Publish NPM Package** → `workflow_dispatch`.

## GitHub Secrets

| Secret | 用途 |
|--------|------|
| `CF_S3_AK` / `CF_S3_SK` | Cloudflare R2 上传 |
| `QINIU_ACCESS_KEY` / `QINIU_SECRET_KEY` | 七牛上传与 CDN 刷新 |
| `GH_TOKEN` | 读取同仓 GitHub Release（未设置时回退 `GITHUB_TOKEN`） |
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
