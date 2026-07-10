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
  1 = 提交失败（HTTP 非 200 / AGC 返回业务错误 / 轮询超时）
  2 = 安全锁未满足 / 参数错误（未发出请求）
"""

import os
import sys
import json
import time
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

# 包编译中错误码，需要轮询等待后重试
PKG_COMPILING_CODES = {
    204144719,   # "The software package is compiling, and the compilation status of the software package is 1"
}
MAX_POLL_RETRIES = 10
POLL_INTERVAL = 15  # 秒


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
    """
    提交审核，自动处理「包还在编译」的情况。

    AGC 的 app-submit 接口在包刚上传完还在编译时会返回 HTTP 200 但 ret.code != 0，
    需要轮询等待编译完成后再重试提交。
    """
    body = {}
    if remark:
        body["remark"] = remark

    for attempt in range(1, MAX_POLL_RETRIES + 1):
        log(f"正在提交审核...（第 {attempt} 次）", "STEP")
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

        # 解析响应体，检查业务状态码
        try:
            resp_data = resp.json()
        except json.JSONDecodeError:
            log(f"提交审核失败: 响应不是有效 JSON", "ERROR")
            log(f"响应: {resp.text[:500]}", "ERROR")
            return False

        ret = resp_data.get("ret", {})
        ret_code = ret.get("code", -1)
        ret_msg = ret.get("msg", "")

        if ret_code == 0:
            log("✅ 提交审核成功！请到 AGC 控制台查看审核进度", "OK")
            log(f"   响应: {resp.text[:300]}", "INFO")
            return True

        # 包还在编译，需要等待后重试
        if ret_code in PKG_COMPILING_CODES:
            log(f"AGC 正在编译软件包（ret.code={ret_code}），等待 {POLL_INTERVAL}s 后重试...", "WARN")
            log(f"   ({attempt}/{MAX_POLL_RETRIES})", "INFO")
            time.sleep(POLL_INTERVAL)
            continue

        # 其他业务错误，直接失败
        log(f"提交审核失败: ret.code={ret_code}", "ERROR")
        log(f"   msg: {ret_msg}", "ERROR")
        log(f"   完整响应: {resp.text[:500]}", "ERROR")
        return False

    # 轮询超时
    log(f"轮询超时：已重试 {MAX_POLL_RETRIES} 次（共 {MAX_POLL_RETRIES * POLL_INTERVAL}s），AGC 仍在编译软件包", "ERROR")
    log("请稍后在 AGC 控制台手动提交审核，或重新运行本脚本", "ERROR")
    return False


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
    time.sleep(3)

    app_id, _client_id, _secret, _token, headers = bootstrap(args.project_root)
    print()

    ok = submit_app(app_id, headers, args.remark)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
