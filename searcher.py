#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信公众号深度研究工具 - 搜狗微信搜索模块
基于搜狗微信搜索 (weixin.sogou.com) 实现公众号文章检索与内容抓取
"""

import sys
import json
import time
import re
import random
import urllib.parse
import urllib.request
import uuid
from datetime import datetime


class RateLimiter:
    """搜狗微信搜索限频器"""

    MIN_INTERVAL = 0.5
    MAX_INTERVAL = 1.5
    CONTENT_INTERVAL = 1
    COOKIE_REFRESH_THRESHOLD = 50

    USER_AGENTS = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
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


def fetch_url(url: str, referer: str = None, is_content: bool = False) -> str:
    """获取URL内容"""
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
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return f"Error: {str(e)}"


def clean_html(text: str) -> str:
    """清理HTML标签和HTML实体"""
    text = re.sub(r'<!--[^>]*-->', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    # 清理HTML实体
    text = text.replace('&ldquo;', '"').replace('&rdquo;', '"')
    text = text.replace('&darr;', '↓').replace('&hellip;', '…')
    text = text.replace('&middot;', '·').replace('&nbsp;', ' ')
    text = text.replace('&quot;', '"').replace('&amp;', '&')
    text = text.replace('&lt;', '<').replace('&gt;', '>')
    text = re.sub(r'&[a-z]+;', '', text)  # 清理其他未知实体
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


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
        return [{"error": "触发验证码，请稍后重试"}]

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


def deep_search(query: str, days: int = 30, fetch_content: bool = True,
                content_limit: int = 5) -> dict:
    """
    深度搜索：多页搜索 + 可选内容抓取

    返回: {
        query, days, total_results, articles: [...],
        error: None or str
    }
    """
    time_to = int(time.time())
    time_from = time_to - days * 86400

    all_results = []
    # 搜索2页以获取更多结果
    for page in range(1, 3):
        results = search_articles(query, page=page, time_from=time_from, time_to=time_to)
        if results and "error" in results[0]:
            return {"query": query, "days": days, "total_results": 0, "articles": [], "error": results[0]["error"]}
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
    if fetch_content:
        for i, item in enumerate(unique_results[:content_limit]):
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
        "total_results": len(unique_results),
        "articles": unique_results,
        "error": None
    }
