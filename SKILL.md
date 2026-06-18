---
name: harmony-agc-publish
description: HarmonyOS app packaging, uploading, and submitting for review on Huawei AppGallery Connect. Use when user asks to publish/upload/submit a HarmonyOS (鸿蒙) app to AGC, AppGallery, or 应用市场, or when user mentions 打包上传, 提审, 上架, 出包, AGC 发布. Triggers in HarmonyOS ArkTS projects (those with build-profile.json5 / oh-package.json5). Provides scripts to check signing config (debug to release), verify version code against on-shelf version via AGC Publishing API, build the release .app via devecocli, upload .app to OBS, and submit for review (with double-safety-lock to prevent accidental production submission). AGC credentials are auto-loaded from project_root/.agc_env.
---

# HarmonyOS AGC Publish Skill

把 HarmonyOS 应用打包、上传到 AppGallery Connect (AGC)、提交审核的端到端流程。

## 触发场景

- 用户说"打包上传到 AGC"、"提审"、"上架华为应用市场"、"出包"
- 用户说"把这个鸿蒙项目发布到 AppGallery Connect"
- 当前工作区是 HarmonyOS ArkTS 项目（含 `build-profile.json5` / `oh-package.json5`）

## 前置条件

1. 项目根目录有 `.agc_env`（已被 `.gitignore`），包含：
   ```bash
   AGC_APP_ID="..."
   AGC_CLIENT_ID="..."          # 必须是团队级（项目=N/A）
   AGC_CLIENT_SECRET="..."
   ```
   skill 内所有脚本都会**自动加载** `project_root/.agc_env`，**不需要手动 `source`**。
2. AGC 上的 API 客户端必须创建为**团队级**（项目字段必须为 `N/A`），否则所有 Publishing API 返回 403。
3. 发布证书与 Profile 路径需在 `scripts/check_signing.py` 顶部配置（见 README 的「修改证书路径」章节）。

## 执行流程

按顺序执行下面 5 步。**任意一步失败必须停止整个流程并向用户报告失败原因，不要继续。**

### Step 1: 检查并切换签名配置

```bash
python3 ~/.codex/skills/harmony-agc-publish/scripts/check_signing.py "$(pwd)"
```

- 解析 `build-profile.json5` 中的 `signingConfigs[0].material`
- 通过路径关键词（"调试"/"Debug" vs "发布"/"Release"）判断当前是调试还是发布
- 如果当前是调试配置，自动改写为发布证书路径（保留其他字段）
- 退出码：0=成功（已是发布或已切换），1=失败

**绝对不能**用调试证书打包上架；切换后会修改 `build-profile.json5`，需要在最终结果里告知用户。

### Step 2: 检查版本号

```bash
python3 ~/.codex/skills/harmony-agc-publish/scripts/check_version.py "$(pwd)"
```

- 从 `AppScope/app.json5` 读取本地 `versionCode` / `versionName`
- 通过 AGC Publishing API 查询应用 `onShelfVersionCode`
- 比较本地 vs 在架
- 退出码：0=本地 > 在架，1=本地 ≤ 在架（必须停止），2=查询失败

如果退出码是 1，**立即停止流程**，向用户报告：本地 vs 在架版本号 + 提示先升级 `AppScope/app.json5` 里的 `versionCode`（整数）和 `versionName`（语义化版本）。

### Step 3: 本地打包 Release

通过 devecocli 执行 Release 模式构建：

```bash
PATH="/usr/local/bin:$PATH" devecocli build --product default --build-mode release
```

**重要：** `devecocli` 依赖 `node`，沙箱环境的 PATH 可能不包含 `/usr/local/bin`，必须显式加上 `PATH="/usr/local/bin:$PATH"`，否则会报 `env: node: No such file or directory`。

构建产物位置（单模块项目通常）：
- `build/outputs/default/mobile_harmony-default-signed.app`

构建期间会有大量 ArkTS WARN（来自三方库），看到 `BUILD SUCCESSFUL` 即视为成功。

### Step 4: 上传 .app 到 AGC（OBS）

```bash
python3 ~/.codex/skills/harmony-agc-publish/scripts/upload_app.py \
    <app_file_path> "$(pwd)"
```

脚本流程：
1. 自动 load `.agc_env`
2. 拿 Access Token
3. 计算 .app 的 SHA256
4. `GET /api/publish/v2/upload-url/for-obs` 拿 OBS 预签名上传地址
5. `PUT` 上传文件到 OBS
6. `PUT /api/publish/v3/app-package-info` 把 objectId / fileName 登记到 AGC

退出码：0=全部成功，1=任一步骤失败。

**完成后停下来等用户确认，不要自动跑 Step 5。**

### Step 5: 提交审核（⚠️ 危险操作，默认不会跑）

```bash
AGC_CONFIRM_SUBMIT=YES \
  python3 ~/.codex/skills/harmony-agc-publish/scripts/submit_review.py \
  --i-know-this-submits-to-production \
  --remark "版本说明" \
  "$(pwd)"
```

**双重安全锁**（缺一不可）：
1. 命令行带 `--i-know-this-submits-to-production`
2. 环境变量 `AGC_CONFIRM_SUBMIT=YES`

任意一项缺失，脚本退出码 2，**不会发送任何请求**。

退出码：0=提交成功，1=提交失败（HTTP 非 200），2=安全锁未满足。

**该步骤会真正把版本提交到华为审核流程，影响线上**。skill 在自动化场景下默认**不要主动执行**该脚本——除非用户在当前会话中显式说"提审"/"提交审核"/"submit for review"，并且已确认上传成功。即便那样，也建议先复述一遍参数让用户最终确认。

## 后续可拓展

- 上传 5 张以上截图（API: `/api/publish/v2/media-info`）
- 上传应用图标
- 多语言版本说明批量更新
- 灰度发布配置

## 文件结构

```
harmony-agc-publish/
├── SKILL.md                          # 本文件
├── agents/openai.yaml
├── scripts/
│   ├── _agc_common.py                # 共用：load_agc_env / get_token / handle_403
│   ├── check_signing.py              # Step 1
│   ├── query_app_info.py             # Step 2 子能力 + 独立查询
│   ├── check_version.py              # Step 2
│   ├── upload_app.py                 # Step 4
│   └── submit_review.py              # Step 5（带安全锁）
└── references/
    └── agc_publishing_api.md         # AGC API 端点速查
```

## 引用文档

- AGC API 端点详情见 `references/agc_publishing_api.md`
- 官方文档：https://developer.huawei.com/consumer/cn/doc/AppGallery-connect-Guides/agcapi-getstarted-0000001111845114
