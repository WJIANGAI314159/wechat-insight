#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信公众号深度研究工具 - 启动脚本

本地使用:
  python start.py               # 默认端口 5000
  python start.py --port 8080   # 指定端口

Render.com 部署:
  不需要此文件，直接用 gunicorn app:app
"""

import os
import sys

project_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_dir)

from app import app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    if '--port' in sys.argv:
        idx = sys.argv.index('--port')
        if idx + 1 < len(sys.argv):
            port = int(sys.argv[idx + 1])

    print("=" * 60)
    print("  微信公众号深度研究工具")
    print(f"  访问地址: http://localhost:{port}")
    print("=" * 60)
    app.run(host='0.0.0.0', port=port, debug=False)
