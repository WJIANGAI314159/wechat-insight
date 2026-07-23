#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信公众号深度研究工具 - 分析模块
对搜索结果进行结构化分析：关键词频率、主题聚类、时间分布、摘要生成
支持方向化分析（跨境电商/一般生活/宏观交易）
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


# ========== 常见停用词 ==========

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
    "ensp", "emsp", "thinsp", "#", "...", "\u2026",
    # 搜索方向补充词（避免它们污染关键词云）
    "选品", "运营", "销量", "趋势", "平台政策",
    "市场", "数据", "政策", "行业", "分析",
])


# ========== 方向化分析配置 ==========

DIRECTION_ANALYSIS_CONFIG = {
    "general": {
        "label": "一般生活",
        "focus_keywords": [
            "热点", "流行", "穿搭", "生活", "美食", "旅游", "健康", "娱乐",
            "消费", "体验", "推荐", "攻略", "打卡", "种草", "测评",
        ],
        "positive_signals": ["增长", "突破", "创新", "机遇", "成功", "红利", "爆发", "流行", "热潮"],
        "negative_signals": ["下降", "风险", "危机", "困难", "挑战", "封禁", "限制", "暴跌", "衰退"],
        "finding_templates": {
            "trend": "话题热度趋势：{trend}，反映了用户对该话题的关注程度",
            "sentiment": "用户舆论整体{sentiment}，说明大众对该话题的情感态度",
            "topics": "热门关联话题：{topics}，揭示了用户关注的具体生活场景",
        },
    },
    "ecommerce": {
        "label": "跨境电商",
        "focus_keywords": [
            "选品", "运营", "销量", "增长", "转化", "ROI", "流量", "广告",
            "供应链", "物流", "仓储", "品类", "爆款", "利润", "定价",
            "TikTok", "Shop", "Amazon", "Shopee", "独立站", "直播", "带货",
            "东南亚", "北美", "欧洲", "中东", "拉美",
        ],
        "positive_signals": ["增长", "突破", "机遇", "红利", "爆发", "蓝海", "风口", "升级", "赋能"],
        "negative_signals": ["风险", "挑战", "封禁", "限制", "监管", "处罚", "暴跌", "裁员", "亏损"],
        "finding_templates": {
            "trend": "电商话题热度{trend}，提示该品类的市场关注度变化",
            "sentiment": "行业情绪{sentiment}，反映跨境电商从业者的信心水平",
            "topics": "核心运营关键词：{topics}，指引选品和运营方向",
        },
    },
    "macro": {
        "label": "宏观交易",
        "focus_keywords": [
            "GDP", "CPI", "利率", "汇率", "通胀", "通缩", "进出口", "贸易",
            "政策", "监管", "法规", "关税", "制裁", "央行", "财政",
            "周期", "估值", "资产", "配置", "风险", "对冲", "套利",
            "供应链", "产业链", "格局", "竞争", "整合",
        ],
        "positive_signals": ["增长", "回升", "复苏", "利好", "刺激", "宽松", "扩张", "机遇"],
        "negative_signals": ["下降", "萎缩", "衰退", "紧缩", "加息", "风险", "不确定", "震荡", "回调"],
        "finding_templates": {
            "trend": "宏观话题热度{trend}，反映市场对该议题的关注度变化",
            "sentiment": "市场情绪{sentiment}，暗示宏观环境对交易决策的影响",
            "topics": "核心宏观议题：{topics}，指向当前市场关注的关键变量",
        },
    },
}


