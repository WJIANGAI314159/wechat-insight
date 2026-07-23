#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信公众号深度研究工具 - 分析模块
对搜索结果进行结构化分析：关键词频率、主题聚类、时间分布、摘要生成
"""

import re
import json
from collections import Counter, defaultdict
from datetime import datetime

try:
    import jieba
    import jieba.analyse
    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False


# 常见停用词
STOP_WORDS = set([
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一", "一个",
    "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好",
    "自己", "这", "他", "她", "它", "们", "那", "些", "什么", "怎么", "如何",
    "可以", "能", "将", "把", "被", "让", "给", "从", "对", "为", "以",
    "及", "与", "或", "但", "而", "又", "则", "所", "其", "之",
    "中", "等", "很", "最", "更", "还", "也", "才", "已", "将",
    "关于", "关于", "进行", "通过", "使用", "实现", "方面", "问题",
    "文章", "内容", "信息", "相关", "以下", "如下", "主要",
    "微信", "公众号", "平台", "用户", "中国", "全球",
    # HTML 实体词（从搜狗搜索结果中解析出的残留）
    "ldquo", "rdquo", "darr", "quot", "amp", "nbsp", "hellip", "middot",
    "ensp", "emsp", "thinsp", "#", "...", "…",
])


def clean_html_entities(text: str) -> str:
    """清理HTML实体残留"""
    text = re.sub(r'&ldquo;', '"', text)
    text = re.sub(r'&rdquo;', '"', text)
    text = re.sub(r'&darr;', '↓', text)
    text = re.sub(r'&hellip;', '…', text)
    text = re.sub(r'&middot;', '·', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&quot;', '"', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&[a-z]+;', '', text)  # 清理其他未知实体
    return text


def extract_keywords_from_text(text: str, top_k: int = 20) -> list:
    """从文本中提取关键词"""
    if not text:
        return []

    # 先清理HTML实体
    text = clean_html_entities(text)

    if JIEBA_AVAILABLE:
        # 使用jieba的TF-IDF提取关键词
        keywords = jieba.analyse.extract_tags(text, topK=top_k, withWeight=True)
        # 过滤停用词、HTML实体残留和纯数字
        filtered = [(word, weight) for word, weight in keywords
                     if word not in STOP_WORDS
                     and len(word) >= 2
                     and not re.match(r'^[a-z]{2,5}$', word)  # 过滤疑似HTML实体词
                     and not re.match(r'^\d+$', word)          # 过滤纯数字
                     and word != '...']
        return filtered
    else:
        # 简单分词：按标点分割，过滤短词和停用词
        words = re.findall(r'[a-zA-Z]+|\d+|[\u4e00-\u9fff]{2,}', text)
        counter = Counter(words)
        filtered = [(word, count) for word, count in counter.most_common(top_k)
                     if word not in STOP_WORDS and len(word) >= 2]
        return filtered


def analyze_articles(articles: list, query: str) -> dict:
    """
    对搜索结果进行深度分析

    返回结构化分析报告:
    {
        summary: str,              # 总体概述
        key_findings: list[str],   # 关键发现
        topic_distribution: dict,  # 主题分布
        source_analysis: dict,     # 来源分析
        time_analysis: dict,       # 时间分析
        keyword_cloud: list,       # 关键词频率
        sentiment_hint: str,       # 情绪倾向提示
        article_ranking: list,     # 文章重要性排名
    }
    """
    if not articles:
        return {
            "summary": f"未找到与「{query}」相关的公众号文章，无法生成分析报告。",
            "key_findings": [],
            "topic_distribution": {},
            "source_analysis": {},
            "time_analysis": {},
            "keyword_cloud": [],
            "sentiment_hint": "无数据",
            "article_ranking": [],
        }

    # 1. 合并所有文本内容（先清理HTML实体）
    all_titles = clean_html_entities(" ".join([a.get("title", "") for a in articles]))
    all_digests = clean_html_entities(" ".join([a.get("digest", "") for a in articles]))
    all_content = clean_html_entities(" ".join([a.get("full_content", "") for a in articles if a.get("full_content")]))
    combined_text = f"{all_titles} {all_digests} {all_content}"

    # 2. 关键词分析
    keyword_weights = extract_keywords_from_text(combined_text, top_k=30)
    keyword_cloud = [{"word": w, "weight": round(float(wt), 4)} for w, wt in keyword_weights]

    # 3. 来源（公众号）分析
    account_counter = Counter([a.get("account", "未知来源") for a in articles])
    source_analysis = {
        "total_sources": len(account_counter),
        "top_sources": [{"name": name, "count": count}
                        for name, count in account_counter.most_common(10)],
        "coverage": f"共涉及 {len(account_counter)} 个不同的公众号"
    }

    # 4. 时间分布分析
    time_articles = [a for a in articles if a.get("time")]
    time_distribution = defaultdict(int)
    for a in time_articles:
        try:
            dt = datetime.strptime(a["time"], "%Y-%m-%d %H:%M")
            time_distribution[dt.strftime("%Y-%m-%d")] += 1
        except ValueError:
            pass

    time_analysis = {
        "distribution": dict(sorted(time_distribution.items())),
        "time_range": "",
        "trend": ""
    }
    if time_distribution:
        dates = sorted(time_distribution.keys())
        time_analysis["time_range"] = f"{dates[0]} 至 {dates[-1]}"
        # 判断趋势
        if len(dates) >= 3:
            recent_count = sum(time_distribution[d] for d in dates[-3:])
            earlier_count = sum(time_distribution[d] for d in dates[:3])
            if recent_count > earlier_count * 1.5:
                time_analysis["trend"] = "热度上升趋势明显"
            elif recent_count < earlier_count * 0.5:
                time_analysis["trend"] = "热度下降趋势明显"
            else:
                time_analysis["trend"] = "热度相对平稳"

    # 5. 主题聚类（基于标题关键词）
    title_keywords = {}
    for a in articles:
        title = clean_html_entities(a.get("title", ""))
        if JIEBA_AVAILABLE:
            words = [w for w in jieba.cut(title)
                     if w not in STOP_WORDS
                     and len(w) >= 2
                     and not re.match(r'^[a-z]{2,5}$', w)
                     and not re.match(r'^\d+$', w)]
        else:
            words = re.findall(r'[a-zA-Z]{4,}|[\u4e00-\u9fff]{2,}', title)
            words = [w for w in words if w not in STOP_WORDS]
        title_keywords[a.get("title", "")] = words

    # 基于关键词共现进行主题发现
    topic_words = Counter()
    for words in title_keywords.values():
        for w in words:
            topic_words[w] += 1

    topic_distribution = {
        "top_topics": [{"topic": word, "count": count}
                       for word, count in topic_words.most_common(15)],
    }

    # 6. 情绪/倾向分析（简单基于关键词）
    positive_words = ["增长", "突破", "创新", "领先", "机遇", "成功", "利好",
                      "上升", "爆发", "红利", "赋能", "升级", "优化"]
    negative_words = ["下降", "风险", "危机", "困难", "挑战", "亏损", "封禁",
                      "限制", "监管", "处罚", "暴跌", "裁员", "衰退"]
    neutral_words = ["分析", "趋势", "报告", "观察", "研究", "数据", "统计"]

    pos_count = sum(1 for w, _ in keyword_weights if w in positive_words)
    neg_count = sum(1 for w, _ in keyword_weights if w in negative_words)

    if pos_count > neg_count + 2:
        sentiment_hint = "偏积极乐观"
    elif neg_count > pos_count + 2:
        sentiment_hint = "偏谨慎悲观"
    else:
        sentiment_hint = "相对中立平衡"

    # 7. 文章重要性排名（基于标题关键词密度 + 来源权威性）
    article_ranking = []
    for a in articles:
        score = 0
        title = a.get("title", "")
        digest = a.get("digest", "")

        # 与查询词的相关度
        query_words = query.split()
        for qw in query_words:
            if qw in title:
                score += 3
            if qw in digest:
                score += 1

        # 关键关键词命中
        top_kw = [w for w, _ in keyword_weights[:10]]
        for kw in top_kw:
            if kw in title:
                score += 2

        # 有全文内容的加分
        if a.get("full_content"):
            score += 2

        article_ranking.append({
            "title": title,
            "account": a.get("account", ""),
            "time": a.get("time", ""),
            "score": score,
            "digest": digest[:100],
            "wx_url": a.get("wx_url", ""),
        })

    article_ranking.sort(key=lambda x: x["score"], reverse=True)

    # 8. 生成关键发现
    key_findings = []

    # 核心关键词发现
    if keyword_weights:
        top_3 = [w for w, _ in keyword_weights[:3]]
        key_findings.append(f"核心话题聚焦于：{', '.join(top_3)}")

    # 来源集中度发现
    if account_counter:
        top_account = account_counter.most_common(1)[0]
        if top_account[1] >= 3:
            key_findings.append(f"「{top_account[0]}」是该话题最活跃的公众号（{top_account[1]}篇相关文章）")

    # 时间趋势发现
    if time_analysis["trend"]:
        key_findings.append(f"话题热度趋势：{time_analysis['trend']}")

    # 情绪发现
    key_findings.append(f"整体舆论倾向：{sentiment_hint}")

    # 关联话题发现
    if topic_words:
        related = [w for w, c in topic_words.most_common(8) if w not in query.split()]
        if related:
            key_findings.append(f"高频关联话题：{', '.join(related[:5])}")

    # 9. 生成总体概述
    summary_parts = [
        f"本次深度研究基于「{query}」关键词，",
        f"共检索到 {len(articles)} 篇微信公众号文章，",
        f"涉及 {len(account_counter)} 个不同公众号来源。",
    ]
    if time_analysis["time_range"]:
        summary_parts.append(f"时间跨度：{time_analysis['time_range']}。")
    if keyword_weights:
        top_kw_str = ", ".join([w for w, _ in keyword_weights[:5]])
        summary_parts.append(f"核心议题围绕 {top_kw_str} 等关键词展开。")
    summary_parts.append(f"舆论整体倾向{sentiment_hint}。")

    summary = "".join(summary_parts)

    return {
        "summary": summary,
        "key_findings": key_findings,
        "topic_distribution": topic_distribution,
        "source_analysis": source_analysis,
        "time_analysis": time_analysis,
        "keyword_cloud": keyword_cloud,
        "sentiment_hint": sentiment_hint,
        "article_ranking": article_ranking[:10],
    }
