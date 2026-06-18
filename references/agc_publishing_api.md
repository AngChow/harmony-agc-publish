# AGC Publishing API 参考

## 认证流程

### 1. 获取 Access Token

```http
POST https://connect-api.cloud.huawei.com/api/oauth2/v1/token
Content-Type: application/json

{
  "grant_type": "client_credentials",
  "client_id": "<API客户端ID>",
  "client_secret": "<API客户端密钥>"
}
```

响应（200）：
```json
{
  "access_token": "eyJ...",
  "expires_in": 172799
}
```

### 2. API 客户端必须是团队级

在 AGC → 用户与访问 → API密钥 → Connect API 创建 API 客户端时：
- **项目** 字段必须为 `N/A`（团队级）
- **角色** 至少为 `APP管理员`

否则所有 Publishing API 调用会返回 `403 client token authorization fail`。

## 通用请求头

```http
client_id: <API客户端ID>
Authorization: Bearer <access_token>
Content-Type: application/json
```

## 关键端点

### 查询应用信息

```http
GET /api/publish/v3/app-info?appId={appId}&lang={lang}
```

关键响应字段（`appInfo`）：
| 字段 | 含义 |
|------|------|
| `versionCode` | AGC 上最新提交的版本号（整数） |
| `versionNumber` | AGC 上最新提交的版本名（如 "2.3.7"） |
| `onShelfVersionCode` | 当前**在架**版本号 |
| `onShelfVersionNumber` | 当前**在架**版本名 |
| `releaseState` | 发布状态（0=未发布，4=已上架，5=审核中等） |
| `reviewState` | 审核状态 |

### 获取文件上传地址

```http
GET /api/publish/v2/upload-url/for-obs?appId={appId}&fileName={name}&sha256={hash}&contentLength={size}&fileType=APP
```

返回 OBS 上传地址和必需的 `x-amz-*` headers。

### 上传文件到 OBS（S3 兼容）

```http
PUT <obs_url>
Authorization: <从上一步返回>
Content-Type: application/octet-stream
x-amz-content-sha256: <SHA256>
x-amz-date: <ISO8601>
host: <OBS host>

<binary file content>
```

### 更新应用软件包信息（上传 .app 包）

> **关键：** 上传 HarmonyOS .app 包必须用此接口，不要用 `app-file-info`（后者只用于图标/截图等素材文件）。

```http
PUT /api/publish/v3/app-package-info?appId={appId}
Content-Type: application/json

{
  "objectId": "CN/2026061809/xxx.app",
  "fileName": "xxx-default-signed.app"
}
```

响应（200）：
```json
{
  "ret": {"code": 0, "msg": "success"},
  "packageId": "1975552458952298432"
}
```

`objectId` 从 OBS 上传步骤的响应 `urlInfo.objectId` 获取。

### 更新应用文件信息（素材文件，非 .app 包）

> 仅用于上传图标、截图等素材文件，**不要**用于上传 .app 软件包。

```http
PUT /api/publish/v3/app-file-info?appId={appId}
Content-Type: application/json

{
  "fileType": "APP",
  "files": [
    {
      "fileName": "xxx.png",
      "sha256": "...",
      "contentLength": "12345",
      "fileType": "APP"
    }
  ]
}
```

### 提交发布

```http
POST /api/publish/v3/app-submit?appId={appId}
Content-Type: application/json

{
  "remark": "版本说明（可选）"
}
```

> **注意**：传包后必须**等待至少 2 分钟**让 AGC 解析软件包，再调用提交发布。

## 错误码速查

| HTTP | 含义 | 排查方向 |
|------|------|---------|
| 403 | `client token authorization fail` | API 客户端项目不是 N/A |
| 404 | 路径不对 | 检查是 v2 还是 v3 |
| 400 | 参数错误 | 检查 query 参数和 body |

## 官方文档

- 获取服务端授权：https://developer.huawei.com/consumer/cn/doc/AppGallery-connect-Guides/agcapi-getstarted-0000001111845114
- Publishing API 参考：https://developer.huawei.com/consumer/cn/doc/AppGallery-connect-References
