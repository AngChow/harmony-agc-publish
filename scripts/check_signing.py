#!/usr/bin/env python3
"""
Step 1: 签名配置检查与自动切换

解析 build-profile.json5 中的 signingConfigs，检测当前是调试还是发布证书。
如果是调试证书，自动改写为发布证书路径。

核心逻辑：
- storeFile（.p12 密钥库）在调试和发布时是同一个文件，不替换
- 只替换 profile（.p7b）和 certpath（.cer）
- 自动扫描 keystore 目录下的子目录，找到发布/调试对应的 .p7b 和 .cer 文件

用法:
  python3 check_signing.py <project_dir>

退出码:
  0 = 已是发布配置 / 已自动切换为发布配置
  1 = 切换失败

环境变量（可选覆盖）:
  HARMONY_KEYSTORE_DIR     密钥库根目录（默认 ~/develop/keystore/harmony）
  HARMONY_RELEASE_PROFILE  发布 Profile 文件完整路径
  HARMONY_RELEASE_CERT     发布证书文件完整路径
"""

import os
import re
import sys
import glob

# ============================================================
# 证书路径配置
# ============================================================
KEYSTORE_DIR = os.environ.get(
    "HARMONY_KEYSTORE_DIR",
    os.path.expanduser("~/develop/keystore/harmony"),
)

# 发布/调试关键词（用于匹配子目录和文件名）
RELEASE_KEYWORDS = ["发布", "Release", "release"]
DEBUG_KEYWORDS = ["调试", "Debug", "debug"]


def find_cert_file(suffix, keywords):
    """
    在 KEYSTORE_DIR 下扫描匹配 keywords 的子目录，找到指定后缀的文件。
    例：find_cert_file('.p7b', RELEASE_KEYWORDS) → 在 "发布Profile" 目录下找 .p7b 文件

    优先级：
    1. 环境变量 HARMONY_RELEASE_PROFILE / HARMONY_RELEASE_CERT
    2. KEYSTORE_DIR 下子目录名含 keywords 的目录中的文件
    3. KEYSTORE_DIR 根目录下文件名含 keywords 的文件
    """
    # 1. 环境变量覆盖
    if suffix == '.p7b':
        env_val = os.environ.get("HARMONY_RELEASE_PROFILE")
    elif suffix == '.cer':
        env_val = os.environ.get("HARMONY_RELEASE_CERT")
    else:
        env_val = None
    if env_val and os.path.exists(env_val):
        return env_val

    # 2. 扫描子目录（子目录名含关键词）
    if not os.path.isdir(KEYSTORE_DIR):
        return None
    for entry in sorted(os.listdir(KEYSTORE_DIR)):
        subdir = os.path.join(KEYSTORE_DIR, entry)
        if not os.path.isdir(subdir):
            continue
        if any(kw in entry for kw in keywords):
            for f in sorted(os.listdir(subdir)):
                if f.endswith(suffix) and not f.startswith('.'):
                    return os.path.join(subdir, f)

    # 3. 扫描根目录（文件名含关键词）
    for f in sorted(os.listdir(KEYSTORE_DIR)):
        full = os.path.join(KEYSTORE_DIR, f)
        if not os.path.isfile(full):
            continue
        if f.endswith(suffix) and any(kw in f for kw in keywords):
            return full

    return None


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
    """检测当前签名配置是调试还是发布（基于 profile 和 certpath 路径中的关键词）"""
    # 提取 profile 路径
    profile_match = re.search(r'"profile"\s*:\s*"([^"]+)"', content)
    cert_match = re.search(r'"certpath"\s*:\s*"([^"]+)"', content)

    profile_path = profile_match.group(1) if profile_match else ""
    cert_path = cert_match.group(1) if cert_match else ""

    # 检查路径中是否包含调试/发布关键词
    all_paths = profile_path + " " + cert_path
    has_debug = any(kw in all_paths for kw in DEBUG_KEYWORDS)
    has_release = any(kw in all_paths for kw in RELEASE_KEYWORDS)

    if has_debug and not has_release:
        return "debug"
    if has_release and not has_debug:
        return "release"
    if has_debug and has_release:
        # 两者都有时，以 profile 路径为准
        if any(kw in profile_path for kw in DEBUG_KEYWORDS):
            return "debug"
        if any(kw in profile_path for kw in RELEASE_KEYWORDS):
            return "release"
    return "unknown"


def switch_to_release(content):
    """
    将签名配置中的 profile 和 certpath 替换为发布证书路径。
    不替换 storeFile（.p12 密钥库在调试和发布时是同一个文件）。
    """
    changes = []

    # 查找发布证书文件
    release_profile = find_cert_file('.p7b', RELEASE_KEYWORDS)
    release_cert = find_cert_file('.cer', RELEASE_KEYWORDS)

    if not release_profile:
        print(f"❌ 未在 {KEYSTORE_DIR} 下找到发布 Profile (.p7b) 文件", file=sys.stderr)
        print(f"   请设置环境变量 HARMONY_RELEASE_PROFILE 指定完整路径", file=sys.stderr)
        return content, changes

    if not release_cert:
        print(f"❌ 未在 {KEYSTORE_DIR} 下找到发布证书 (.cer) 文件", file=sys.stderr)
        print(f"   请设置环境变量 HARMONY_RELEASE_CERT 指定完整路径", file=sys.stderr)
        return content, changes

    # 替换 profile 路径
    new_content = re.sub(
        r'("profile"\s*:\s*")([^"]+)(")',
        lambda m: f'{m.group(1)}{release_profile}{m.group(3)}',
        content,
    )
    if new_content != content:
        changes.append(f"profile -> {release_profile}")
        content = new_content

    # 替换 certpath 路径
    new_content = re.sub(
        r'("certpath"\s*:\s*")([^"]+)(")',
        lambda m: f'{m.group(1)}{release_cert}{m.group(3)}',
        content,
    )
    if new_content != content:
        changes.append(f"certpath -> {release_cert}")
        content = new_content

    # 注意：不替换 storeFile，因为 .p12 密钥库在调试和发布时是同一个文件

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
        print("   (storeFile 未修改：.p12 密钥库在调试和发布时共用)")
        sys.exit(0)

    print("⚠️  无法确定当前签名类型，请手动检查 build-profile.json5")
    sys.exit(1)


if __name__ == "__main__":
    main()
