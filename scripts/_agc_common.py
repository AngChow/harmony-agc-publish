"""
harmony-agc-publish skill - 公共模块
集中处理: .agc_env 自动加载、AGC 凭据校验、Access Token 获取、HTTP 请求封装、错误提示
"""

import os
import sys
import json
from pathlib import Path

import requests

# ============================================================
# 常量
# ============================================================
API_BASE = "https://connect-api.cloud.huawei.com"
TOKEN_URL = f"{API_BASE}/api/oauth2/v1/token"

# Publishing API v3
APP_INFO_URL = f"{API_BASE}/api/publish/v3/app-info"
APP_FILE_INFO_URL = f"{API_BASE}/api/publish/v3/app-file-info"
APP_PACKAGE_INFO_URL = f"{API_BASE}/api/publish/v3/app-package-info"
APP_SUBMIT_URL = f"{API_BASE}/api/publish/v3/app-submit"

# Upload Management API (v2)
UPLOAD_URL_ENDPOINT = f"{API_BASE}/api/publish/v2/upload-url/for-obs"


# ============================================================
# 日志
# ============================================================
def log(msg, level="INFO"):
    colors = {
        "INFO": "\033[36m", "OK": "\033[32m", "WARN": "\033[33m",
        "ERROR": "\033[31m", "STEP": "\033[35m",
    }
    reset = "\033[0m"
    color = colors.get(level, "")
    # 写到 stderr，避免污染 stdout（query_app_info 输出 JSON）
    print(f"{color}[{level}]{reset} {msg}", file=sys.stderr)


# ============================================================
# .agc_env 自动加载
# ============================================================
def load_agc_env(project_root=None):
    """
    从 project_root/.agc_env 加载凭据到 os.environ。
    优先使用已有的环境变量（不覆盖外部 export 的值）。
    如果未提供 project_root，则从 cwd 向上找 .agc_env。
    """
    env_file = None
    if project_root:
        candidate = Path(project_root) / ".agc_env"
        if candidate.exists():
            env_file = candidate
    else:
        cur = Path.cwd()
        for p in [cur, *cur.parents]:
            candidate = p / ".agc_env"
            if candidate.exists():
                env_file = candidate
                break

    if env_file is None:
        return False

    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        # 不覆盖已 export 的值
        os.environ.setdefault(k, v)
    return True


# ============================================================
# 凭据 / Token
# ============================================================
def get_credentials():
    """返回 (app_id, client_id, client_secret)，缺失则退出"""
    app_id = os.environ.get("AGC_APP_ID", "")
    client_id = os.environ.get("AGC_CLIENT_ID", "")
    client_secret = os.environ.get("AGC_CLIENT_SECRET", "")
    missing = [k for k, v in {
        "AGC_APP_ID": app_id,
        "AGC_CLIENT_ID": client_id,
        "AGC_CLIENT_SECRET": client_secret,
    }.items() if not v]
    if missing:
        log(f"缺少环境变量: {', '.join(missing)}", "ERROR")
        log("请确认项目根目录有 .agc_env 文件，且包含 AGC_APP_ID / AGC_CLIENT_ID / AGC_CLIENT_SECRET", "ERROR")
        sys.exit(1)
    return app_id, client_id, client_secret


def get_access_token(client_id, client_secret):
    """获取 AGC Access Token"""
    log("正在获取 Access Token...", "STEP")
    resp = requests.post(
        TOKEN_URL,
        json={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    if resp.status_code != 200:
        log(f"获取 Token 失败: HTTP {resp.status_code}", "ERROR")
        log(f"响应: {resp.text[:500]}", "ERROR")
        sys.exit(1)
    data = resp.json()
    token = data.get("access_token")
    if not token:
        log(f"Token 响应缺少 access_token: {data}", "ERROR")
        sys.exit(1)
    expires_in = data.get("expires_in", 0)
    log(f"Token 获取成功 (有效期 {expires_in // 3600}h)", "OK")
    return token


def get_auth_headers(token, client_id):
    return {
        "client_id": client_id,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


# ============================================================
# 错误提示
# ============================================================
def handle_403(context):
    log(f"{context} 返回 403 Forbidden", "ERROR")
    log("最可能原因: API 客户端创建时「项目」未选择「N/A」（必须是团队级）", "ERROR")
    log("修复: 登录 AGC -> 用户与访问 -> API密钥 -> Connect API -> 新建团队级客户端", "ERROR")
    log("然后用新的 client_id / client_secret 更新 .agc_env", "ERROR")


# ============================================================
# 便捷调用
# ============================================================
def bootstrap(project_root=None):
    """
    一站式入口：加载 .agc_env -> 校验凭据 -> 拿 Token
    返回 (app_id, client_id, client_secret, token, auth_headers)
    """
    load_agc_env(project_root)
    app_id, client_id, client_secret = get_credentials()
    token = get_access_token(client_id, client_secret)
    headers = get_auth_headers(token, client_id)
    return app_id, client_id, client_secret, token, headers
