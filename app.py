#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信公众号深度研究工具 - Flask Web服务
提供 Web API 和页面服务，支持报告持久化和搜索缓存
"""

import os
import sys
import json
import time
import re
import uuid
import threading
from flask import Flask, request, jsonify, render_template_string

# 确保模块可导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from searcher import deep_search
from analyzer import analyze_articles
import db

app = Flask(__name__)

# 启动时初始化数据库
db.init_db()

# ========== 异步任务追踪器 ==========
# 内存中存储搜索任务状态（适用于单 worker 的免费部署）
_jobs = {}
_jobs_lock = threading.Lock()


# ========== HTML 前端模板 ==========

HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>微信公众号深度研究工具</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }

:root {
  --primary: #07C160;
  --primary-light: #0AD06E;
  --primary-dark: #05A34E;
  --bg: #f5f7fa;
  --card-bg: #fff;
  --text: #1a1a2e;
  --text-secondary: #666;
  --text-light: #999;
  --border: #e8ecf1;
  --shadow: 0 2px 12px rgba(0,0,0,0.08);
  --shadow-hover: 0 4px 20px rgba(0,0,0,0.12);
  --radius: 12px;
  --radius-sm: 8px;
  --danger: #e74c3c;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
  min-height: 100vh;
}

/* Header */
.header {
  background: linear-gradient(135deg, var(--primary) 0%, #2DC84D 100%);
  color: white;
  padding: 32px 0 24px;
  text-align: center;
  position: relative;
  overflow: hidden;
}
.header::before {
  content: '';
  position: absolute;
  top: -50%; left: -50%;
  width: 200%; height: 200%;
  background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 60%);
  animation: pulse 8s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.05); }
}
.header h1 { font-size: 28px; font-weight: 700; margin-bottom: 8px; position: relative; }
.header p { font-size: 14px; opacity: 0.9; position: relative; }
.header-actions {
  position: absolute;
  top: 20px;
  right: 24px;
  display: flex;
  gap: 8px;
  z-index: 10;
}
.history-btn {
  background: rgba(255,255,255,0.2);
  color: white;
  border: 1px solid rgba(255,255,255,0.3);
  padding: 8px 16px;
  border-radius: 20px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.history-btn:hover {
  background: rgba(255,255,255,0.35);
}

/* Search Box */
.search-section {
  max-width: 720px;
  margin: -20px auto 0;
  padding: 0 20px;
  position: relative;
  z-index: 10;
}
.search-box {
  background: var(--card-bg);
  border-radius: var(--radius);
  box-shadow: var(--shadow-hover);
  padding: 24px;
  display: flex;
  gap: 12px;
  align-items: stretch;
}
.search-input {
  flex: 1;
  padding: 12px 16px;
  border: 2px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 16px;
  transition: border-color 0.2s;
  outline: none;
}
.search-input:focus { border-color: var(--primary); }
.search-input::placeholder { color: var(--text-light); }
.time-select {
  padding: 12px 8px;
  border: 2px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 14px;
  background: white;
  outline: none;
  min-width: 90px;
}
.search-btn {
  padding: 12px 28px;
  background: var(--primary);
  color: white;
  border: none;
  border-radius: var(--radius-sm);
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}
.search-btn:hover { background: var(--primary-light); transform: translateY(-1px); }
.search-btn:active { background: var(--primary-dark); }
.search-btn.loading { opacity: 0.7; pointer-events: none; }
.search-btn.loading::after {
  content: '';
  display: inline-block;
  width: 16px; height: 16px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
  margin-left: 8px;
  vertical-align: middle;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* Main Content */
.container {
  max-width: 720px;
  margin: 24px auto;
  padding: 0 20px;
}

/* Empty State */
.empty-state {
  text-align: center;
  padding: 80px 20px;
  color: var(--text-light);
}
.empty-icon { font-size: 64px; margin-bottom: 16px; opacity: 0.4; }
.empty-text { font-size: 16px; }

/* Error State */
.error-state {
  background: #fff3f3;
  border: 1px solid #ffcdd2;
  border-radius: var(--radius-sm);
  padding: 16px 20px;
  color: #c62828;
  margin-bottom: 16px;
}

/* Cache Badge */
.cache-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: rgba(7,193,96,0.1);
  color: var(--primary-dark);
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 500;
  margin-bottom: 12px;
}

/* Report Card */
.report-card {
  background: var(--card-bg);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 24px;
  margin-bottom: 16px;
  transition: box-shadow 0.2s;
}
.report-card:hover { box-shadow: var(--shadow-hover); }
.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  font-size: 18px;
  font-weight: 600;
}
.card-icon {
  width: 28px; height: 28px;
  background: var(--primary);
  color: white;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
}

/* Summary */
.summary-text {
  font-size: 15px;
  line-height: 1.8;
  color: var(--text);
  padding: 12px 0;
}

/* Key Findings */
.finding-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
}
.finding-item:last-child { border-bottom: none; }
.finding-num {
  background: var(--primary);
  color: white;
  width: 24px; height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}
.finding-text { font-size: 14px; line-height: 1.6; }

/* Source Analysis */
.source-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
}
.source-name { font-size: 14px; font-weight: 500; flex: 1; }
.source-bar-wrap {
  flex: 2;
  height: 8px;
  background: var(--border);
  border-radius: 4px;
  overflow: hidden;
}
.source-bar {
  height: 100%;
  background: var(--primary);
  border-radius: 4px;
  transition: width 0.5s ease;
}
.source-count {
  font-size: 13px;
  color: var(--text-secondary);
  width: 40px;
  text-align: right;
}

/* Keyword Cloud */
.kw-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 0;
}
.kw-tag {
  padding: 6px 12px;
  background: rgba(7,193,96,0.08);
  color: var(--primary-dark);
  border-radius: 20px;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.2s;
}
.kw-tag:hover { background: rgba(7,193,96,0.15); transform: scale(1.05); }
.kw-tag.hot {
  background: var(--primary);
  color: white;
  font-size: 15px;
  font-weight: 600;
}

/* Time Distribution */
.time-chart {
  display: flex;
  align-items: flex-end;
  gap: 4px;
  height: 120px;
  padding: 8px 0;
}
.time-bar-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 30px;
}
.time-bar {
  width: 100%;
  background: var(--primary);
  border-radius: 4px 4px 0 0;
  transition: height 0.5s ease;
  min-height: 4px;
  max-width: 40px;
}
.time-label {
  font-size: 10px;
  color: var(--text-light);
  margin-top: 4px;
  white-space: nowrap;
}
.time-count {
  font-size: 11px;
  color: var(--text-secondary);
  font-weight: 600;
  margin-bottom: 2px;
}

/* Article List */
.article-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 0;
  border-bottom: 1px solid var(--border);
  cursor: default;
  transition: background 0.2s;
}
.article-item:last-child { border-bottom: none; }
.article-item:hover { background: rgba(7,193,96,0.04); }
.article-score {
  background: #f0f0f0;
  color: var(--text-secondary);
  width: 32px; height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}
.article-score.high {
  background: var(--primary);
  color: white;
}
.article-info { flex: 1; }
.article-title {
  font-size: 15px;
  font-weight: 600;
  line-height: 1.5;
  color: var(--text);
  margin-bottom: 4px;
}
.article-title a { color: var(--text); text-decoration: none; }
.article-title a:hover { color: var(--primary); }
.article-meta {
  font-size: 12px;
  color: var(--text-light);
  display: flex;
  gap: 12px;
}
.article-digest {
  font-size: 13px;
  color: var(--text-secondary);
  margin-top: 6px;
  line-height: 1.5;
}

/* Stats Row */
.stats-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.stat-card {
  background: rgba(7,193,96,0.06);
  border-radius: var(--radius-sm);
  padding: 16px;
  text-align: center;
}
.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--primary-dark);
}
.stat-label {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 4px;
}

/* Trend Tag */
.trend-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 500;
}
.trend-tag.up { background: rgba(7,193,96,0.1); color: var(--primary-dark); }
.trend-tag.down { background: rgba(244,67,54,0.1); color: #c62828; }
.trend-tag.flat { background: rgba(0,0,0,0.06); color: var(--text-secondary); }

/* Section Divider */
.section-divider {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 24px 0 16px;
}
.section-divider .dot {
  width: 4px; height: 4px;
  background: var(--primary);
  border-radius: 50%;
}
.section-divider .line { flex: 1; height: 1px; background: var(--border); }
.section-divider .label {
  font-size: 12px;
  color: var(--text-light);
  font-weight: 500;
}

/* History List */
.history-list { margin-top: 16px; }
.history-item {
  background: var(--card-bg);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 20px;
  margin-bottom: 12px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: flex-start;
  gap: 16px;
}
.history-item:hover {
  box-shadow: var(--shadow-hover);
  transform: translateY(-1px);
}
.history-info { flex: 1; }
.history-query {
  font-size: 16px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 4px;
}
.history-meta {
  font-size: 12px;
  color: var(--text-light);
  display: flex;
  gap: 12px;
}
.history-summary {
  font-size: 13px;
  color: var(--text-secondary);
  margin-top: 8px;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.history-delete {
  background: none;
  border: none;
  color: var(--text-light);
  cursor: pointer;
  font-size: 18px;
  padding: 4px 8px;
  border-radius: 4px;
  transition: all 0.2s;
}
.history-delete:hover { color: var(--danger); background: rgba(231,76,60,0.1); }

/* Back Button */
.back-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: none;
  border: none;
  color: var(--primary-dark);
  font-size: 14px;
  cursor: pointer;
  margin-bottom: 16px;
  padding: 8px 0;
}
.back-btn:hover { text-decoration: underline; }

/* Responsive */
@media (max-width: 480px) {
  .search-box { flex-direction: column; }
  .header h1 { font-size: 22px; }
  .stats-row { grid-template-columns: repeat(2, 1fr); }
  .header-actions { right: 12px; top: 12px; }
}

/* Scroll animation */
.fade-in { animation: fadeIn 0.5s ease forwards; opacity: 0; }
@keyframes fadeIn { to { opacity: 1; } }
</style>
</head>
<body>

<!-- Header -->
<div class="header">
  <div class="header-actions">
    <button class="history-btn" onclick="showHistory()">📋 历史报告</button>
  </div>
  <h1>🔍 微信公众号深度研究</h1>
  <p>输入关键词，全网搜索公众号文章，智能分析趋势与结论</p>
</div>

<!-- Search Box -->
<div class="search-section">
  <div class="search-box">
    <input type="text" class="search-input" id="queryInput"
           placeholder="输入关键词，如：TikTok冬季、AI创业、新能源汽车..."
           value="">
    <select class="time-select" id="timeSelect">
      <option value="7">近7天</option>
      <option value="30" selected>近30天</option>
      <option value="90">近90天</option>
      <option value="365">近一年</option>
    </select>
    <select class="time-select" id="directionSelect">
      <option value="general" selected>一般生活</option>
      <option value="ecommerce">跨境电商</option>
      <option value="macro">宏观交易</option>
    </select>
    <button class="search-btn" id="searchBtn" onclick="doSearch()">
      深度研究
    </button>
  </div>
</div>

<!-- Main Content -->
<div class="container" id="mainContent">
  <div class="empty-state" id="emptyState">
    <div class="empty-icon">📖</div>
    <div class="empty-text">输入关键词开始深度研究<br>将从全网公众号文章中搜索、整理、分析</div>
  </div>
</div>

<script>
let currentData = null;
let pollTimer = null;

async function doSearch() {
  const query = document.getElementById('queryInput').value.trim();
  if (!query) { alert('请输入关键词'); return; }

  const days = document.getElementById('timeSelect').value;
  const direction = document.getElementById('directionSelect').value;
  const btn = document.getElementById('searchBtn');
  const content = document.getElementById('mainContent');

  btn.classList.add('loading');
  btn.textContent = '正在研究';
  content.innerHTML = '<div class="empty-state"><div class="empty-icon">\u23F3</div><div class="empty-text">\u6b63\u5728\u641c\u7d22\u516c\u4f17\u53f7\u6587\u7ae0\u5e76\u6df1\u5ea6\u5206\u6790\u4e2d...<br>\u9884\u8ba1\u9700\u89813-8\u5206\u949f\uff0810\u9875\u641c\u7d22+20\u7bc7\u5168\u6587\u6293\u53d6\uff09\uff0c\u8bf7\u8010\u5fc3\u7b49\u5f85</div></div>';

  try {
    // 1. 发起搜索任务
    const startRes = await fetch('/api/search', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({q: query, days: parseInt(days), direction: direction})
    });
    const startData = await startRes.json();

    // 如果是缓存命中，直接返回了结果
    if (startData.status === 'done') {
      currentData = startData;
      renderReport(startData);
      return;
    }

    // 否则轮询任务状态
    const jobId = startData.job_id;
    if (!jobId) {
      content.innerHTML = `<div class="error-state">❌ ${startData.error || '启动搜索失败'}</div>`;
      return;
    }

    // 2. 轮询状态
    let elapsed = 0;
    pollTimer = setInterval(async () => {
      elapsed += 3;
      try {
        const statusRes = await fetch(`/api/status/${jobId}`);
        const statusData = await statusRes.json();

        if (statusData.status === 'done') {
          clearInterval(pollTimer);
          pollTimer = null;
          currentData = statusData;
          renderReport(statusData);
        } else if (statusData.status === 'error') {
          clearInterval(pollTimer);
          pollTimer = null;
          content.innerHTML = `<div class="error-state">❌ ${statusData.error}</div>`;
        } else {
          // 更新进度提示
          content.innerHTML = `<div class="empty-state"><div class="empty-icon">⏳</div><div class="empty-text">${statusData.message || '正在分析中...'}<br>已用时 ${elapsed} 秒</div></div>`;
        }
      } catch (e) {
        // 轮询出错，继续尝试
      }
    }, 3000);

  } catch (e) {
    content.innerHTML = `<div class="error-state">❌ 请求失败: ${e.message}</div>`;
  } finally {
    btn.classList.remove('loading');
    btn.textContent = '深度研究';
  }
}

function renderReport(data) {
  const analysis = data.analysis;
  const articles = data.articles;
  const content = document.getElementById('mainContent');

  let html = '';

  // Cache badge
  if (data.cached) {
    html += `<div class="cache-badge">\u26a1 来自缓存（报告 #${data.report_id}）</div>`;
  } else if (data.report_id) {
    html += `<div class="cache-badge">\ud83d\udcbe 已保存（报告 #${data.report_id}）</div>`;
  }

  // Direction badge
  const dirLabel = data.analysis?.direction_label || data.direction_label || '';
  if (dirLabel) {
    html += `<div class="cache-badge" style="background:rgba(33,150,243,0.1);color:#1976d2">\ud83c\udff7\ufe0f ${dirLabel}</div>`;
  }

  // Back button if viewing from history
  if (data.from_history) {
    html += `<button class="back-btn" onclick="showHistory()">← 返回历史报告</button>`;
  }

  // Stats Row
  html += `
  <div class="stats-row fade-in" style="animation-delay:0.1s">
    <div class="stat-card">
      <div class="stat-value">${data.total_results}</div>
      <div class="stat-label">相关文章</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${analysis.source_analysis.total_sources}</div>
      <div class="stat-label">公众号来源</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${analysis.time_analysis.time_range || '—'}</div>
      <div class="stat-label">时间跨度</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${analysis.sentiment_hint}</div>
      <div class="stat-label">舆论倾向</div>
    </div>
  </div>`;

  // Summary
  html += `
  <div class="report-card fade-in" style="animation-delay:0.2s">
    <div class="card-header"><div class="card-icon">📝</div>研究概述</div>
    <div class="summary-text">${analysis.summary}</div>
  </div>`;

  // Key Findings
  if (analysis.key_findings.length > 0) {
    html += `
    <div class="report-card fade-in" style="animation-delay:0.3s">
      <div class="card-header"><div class="card-icon">💡</div>关键发现</div>`;
    analysis.key_findings.forEach((f, i) => {
      html += `<div class="finding-item"><div class="finding-num">${i + 1}</div><div class="finding-text">${f}</div></div>`;
    });
    html += `</div>`;
  }

  // Keyword Cloud
  if (analysis.keyword_cloud.length > 0) {
    html += `
    <div class="report-card fade-in" style="animation-delay:0.4s">
      <div class="card-header"><div class="card-icon">🏷️</div>关键词热度</div>
      <div class="kw-cloud">`;
    analysis.keyword_cloud.forEach((kw, i) => {
      const cls = i < 3 ? 'hot' : '';
      html += `<span class="kw-tag ${cls}">${kw.word}</span>`;
    });
    html += `</div></div>`;
  }

  // Direction Focus Keywords
  if (analysis.focus_keywords_hit && analysis.focus_keywords_hit.length > 0) {
    html += `
    <div class="report-card fade-in" style="animation-delay:0.45s">
      <div class="card-header"><div class="card-icon">\ud83c\udfaf</div>${analysis.direction_label || ''}\u65b9\u5411\u4fe1\u53f7\u8bcd</div>
      <div class="kw-cloud">`;
    analysis.focus_keywords_hit.forEach((kw, i) => {
      const cls = i < 3 ? 'hot' : '';
      html += `<span class="kw-tag ${cls}">${kw.word} <span style="font-size:11px;opacity:0.7">(${kw.count})</span></span>`;
    });
    html += `</div></div>`;
  }

  // Source Analysis
  if (analysis.source_analysis.top_sources.length > 0) {
    const maxCount = analysis.source_analysis.top_sources[0].count;
    html += `
    <div class="report-card fade-in" style="animation-delay:0.5s">
      <div class="card-header"><div class="card-icon">📊</div>公众号来源分布</div>`;
    analysis.source_analysis.top_sources.forEach(s => {
      const pct = Math.round(s.count / maxCount * 100);
      html += `<div class="source-item"><div class="source-name">${s.name}</div><div class="source-bar-wrap"><div class="source-bar" style="width:${pct}%"></div></div><div class="source-count">${s.count}篇</div></div>`;
    });
    html += `</div>`;
  }

  // Time Distribution
  const timeDist = analysis.time_analysis.distribution;
  if (Object.keys(timeDist).length > 0) {
    const maxTime = Math.max(...Object.values(timeDist));
    html += `
    <div class="report-card fade-in" style="animation-delay:0.6s">
      <div class="card-header"><div class="card-icon">📈</div>时间热度分布
        ${analysis.time_analysis.trend ? `<span class="trend-tag ${
          analysis.time_analysis.trend.includes('上升') ? 'up' :
          analysis.time_analysis.trend.includes('下降') ? 'down' : 'flat'
        }">${analysis.time_analysis.trend}</span>` : ''}
      </div>
      <div class="time-chart">`;
    Object.entries(timeDist).forEach(([date, count]) => {
      const hPct = Math.max(4, Math.round(count / maxTime * 100));
      html += `<div class="time-bar-item"><div class="time-count">${count}</div><div class="time-bar" style="height:${hPct}%"></div><div class="time-label">${date.slice(5)}</div></div>`;
    });
    html += `</div></div>`;
  }

  // Divider
  html += `<div class="section-divider"><div class="dot"></div><div class="line"></div><div class="label">文章列表（按相关性排序）</div><div class="line"></div><div class="dot"></div></div>`;

  // Article Ranking
  if (analysis.article_ranking.length > 0) {
    analysis.article_ranking.forEach((a, i) => {
      const scoreCls = a.score >= 8 ? 'high' : '';
      const titleHtml = a.wx_url ? `<a href="${a.wx_url}" target="_blank">${a.title}</a>` : a.title;
      html += `
      <div class="report-card fade-in" style="animation-delay:${0.7 + i * 0.05}s">
        <div class="article-item">
          <div class="article-score ${scoreCls}">${a.score}</div>
          <div class="article-info">
            <div class="article-title">${titleHtml}</div>
            <div class="article-meta"><span>${a.account || '未知来源'}</span><span>${a.time || ''}</span></div>
            ${a.digest ? `<div class="article-digest">${a.digest}</div>` : ''}
          </div>
        </div>
      </div>`;
    });
  }

  content.innerHTML = html;
  content.scrollIntoView({ behavior: 'smooth' });
}

// ========== History ==========

async function showHistory() {
  const content = document.getElementById('mainContent');
  content.innerHTML = '<div class="empty-state"><div class="empty-icon">⏳</div><div class="empty-text">加载历史报告...</div></div>';

  try {
    const res = await fetch('/api/history');
    const reports = await res.json();

    if (!reports || reports.length === 0) {
      content.innerHTML = '<div class="empty-state"><div class="empty-icon">📋</div><div class="empty-text">还没有历史报告<br>搜索一次就会自动保存</div></div>';
      return;
    }

    let html = `<button class="back-btn" onclick="location.reload()">← 返回搜索</button>
                <div class="section-divider"><div class="dot"></div><div class="line"></div><div class="label">共 ${reports.length} 份报告</div><div class="line"></div><div class="dot"></div></div>
                <div class="history-list">`;

    reports.forEach(r => {
      const dirMap = {'general':'一般生活','ecommerce':'跨境电商','macro':'宏观交易'};
      const dirLabel = dirMap[r.direction] || '一般生活';
      html += `
      <div class="history-item" onclick="loadReport(${r.id})">
        <div class="history-info">
          <div class="history-query">\ud83d\udd0d ${r.query} <span style="font-size:12px;color:#1976d2;background:rgba(33,150,243,0.1);padding:2px 8px;border-radius:12px;margin-left:8px">${dirLabel}</span></div>
          <div class="history-meta">
            <span>\ud83d\udcca ${r.total_results} 篇文章</span>
            <span>\ud83d\udcc5 ${r.created_at}</span>
            <span>\u23f1 近${r.days}天</span>
            <span>\ud83d\udcc8 ${r.sentiment_hint}</span>
          </div>
          <div class="history-summary">${r.summary || ''}</div>
        </div>
        <button class="history-delete" onclick="deleteReport(event, ${r.id})">\ud83d\uddd1</button>
      </div>`;
    });

    html += '</div>';
    content.innerHTML = html;
  } catch (e) {
    content.innerHTML = `<div class="error-state">❌ 加载失败: ${e.message}</div>`;
  }
}

async function loadReport(id) {
  const content = document.getElementById('mainContent');
  content.innerHTML = '<div class="empty-state"><div class="empty-icon">⏳</div><div class="empty-text">加载报告中...</div></div>';

  try {
    const res = await fetch(`/api/report/${id}`);
    const data = await res.json();

    if (data.error) {
      content.innerHTML = `<div class="error-state">❌ ${data.error}</div>`;
      return;
    }

    data.from_history = true;
    currentData = data;
    renderReport(data);
  } catch (e) {
    content.innerHTML = `<div class="error-state">❌ 加载失败: ${e.message}</div>`;
  }
}

async function deleteReport(event, id) {
  event.stopPropagation();
  if (!confirm('确定删除这份报告？')) return;

  try {
    await fetch(`/api/report/${id}`, { method: 'DELETE' });
    showHistory();
  } catch (e) {
    alert('删除失败: ' + e.message);
  }
}

// Enter key triggers search
document.getElementById('queryInput').addEventListener('keydown', function(e) {
  if (e.key === 'Enter') doSearch();
});
</script>
</body>
</html>
"""


