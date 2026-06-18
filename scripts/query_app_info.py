#!/usr/bin/env python3
"""
查询 AGC 上的应用信息，输出 JSON 到 stdout。
供 check_version.py 等脚本调用，也可以独立使用。

用法:
  python3 query_app_info.py [<project_root>]

如果传入 project_root，会自动加载 project_root/.agc_env。
否则从 cwd 向上找 .agc_env。
"""
import os
import sys
import json
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _agc_common import (  # noqa: E402
    load_agc_env, get_credentials, get_access_token,
    get_auth_headers, APP_INFO_URL,
)


def main():
    project_root = os.path.abspath(sys.argv[1]) if len(sys.argv) >= 2 else None
    load_agc_env(project_root)

    app_id, client_id, client_secret = get_credentials()
    token = get_access_token(client_id, client_secret)
    headers = get_auth_headers(token, client_id)

    resp = requests.get(
        APP_INFO_URL,
        params={"appId": app_id},
        headers=headers,
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"❌ 查询失败 HTTP {resp.status_code}: {resp.text[:300]}", file=sys.stderr)
        sys.exit(1)

    info = resp.json()
    print(json.dumps(info, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
