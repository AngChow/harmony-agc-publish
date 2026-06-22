"""
harmony-agc-publish skill - Bugly 公共模块
集中处理: .bugly_env 自动加载、Bugly 凭据校验、Java 环境检查、jar 工具管理
"""

import os
import sys
import shutil
import zipfile
import tempfile
from pathlib import Path

import requests

# ============================================================
# 常量
# ============================================================
BUGLY_JAR_VERSION = "v3.4.23"
BUGLY_JAR_DOWNLOAD_URL = (
    "https://bugly.tds.qq.com/docs/assets/files/"
    "buglyqq-upload-symbol-v3.4.23-b6beab55ae31e4b012d4cfe4bc113ba8.zip"
)

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
JAR_DIR = SKILL_DIR / "tools"
JAR_PATH = JAR_DIR / "buglyqq-upload-symbol.jar"


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
    print(f"{color}[{level}]{reset} {msg}", file=sys.stderr)


# ============================================================
# .bugly_env 自动加载
# ============================================================
def load_bugly_env(project_root=None):
    """
    从 project_root/.bugly_env 加载凭据到 os.environ。
    优先使用已有的环境变量（不覆盖外部 export 的值）。
    """
    env_file = None
    if project_root:
        candidate = Path(project_root) / ".bugly_env"
        if candidate.exists():
            env_file = candidate
    else:
        cur = Path.cwd()
        for p in [cur, *cur.parents]:
            candidate = p / ".bugly_env"
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
        os.environ.setdefault(k, v)
    return True


# ============================================================
# 凭据
# ============================================================
def get_bugly_credentials():
    """返回 (app_id, app_key)，缺失则退出"""
    app_id = os.environ.get("BUGLY_APP_ID", "")
    app_key = os.environ.get("BUGLY_APP_KEY", "")
    missing = [k for k, v in {
        "BUGLY_APP_ID": app_id,
        "BUGLY_APP_KEY": app_key,
    }.items() if not v]
    if missing:
        log(f"缺少环境变量: {', '.join(missing)}", "ERROR")
        log("请确认项目根目录有 .bugly_env 文件，且包含 BUGLY_APP_ID / BUGLY_APP_KEY", "ERROR")
        sys.exit(1)
    return app_id, app_key


# ============================================================
# Java 环境检查
# ============================================================
def check_java():
    """检查 Java 是否可用，返回版本字符串"""
    import subprocess
    log("正在检查 Java 环境...", "STEP")
    try:
        result = subprocess.run(
            ["java", "-version"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            log("java -version 返回非零退出码", "ERROR")
            sys.exit(1)
        version_output = result.stderr or result.stdout
        for line in version_output.splitlines():
            if "version" in line:
                log(f"Java 环境: {line.strip()}", "OK")
                return line.strip()
        log("Java 环境检查通过", "OK")
        return version_output.strip()
    except FileNotFoundError:
        log("未找到 java 命令，请安装 Java 8+ 运行环境", "ERROR")
        sys.exit(1)
    except Exception as e:
        log(f"Java 环境检查失败: {e}", "ERROR")
        sys.exit(1)


# ============================================================
# jar 工具管理
# ============================================================
def get_jar_path():
    """
    获取 Bugly 符号表上传 jar 工具路径。
    优先级:
      1. BUGLY_JAR_PATH 环境变量
      2. skill 目录 tools/buglyqq-upload-symbol.jar
      3. 自动下载
    """
    # 1. 环境变量
    env_jar = os.environ.get("BUGLY_JAR_PATH", "")
    if env_jar and Path(env_jar).exists():
        log(f"使用环境变量指定的 jar: {env_jar}", "OK")
        return env_jar

    # 2. skill 目录
    if JAR_PATH.exists():
        log(f"使用 skill 自带 jar: {JAR_PATH}", "OK")
        return str(JAR_PATH)

    # 3. 自动下载
    log(f"未找到 jar 工具，正在自动下载 {BUGLY_JAR_VERSION}...", "STEP")
    return download_jar()


def download_jar():
    """从 Bugly 官网下载 jar 工具"""
    JAR_DIR.mkdir(parents=True, exist_ok=True)

    tmp_dir = Path(tempfile.mkdtemp())
    zip_path = tmp_dir / "bugly-symbol-tool.zip"

    try:
        log(f"正在下载: {BUGLY_JAR_DOWNLOAD_URL}", "STEP")
        resp = requests.get(BUGLY_JAR_DOWNLOAD_URL, timeout=120, stream=True)
        resp.raise_for_status()

        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        with open(zip_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8 * 1024 * 1024):
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = downloaded * 100 / total
                    print(f"\r  下载进度: {downloaded / 1024 / 1024:.1f} / {total / 1024 / 1024:.1f} MB ({pct:.0f}%)",
                          end="", file=sys.stderr)
        print(file=sys.stderr)
        log("下载完成", "OK")

        # 解压
        log("正在解压...", "STEP")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp_dir)

        # 查找 jar 文件
        jar_files = list(tmp_dir.rglob("*.jar"))
        if not jar_files:
            log("解压后未找到 jar 文件", "ERROR")
            sys.exit(1)

        # 复制到 tools 目录
        shutil.copy2(jar_files[0], JAR_PATH)
        log(f"jar 工具已安装到: {JAR_PATH}", "OK")
        return str(JAR_PATH)

    except Exception as e:
        log(f"下载 jar 工具失败: {e}", "ERROR")
        sys.exit(1)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ============================================================
# 便捷调用
# ============================================================
def bootstrap(project_root=None):
    """
    一站式入口：加载 .bugly_env -> 校验凭据 -> 检查 Java -> 获取 jar 路径
    返回 (app_id, app_key, jar_path)
    """
    load_bugly_env(project_root)
    app_id, app_key = get_bugly_credentials()
    check_java()
    jar_path = get_jar_path()
    return app_id, app_key, jar_path
