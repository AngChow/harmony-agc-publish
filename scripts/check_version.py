#!/usr/bin/env python3
"""
版本号检查：对比本地项目版本与 AGC 在架版本。
本地 versionCode 必须 > 在架 versionCode 才能继续。

用法:
  python3 check_version.py <project_dir>

退出码:
  0 = 版本号检查通过
  1 = 版本号不满足要求（<= 在架版本）
  2 = 查询 AGC 失败
"""
import sys, os, re, json, subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def strip_json5(text):
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    text = re.sub(r'//[^\n]*', '', text)
    text = re.sub(r',\s*([}\]])', r'\1', text)
    return text

def parse_json5(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.loads(strip_json5(f.read()))

def get_local_version(project_dir):
    """从 app.json5 读取 versionCode 和 versionName"""
    app_json5 = os.path.join(project_dir, "AppScope", "app.json5")
    if not os.path.exists(app_json5):
        app_json5 = os.path.join(project_dir, "entry", "src", "main", "module.json5")
    data = parse_json5(app_json5)
    app = data.get("app", data)
    return {
        "versionCode": app.get("versionCode", 0),
        "versionName": app.get("versionName", "0.0.0"),
    }

def query_agc_shelf_version(project_dir):
    """调用 query_app_info.py 查询 AGC 在架版本（自动从 project_dir/.agc_env 加载凭据）"""
    query_script = os.path.join(SCRIPT_DIR, "query_app_info.py")
    result = subprocess.run(
        [sys.executable, query_script, project_dir],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        return None, result.stderr
    data = json.loads(result.stdout)
    if data.get("ret", {}).get("code") != 0:
        return None, json.dumps(data.get("ret", {}))
    app_info = data.get("appInfo", {})
    return {
        "onShelfVersionCode": app_info.get("onShelfVersionCode", 0),
        "onShelfVersionNumber": app_info.get("onShelfVersionNumber", "0.0.0"),
        "versionCode": app_info.get("versionCode", 0),
        "versionNumber": app_info.get("versionNumber", "0.0.0"),
    }, None

def main():
    project_dir = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    print(f"项目目录: {project_dir}")
    print()

    # 1. 读取本地版本
    local = get_local_version(project_dir)
    print(f"本地版本: versionCode={local['versionCode']}, versionName={local['versionName']}")

    # 2. 查询 AGC 在架版本
    agc, err = query_agc_shelf_version(project_dir)
    if err:
        print(f"❌ 查询 AGC 应用信息失败: {err}")
        sys.exit(2)
    print(f"AGC 在架版本: versionCode={agc['onShelfVersionCode']}, versionName={agc['onShelfVersionNumber']}")
    print(f"AGC 最新提交版本: versionCode={agc['versionCode']}, versionName={agc['versionNumber']}")
    print()

    # 3. 比较版本号
    if local['versionCode'] <= agc['onShelfVersionCode']:
        print(f"❌ 版本号检查未通过！")
        print(f"   本地 versionCode ({local['versionCode']}) <= 在架 versionCode ({agc['onShelfVersionCode']})")
        print(f"   请先升级项目版本号后再打包上传。")
        sys.exit(1)
    else:
        print(f"✅ 版本号检查通过！")
        print(f"   本地 versionCode ({local['versionCode']}) > 在架 versionCode ({agc['onShelfVersionCode']})")
        sys.exit(0)

if __name__ == "__main__":
    main()
