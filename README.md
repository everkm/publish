## Usage

Static Content Generator. Pure HTML template engine based on markdown files, syntax from Jinja2. Built for official website, Blog and WIKI, and so on.

Please visit [Everkm Publish](https://publish.everkm.com) for more details.

## Install

```bash
npm add everkm-publish
# or
pnpm add everkm-publish
```

`postinstall` downloads the platform binary from CDN (`.com` → GitHub → `.cn`), with a 5s timeout per source.

## Release (maintainers)

本仓库即 [`everkm/publish`](https://github.com/everkm/publish)（`everkm-publish-npm` 仅为本地/历史别名）。

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

Required secrets: `CF_S3_AK`, `CF_S3_SK`, `QINIU_ACCESS_KEY`, `QINIU_SECRET_KEY`, `GH_TOKEN`, `NPM_TOKEN`, `NOTIFY_DAYU_ENDPOINT`。
