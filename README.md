# harmony-agc-publish

> 一个 [Codex](https://github.com/openai/codex) / [Claude Code](https://docs.anthropic.com/en/docs/claude-code) Skill，实现 HarmonyOS（鸿蒙）ArkTS 应用的 **打包 → 上传 → 提审** 全流程自动化，基于华为 [AppGallery Connect Publishing API](https://developer.huawei.com/consumer/cn/doc/AppGallery-connect-Guides/agcapi-getstarted-0000001111845114)。

---

## ✨ 功能概览

| 步骤 | 能力 | 风险等级 |
|:---:|------|:---:|
| **Step 1** | 签名配置检查 — 自动检测调试/发布证书，必要时一键切换为发布证书 | 仅改本地文件 |
| **Step 2** | 版本号校验 — 调 AGC API 查询在架版本，确保本地版本号 > 在架版本 | 只读 |
| **Step 3** | Release 打包 — 调用 `devecocli` 构建 signed `.app` | 本地构建 |
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

### 3. 项目配置

#### 3.1 创建 `.agc_env`（凭据文件）

在鸿蒙项目**根目录**创建 `.agc_env` 文件（**务必加入 `.gitignore`**）：

```bash
# 项目根目录/.agc_env
AGC_APP_ID="你的应用AppID"
AGC_CLIENT_ID="上一步创建的API客户端ID"
AGC_CLIENT_SECRET="上一步创建的API客户端密钥"
```

Skill 内所有脚本会**自动加载** `project_root/.agc_env`，无需手动 `source`。如果你在外部 shell 已 `export` 了同名变量，外部值优先（不会被 `.agc_env` 覆盖）。

#### 3.2 修改证书路径（⚠️ 必做）

打开 `scripts/check_signing.py`，修改以下常量为你自己的证书路径：

```python
# ════════════ 证书路径配置（按需修改）════════════
KEYSTORE_PATH  = "/your/path/to/keystore.p12"
RELEASE_PROFILE = "/your/path/to/release_profile.p7b"
RELEASE_CERT    = "/your/path/to/release_cert.cer"
# ════════════════════════════════════════════════
```

#### 3.3 确保 `.gitignore` 包含 `.agc_env`

```bash
echo ".agc_env" >> .gitignore
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
│   ├── check_signing.py               # Step 1: 签名配置检查与自动切换
│   ├── query_app_info.py              # AGC 应用信息查询（独立可用 + 被 check_version 调用）
│   ├── check_version.py               # Step 2: 本地版本号 vs AGC 在架版本号比对
│   ├── upload_app.py                  # Step 4: 上传 .app 到 OBS + 登记软件包信息
│   └── submit_review.py               # Step 5: 提交审核（带双重安全锁）
└── references/
    └── agc_publishing_api.md          # AGC Publishing API 端点速查文档
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
| `upload_app.py` | 0 | 上传 + 软件包登记全部成功 |
| | 1 | 任意步骤失败 |
| `submit_review.py` | 0 | 提交成功 |
| | 1 | 提交失败（HTTP 非 200） |
| | 2 | 安全锁未满足，未发送任何请求 |

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

---

## 📚 参考文档

- [AGC Publishing API 入门](https://developer.huawei.com/consumer/cn/doc/AppGallery-connect-Guides/agcapi-getstarted-0000001111845114)
- [Publishing API 参考](https://developer.huawei.com/consumer/cn/doc/AppGallery-connect-References)
- [Upload Management API 参考](https://developer.huawei.com/consumer/cn/doc/AppGallery-connect-References/agcapi-upload_url-0000001843298261)
- [角色与权限](https://developer.huawei.com/consumer/cn/doc/app/agc-help-rolepermission-0000002271930352)

---

## 📄 License

MIT
