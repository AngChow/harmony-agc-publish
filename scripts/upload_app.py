#!/usr/bin/env python3
"""
Step 4: 上传 .app 文件到 AppGallery Connect

用法:
  python3 upload_app.py <app_file_path> [<project_root>]

行为:
  1. 自动从 project_root/.agc_env 加载 AGC 凭据
  2. 获取 Access Token
  3. 计算文件 SHA256
  4. 获取 OBS 上传地址
  5. 上传文件到 OBS
  6. 更新 AGC 应用软件包信息（PUT /api/publish/v3/app-package-info）

完成后不会自动提审，请手动跑 submit_review.py 或在 AGC 控制台提交。

退出码:
  0 = 上传 + 文件信息更新都成功
  1 = 任意一步失败
"""

import os
import sys
import json
import hashlib
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _agc_common import (  # noqa: E402
    log, bootstrap, handle_403,
    UPLOAD_URL_ENDPOINT, APP_PACKAGE_INFO_URL,
)


def get_file_sha256(file_path):
    log(f"正在计算文件哈希: {os.path.basename(file_path)}", "STEP")
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            data = f.read(8 * 1024 * 1024)
            if not data:
                break
            sha256.update(data)
    result = sha256.hexdigest()  # 小写 hex；OBS x-amz-content-sha256 严格要求小写
    log(f"SHA256: {result}", "OK")
    return result


def get_upload_url(app_id, headers, file_path, sha256, file_size):
    log("正在获取 OBS 上传地址...", "STEP")
    params = {
        "appId": app_id,
        "fileName": os.path.basename(file_path),
        "sha256": sha256,
        "contentLength": str(file_size),
        "fileType": "APP",
    }
    resp = requests.get(UPLOAD_URL_ENDPOINT, params=params, headers=headers, timeout=30)
    if resp.status_code == 403:
        handle_403("获取上传地址")
        sys.exit(1)
    if resp.status_code != 200:
        log(f"获取上传地址失败: HTTP {resp.status_code}", "ERROR")
        log(f"响应: {resp.text[:500]}", "ERROR")
        sys.exit(1)
    data = resp.json()
    log("上传地址获取成功", "OK")
    return data


def upload_file_to_obs(upload_info, file_path, file_size):
    log(f"正在上传文件到 OBS ({file_size / 1024 / 1024:.1f} MB)...", "STEP")
    # AGC 真实响应结构：{ret, urlInfo: {url, method, headers, objectId}}
    url_info = upload_info.get("urlInfo") or upload_info
    obs_url = url_info.get("url") or url_info.get("uploadUrl") or ""
    method = (url_info.get("method") or "PUT").upper()
    obs_headers = dict(url_info.get("headers") or {})
    object_id = url_info.get("objectId", "")

    if not obs_url:
        log(f"上传地址为空，完整响应: {json.dumps(upload_info, ensure_ascii=False)[:500]}", "ERROR")
        sys.exit(1)

    # 兜底 Content-Type / Content-Length
    if not any(k.lower() == "content-type" for k in obs_headers):
        obs_headers["Content-Type"] = "application/octet-stream"
    obs_headers["Content-Length"] = str(file_size)

    with open(file_path, "rb") as f:
        resp = requests.request(method, obs_url, data=f, headers=obs_headers, timeout=900)

    if resp.status_code not in (200, 201, 204):
        log(f"文件上传失败: HTTP {resp.status_code}", "ERROR")
        log(f"响应: {resp.text[:500]}", "ERROR")
        sys.exit(1)
    log(f"文件上传成功 (objectId: {object_id})", "OK")
    return object_id


def update_app_package_info(app_id, headers, file_name, object_id):
    """向 AGC 登记软件包信息（PUT /api/publish/v3/app-package-info）

    注意：这是上传 .app 包的正确接口。
    app-file-info 是给图标/截图等素材文件用的，不是给 .app 包用的。
    """
    log("正在更新 AGC 应用软件包信息...", "STEP")
    body = {
        "objectId": object_id,
        "fileName": file_name,
    }
    resp = requests.put(
        APP_PACKAGE_INFO_URL,
        params={"appId": app_id},
        json=body,
        headers=headers,
        timeout=30,
    )
    if resp.status_code == 403:
        handle_403("更新软件包信息")
        sys.exit(1)
    if resp.status_code != 200:
        log(f"更新软件包信息失败: HTTP {resp.status_code}", "ERROR")
        log(f"响应: {resp.text[:500]}", "ERROR")
        sys.exit(1)
    data = resp.json()
    ret = data.get("ret", {})
    if ret.get("code") != 0:
        log(f"更新软件包信息业务错误: {ret}", "ERROR")
        sys.exit(1)
    package_id = data.get("packageId", "")
    log(f"应用软件包信息更新成功 (packageId: {package_id})", "OK")
    return package_id

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    file_path = os.path.abspath(sys.argv[1])
    project_root = os.path.abspath(sys.argv[2]) if len(sys.argv) >= 3 else None

    if not os.path.exists(file_path):
        log(f"文件不存在: {file_path}", "ERROR")
        sys.exit(1)
    if not file_path.endswith(".app"):
        log(f"⚠️  文件后缀不是 .app: {file_path}", "WARN")

    file_size = os.path.getsize(file_path)
    print()
    print("=" * 60)
    print("  AGC 上传 - HarmonyOS .app")
    print("=" * 60)
    log(f"目标文件: {file_path}")
    log(f"文件大小: {file_size / 1024 / 1024:.1f} MB")
    print()

    app_id, client_id, _secret, _token, headers = bootstrap(project_root)
    print()

    sha256 = get_file_sha256(file_path)
    print()

    upload_info = get_upload_url(app_id, headers, file_path, sha256, file_size)
    print()

    object_id = upload_file_to_obs(upload_info, file_path, file_size)
    print()

    update_app_package_info(app_id, headers, os.path.basename(file_path), object_id)
    print()

    print("=" * 60)
    log("上传完成 ✅", "OK")
    log("如需提审，运行 submit_review.py（带 AGC_CONFIRM_SUBMIT=YES）", "INFO")
    print("=" * 60)


if __name__ == "__main__":
    main()
