#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DeepSeek AI 分镜脚本生成：单条生成 + 全智能批量（每次创意不同）"""
import json
import re
import time
import uuid

import requests

from config import DEEPSEEK_BASE, DEEPSEEK_MODEL, get_deepseek_key

# 创意角度池：批量生成时轮换，保证每条不重样
ANGLES = [
    "公园遛弯·家人陪伴（温暖日常）",
    "海边日落·后躺看海（治愈浪漫）",
    "老城街头·买菜归来（市井烟火）",
    "高铁出行·安检登机（便捷出行）",
    "广场晨练·太极扇舞（活力清晨）",
    "超市购物·满载而归（轻松购物）",
    "湖边垂钓·静享时光（悠闲自在）",
    "接孙子放学·爷孙同行（亲情陪伴）",
    "小区花园·邻里夸赞（社交面子）",
    "早市赶集·豆浆油条（生活气息）",
    "郊游野餐·草地暖阳（休闲假日）",
    "老友聚会·公园下棋（老有所乐）",
    "机场候机·从容出行（长途无忧）",
    "孙子婚礼·隆重出席（重要场合）",
    "雨天出行·防滑安心（安全守护）",
    "医院复查·轻松往返（健康关怀）",
    "菜园劳作·自给自足（田园生活）",
    "博物馆参观·慢游细品（文化熏陶）",
    "夜市逛吃·人间美味（夜色烟火）",
    "旅行拍照·打卡胜地（网红爷爷）",
]

SYSTEM_PROMPT = """你是资深短视频导演，专为「爱优护轻便侠218电动轮椅」创作电商推广分镜脚本。

产品核心卖点（只能从以下选取，禁止编造）：
- 超轻：仅13.8kg（车架），航天级镁铝合金，单手可提，1秒折叠，折叠后比行李箱还小，可上飞机高铁公交
- 安全：自研3.0防翻系统、智能电磁刹车松手即停、400W大马力电机、轻松上30°陡坡、高亮尾灯
- 舒适：105-145°多角度后躺、双侧汽车级减震大弹簧、4cm加厚海绵坐垫、透气网布
- 智能：15m手机遥控、1分钟学会、语音播报、360°转向操纵杆、液晶屏
- 续航：10Ah=16km / 15Ah=25km / 22Ah=39km

创作规则：
1. 角色默认「欧洲老爷爷」（白发西方面孔精瘦，白衬衫+休闲裤）；女性角色可换年轻女性（吊带衫身材傲人）或年长女性（开衫针织）
2. 电动轮椅必须由乘坐者自己操控行驶（操纵杆/手机遥控），家人只在旁并肩走，绝不推车
3. 称呼统一「轻便折叠电动轮椅」，不写外观细节（外观由参考图决定），不出现品牌名/价格/参数文字
4. 每个分镜 10 秒，画面要具体有画面感（场景/机位/动作/镜头运动），镜头切换干脆
5. 全程无旁白字幕，无 BGM（后期加）
6. 结尾要有记忆点（定格/反转/互动）
7. 口播文案中的数字一律用中文读法书写：型号编号逐位读（218写成「二幺八」），数量单位用中文数值（39公里写成「三十九公里」、15米写成「十五米」、13.8公斤写成「十三点八公斤」、400W写成「四百瓦」）

输出格式（严格）：
【分镜1】画面描述...
【分镜2】画面描述...
...
【分镜N】画面描述...

---口播文案---
与分镜同步的完整口播解说文案（约每分镜30字，总时长与分镜数×10秒匹配，语气亲切有感染力，突出卖点，可口语化）"""


def _call_deepseek(user_prompt: str, max_tokens: int = 2000) -> str:
    key = get_deepseek_key()
    if not key:
        raise RuntimeError("未配置 DeepSeek API Key（AI 分镜生成需要）")
    for attempt in range(3):
        try:
            resp = requests.post(
                f"{DEEPSEEK_BASE}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": DEEPSEEK_MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.95, "max_tokens": max_tokens,
                },
                timeout=120,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"DeepSeek HTTP {resp.status_code}: {resp.text[:200]}")
            return resp.json()["choices"][0]["message"]["content"]
        except requests.exceptions.RequestException as e:
            if attempt == 2:
                raise RuntimeError(f"DeepSeek 请求失败: {e}")
            time.sleep(3)


def parse_storyboard(text: str) -> tuple[list[str], str]:
    """解析输出 → (分镜列表, 口播文案)"""
    shots = re.findall(r"【分镜\d+\s*[·.\-]?\s*[^\n】]*】([\s\S]*?)(?=【分镜\d+|---口播文案---|$)", text)
    shots = [s.strip() for s in shots if s.strip()]
    dub = ""
    m = re.search(r"---口播文案---\s*([\s\S]*?)$", text)
    if m:
        dub = m.group(1).strip()
    if not shots:  # 兜底：按行拆分
        shots = [l.strip() for l in text.splitlines() if l.strip() and not l.startswith("---")]
    return shots, dub


def build_user_prompt(angle: str, num_shots: int, product_info: str = "", template: str = "") -> str:
    # 节奏模板
    pace = {
        "": "节奏明快、镜头切换干脆（默认 3 分镜快节奏风格）",
        "d": "爆款洗脑逻辑：反差人设+魔性重复+快切卡点+路人惊讶反应+结尾定格反转",
        "slow2": "慢节奏沉浸式：每个分镜画面从容展开，镜头缓慢推移/环绕，情绪舒缓，适合纪录片/情感向",
        "slow1": "慢节奏电影感：单镜头长叙事，镜头极缓，氛围拉满，一镜到底的感觉",
    }.get(template, "节奏明快")
    base = (
        f"请创作 1 条成片的分镜脚本，共 {num_shots} 个分镜（每分镜 10 秒）。\n"
        f"节奏要求：{pace}\n"
        f"创意场景角度：{angle}\n"
    )
    if product_info:
        base += f"产品资料（必须精准引用，作为文案卖点依据）：\n{product_info}\n"
    base += "要求：每个分镜画面具体、有创意有脑洞、不重样；卖点自然融入场景；严格按格式输出。"
    return base


def generate_storyboard(angle: str, num_shots: int, product_info: str = "",
                        template: str = "") -> dict:
    """生成一条分镜脚本 → {shots: [...], dub: str, angle: str}"""
    text = _call_deepseek(build_user_prompt(angle, num_shots, product_info, template))
    shots, dub = parse_storyboard(text)
    if not shots:
        raise RuntimeError("AI 未返回有效分镜，请重试或手动填写")
    if len(shots) > num_shots:
        shots = shots[:num_shots]
    if not dub:  # 兜底：用分镜文本拼口播
        dub = "。".join(re.sub(r"【.*?】", "", s).strip() for s in shots) + "。"
    return {"shots": shots, "dub": dub, "angle": angle}


def generate_batch(count: int, num_shots: int, start_index: int = 1,
                   product_info: str = "", template: str = "") -> list[dict]:
    """全智能批量：count 条，角度池轮换，每条独立请求（随机选角度避免顺序重复感）"""
    import random
    random.seed(time.time())
    results = []
    for i in range(count):
        angle = random.choice(ANGLES) if count <= len(ANGLES) else ANGLES[i % len(ANGLES)]
        if count > len(ANGLES) and i >= len(ANGLES):
            angle = f"{ANGLES[i % len(ANGLES)]}·变奏{i // len(ANGLES) + 1}"
        card = generate_storyboard(angle, num_shots, product_info, template)
        card["batch_no"] = start_index + i
        results.append(card)
    return results
