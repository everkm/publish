## npm 发布 `everkm-publish@0.16.9` 问题记录

### 背景
- 在本地项目 `everkm-publish-npm` 中执行 `npm publish`。
- `package.json` 中的包名为 `everkm-publish`，版本为 `0.16.9`。

### 现象
- npm 日志里出现：
  - `PUT https://registry.npmjs.org/everkm-publish 404 Not Found`
  - `error code E404`
- 随后检查身份时执行：
  - `npm config get registry` 输出 `https://registry.npmjs.org/`
  - `npm whoami` 返回：
    - `npm error code E401`
    - `npm error 401 Unauthorized - GET https://registry.npmjs.org/-/whoami`

### 原因分析
- `registry` 已指向官方 `https://registry.npmjs.org/`，说明不是源配置错误。
- `npm whoami` 返回 `E401 Unauthorized`，表明当前 npm **未登录或登录状态失效**。
- 在未授权的情况下执行 `publish`，导致与 registry 交互时出现异常，表现为：
  - `npm publish` 请求 `PUT https://registry.npmjs.org/everkm-publish` 时返回 `404 Not Found`。
  - 结合 `E401` 来看，实质问题是**认证失败**而不是资源真的不存在。

### 解决方案
1. 确认 registry：
   ```bash
   npm config get registry
   # 期望输出：
   # https://registry.npmjs.org/
   ```
2. 重新登录 npm：
   ```bash
   npm login
   # 按提示输入用户名、密码、邮箱以及（如有）2FA 验证
   ```
3. 确认登录成功：
   ```bash
   npm whoami
   # 能正常输出 npm 用户名即表示登录成功
   ```
4. 再次发布：
   ```bash
   npm publish --registry=https://registry.npmjs.org/
   ```

### 经验与教训
- 遇到 npm `E404` 且伴随 `E401 Unauthorized` 时，需要优先检查 **登录状态**，而不仅仅是 registry 配置。
- 在发布前可以先执行一次：
  ```bash
  npm whoami
  ```
  确认身份有效，再进行 `npm publish`，可以避免掉在认证问题上浪费时间。

