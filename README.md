# harmony-agc-publish

> 一个 [Codex](https://github.com/openai/codex) / [Claude Code](https://docs.anthropic.com/en/docs/claude-code) Skill，实现 HarmonyOS（鸿蒙）ArkTS 应用的 **打包 → 上传符号表 → 上传 AGC → 提审** 全流程自动化，基于华为 [AppGallery Connect Publishing API](https://developer.huawei.com/consumer/cn/doc/AppGallery-connect-Guides/agcapi-getstarted-0000001111845114) 和 [Bugly 符号表上传工具](https://bugly.tds.qq.com/docs/tutorial/symbol/harmony)。

---

## ✨ 功能概览

| 步骤 | 能力 | 风险等级 |
|:---:|------|:---:|
| **Step 1** | 签名配置检查 — 自动检测调试/发布证书，必要时一键切换为发布证书 | 仅改本地文件 |
| **Step 2** | 版本号校验 — 调 AGC API 查询在架版本，确保本地版本号 > 在架版本 | 只读 |
| **Step 3** | Release 打包 — 调用 `devecocli` 构建 signed `.app` | 本地构建 |
| **Step 3.5** | Bugly 符号表上传 — 自动扫描 nameCache.json / sourceMaps.json / Debug SO 并上传到 Bugly | 写 Bugly 平台 |
| **Step 4** | 上传到 AGC — 计算 SHA256 → 获取 OBS 预签名地址 → 上传 → 登记软件包信息 | 写 AGC 草稿态 |
| **Step 5** | 提交审核 — 调用 `app-submit` 接口提交发布 | ⚠️ **写线上** |

**Step 5 带双重安全锁**，缺一不可，防止 AI Agent 误触发线上提审。

---

## 📋 使用前提

### 1. 开发环境

| 依赖 | 说明 |
|------|------|
| [Codex](https://github.com/openai/codex) | 本 Skill 运行在 Codex 桌面端或 Claude Code，通过 `SKILL.md` 约束 Agent 行为 |
| [DevEco CLI](https://developer.huawei.com/consumer/cn/deveco-studio/) | `devecocli` 命令行工具，用于鸿蒙应用编译打包 |
| Python 3.8+ | 脚本运行环境，需安装 `requests` 库 |
| Java 8+ | Bugly 符号表上传工具依赖（Step 3.5） |
| HarmonyOS SDK | DevEco Studio 安装时自带 |

### 2. 华为 AppGallery Connect 平台配置

#### 2.1 创建团队级 API 客户端（⚠️ 关键）

> 这是整个流程能否跑通的**最关键一步**，配错了所有 API 都会返回 403。

1. 登录 [AppGallery Connect](https://developer.huawei.com/consumer/cn/agconnect/)
2. 进入 **「用户与访问」→「API 密钥」→「Connect API」**
3. 选择 **「API 客户端」** 页签，点击 **「创建」**
4. 填写配置：

   | 字段 | 值 | 说明 |
   |------|------|------|
   | 名称 | 自定义 | 如 `codex-publish-bot` |
   | **项目** | **N/A** | ⚠️ **必须选 N/A（团队级）**，选了具体项目会导致所有 Publishing API 返回 403 |
   | 角色 | APP管理员（或更高） | 决定了 API 客户端的权限范围 |

5. 创建成功后，记录列表中的 **「ID」** 和 **「密钥」**

#### 2.2 准备发布证书和 Profile

在 AGC 平台申请发布证书（`.cer`）和发布 Profile（`.p7b`），下载到本地。调试证书和发布证书**不要混用** — 本 Skill 会在打包前自动检查并切换。

> 参考华为文档：[申请发布证书](https://developer.huawei.com/consumer/cn/doc/app/agc-help-release-cert-0000001914361573) / [申请发布 Profile](https://developer.huawei.com/consumer/cn/doc/app/agc-help-release-profile-0000001914681405)

### 3. Bugly 平台配置（Step 3.5，可选）

如果项目集成了 Bugly 崩溃监控，建议配置符号表自动上传，否则线上崩溃堆栈将无法还原。

1. 在 [Bugly 控制台](https://bugly.tds.qq.com/) 获取 App ID 和 App Key
2. 在项目根目录创建 `.bugly_env` 文件（**务必加入 `.gitignore`**）：

   ```bash
   # 项目根目录/.bugly_env
   BUGLY_APP_ID="你的Bugly App ID"
   BUGLY_APP_KEY="你的Bugly App Key"
   ```

3. 确保本机有 Java 8+ 运行环境

> **如果 `.bugly_env` 不存在，Step 3.5 会自动跳过（不报错），不影响打包上传流程。**

### 4. 项目配置

#### 4.1 创建 `.agc_env`（AGC 凭据文件）

在鸿蒙项目**根目录**创建 `.agc_env` 文件（**务必加入 `.gitignore`**）：

```bash
# 项目根目录/.agc_env
AGC_APP_ID="你的应用AppID"
AGC_CLIENT_ID="上一步创建的API客户端ID"
AGC_CLIENT_SECRET="上一步创建的API客户端密钥"
```

Skill 内所有脚本会**自动加载** `project_root/.agc_env`，无需手动 `source`。如果你在外部 shell 已 `export` 了同名变量，外部值优先（不会被 `.agc_env` 覆盖）。

#### 4.2 证书目录结构

`check_signing.py` 会**自动扫描** keystore 目录下的子目录来查找发布证书，无需手动配置路径。请按以下结构组织证书文件：

```
~/develop/keystore/harmony/          ← 默认路径（可通过 HARMONY_KEYSTORE_DIR 环境变量覆盖）
├── xrxs.p12                          ← .p12 密钥库（调试和发布共用，不切换）
├── 发布Profile/                       ← 子目录名含"发布"或"Release"
│   └── xxx.p7b                       ← 发布 Profile 文件
├── 发布证书/                           ← 子目录名含"发布"或"Release"
│   └── xxx.cer                       ← 发布证书文件
├── 调试Profile/                       ← 子目录名含"调试"或"Debug"
│   └── xxx.p7b                       ← 调试 Profile 文件
└── 调试证书/                           ← 子目录名含"调试"或"Debug"
    └── xxx.cer                       ← 调试证书文件
```

脚本通过子目录名中的关键词（"发布"/"Release" vs "调试"/"Debug"）来区分调试和发布证书。**只替换 `.p7b`（Profile）和 `.cer`（证书），不替换 `.p12`（密钥库）**。

如果你的目录结构不同，可通过环境变量覆盖：

```bash
export HARMONY_KEYSTORE_DIR="/your/keystore/path"
export HARMONY_RELEASE_PROFILE="/full/path/to/release.p7b"   # 可选：直接指定发布 Profile
export HARMONY_RELEASE_CERT="/full/path/to/release.cer"       # 可选：直接指定发布证书
```

#### 4.3 确保 `.gitignore` 包含凭据文件

```bash
echo ".agc_env" >> .gitignore
echo ".bugly_env" >> .gitignore
```

---

## 🚀 快速开始

### 安装 Skill

将本目录复制到 CodeX / Claude Code 的 skills 目录：

```bash
cp -r harmony-agc-publish ~/.codex/skills/
```

### 日常使用

在 CodeX / Claude Code 中直接对话即可触发，例如：

> "把这个鸿蒙项目打包上传到 AGC"

CodeX / Claude Code 会自动按顺序执行 Step 1 → 4，并在 Step 5 前停下来等你确认。

### 手动执行（脱离 CodeX / Claude Code）

你也可以直接在终端跑各个脚本：

```bash
cd /path/to/your/harmony-project

# Step 1: 检查/切换签名配置
python3 ~/.codex/skills/harmony-agc-publish/scripts/check_signing.py "$(pwd)"

# Step 2: 检查版本号（本地 vs AGC 在架）
python3 ~/.codex/skills/harmony-agc-publish/scripts/check_version.py "$(pwd)"

# Step 3: Release 打包
PATH="/usr/local/bin:$PATH" devecocli build --product default --build-mode release

# Step 3.5: 上传符号表到 Bugly（需 .bugly_env，不存在则自动跳过）
python3 ~/.codex/skills/harmony-agc-publish/scripts/upload_bugly_symbol.py "$(pwd)"

# Step 4: 上传 .app 到 AGC
python3 ~/.codex/skills/harmony-agc-publish/scripts/upload_app.py \
    build/outputs/default/your-app-signed.app "$(pwd)"

# Step 5: 提审（⚠️ 双重安全锁，请确认后再执行）
AGC_CONFIRM_SUBMIT=YES \
    python3 ~/.codex/skills/harmony-agc-publish/scripts/submit_review.py \
    --i-know-this-submits-to-production \
    --remark "修复若干已知问题" \
    "$(pwd)"
```

### 独立查询应用信息

```bash
python3 ~/.codex/skills/harmony-agc-publish/scripts/query_app_info.py "$(pwd)"
```

输出 JSON，包含 `versionCode`、`onShelfVersionCode`、`releaseState`、`reviewState` 等字段。

### 独立上传符号表到 Bugly

如果你已经打过 Release 包，只想单独上传符号表（例如补传之前版本的符号表）：

```bash
python3 ~/.codex/skills/harmony-agc-publish/scripts/upload_bugly_symbol.py "$(pwd)"
```

脚本会自动扫描构建产物中的 `nameCache.json`、`sourceMaps.json` 和 Debug SO 文件并上传。

---

## 📁 文件结构

```
harmony-agc-publish/
├── README.md                          # 本文件
├── SKILL.md                           # CodeX / Claude Code Agent 指令文件（定义触发条件与执行流程）
├── agents/
│   └── openai.yaml                    # Agent 配置
├── scripts/
│   ├── _agc_common.py                 # 公共模块：.agc_env 加载 / Token 获取 / 错误处理
│   ├── _bugly_common.py               # 公共模块：.bugly_env 加载 / Java 检查 / jar 工具管理
│   ├── check_signing.py               # Step 1: 签名配置检查与自动切换
│   ├── query_app_info.py              # AGC 应用信息查询（独立可用 + 被 check_version 调用）
│   ├── check_version.py               # Step 2: 本地版本号 vs AGC 在架版本号比对
│   ├── upload_bugly_symbol.py         # Step 3.5: Bugly 符号表上传
│   ├── upload_app.py                  # Step 4: 上传 .app 到 OBS + 登记软件包信息
│   └── submit_review.py               # Step 5: 提交审核（带双重安全锁）
├── tools/
│   └── buglyqq-upload-symbol.jar      # Bugly 符号表上传工具（.gitignore，自动下载）
└── references/
    ├── agc_publishing_api.md          # AGC Publishing API 端点速查文档
    └── bugly_symbol_tool.md           # Bugly 符号表工具参考文档
```

---

## 🔧 各脚本退出码

| 脚本 | 退出码 | 含义 |
|------|:---:|------|
| `check_signing.py` | 0 | 已是发布配置 / 已自动切换为发布配置 |
| | 1 | 切换失败 |
| `check_version.py` | 0 | 版本号检查通过（本地 > 在架） |
| | 1 | 版本号不满足要求（本地 ≤ 在架），必须停止 |
| | 2 | 查询 AGC 失败 |
| `upload_bugly_symbol.py` | 0 | 上传成功（或非严格模式下上传失败 / .bugly_env 不存在自动跳过） |
| | 1 | 严格模式（BUGLY_STRICT=YES）下上传失败 / Java 不可用 |
| `upload_app.py` | 0 | 上传 + 软件包登记全部成功 |
| | 1 | 任意步骤失败 |
| `submit_review.py` | 0 | 提交成功 |
| | 1 | 提交失败（HTTP 非 200） |
| | 2 | 安全锁未满足，未发送任何请求 |

---

## 🐛 Bugly 符号表上传

### 工作原理

Step 3.5 在 Release 打包完成后执行，自动扫描构建产物中的符号表文件并上传到 Bugly：

| 符号表文件 | 用途 | 默认路径 |
|-----------|------|---------|
| **nameCache.json** | 还原混淆后的 ts/js 符号名 | `<Module>/build/default/cache/default/default@CompileArkTS/esmodule/release/obfuscation/nameCache.json` |
| **sourceMaps.json** | 还原混淆前后的 ts/js 行号 | `<Module>/build/default/cache/default/default@CompileArkTS/esmodule/release/sourceMaps.json` |
| **Debug SO** | 还原 Native (C/C++) Crash 堆栈 | `<Module>/build/default/intermediates/cmake/default/obj/<架构>/*.so` |

### 容错策略

- **默认非阻塞**：上传失败只 warn，不中断打包上传流程
- **严格模式**：设置 `BUGLY_STRICT=YES` 环境变量可改为阻塞模式
- **`.bugly_env` 不存在**：自动跳过，不报错

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `HARMONY_KEYSTORE_DIR` | 密钥库根目录 | `~/develop/keystore/harmony` |
| `HARMONY_RELEASE_PROFILE` | 发布 Profile 完整路径（覆盖自动扫描） | - |
| `HARMONY_RELEASE_CERT` | 发布证书完整路径（覆盖自动扫描） | - |
| `BUGLY_STRICT` | 设为 `YES` 时 Bugly 上传失败会中断流程 | - |
| `BUGLY_JAR_PATH` | Bugly jar 工具路径（覆盖自动查找） | - |

---

## 🔒 Step 5 安全机制

提审是**写线上**操作，本 Skill 采用**双重安全锁**防止误触发：

| 安全锁 | 方式 | 说明 |
|:---:|------|------|
| 锁 1 | 命令行参数 `--i-know-this-submits-to-production` | 必须显式带上 |
| 锁 2 | 环境变量 `AGC_CONFIRM_SUBMIT=YES` | 必须显式设置 |

**两把锁缺一不可**。任意一把缺失，脚本直接退出（exit code 2），**不会发送任何 HTTP 请求**。

CodeX / Claude Code Agent 在自动化场景下**默认不执行 Step 5**，即使用户说"提审"也会先复述参数让用户最终确认。

---

## ⚠️ 踩坑记录

在开发过程中踩过的坑，供后来者参考：

### 1. API 客户端必须选 N/A（团队级）

AGC 创建 API 客户端时如果「项目」选了具体项目而不是 `N/A`，所有 Publishing API 返回 403，响应体为空，只有 HTTP reason phrase 里有线索（`client token authorization fail`）。用 `curl -D -` 可以看到。

### 2. 上传 .app 包用 `app-package-info`，不是 `app-file-info`

华为文档里有两个容易混淆的接口：

| 接口 | 用途 |
|------|------|
| `PUT /api/publish/v3/app-package-info` | ✅ 上传 **.app 软件包**（body 只需 `objectId` + `fileName`） |
| `PUT /api/publish/v3/app-file-info` | ❌ 上传**图标/截图等素材文件**（不能用于 .app 包） |

用错接口的表征：OBS 上传成功，`app-file-info` 也返回 200，但 AGC 后台「软件包管理」里看不到新版本。

### 3. OBS 上传的 SHA256 必须是小写 hex

`x-amz-content-sha256` header 严格要求**小写**。如果你用 `sha256.hexdigest().upper()` 大写传给 AGC 获取上传地址，AGC 会把大写值原样回填到 OBS 的 header 里，导致 `XAmzContentSHA256Mismatch` 错误。

### 4. OBS 响应结构是嵌套的

获取上传地址的响应结构是 `{ret, urlInfo: {url, method, headers, objectId}}`，不是顶层的 `url`。要从 `urlInfo` 里取。

### 5. devecocli 需要 node 在 PATH 中

在非交互式 shell（如 CodeX / Claude Code 沙箱）中调用 `devecocli` 时，`/usr/local/bin` 可能不在 PATH 里，导致 `env: node: No such file or directory`。解决方式：

```bash
PATH="/usr/local/bin:$PATH" devecocli build --product default --build-mode release
```

### 6. 签名证书自动扫描：不要硬编码文件名

`check_signing.py` 早期版本硬编码了 `release.p12` / `Release.p7b` / `Release.cer` 三个文件名，但实际项目中密钥库名为 `xrxs.p12`、Profile 在 `发布Profile/` 子目录下且文件名含空格。改为**自动扫描 keystore 目录下的子目录**，通过目录名中的关键词（"发布"/"Release" vs "调试"/"Debug"）匹配。

**关键：`.p12` 密钥库在调试和发布时是同一个文件，不应替换。只替换 `.p7b`（Profile）和 `.cer`（证书）。**

### 7. Bugly 符号表扫描：glob 大小写敏感

`upload_bugly_symbol.py` 中扫描 `default@CompileArkTS` 目录时，早期用 `*CompileArkTs*` glob 模式（小写 `Ts`），但实际目录名是 `default@CompileArkTS`（大写 `TS`）。macOS 上 Python `glob` 是大小写敏感的，导致找不到符号表文件。改为 `*ompile*rk*` 模式规避大小写问题。

### 8. Worker 线程中不能调用 SlsUtils

在鸿蒙 Worker 线程中调用 `SlsUtils.pushLogForFaceProcess` 会因 MMKV 未初始化而抛出 `Error: You should Call MMKV.initialize() first.`，导致整个函数崩溃。Worker 线程中的日志应使用 `Logger`，SLS 日志通过 `postMessage` 传回主线程处理。

---

## 📚 参考文档

- [AGC Publishing API 入门](https://developer.huawei.com/consumer/cn/doc/AppGallery-connect-Guides/agcapi-getstarted-0000001111845114)
- [Publishing API 参考](https://developer.huawei.com/consumer/cn/doc/AppGallery-connect-References)
- [Upload Management API 参考](https://developer.huawei.com/consumer/cn/doc/AppGallery-connect-References/agcapi-upload_url-0000001843298261)
- [角色与权限](https://developer.huawei.com/consumer/cn/doc/app/agc-help-rolepermission-0000002271930352)
- [Bugly 符号表上传工具](https://bugly.tds.qq.com/docs/tutorial/symbol/tool/)
- [Bugly Harmony 符号表](https://bugly.tds.qq.com/docs/tutorial/symbol/harmony)

---

## 📄 License

MIT
