#!/usr/bin/env python3
"""
Step 5: 提交 HarmonyOS 应用审核 (POST /api/publish/v3/app-submit)

⚠️ 危险操作：该接口会真正把当前已上传的版本提交到华为审核。
   一旦提交成功，要撤回需要登录 AGC 控制台手动操作，可能影响线上流程。

安全锁（**必须**同时满足）:
  1. 命令行带 --i-know-this-submits-to-production 标志
  2. 环境变量 AGC_CONFIRM_SUBMIT=YES

两者缺一不可，否则直接退出（exit 2）不发送任何请求。

用法:
  AGC_CONFIRM_SUBMIT=YES python3 submit_review.py \
      --i-know-this-submits-to-production [--remark "本次更新内容"] [<project_root>]

退出码:
  0 = 提交成功
  1 = 提交失败（HTTP 非 200）
  2 = 安全锁未满足 / 参数错误（未发出请求）
"""

import os
import sys
import argparse
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _agc_common import (  # noqa: E402
    log, bootstrap, handle_403, APP_SUBMIT_URL,
)


SAFETY_FLAG = "--i-know-this-submits-to-production"
SAFETY_ENV = "AGC_CONFIRM_SUBMIT"
SAFETY_ENV_VALUE = "YES"


def check_safety_lock(args):
    """两道锁同时满足才放行"""
    has_flag = args.confirm
    env_val = os.environ.get(SAFETY_ENV, "")
    has_env = env_val == SAFETY_ENV_VALUE

    if has_flag and has_env:
        return True

    log("════════════════════════════════════════════════════════════", "ERROR")
    log("🛑 安全锁未通过，已阻止提交。提审是 *写线上* 操作，必须双重确认：", "ERROR")
    log(f"   1) 命令行加 {SAFETY_FLAG}    {'✅' if has_flag else '❌'}", "ERROR")
    log(f"   2) 环境变量 {SAFETY_ENV}={SAFETY_ENV_VALUE}                {'✅' if has_env else '❌'}", "ERROR")
    log("", "ERROR")
    log("   正确示例:", "ERROR")
    log(f"   AGC_CONFIRM_SUBMIT=YES python3 submit_review.py {SAFETY_FLAG} --remark '版本说明'", "ERROR")
    log("════════════════════════════════════════════════════════════", "ERROR")
    return False


def submit_app(app_id, headers, remark=""):
    log("正在提交审核...", "STEP")
    body = {}
    if remark:
        body["remark"] = remark
    resp = requests.post(
        APP_SUBMIT_URL,
        params={"appId": app_id},
        json=body,
        headers=headers,
        timeout=30,
    )
    if resp.status_code == 403:
        handle_403("提交审核")
        return False
    if resp.status_code != 200:
        log(f"提交审核失败: HTTP {resp.status_code}", "ERROR")
        log(f"响应: {resp.text[:500]}", "ERROR")
        return False
    log("✅ 提交审核成功！请到 AGC 控制台查看审核进度", "OK")
    log(f"   响应: {resp.text[:300]}", "INFO")
    return True


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(SAFETY_FLAG, dest="confirm", action="store_true")
    parser.add_argument("--remark", default="", help="版本备注（可选）")
    parser.add_argument("--help", "-h", action="store_true")
    parser.add_argument("project_root", nargs="?", default=None)
    args = parser.parse_args()

    if args.help:
        print(__doc__)
        sys.exit(0)

    print()
    print("=" * 60)
    print("  AGC 提交审核 - HarmonyOS")
    print("=" * 60)
    print()

    # 安全锁
    if not check_safety_lock(args):
        sys.exit(2)

    log("⚠️  双重安全锁已通过，3 秒后真实提交...", "WARN")
    import time
    time.sleep(3)

    app_id, _client_id, _secret, _token, headers = bootstrap(args.project_root)
    print()

    ok = submit_app(app_id, headers, args.remark)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
