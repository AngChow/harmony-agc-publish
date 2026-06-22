#!/usr/bin/env python3
"""
Step 3.5: 上传鸿蒙符号表到 Bugly

在 Step 3 (打包) 完成后调用，自动定位构建产物中的符号表文件，
通过 Bugly jar 工具上传到 Bugly 平台。

用法:
  python3 upload_bugly_symbol.py <project_root>

前置条件:
  1. 已完成 Release 打包 (Step 3)
  2. project_root/.bugly_env 包含 BUGLY_APP_ID / BUGLY_APP_KEY
  3. 本机有 Java 8+ 环境

退出码:
  0 = 上传成功（或非严格模式下上传失败）
  1 = 严格模式下上传失败 / 凭据缺失 / Java 不可用 / 无符号表文件
"""

import os
import sys
import re
import json
import glob
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _bugly_common import (  # noqa: E402
    log, load_bugly_env, get_bugly_credentials, get_jar_path,
    check_java, BUGLY_JAR_VERSION,
)


# ============================================================
# JSON5 解析（与 check_version.py 保持一致）
# ============================================================
def strip_json5(text):
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    text = re.sub(r'//[^\n]*', '', text)
    text = re.sub(r',\s*([}\]])', r'\1', text)
    return text


def parse_json5(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.loads(strip_json5(f.read()))


# ============================================================
# 读取版本信息
# ============================================================
def get_app_version(project_root):
    """从 AppScope/app.json5 读取 versionName 和 versionCode"""
    app_json5 = Path(project_root) / "AppScope" / "app.json5"
    if not app_json5.exists():
        app_json5 = Path(project_root) / "entry" / "src" / "main" / "module.json5"
    if not app_json5.exists():
        log(f"找不到 app.json5: {app_json5}", "ERROR")
        sys.exit(1)
    data = parse_json5(str(app_json5))
    app = data.get("app", data)
    version_name = str(app.get("versionName", "0.0.0"))
    version_code = str(app.get("versionCode", "1"))
    log(f"应用版本: versionName={version_name}, versionCode={version_code}", "INFO")
    return version_name, version_code


# ============================================================
# 定位 Module 列表
# ============================================================
def get_modules(project_root):
    """从 build-profile.json5 读取所有 module 名称"""
    build_profile = Path(project_root) / "build-profile.json5"
    modules = []
    if build_profile.exists():
        try:
            data = parse_json5(str(build_profile))
            module_list = data.get("modules", [])
            for m in module_list:
                name = m.get("name", "")
                src_path = m.get("srcPath", "")
                if name:
                    modules.append({"name": name, "srcPath": src_path})
        except Exception as e:
            log(f"解析 build-profile.json5 失败: {e}", "WARN")

    # 兜底：如果没解析到，用默认 entry
    if not modules:
        modules = [{"name": "entry", "srcPath": "entry"}]

    log(f"发现 {len(modules)} 个 Module: {[m['name'] for m in modules]}", "INFO")
    return modules


# ============================================================
# 定位符号表文件
# ============================================================
def find_debug_so_dirs(project_root, modules):
    """
    查找 Debug SO 文件目录。
    路径模式: <Module>/build/default/intermediates/cmake/default/obj/<架构>/
    """
    so_dirs = []
    for mod in modules:
        mod_name = mod["name"]
        # 模块的 build 目录可能在 srcPath 下或直接以模块名命名
        mod_build = Path(project_root) / mod_name / "build"
        if not mod_build.exists():
            mod_build = Path(project_root) / mod.get("srcPath", mod_name) / "build"
        if not mod_build.exists():
            continue

        # 查找 cmake 产物
        cmake_obj_pattern = str(mod_build / "default" / "intermediates" / "cmake" / "default" / "obj" / "*")
        arch_dirs = glob.glob(cmake_obj_pattern)
        for arch_dir in arch_dirs:
            so_files = glob.glob(os.path.join(arch_dir, "*.so"))
            if so_files:
                so_dirs.append(arch_dir)
                log(f"  Module [{mod_name}] 发现 Debug SO: {arch_dir} ({len(so_files)} 个 .so)", "OK")

    if not so_dirs:
        log("未找到 Debug SO 文件（项目可能无 Native C/C++ 代码或未使用 CMake）", "WARN")
    return so_dirs


def find_mapping_files(project_root, modules):
    """
    查找 nameCache.json 和 sourceMaps.json 文件。
    路径模式:
      nameCache: <Module>/build/default/cache/default/default@CompileArkTs/esmodule/release/obfuscation/nameCache.json
      sourceMaps: <Module>/build/default/cache/default/default@CompileArkTs/esmodule/release/sourceMaps.json
    """
    mapping_files = []  # 存储所有找到的 mapping 文件路径

    for mod in modules:
        mod_name = mod["name"]
        mod_build = Path(project_root) / mod_name / "build"
        if not mod_build.exists():
            mod_build = Path(project_root) / mod.get("srcPath", mod_name) / "build"
        if not mod_build.exists():
            continue

        # 查找 cache 目录下的 mapping 文件
        cache_base = mod_build / "default" / "cache" / "default"
        # 使用 glob 匹配 default@CompileArkTs 目录（可能名字有变化）
        compile_dirs = glob.glob(str(cache_base / "*ompile*rk*" / "esmodule" / "release"))
        if not compile_dirs:
            # 尝试不带 esmodule 的路径
            compile_dirs = glob.glob(str(cache_base / "*ompile*rk*" / "*" / "release"))

        for compile_dir in compile_dirs:
            # nameCache.json
            namecache_path = os.path.join(compile_dir, "obfuscation", "nameCache.json")
            if os.path.exists(namecache_path):
                mapping_files.append(namecache_path)
                log(f"  Module [{mod_name}] 发现 nameCache.json: {namecache_path}", "OK")

            # sourceMaps.json
            sourcemaps_path = os.path.join(compile_dir, "sourceMaps.json")
            if os.path.exists(sourcemaps_path):
                mapping_files.append(sourcemaps_path)
                log(f"  Module [{mod_name}] 发现 sourceMaps.json: {sourcemaps_path}", "OK")

    if not mapping_files:
        log("未找到 nameCache.json / sourceMaps.json（项目可能未开启代码混淆）", "WARN")

    return mapping_files


# ============================================================
# 准备上传目录
# ============================================================
import tempfile
import shutil


def prepare_upload_dirs(so_dirs, mapping_files):
    """
    Bugly jar 工具的 -inputSymbol 和 -inputMapping 接受的是目录路径。
    将找到的文件整理到临时目录中。
    """
    tmp_base = Path(tempfile.mkdtemp(prefix="bugly_symbol_"))

    # 准备 symbol 目录（放 debug so）
    symbol_dir = tmp_base / "symbol"
    symbol_dir.mkdir()

    # 准备 mapping 目录（放 nameCache/sourceMaps）
    mapping_dir = tmp_base / "mapping"
    mapping_dir.mkdir()

    # 复制 debug so 到 symbol 目录
    has_symbol = False
    for so_dir in so_dirs:
        for so_file in glob.glob(os.path.join(so_dir, "*.so")):
            shutil.copy2(so_file, symbol_dir / os.path.basename(so_file))
            has_symbol = True

    # 复制 mapping 文件到 mapping 目录
    has_mapping = False
    for mf in mapping_files:
        shutil.copy2(mf, mapping_dir / os.path.basename(mf))
        has_mapping = True

    return str(symbol_dir), str(mapping_dir), has_symbol, has_mapping, tmp_base


# ============================================================
# 上传符号表
# ============================================================
def upload_to_bugly(jar_path, app_id, app_key, version, version_code,
                    symbol_dir, mapping_dir, has_symbol, has_mapping):
    """
    调用 Bugly jar 工具上传符号表。
    Harmony 平台需要 LLVM_USE=true。
    """
    cmd = [
        "java", "-jar", jar_path,
        "-appid", app_id,
        "-appkey", app_key,
        "-version", version,
        "-platform", "Harmony",
        "-buildNo", version_code,
    ]

    if has_symbol:
        cmd.extend(["-inputSymbol", symbol_dir])
    if has_mapping:
        cmd.extend(["-inputMapping", mapping_dir])

    log(f"执行命令: {' '.join(cmd[:4])}... -platform Harmony ...", "STEP")
    log(f"  完整参数: -appid {app_id} -version {version} -buildNo {version_code}", "INFO")
    log(f"  -inputSymbol: {symbol_dir if has_symbol else '(无)'}", "INFO")
    log(f"  -inputMapping: {mapping_dir if has_mapping else '(无)'}", "INFO")

    # Harmony 必须设置 LLVM_USE=true（Dwarf 5 格式支持）
    env = os.environ.copy()
    env["LLVM_USE"] = "true"

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        timeout=600,  # 10 分钟超时
    )

    # 合并 stdout + stderr 用于输出和判断
    full_output = result.stdout + result.stderr

    # 打印 jar 输出
    for line in full_output.strip().splitlines():
        if line.strip():
            if "##[error]" in line or "Exception" in line or "error" in line.lower():
                log(f"  [jar] {line.strip()}", "ERROR")
            elif "##[info]" in line:
                log(f"  [jar] {line.strip()}", "INFO")
            else:
                log(f"  [jar] {line.strip()}")

    # 判断成功/失败
    # Bugly jar 的 ##[error] 不一定代表整体失败：
    #   - 非致命错误（如某个 SO 文件不合法）会输出 ##[error] 但继续上传其他文件
    #   - 真正的成功标志是输出中包含 "上传成功"
    #   - 真正的失败标志是输出中包含 "上传符号表出错" 或 "上传失败"（且没有"上传成功"）
    has_upload_success = "上传成功" in full_output
    has_upload_failure = "上传符号表出错" in full_output or "上传失败" in full_output
    has_error = has_upload_failure and not has_upload_success
    has_success = has_upload_success

    return result.returncode, has_error, has_success, full_output


