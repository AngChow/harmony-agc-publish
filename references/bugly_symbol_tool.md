# Bugly 符号表上传工具参考

## 工具信息

| 项目 | 内容 |
|------|------|
| 工具名称 | buglyqq-upload-symbol |
| 当前版本 | V3.4.23 |
| 文件格式 | Java jar 包（约 37MB） |
| Java 要求 | Java 8+（JDK 8 编译，已在 Mac 验证 Java 8/11/17/19） |
| 下载地址 | https://bugly.tds.qq.com/docs/tutorial/symbol/tool/ |

## 命令行用法

### 基本命令

```bash
# Harmony 平台必须先设置（Dwarf 5 格式支持）
export LLVM_USE=true

java -jar buglyqq-upload-symbol.jar \
  -appid <APP_ID> \
  -appkey <APP_KEY> \
  -version <App Version> \
  -platform Harmony \
  -inputSymbol <debug_so_folder> \
  -inputMapping <mapping_folder> \
  -buildNo <buildNo>
```

### 参数说明

| 参数 | 说明 | Harmony 平台 |
|------|------|-------------|
| `-appid` | Bugly App ID | 必填 |
| `-appkey` | Bugly App Key | 必填 |
| `-version` | App 版本号，必须与 crash 上报版本一致 | 必填（取 versionName） |
| `-platform` | 平台类型（Android/IOS/MAC/Windows/Harmony/Linux/Electron） | `Harmony`（注意大小写） |
| `-inputSymbol` | 原始符号表所在文件夹路径 | Debug SO 目录 |
| `-inputMapping` | mapping 文件路径或目录 | nameCache.json / sourceMaps.json |
| `-buildNo` | 构建号，用于区分同版本多构建 | 可选（取 versionCode） |

### 环境变量

| 变量 | 说明 |
|------|------|
| `LLVM_USE` | Harmony 平台必须设为 `true`（Dwarf 5 格式解析） |

## Harmony 符号表文件

### 1. Debug SO（Native 符号表）

- **用途**: 还原 Native (C/C++) Crash 堆栈
- **格式**: Dwarf 5 调试信息
- **默认路径**: `<Module>/build/default/intermediates/cmake/default/obj/<架构>/`
- **匹配方式**: 通过 SO UUID 匹配

### 2. nameCache.json（混淆映射）

- **用途**: 还原混淆后的 ts/js 符号名
- **默认路径**: `<Module>/build/default/cache/default/default@CompileArkTs/esmodule/release/obfuscation/nameCache.json`
- **匹配方式**: 通过 Hap 版本 + 构建号关联
- **命名建议**: 宿主用 `nameCache.json`，组件用 `xxx_nameCache.json`

### 3. sourceMaps.json（行号映射）

- **用途**: 还原混淆前后的 ts/js 行号
- **默认路径**: `<Module>/build/default/cache/default/default@CompileArkTs/esmodule/release/sourceMaps.json`
- **匹配方式**: 通过 Hap 版本 + 构建号关联
- **命名建议**: 宿主用 `sourceMaps.json`，组件用 `xxx_sourceMaps.json`

## 输出判断

### 成功标志
- jar 退出码为 0
- 输出中包含 `success` 且无 `##[error]`

### 失败标志
- 输出中包含 `##[error]`
- 输出中包含 Java 异常堆栈
- 常见错误码：
  - `1008`: App ID 不存在
  - 其他: 网络/权限/文件格式问题

## 注意事项

1. **版本号一致性**: `-version` 参数必须与 Bugly 平台上 crash 上报的版本号完全一致
2. **同名覆盖**: 相同版本号 + 构建号的同名文件会被覆盖
3. **多文件上传**: 同一版本 + 构建号支持上传多个文件，通过文件名区分
4. **LLVM_USE**: Harmony 平台 Dwarf 5 格式必须设置此环境变量
5. **构建产物备份**: 建议每次发布时备份符号表文件

## 官方文档

- 符号表上传工具: https://bugly.tds.qq.com/docs/tutorial/symbol/tool/
- Harmony 符号表: https://bugly.tds.qq.com/docs/tutorial/symbol/harmony
- 符号表概览: https://bugly.tds.qq.com/docs/tutorial/symbol/summary
- UUID 说明: https://bugly.tds.qq.com/docs/tutorial/symbol/uuid
- FAQ: https://bugly.tds.qq.com/docs/tutorial/symbol/faq
