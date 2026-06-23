#!/usr/bin/env python3
"""
Step 1: 签名配置检查与自动切换

支持两种 build-profile.json5 格式：

1. 双签名配置（推荐）：
   - signingConfigs 包含 "debug" 和 "release" 两个独立配置
   - products[].signingConfig 引用其中一个
   - 切换方式：将 products[].signingConfig 从 "debug" 改为 "release"

2. 单签名配置（兼容旧格式）：
   - signingConfigs 只有一个配置
   - 通过 profile/certpath 路径关键词判断当前是调试还是发布
   - 切换方式：替换 profile 和 certpath 路径

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
import json

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


def parse_json5(text):
    """解析 JSON5 文本为 dict"""
    return json.loads(strip_json5(text))


def read_build_profile(project_dir):
    path = os.path.join(project_dir, "build-profile.json5")
    if not os.path.exists(path):
        print(f"❌ 找不到 build-profile.json5: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


# ============================================================
# 双签名配置模式（推荐）
# ============================================================
def has_dual_signing_configs(data):
    """
    检测 build-profile.json5 是否包含 "debug" 和 "release" 两套独立签名配置。
    """
    configs = data.get("app", {}).get("signingConfigs", [])
    names = {c.get("name", "") for c in configs}
    return "debug" in names and "release" in names


def get_active_signing_config(data):
    """
    获取 products 中当前引用的签名配置名称。
    返回第一个 product 的 signingConfig 值。
    """
    products = data.get("app", {}).get("products", [])
    if not products:
        return None
    return products[0].get("signingConfig")


def switch_product_signing_config(raw_text, from_name, to_name):
    """
    在原始文本中将 products[].signingConfig 从 from_name 切换为 to_name。
    只替换 "signingConfig" 字段（该字段仅出现在 products 中），不影响 signingConfigs 定义。
    """
    pattern = re.compile(
        r'("signingConfig"\s*:\s*")' + re.escape(from_name) + r'(")'
    )
    new_text, count = pattern.subn(
        lambda m: f'{m.group(1)}{to_name}{m.group(2)}',
        raw_text,
    )
    return new_text, count


# ============================================================
# 单签名配置模式（兼容旧格式）
# ============================================================
def detect_signing_type_by_path(content):
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


def switch_to_release_by_path(content):
    """
    单配置模式：将签名配置中的 profile 和 certpath 替换为发布证书路径。
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


# ============================================================
# 主流程
# ============================================================
def main():
    project_dir = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    print(f"项目目录: {project_dir}")

    raw = read_build_profile(project_dir)

    # 尝试解析为 JSON5
    try:
        data = parse_json5(raw)
    except json.JSONDecodeError as e:
        print(f"⚠️  build-profile.json5 解析失败: {e}", file=sys.stderr)
        print("   回退到单配置模式（路径关键词检测）", file=sys.stderr)
        data = None

    # ============================================================
    # 模式 1：双签名配置（debug + release 独立配置）
    # ============================================================
    if data and has_dual_signing_configs(data):
        active = get_active_signing_config(data)
        print(f"检测到双签名配置模式（debug + release）")
        print(f"当前 products 引用的签名配置: {active}")

        if active == "release":
            print("✅ 已配置发布证书和 Profile，无需切换")
            sys.exit(0)

        if active == "debug":
            print("⚠️  当前使用调试签名配置，正在切换为发布签名配置...")
            new_content, count = switch_product_signing_config(raw, "debug", "release")

            if count == 0:
                print("⚠️  未找到需要替换的 signingConfig 字段，请手动检查 build-profile.json5")
                sys.exit(1)

            # 写回文件
            profile_path = os.path.join(project_dir, "build-profile.json5")
            with open(profile_path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            print(f"✅ 已将 products[].signingConfig 从 \"debug\" 切换为 \"release\"（{count} 处）")
            sys.exit(0)

        # active 为其他值或 None
        print(f"⚠️  当前 signingConfig 值为 \"{active}\"，无法自动判断类型")
        print("   请手动检查 build-profile.json5 中的 products[].signingConfig")
        sys.exit(1)

    # ============================================================
    # 模式 2：单签名配置（兼容旧格式，通过路径关键词检测）
    # ============================================================
    print("检测到单签名配置模式（路径关键词检测）")
    signing_type = detect_signing_type_by_path(raw)

    if signing_type == "release":
        print("✅ 已配置发布证书和 Profile，无需切换")
        sys.exit(0)

    if signing_type == "debug":
        print("⚠️  当前使用调试证书/Profile，正在切换为发布证书...")
        new_content, changes = switch_to_release_by_path(raw)

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
