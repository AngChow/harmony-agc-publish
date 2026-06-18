#!/usr/bin/env python3
"""
Step 1: 签名配置检查与自动切换

解析 build-profile.json5 中的 signingConfigs，检测当前是调试还是发布证书。
如果是调试证书，自动改写为发布证书路径。

用法:
  python3 check_signing.py <project_dir>

退出码:
  0 = 已是发布配置 / 已自动切换为发布配置
  1 = 切换失败
"""

import os
import re
import sys

# ============================================================
# 证书路径配置 —— 请根据你的实际环境修改
# ============================================================
KEYSTORE_DIR = os.environ.get(
    "HARMONY_KEYSTORE_DIR",
    os.path.expanduser("~/develop/keystore/harmony"),
)

KEYSTORE_FILE = os.path.join(KEYSTORE_DIR, os.environ.get("HARMONY_KEYSTORE_FILE", "release.p12"))

RELEASE_PROFILE = os.path.join(KEYSTORE_DIR, os.environ.get("HARMONY_RELEASE_PROFILE", "Release.p7b"))
RELEASE_CERT    = os.path.join(KEYSTORE_DIR, os.environ.get("HARMONY_RELEASE_CERT",    "Release.cer"))

# 调试证书（用于检测当前是否为调试模式，不需要太精确）
DEBUG_KEYWORDS = ["调试", "Debug", "debug"]
RELEASE_KEYWORDS = ["发布", "Release", "release"]

# ============================================================
# JSON5 简易解析
# ============================================================
def strip_json5(text):
    """去除 JSON5 注释和尾逗号"""
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    text = re.sub(r'//[^\n]*', '', text)
    text = re.sub(r',\s*([}\]])', r'\1', text)
    return text


def read_build_profile(project_dir):
    path = os.path.join(project_dir, "build-profile.json5")
    if not os.path.exists(path):
        print(f"❌ 找不到 build-profile.json5: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def detect_signing_type(content):
    """检测当前签名配置是调试还是发布"""
    has_debug = any(kw in content for kw in DEBUG_KEYWORDS)
    has_release = any(kw in content for kw in RELEASE_KEYWORDS)
    if has_debug and not has_release:
        return "debug"
    if has_release and not has_debug:
        return "release"
    # 两者都有时，看 profile 路径
    profile_match = re.search(r'"profile"\s*:\s*"([^"]+)"', content)
    if profile_match:
        profile_path = profile_match.group(1)
        if any(kw in profile_path for kw in DEBUG_KEYWORDS):
            return "debug"
        if any(kw in profile_path for kw in RELEASE_KEYWORDS):
            return "release"
    return "unknown"


def switch_to_release(content):
    """将签名配置中的 profile 和 certpath 替换为发布证书路径"""
    changes = []

    # 替换 profile 路径
    new_content = re.sub(
        r'("profile"\s*:\s*")([^"]+)(")',
        lambda m: f'{m.group(1)}{RELEASE_PROFILE}{m.group(3)}',
        content,
    )
    if new_content != content:
        changes.append(f"profile -> {RELEASE_PROFILE}")
        content = new_content

    # 替换 certpath 路径
    new_content = re.sub(
        r'("certpath"\s*:\s*")([^"]+)(")',
        lambda m: f'{m.group(1)}{RELEASE_CERT}{m.group(3)}',
        content,
    )
    if new_content != content:
        changes.append(f"certpath -> {RELEASE_CERT}")
        content = new_content

    # 替换 keystore 路径（store文件路径，如果存在）
    new_content = re.sub(
        r'("storeFile"\s*:\s*")([^"]+)(")',
        lambda m: f'{m.group(1)}{KEYSTORE_FILE}{m.group(3)}',
        content,
    )
    if new_content != content:
        changes.append(f"storeFile -> {KEYSTORE_FILE}")
        content = new_content

    return content, changes


def main():
    project_dir = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    print(f"项目目录: {project_dir}")

    raw = read_build_profile(project_dir)

    # 检测当前签名类型
    signing_type = detect_signing_type(raw)

    if signing_type == "release":
        print("✅ 已配置发布证书和 Profile，无需切换")
        sys.exit(0)

    if signing_type == "debug":
        print("⚠️  当前使用调试证书/Profile，正在切换为发布证书...")
        new_content, changes = switch_to_release(raw)

        if not changes:
            print("⚠️  未检测到需要替换的路径字段，请手动检查 build-profile.json5")
            sys.exit(1)

        # 写回文件
        profile_path = os.path.join(project_dir, "build-profile.json5")
        with open(profile_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        print("✅ 已切换为发布证书和 Profile")
        for change in changes:
            print(f"   {change}")
        sys.exit(0)

    print("⚠️  无法确定当前签名类型，请手动检查 build-profile.json5")
    sys.exit(1)


if __name__ == "__main__":
    main()