# ========== 工具函数 ==========

def clean_text_for_json(text: str) -> str:
    """清理文本中的HTML实体残留"""
    if not text:
        return text
    text = text.replace('&ldquo;', '"').replace('&rdquo;', '"')
    text = text.replace('&darr;', '↓').replace('&hellip;', '…')
    text = text.replace('&middot;', '·').replace('&nbsp;', ' ')
    text = text.replace('&quot;', '"').replace('&amp;', '&')
    text = re.sub(r'&[a-z]+;', '', text)
    return text


# ========== 异步搜索 Worker ==========

def _do_search_worker(job_id: str, query: str, days: int, direction: str = "general"):
    """在后台线程中执行搜索任务"""
    try:
        with _jobs_lock:
            _jobs[job_id]["message"] = "正在搜索公众号文章（10页深度搜索）..."

        result = deep_search(query, days=days, fetch_content=True,
                             content_limit=20, direction=direction, max_pages=10)

        if result["error"]:
            with _jobs_lock:
                _jobs[job_id]["status"] = "error"
                _jobs[job_id]["error"] = result["error"]
            return

        articles = result["articles"]

        # 清理HTML实体残留
        for a in articles:
            a["title"] = clean_text_for_json(a.get("title", ""))
            a["digest"] = clean_text_for_json(a.get("digest", ""))
            if a.get("full_content"):
                a["full_content"] = clean_text_for_json(a["full_content"])

        with _jobs_lock:
            _jobs[job_id]["message"] = f"已搜索到 {len(articles)} 篇文章，正在抓取全文并分析..."

        # 分析结果（传入方向）
        analysis = analyze_articles(articles, query, direction=direction)

        # 清理分析结果中的HTML实体
        analysis["summary"] = clean_text_for_json(analysis.get("summary", ""))
        analysis["key_findings"] = [clean_text_for_json(f) for f in analysis.get("key_findings", [])]
        for kw in analysis.get("keyword_cloud", []):
            kw["word"] = clean_text_for_json(kw.get("word", ""))
        for a in analysis.get("article_ranking", []):
            a["title"] = clean_text_for_json(a.get("title", ""))
            a["digest"] = clean_text_for_json(a.get("digest", ""))

        # 保存到数据库
        report_id = db.save_report(query, days, result["total_results"], articles, analysis, direction=direction)

        # 标记任务完成
        with _jobs_lock:
            _jobs[job_id]["status"] = "done"
            _jobs[job_id]["result"] = {
                "query": query,
                "days": days,
                "direction": direction,
                "total_results": result["total_results"],
                "articles": articles,
                "analysis": analysis,
                "error": None,
                "report_id": report_id
            }

    except Exception as e:
        with _jobs_lock:
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["error"] = f"服务内部错误: {str(e)}"