def clean_html_entities(text: str) -> str:
    """清理HTML实体残留"""
    if not text:
        return text
    text = re.sub(r'&ldquo;', '\u201c', text)
    text = re.sub(r'&rdquo;', '\u201d', text)
    text = re.sub(r'&darr;', '\u2193', text)
    text = re.sub(r'&hellip;', '\u2026', text)
    text = re.sub(r'&middot;', '\u00b7', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&quot;', '"', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&[a-z]+;', '', text)
    return text


def extract_keywords_from_text(text: str, top_k: int = 20) -> list:
    """从文本中提取关键词"""
    if not text:
        return []

    text = clean_html_entities(text)

    if JIEBA_AVAILABLE:
        keywords = jieba.analyse.extract_tags(text, topK=top_k, withWeight=True)
        filtered = [(word, weight) for word, weight in keywords
                     if word not in STOP_WORDS
                     and len(word) >= 2
                     and not re.match(r'^[a-z]{2,5}$', word)
                     and not re.match(r'^\d+$', word)
                     and word != '...']
        return filtered
    else:
        words = re.findall(r'[a-zA-Z]+|\d+|[\u4e00-\u9fff]{2,}', text)
        counter = Counter(words)
        filtered = [(word, count) for word, count in counter.most_common(top_k)
                     if word not in STOP_WORDS and len(word) >= 2]
        return filtered


def analyze_articles(articles: list, query: str, direction: str = "general") -> dict:
    """
    对搜索结果进行深度分析

    参数：
        articles: 文章列表
        query: 搜索关键词
        direction: 分析方向 (general/ecommerce/macro)

    返回结构化分析报告
    """
    config = DIRECTION_ANALYSIS_CONFIG.get(direction, DIRECTION_ANALYSIS_CONFIG["general"])
    direction_label = config["label"]

    if not articles:
        return {
            "summary": f"未找到与「{query}」（{direction_label}方向）相关的公众号文章，无法生成分析报告。",
            "key_findings": [],
            "topic_distribution": {},
            "source_analysis": {},
            "time_analysis": {},
            "keyword_cloud": [],
            "sentiment_hint": "无数据",
            "article_ranking": [],
            "direction": direction,
            "direction_label": direction_label,
        }

    # 1. 合并所有文本内容
    all_titles = clean_html_entities(" ".join([a.get("title", "") for a in articles]))
    all_digests = clean_html_entities(" ".join([a.get("digest", "") for a in articles]))
    all_content = clean_html_entities(" ".join([a.get("full_content", "") for a in articles if a.get("full_content")]))
    combined_text = f"{all_titles} {all_digests} {all_content}"

    # 2. 关键词分析
    keyword_weights = extract_keywords_from_text(combined_text, top_k=30)
    keyword_cloud = [{"word": w, "weight": round(float(wt), 4)} for w, wt in keyword_weights]

    # 3. 来源（公众号）分析
    account_counter = Counter([a.get("account", "\u672a\u77e5\u6765\u6e90") for a in articles])
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

    topic_words = Counter()
    for words in title_keywords.values():
        for w in words:
            topic_words[w] += 1

    topic_distribution = {
        "top_topics": [{"topic": word, "count": count}
                       for word, count in topic_words.most_common(15)],
    }

    # 6. 方向化信号分析
    focus_kw_hits = []
    for kw in config["focus_keywords"]:
        count = combined_text.lower().count(kw.lower())
        if count > 0:
            focus_kw_hits.append((kw, count))
    focus_kw_hits.sort(key=lambda x: x[1], reverse=True)

    # 7. 情绪/倾向分析
    pos_count = sum(1 for w, _ in keyword_weights if w in config["positive_signals"])
    neg_count = sum(1 for w, _ in keyword_weights if w in config["negative_signals"])

    if pos_count > neg_count + 2:
        sentiment_hint = "偏积极乐观"
    elif neg_count > pos_count + 2:
        sentiment_hint = "偏谨慎悲观"
    else:
        sentiment_hint = "相对中立平衡"

    # 8. 文章重要性排名（方向化加分）
    article_ranking = []
    for a in articles:
        score = 0
        title = a.get("title", "")
        digest = a.get("digest", "")
        full = a.get("full_content", "")

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

        # 方向关键词命中加分
        for kw, _ in focus_kw_hits[:10]:
            if kw in title or kw in digest:
                score += 2

        # 有全文内容的加分
        if full:
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

    # 9. 生成方向化关键发现
    key_findings = []

    # 核心关键词发现
    if keyword_weights:
        top_3 = [w for w, _ in keyword_weights[:3]]
        key_findings.append(f"核心话题聚焦于：{', '.join(top_3)}")

    # 方向关键词发现
    if focus_kw_hits:
        top_focus = [kw for kw, _ in focus_kw_hits[:5]]
        key_findings.append(f"{direction_label}方向高频信号词：{', '.join(top_focus)}")

    # 来源集中度发现
    if account_counter:
        top_account = account_counter.most_common(1)[0]
        if top_account[1] >= 3:
            key_findings.append(f"「{top_account[0]}」是该话题最活跃的公众号（{top_account[1]}篇相关文章）")

    # 时间趋势发现（方向化模板）
    if time_analysis["trend"]:
        trend_finding = config["finding_templates"]["trend"].format(trend=time_analysis["trend"])
        key_findings.append(trend_finding)

    # 情绪发现（方向化模板）
    sentiment_finding = config["finding_templates"]["sentiment"].format(sentiment=sentiment_hint)
    key_findings.append(sentiment_finding)

    # 关联话题发现（方向化模板）
    if topic_words:
        related = [w for w, c in topic_words.most_common(8) if w not in query.split()]
        if related:
            topics_finding = config["finding_templates"]["topics"].format(topics=", ".join(related[:5]))
            key_findings.append(topics_finding)

    # 10. 生成总体概述
    summary_parts = [
        f"本次深度研究基于「{query}」关键词（{direction_label}方向），",
        f"共检索到 {len(articles)} 篇微信公众号文章，",
        f"涉及 {len(account_counter)} 个不同公众号来源。",
    ]
    if time_analysis["time_range"]:
        summary_parts.append(f"时间跨度：{time_analysis['time_range']}。")
    if keyword_weights:
        top_kw_str = ", ".join([w for w, _ in keyword_weights[:5]])
        summary_parts.append(f"核心议题围绕 {top_kw_str} 等关键词展开。")
    if focus_kw_hits:
        top_focus_str = ", ".join([kw for kw, _ in focus_kw_hits[:3]])
        summary_parts.append(f"{direction_label}维度信号词：{top_focus_str}。")
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
        "article_ranking": article_ranking[:15],
        "direction": direction,
        "direction_label": direction_label,
        "focus_keywords_hit": [{"word": w, "count": c} for w, c in focus_kw_hits[:10]],
    }
