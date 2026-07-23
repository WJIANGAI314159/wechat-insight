#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
push_to_github.py - 通过 GitHub API 上传项目代码
不需要安装 git，只需要 GitHub 账号和 Personal Access Token
"""

import os
import json
import base64
import ssl
import time
import urllib.request
import urllib.error
import sys

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
FILES = [
    'app.py', 'searcher.py', 'analyzer.py', 'db.py',
    'deploy.sh', 'requirements.txt', '.gitignore',
    'Procfile', 'render.yaml', 'start.py', 'proxies.txt',
    'README.md', 'push_to_github.py'
]
REPO_NAME = 'wechat-insight'


def github_api(method, path, token, data=None, max_retries=3):
    """调用 GitHub API，带重试和更稳定的 SSL 配置"""
    url = f"https://api.github.com{path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "wechat-insight-deploy",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode() if data else None

    # 使用更稳定的 TLS 上下文
    ctx = ssl.create_default_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2

    for attempt in range(max_retries):
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
                return json.loads(resp.read().decode()), resp.status
        except urllib.error.HTTPError as e:
            try:
                error_data = json.loads(e.read().decode())
            except Exception:
                error_data = {"message": str(e)}
            # 对可重试错误进行等待后重试
            if attempt < max_retries - 1 and e.code in (500, 502, 503, 504, 403):
                wait = 2 ** attempt
                print(f"      ⚠️  {method} {path} HTTP {e.code}，{wait}s 后重试 ({attempt+1}/{max_retries})...")
                time.sleep(wait)
                continue
            return error_data, e.code
        except Exception as e:
            msg = str(e)
            if attempt < max_retries - 1 and ("EOF" in msg or "Connection" in msg or "reset" in msg or "timeout" in msg.lower()):
                wait = 2 ** attempt
                print(f"      ⚠️  {method} {path} 网络错误，{wait}s 后重试 ({attempt+1}/{max_retries})...")
                time.sleep(wait)
                continue
            return {"message": msg}, 0

    return {"message": "超过最大重试次数"}, 0


def main():
    print()
    print("=" * 55)
    print("  上传代码到 GitHub（不需要安装 git）")
    print("=" * 55)
    print()
    print("如果你还没有 GitHub Personal Access Token，请按以下步骤创建：")
    print("  1. 打开 https://github.com/settings/tokens")
    print("  2. 点「Generate new token (classic)」")
    print("  3. Note 填: wechat-insight")
    print("  4. Expiration 选: 30 days")
    print("  5. 勾选: repo（第一个选项，全选）")
    print("  6. 点「Generate token」")
    print("  7. 复制生成的 token（只显示一次！）")
    print()

    username = input("GitHub 用户名: ").strip()
    token = input("Personal Access Token: ").strip()

    if not username or not token:
        print("❌ 用户名和 Token 不能为空")
        return

    # 1. 创建仓库
    print(f"\n[1/3] 创建 GitHub 仓库 {REPO_NAME}...")
    result, status = github_api("POST", "/user/repos", token, {
        "name": REPO_NAME,
        "description": "微信公众号深度研究工具",
        "private": False,
        "auto_init": False,
    })

    if status == 201:
        print(f"  ✅ 仓库已创建")
    elif status == 422:
        print(f"  ⚠️  仓库已存在，将直接上传文件")
    else:
        msg = result.get("message", "未知错误") if isinstance(result, dict) else str(result)
        print(f"  ❌ 创建仓库失败: {msg}")
        if "Bad credentials" in str(msg):
            print("     Token 不正确，请检查")
        return

    # 2. 上传文件
    print(f"\n[2/3] 上传 {len(FILES)} 个文件...")
    success_count = 0
    failed_files = []

    for i, filename in enumerate(FILES, 1):
        filepath = os.path.join(PROJECT_DIR, filename)
        if not os.path.exists(filepath):
            print(f"  [{i}/{len(FILES)}] ⏭️  {filename}（跳过，文件不存在）")
            continue

        file_size = os.path.getsize(filepath)
        print(f"  [{i}/{len(FILES)}] 准备上传 {filename} ({file_size} bytes)...")

        with open(filepath, 'rb') as f:
            content = base64.b64encode(f.read()).decode()

        # 先检查文件是否已存在（需要 SHA 才能更新）
        existing, existing_status = github_api("GET", f"/repos/{username}/{REPO_NAME}/contents/{filename}", token)

        data = {
            "message": f"Update {filename}",
            "content": content,
        }
        if isinstance(existing, dict) and existing.get("sha"):
            data["sha"] = existing["sha"]

        result, status = github_api(
            "PUT",
            f"/repos/{username}/{REPO_NAME}/contents/{filename}",
            token,
            data
        )

        # 如果失败是因为 sha 缺失，说明文件已存在但 GET 时没拿到 sha，再试一次
        if status == 422 and not data.get("sha"):
            print(f"      ⚠️  缺少 sha，重新获取后重试...")
            existing, _ = github_api("GET", f"/repos/{username}/{REPO_NAME}/contents/{filename}", token, max_retries=5)
            if isinstance(existing, dict) and existing.get("sha"):
                data["sha"] = existing["sha"]
                data["message"] = f"Retry update {filename}"
                result, status = github_api(
                    "PUT",
                    f"/repos/{username}/{REPO_NAME}/contents/{filename}",
                    token,
                    data
                )

        if status in (200, 201):
            print(f"  [{i}/{len(FILES)}] ✅ {filename}")
            success_count += 1
        else:
            msg = result.get("message", "未知错误") if isinstance(result, dict) else str(result)
            print(f"  [{i}/{len(FILES)}] ❌ {filename}: {msg}")
            failed_files.append((filename, content))

        # 上传间隔，避免触发限流
        time.sleep(0.5)

    # 对失败的文件再做一次兜底重试
    if failed_files:
        print(f"\n  对 {len(failed_files)} 个失败文件进行兜底重试...")
        for filename, content in failed_files:
            existing, _ = github_api("GET", f"/repos/{username}/{REPO_NAME}/contents/{filename}", token, max_retries=5)
            data = {"message": f"Retry update {filename}", "content": content}
            if isinstance(existing, dict) and existing.get("sha"):
                data["sha"] = existing["sha"]
            result, status = github_api(
                "PUT",
                f"/repos/{username}/{REPO_NAME}/contents/{filename}",
                token,
                data
            )
            if status in (200, 201):
                print(f"    ✅ {filename} 重试成功")
                success_count += 1
            else:
                msg = result.get("message", "未知错误") if isinstance(result, dict) else str(result)
                print(f"    ❌ {filename} 重试仍失败: {msg}")

    # 3. 完成
    print(f"\n[3/3] 完成！成功上传 {success_count}/{len(FILES)} 个文件")
    print()
    print(f"  仓库地址: https://github.com/{username}/{REPO_NAME}")
    print()
    print("  接下来在腾讯云服务器上更新代码：")
    print(f"    cd /opt/wechat-insight")
    print(f"    git pull")
    print(f"    supervisorctl restart wechat-insight")
    print()
    print("  如果是新服务器（首次部署）：")
    print(f"    sudo su")
    print(f"    git clone https://github.com/{username}/{REPO_NAME}.git /opt/wechat-insight")
    print(f"    cd /opt/wechat-insight && bash deploy.sh")
    print()


if __name__ == "__main__":
    main()
