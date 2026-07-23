#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信公众号深度研究工具 - 搜狗微信搜索模块
基于搜狗微信搜索 (weixin.sogou.com) 实现公众号文章检索与内容抓取

功能：
- 多页深度搜索（最多10页）
- 全文内容抓取（最多20篇）
- 代理轮换（降低反爬风险）
- 方向化搜索（跨境电商/一般生活/宏观交易）
"""

import sys
import json
import time
import re
import random
import urllib.parse
import urllib.request
import uuid
import os
from datetime import datetime


# ========== 方向化搜索配置 ==========

DIRECTION_CONFIG = {
    "general": {
        "label": "一般生活",
        "suffix_keywords": [],  # 不补充关键词
        "description": "原样搜索，关注话题热度和流行趋势",
    },
    "ecommerce": {
        "label": "跨境电商",
        "suffix_keywords": ["选品", "运营", "销量", "趋势", "平台政策"],
        "description": "补充电商相关关键词，关注市场机会和选品方向",
    },
    "macro": {
        "label": "宏观交易",
        "suffix_keywords": ["市场", "数据", "政策", "行业", "分析"],
        "description": "补充宏观相关关键词，关注政策影响和行业趋势",
    },
}


def build_search_query(query: str, direction: str) -> str:
    """根据方向构建搜索关键词"""
    config = DIRECTION_CONFIG.get(direction, DIRECTION_CONFIG["general"])
    if not config["suffix_keywords"]:
        return query
    # 用空格连接原始关键词和方向补充词，搜狗会做分词匹配
    suffix = " ".join(config["suffix_keywords"])
    return f"{query} {suffix}"


# ========== 代理轮换管理器 ==========

class ProxyManager:
    """
    代理轮换管理器。
    
    通过环境变量 PROXY_LIST 配置代理列表（逗号分隔）。
    格式: http://ip:port 或 http://user:pass@ip:port
    如果没有配置代理，则直连。
    """

    def __init__(self):
        self.proxies = []
        self.failed_proxies = set()
        self._load_proxies()

    def _load_proxies(self):
        """从环境变量加载代理列表"""
        proxy_env = os.environ.get("PROXY_LIST", "").strip()
        if proxy_env:
            self.proxies = [p.strip() for p in proxy_env.split(",") if p.strip()]
            print(f"[ProxyManager] 已加载 {len(self.proxies)} 个代理")
        else:
            # 尝试从文件加载
            proxy_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxies.txt")
            if os.path.exists(proxy_file):
                with open(proxy_file, "r") as f:
                    self.proxies = [line.strip() for line in f if line.strip() and not line.startswith("#")]
                if self.proxies:
                    print(f"[ProxyManager] 从 proxies.txt 加载 {len(self.proxies)} 个代理")

    def get_proxy(self) -> dict | None:
        """获取一个可用的代理，返回 urllib 格式的 proxy handler dict"""
        available = [p for p in self.proxies if p not in self.failed_proxies]
        if not available:
            return None
        proxy = random.choice(available)
        return {"http": proxy, "https": proxy}

    def mark_failed(self, proxy_dict: dict | None):
        """标记代理失败"""
        if not proxy_dict:
            return
        proxy_url = proxy_dict.get("http") or proxy_dict.get("https")
        if proxy_url:
            self.failed_proxies.add(proxy_url)
            # 如果所有代理都失败了，重置失败列表（给它们第二次机会）
            if len(self.failed_proxies) >= len(self.proxies):
                self.failed_proxies.clear()
                print("[ProxyManager] 所有代理均已失败，重置失败列表")

    @property
    def has_proxies(self) -> bool:
        return len(self.proxies) > 0


proxy_manager = ProxyManager()


# ========== 限频器 ==========

class RateLimiter:
    """搜狗微信搜索限频器"""

    MIN_INTERVAL = 1.0       # 页面搜索最小间隔（秒）
    MAX_INTERVAL = 3.0       # 页面搜索最大间隔（秒）
    CONTENT_INTERVAL = 1.5   # 内容抓取间隔（秒）
    COOKIE_REFRESH_THRESHOLD = 30  # 每30次请求刷新一次cookie

    USER_AGENTS = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    ]

    def __init__(self, enabled=True):
        self.enabled = enabled
        self.request_count = 0
        self.last_request_time = 0
        self.suv_cookie = self._generate_suv()

    def _generate_suv(self) -> str:
        return uuid.uuid4().hex.upper()

    def get_user_agent(self) -> str:
        return random.choice(self.USER_AGENTS)

    def get_cookies(self) -> str:
        if self.request_count >= self.COOKIE_REFRESH_THRESHOLD:
            self.suv_cookie = self._generate_suv()
            self.request_count = 0
        return f"SUV={self.suv_cookie}"

    def wait(self, is_content_fetch: bool = False):
        if not self.enabled:
            self.request_count += 1
            return
        elapsed = time.time() - self.last_request_time
        if is_content_fetch:
            wait_time = self.CONTENT_INTERVAL
        else:
            wait_time = random.uniform(self.MIN_INTERVAL, self.MAX_INTERVAL)
        if elapsed < wait_time:
            time.sleep(wait_time - elapsed)
        self.last_request_time = time.time()
        self.request_count += 1


rate_limiter = RateLimiter()


# ========== HTTP 请求 ==========

def fetch_url(url: str, referer: str = None, is_content: bool = False,
              max_retries: int = 2) -> str:
    """获取URL内容，支持代理轮换和重试"""
    for attempt in range(max_retries + 1):
        rate_limiter.wait(is_content_fetch=is_content)
        headers = {
            "User-Agent": rate_limiter.get_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cookie": rate_limiter.get_cookies(),
        }
        if referer:
            headers["Referer"] = referer
        req = urllib.request.Request(url, headers=headers)

        # 尝试代理
        proxy_dict = proxy_manager.get_proxy() if proxy_manager.has_proxies else None
        if proxy_dict:
            proxy_handler = urllib.request.ProxyHandler(proxy_dict)
            opener = urllib.request.build_opener(proxy_handler)
        else:
            opener = urllib.request.build_opener()

        try:
            with opener.open(req, timeout=30) as response:
                return response.read().decode("utf-8", errors="ignore")
        except Exception as e:
            # 如果是代理请求失败，标记代理并重试
            if proxy_dict:
                proxy_manager.mark_failed(proxy_dict)
                if attempt < max_retries:
                    continue
            # 非代理或重试次数用完
            if attempt < max_retries:
                time.sleep(2)  # 等待后重试
                continue
            return f"Error: {str(e)}"

    return "Error: max retries exceeded"


# ========== HTML 清理 ==========

def clean_html(text: str) -> str:
    """清理HTML标签和HTML实体"""
    text = re.sub(r'<!--[^>]*-->', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    # 清理HTML实体
    text = text.replace('&ldquo;', '\u201c').replace('&rdquo;', '\u201d')
    text = text.replace('&darr;', '\u2193').replace('&hellip;', '\u2026')
    text = text.replace('&middot;', '\u00b7').replace('&nbsp;', ' ')
    text = text.replace('&quot;', '"').replace('&amp;', '&')
    text = text.replace('&lt;', '<').replace('&gt;', '>')
    text = re.sub(r'&[a-z]+;', '', text)  # 清理其他未知实体
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ========== 搜索文章 ==========

def search_articles(query: str, page: int = 1,
                    time_from: int = None, time_to: int = None) -> list:
    """
    搜狗微信搜索文章

    返回: [{title, digest, account, time, sogou_link}, ...]
    """
    encoded_query = urllib.parse.quote(query)
    url = f"https://weixin.sogou.com/weixin?type=2&query={encoded_query}&page={page}&ie=utf8"

    if time_from is not None:
        url += f"&ft={time_from}"
    if time_to is not None:
        url += f"&et={time_to}"

    html = fetch_url(url)
    if html.startswith("Error:"):
        return [{"error": html}]
    if "请输入验证码" in html or "antispider" in html:
        return [{"error": "触发搜狗验证码，请稍后重试（建议降低搜索频率或配置代理）"}]

    results = []
    li_pattern = r'<li[^>]*id="sogou_vr_\d+_box_\d+"[^>]*>(.*?)</li>'
    items = re.findall(li_pattern, html, re.DOTALL)

    for item in items:
        result = {}
        link_match = re.search(r'href="(/link\?url=[^"]+)"', item)
        if link_match:
            link = link_match.group(1).replace("&amp;", "&").replace(" ", "%20")
            result["sogou_link"] = "https://weixin.sogou.com" + link
        title_match = re.search(r'<h3>\s*<a[^>]*>(.*?)</a>\s*</h3>', item, re.DOTALL)
        if title_match:
            result["title"] = clean_html(title_match.group(1))
        digest_match = re.search(r'<p[^>]*class="txt-info"[^>]*>(.*?)</p>', item, re.DOTALL)
        if digest_match:
            result["digest"] = clean_html(digest_match.group(1))[:200]
        account_match = re.search(r'<span[^>]*class="all-time-y2"[^>]*>([^<]+)</span>', item)
        if account_match:
            result["account"] = account_match.group(1).strip()
        time_match = re.search(r"timeConvert\('(\d+)'\)", item)
        if time_match:
            timestamp = int(time_match.group(1))
            result["time"] = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
        if result.get("title"):
            results.append(result)

    return results


# ========== 获取文章原文 ==========

def get_article_content(sogou_link: str) -> dict:
    """获取文章原文内容"""
    html = fetch_url(sogou_link, referer="https://weixin.sogou.com/", is_content=True)
    if html.startswith("Error:"):
        return {"error": html}

    url_parts = re.findall(r"url \+= '([^']+)'", html)
    if url_parts:
        wx_url = "".join(url_parts).replace("@", "")
    else:
        wx_match = re.search(r'var\s+url\s*=\s*["\']([^"\']+)["\']', html)
        if wx_match:
            wx_url = wx_match.group(1)
        else:
            return {"error": "无法解析微信文章链接"}

    article_html = fetch_url(wx_url, referer="https://weixin.sogou.com/", is_content=True)
    if article_html.startswith("Error:"):
        return {"error": article_html}

    result = {"wx_url": wx_url}

    title_match = re.search(r'<h1[^>]*class="rich_media_title"[^>]*>(.*?)</h1>', article_html, re.DOTALL)
    if not title_match:
        title_match = re.search(r'<title>([^<]+)</title>', article_html)
    if title_match:
        result["title"] = clean_html(title_match.group(1))

    account_match = re.search(r'<a[^>]*id="js_name"[^>]*>([^<]+)</a>', article_html)
    if account_match:
        result["account"] = account_match.group(1).strip()

    time_match = re.search(r'<em[^>]*id="publish_time"[^>]*>([^<]+)</em>', article_html)
    if time_match:
        result["publish_time"] = time_match.group(1).strip()

    content_match = re.search(r'<div[^>]*id="js_content"[^>]*>(.*?)</div>\s*<script', article_html, re.DOTALL)
    if content_match:
        content = content_match.group(1)
        content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL)
        content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL)
        content = re.sub(r'<[^>]+>', '\n', content)
        content = re.sub(r'\n\s*\n', '\n\n', content)
        content = re.sub(r'&nbsp;', ' ', content)
        content = re.sub(r'&[a-z]+;', '', content)
        result["content"] = content.strip()

    return result


# ========== 深度搜索 ==========

def deep_search(query: str, days: int = 30, fetch_content: bool = True,
                content_limit: int = 20, direction: str = "general",
                max_pages: int = 10) -> dict:
    """
    深度搜索：多页搜索 + 可选内容抓取

    参数：
        query: 搜索关键词
        days: 搜索时间范围（天）
        fetch_content: 是否抓取文章全文
        content_limit: 抓取全文的最大文章数
        direction: 搜索方向 (general/ecommerce/macro)
        max_pages: 最大搜索页数

    返回: {
        query, days, direction, total_results, articles: [...],
        error: None or str
    }
    """
    # 根据方向构建搜索词
    search_query = build_search_query(query, direction)

    time_to = int(time.time())
    time_from = time_to - days * 86400

    all_results = []
    for page in range(1, max_pages + 1):
        results = search_articles(search_query, page=page, time_from=time_from, time_to=time_to)
        if results and "error" in results[0]:
            # 如果是第一页就报错，直接返回错误
            if page == 1:
                return {"query": query, "days": days, "direction": direction,
                        "total_results": 0, "articles": [], "error": results[0]["error"]}
            # 后续页报错，用已有结果继续
            break
        all_results.extend(results)
        if len(results) < 10:
            break  # 没有更多页

    # 去重（按标题）
    seen_titles = set()
    unique_results = []
    for r in all_results:
        if r.get("title") and r["title"] not in seen_titles:
            seen_titles.add(r["title"])
            unique_results.append(r)

    # 可选：获取文章原文
    if fetch_content and unique_results:
        fetch_count = min(content_limit, len(unique_results))
        for i, item in enumerate(unique_results[:fetch_count]):
            if "sogou_link" not in item:
                continue
            content = get_article_content(item["sogou_link"])
            if "error" not in content:
                item["wx_url"] = content.get("wx_url")
                item["full_content"] = content.get("content", "")
                if content.get("account") and not item.get("account"):
                    item["account"] = content["account"]
                if content.get("publish_time") and not item.get("time"):
                    item["time"] = content["publish_time"]

    return {
        "query": query,
        "days": days,
        "direction": direction,
        "total_results": len(unique_results),
        "articles": unique_results,
        "error": None
    }