# ========== 路由 ==========

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/search', methods=['POST'])
def api_search():
    """启动搜索任务（异步）。如果命中缓存则直接返回结果。"""
    data = request.get_json(silent=True) or {}
    query = (data.get('q') or '').strip()
    days = int(data.get('days', 30))
    direction = data.get('direction', 'general')
    # 校验方向
    if direction not in ('general', 'ecommerce', 'macro'):
        direction = 'general'

    if not query:
        return jsonify({"error": "请提供搜索关键词"})

    # 1. 先查缓存（按方向区分）
    cached = db.get_cached_report(query, days, direction=direction)
    if cached:
        cached["status"] = "done"
        return jsonify(cached)

    # 2. 启动后台搜索任务
    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _jobs[job_id] = {
            "status": "running",
            "message": "正在启动搜索...",
            "query": query,
            "days": days,
            "direction": direction,
            "created_at": time.time(),
            "result": None,
            "error": None,
        }

    thread = threading.Thread(target=_do_search_worker, args=(job_id, query, days, direction), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id, "status": "running"})


@app.route('/api/status/<job_id>')
def api_status(job_id):
    """查询搜索任务状态"""
    with _jobs_lock:
        job = _jobs.get(job_id)

    if not job:
        return jsonify({"status": "error", "error": "任务不存在或已过期"})

    if job["status"] == "done":
        result = job["result"]
        # 清理旧任务（保留1小时）
        if time.time() - job["created_at"] > 3600:
            with _jobs_lock:
                _jobs.pop(job_id, None)
        return jsonify({**result, "status": "done"})

    if job["status"] == "error":
        return jsonify({"status": "error", "error": job["error"]})

    return jsonify({"status": "running", "message": job.get("message", "正在搜索...")})


@app.route('/api/history')
def api_history():
    """获取历史报告列表"""
    reports = db.get_all_reports(limit=50)
    return jsonify(reports)


@app.route('/api/report/<int:report_id>')
def api_report(report_id):
    """获取指定报告的完整数据"""
    report = db.get_report_by_id(report_id)
    if report:
        return jsonify(report)
    return jsonify({"error": "报告不存在"}), 404


@app.route('/api/report/<int:report_id>', methods=['DELETE'])
def api_delete_report(report_id):
    """删除指定报告"""
    deleted = db.delete_report(report_id)
    if deleted:
        return jsonify({"ok": True})
    return jsonify({"error": "报告不存在"}), 404


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("=" * 60)
    print("  微信公众号深度研究工具")
    print(f"  访问地址: http://localhost:{port}")
    print("=" * 60)
    app.run(host='0.0.0.0', port=port, debug=False)