# ============================================================
# 主流程
# ============================================================
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    project_root = os.path.abspath(sys.argv[1])

    print()
    print("=" * 60)
    print("  Bugly 符号表上传 - HarmonyOS")
    print("=" * 60)
    log(f"项目目录: {project_root}")
    print()

    # 1. 加载 .bugly_env
    if not load_bugly_env(project_root):
        log("未找到 .bugly_env 文件，跳过 Bugly 符号表上传", "WARN")
        log("如需上传符号表，请在项目根目录创建 .bugly_env（参考 SKILL.md）", "INFO")
        sys.exit(0)

    # 2. 获取凭据
    app_id, app_key = get_bugly_credentials()
    log(f"Bugly App ID: {app_id}", "OK")
    print()

    # 3. 检查 Java
    if not check_java():
        log("Java 环境不可用，无法上传符号表", "ERROR")
        if os.environ.get("BUGLY_STRICT", "").upper() == "YES":
            sys.exit(1)
        sys.exit(0)

    # 4. 检查/定位 jar
    jar_path = get_jar_path()
    if not jar_path:
        log("Bugly jar 工具不可用，跳过符号表上传", "ERROR")
        if os.environ.get("BUGLY_STRICT", "").upper() == "YES":
            sys.exit(1)
        sys.exit(0)
    print()

    # 5. 读取版本信息
    version_name, version_code = get_app_version(project_root)
    print()

    # 6. 定位 Module 列表
    modules = get_modules(project_root)
    print()

    # 7. 定位符号表文件
    log("正在扫描符号表文件...", "STEP")
    so_dirs = find_debug_so_dirs(project_root, modules)
    mapping_files = find_mapping_files(project_root, modules)
    print()

    if not so_dirs and not mapping_files:
        log("未找到任何符号表文件，请确认已完成 Release 打包", "ERROR")
        if os.environ.get("BUGLY_STRICT", "").upper() == "YES":
            sys.exit(1)
        sys.exit(0)

    # 8. 准备上传目录
    log("正在准备上传目录...", "STEP")
    symbol_dir, mapping_dir, has_symbol, has_mapping, tmp_base = prepare_upload_dirs(
        so_dirs, mapping_files
    )
    log(f"临时目录: {tmp_base}", "INFO")
    log(f"Symbol 目录: {symbol_dir} ({'有文件' if has_symbol else '空'})", "INFO")
    log(f"Mapping 目录: {mapping_dir} ({'有文件' if has_mapping else '空'})", "INFO")
    print()

    # 9. 上传
    log("开始上传符号表到 Bugly...", "STEP")
    print()
    ret_code, has_error, has_success, output = upload_to_bugly(
        jar_path, app_id, app_key, version_name, version_code,
        symbol_dir, mapping_dir, has_symbol, has_mapping
    )
    print()

    # 10. 清理临时目录
    shutil.rmtree(tmp_base, ignore_errors=True)

    # 清理 Bugly jar 在项目目录下创建的 buglybin 临时目录
    buglybin = Path(project_root) / 'buglybin'
    if buglybin.exists():
        shutil.rmtree(buglybin, ignore_errors=True)
        log('已清理 buglybin 临时目录', 'INFO')

    # 11. 结果判断
    strict = os.environ.get("BUGLY_STRICT", "").upper() == "YES"

    if has_success and not has_error:
        print("=" * 60)
        log("Bugly 符号表上传成功 ✅", "OK")
        log(f"  版本: {version_name} (buildNo: {version_code})", "INFO")
        print("=" * 60)
        sys.exit(0)

    if has_error:
        log("Bugly 符号表上传失败 ❌", "ERROR")
        log(f"  版本: {version_name} (buildNo: {version_code})", "ERROR")
        if strict:
            sys.exit(1)
        else:
            log("非严格模式，不中断流程（设置 BUGLY_STRICT=YES 可改为阻塞）", "WARN")
            sys.exit(0)

    # ret_code 为 0 但没有明确的 success 标志，视为成功
    if ret_code == 0:
        print("=" * 60)
        log("Bugly 符号表上传完成（退出码 0）✅", "OK")
        print("=" * 60)
        sys.exit(0)
    else:
        log(f"Bugly jar 退出码非零: {ret_code}", "ERROR")
        if strict:
            sys.exit(1)
        else:
            log("非严格模式，不中断流程", "WARN")
            sys.exit(0)


if __name__ == "__main__":
    main()
