#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""edge-tts 免费配音模块(替代本地 GPT-SoVITS): 音色列表 / 试听 / 分段配音

- 微软神经语音, 免费在线合成, 无需本地服务/显卡/模型
- 语速用 rate 参数(纯变速不变调), 音量在混流阶段用 ffmpeg 控制
- 直连失败自动走本机 VPN 代理(127.0.0.1:15715)重试
"""
import asyncio
import re
import subprocess
import uuid
from pathlib import Path

import edge_tts

from config import FFMPEG, TTS_DIR

# 微软神经语音(中文) - 免费在线 TTS
EDGE_VOICES = [
    {"id": "zh-CN-YunyangNeural", "name": "云扬·男(新闻解说)", "gender": "男", "desc": "沉稳大气，纪录片/宣传片解说首选"},
    {"id": "zh-CN-YunjianNeural", "name": "云健·男(浑厚)", "gender": "男", "desc": "浑厚有力，大气宣传"},
    {"id": "zh-CN-YunxiNeural", "name": "云希·男(年轻)", "gender": "男", "desc": "阳光活力，年轻感"},
    {"id": "zh-CN-YunxiaNeural", "name": "云夏·男(少年)", "gender": "男", "desc": "清爽少年音"},
    {"id": "zh-CN-YunfengNeural", "name": "云枫·男(轻松)", "gender": "男", "desc": "轻松亲和"},
    {"id": "zh-CN-XiaoxiaoNeural", "name": "晓晓·女(通用)", "gender": "女", "desc": "温柔亲切，最常用女声"},
    {"id": "zh-CN-XiaoyiNeural", "name": "晓伊·女(活泼)", "gender": "女", "desc": "甜美活泼"},
    {"id": "zh-CN-XiaohanNeural", "name": "晓涵·女(温暖)", "gender": "女", "desc": "温暖治愈"},
    {"id": "zh-CN-XiaomoNeural", "name": "晓墨·女(柔和)", "gender": "女", "desc": "柔和知性"},
    {"id": "zh-CN-XiaoruiNeural", "name": "晓睿·女(成熟)", "gender": "女", "desc": "成熟稳重"},
    {"id": "zh-CN-XiaozhenNeural", "name": "晓甄·女(电台)", "gender": "女", "desc": "电台播音感"},
]

PROXY = "http://127.0.0.1:15715"  # 本机 VPN 代理(直连失败时兜底)

# ---------- 数字转中文读法(配音准确) ----------
# 型号/编号逐位读: 218 → 二幺八; 带单位数值读: 39公里 → 三十九公里
_CN = "零一二三四五六七八九"
_DIGIT_SPOKEN = {"0": "零", "1": "幺", "2": "二", "3": "三", "4": "四",
                 "5": "五", "6": "六", "7": "七", "8": "八", "9": "九"}
_UNIT_MAP = {
    # 字母单位(长词优先匹配)
    "km": "公里", "kg": "公斤", "Ah": "安时", "Hz": "赫兹", "mA": "毫安",
    "m": "米", "W": "瓦", "V": "伏", "A": "安", "h": "小时", "min": "分钟", "s": "秒",
    # 中文单位
    "公里": "公里", "千米": "千米", "公斤": "公斤", "千克": "千克", "斤": "斤",
    "克": "克", "吨": "吨", "米": "米", "厘米": "厘米", "毫米": "毫米",
    "寸": "寸", "英寸": "英寸", "毫升": "毫升", "升": "升", "度": "度",
    "伏": "伏", "瓦": "瓦", "安": "安", "毫安": "毫安", "赫兹": "赫兹",
    "分钟": "分钟", "小时": "小时", "秒": "秒", "档": "档",
}
_UNIT_ALT = "|".join(sorted(_UNIT_MAP.keys(), key=len, reverse=True))
_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_DEG_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[°度]")
_UNIT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(" + _UNIT_ALT + ")")
_RAW_NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def _int_to_cn(n: int) -> str:
    """整数 0-999999 转中文读数: 15→十五, 39→三十九, 218→二百一十八"""
    if n == 0:
        return "零"
    if n < 0:
        return "负" + _int_to_cn(-n)
    if n >= 10000:
        w, r = divmod(n, 10000)
        tail = "" if r == 0 else ("零" + _int_to_cn(r) if r < 1000 else _int_to_cn(r))
        return _int_to_cn(w) + "万" + tail
    units = ["", "十", "百", "千"]
    out, s = "", str(n)
    for i, ch in enumerate(s):
        d = int(ch)
        pos = len(s) - 1 - i
        if d == 0:
            if out and not out.endswith("零"):
                out += "零"
        elif d == 1 and pos == 1 and len(s) == 2:
            out += "十"  # 10-19: 十五、十八, 不读"一十五"
        else:
            out += _CN[d] + units[pos]
    return out.rstrip("零")


def _num_value_cn(s: str) -> str:
    """数值读法(带单位): 15→十五, 13.8→十三点八"""
    if "." in s:
        a, b = s.split(".", 1)
        r = _int_to_cn(int(a)) if a else "零"
        return r + "点" + "".join(_CN[int(c)] for c in b)
    return _int_to_cn(int(s))


def _digit_cn(s: str) -> str:
    """型号/编号逐位读: 218→二幺八, 3.0→三点零"""
    if "." in s:
        a, b = s.split(".", 1)
        return _digit_cn(a) + "点" + "".join(_DIGIT_SPOKEN.get(c, c) for c in b)
    return "".join(_DIGIT_SPOKEN.get(c, c) for c in s)


def normalize_text(text: str) -> str:
    """数字转中文读法, 保证配音准确(幂等):
    - 30% → 百分之三十; 30° → 三十度
    - 带单位 → 数值读法: 15米→十五米, 39公里→三十九公里, 13.8公斤→十三点八公斤, 400W→四百瓦
    - 裸数字 → 型号逐位读: 218→二幺八, F2Q→F二Q
    """
    if not text:
        return text
    text = _PCT_RE.sub(lambda m: "百分之" + _num_value_cn(m.group(1)), text)
    text = _DEG_RE.sub(lambda m: _num_value_cn(m.group(1)) + "度", text)
    text = _UNIT_RE.sub(lambda m: _num_value_cn(m.group(1)) + _UNIT_MAP[m.group(2)], text)
    text = _RAW_NUM_RE.sub(lambda m: _digit_cn(m.group(0)), text)
    return text


def service_status() -> dict:
    """edge-tts 无需本地服务, 恒可用(依赖联网)"""
    return {"running": True, "provider": "edge-tts", "port": None, "root": ""}


def start_service() -> dict:
    return service_status()


def list_voices() -> list[dict]:
    return [dict(v) for v in EDGE_VOICES]


def _rate_from_speed(speed: float) -> str:
    """语速 0.7-1.3 → edge-tts rate 百分比(纯变速不变调)"""
    pct = int(round((speed - 1.0) * 100))
    pct = max(-50, min(50, pct))
    return f"{pct:+d}%"


async def _tts_async(text: str, voice_id: str, rate: str, out_path: Path):
    """edge-tts 单段合成（async 版），直连失败自动走代理重试"""
    async def _run(proxy):
        com = edge_tts.Communicate(text, voice_id, rate=rate, proxy=proxy)
        await com.save(str(out_path))
    try:
        await _run(None)
    except Exception:
        # 直连失败 → 走本机 VPN 代理重试一次
        try:
            await _run(PROXY)
        except Exception as e:
            raise RuntimeError(f"edge-tts 合成失败(直连与代理均失败): {e}")
    if not out_path.exists() or out_path.stat().st_size < 200:
        raise RuntimeError("edge-tts 返回为空，请检查网络后重试")


def _tts_sync(text: str, voice: dict, speed: float = 1.0,
              out_path: Path = None) -> Path:
    """同步单段合成（试听用），返回 mp3 路径"""
    out_path = out_path or (TTS_DIR / f"tts_{uuid.uuid4().hex[:8]}.mp3")
    text = normalize_text(text)  # 数字转中文读法(型号218→二幺八, 39公里→三十九公里)
    rate = _rate_from_speed(speed)
    try:
        asyncio.run(_tts_async(text, voice["id"], rate, out_path))
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"edge-tts 合成失败: {e}")
    return out_path


def split_text(text: str, max_chars: int = 180) -> list[str]:
    """按句切分，长句按 max_chars 硬切（每段独立合成，保证稳定性）"""
    import re
    text = re.sub(r"\s+", "", text)
    sentences = [s for s in re.split(r"(?<=[。！？!?；;])", text) if s]
    chunks, cur = [], ""
    for s in sentences:
        if len(s) > max_chars:  # 超长句硬切
            for i in range(0, len(s), max_chars):
                chunks.append(s[i:i + max_chars])
            continue
        if cur and len(cur) + len(s) > max_chars:
            chunks.append(cur)
            cur = s
        else:
            cur += s
    if cur:
        chunks.append(cur)
    return chunks


def dub_text(text: str, voice: dict, speed: float = 1.0, tag: str = "dub",
             on_seg: callable = None) -> Path:
    """整段文案配音：分段 edge-tts 并发合成 → 拼接 → 返回 wav 路径。on_seg(i, n, path) 每段完成回调"""
    segs = split_text(text)
    if not segs:
        raise RuntimeError("配音文案为空")
    rate = _rate_from_speed(speed)

    async def _synth(i: int, seg: str):
        p = TTS_DIR / f"{tag}_{i:02d}.mp3"
        await _tts_async(normalize_text(seg), voice["id"], rate, p)
        return i, p

    async def _run_all():
        return await asyncio.gather(*[_synth(i, s) for i, s in enumerate(segs)])

    parts = [p for _, p in sorted(asyncio.run(_run_all()))]
    if on_seg:
        for i, p in enumerate(parts, 1):
            on_seg(i, len(parts), p)
    out = TTS_DIR / f"{tag}_full.wav"
    if len(parts) == 1:
        subprocess.run(
            [str(FFMPEG), "-y", "-i", str(parts[0]), "-ac", "1", "-ar", "24000",
             "-c:a", "pcm_s16le", str(out)],
            capture_output=True, check=True)
    else:
        inputs = []
        for p in parts:
            inputs += ["-i", str(p)]
        flt = "".join(f"[{i}:a]" for i in range(len(parts))) + \
            f"concat=n={len(parts)}:v=0:a=1[a]"
        subprocess.run(
            [str(FFMPEG), "-y"] + inputs +
            ["-filter_complex", flt, "-map", "[a]", "-ac", "1", "-ar", "24000",
             "-c:a", "pcm_s16le", str(out)],
            capture_output=True, check=True)
    return out
