# 微信公众号深度研究工具 - 部署指南

## 本地运行

```bash
cd wechat-insight
pip install flask jieba
python start.py
# 访问 http://localhost:5000
```

## Render.com 免费版部署（推荐）

### 第一步：推送到 GitHub

1. 在 GitHub 创建一个新仓库（如 `wechat-insight`）
2. 把 `wechat-insight/` 目录下的所有文件推上去：

```bash
cd wechat-insight
git init
git add .
git commit -m "微信公众号深度研究工具"
git remote add origin https://github.com/你的用户名/wechat-insight.git
git push -u origin main
```

### 第二步：在 Render.com 创建服务

1. 打开 https://render.com 注册/登录
2. 点击 **New** → **Web Service**
3. 连接你的 GitHub 账号，选择 `wechat-insight` 仓库
4. 填写配置：
   - **Name**: `wechat-insight`（或你喜欢的名字）
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 180`
   - **Plan**: Free
5. 点击 **Create Web Service**
6. 等待构建完成（约2-3分钟）

### 第三步：获取公网地址

部署完成后，Render 会给你一个地址，类似：
```
https://wechat-insight-xxxx.onrender.com
```

把这个地址发给朋友，他们直接打开就能用。

## 功能说明

- **关键词搜索**：输入关键词，全网搜索微信公众号文章
- **自动分析**：生成研究概述、关键发现、关键词热度、来源分布、时间趋势
- **历史报告**：每次搜索自动保存，可随时回看（点击右上角"📋 历史报告"）
- **搜索缓存**：相同关键词6小时内直接返回缓存，减少反爬触发
- **异步搜索**：后台搜索+前端轮询，兼容 Render 30秒超时限制

## 注意事项

1. **Render 免费版限制**：
   - 15分钟无访问会休眠，再次访问需等待10-20秒冷启动
   - SQLite 数据在重新部署后会丢失（休眠唤醒不丢失）
   - 如需数据持久化，可升级付费版或接入外部数据库

2. **搜狗反爬**：
   - 短时间频繁搜索可能触发验证码
   - 已内置请求限频和缓存机制缓解
   - 如持续触发，等待几分钟后重试

3. **升级建议**：
   - 如需更稳定的服务，可升级到 Render 付费版（$7/月，无休眠）
   - 如需数据持久化，可接入 Render PostgreSQL 或外部数据库
