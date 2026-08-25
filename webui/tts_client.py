#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GPT-SoVITS 本地配音服务：服务管理 / 音色克隆 / 试听 / 批量配音"""
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.parse
import uuid
from pathlib import Path

import requests

from config import (GPT_SOVITS_ROOT, GPT_SOVITS_VENV_PY, GPT_SOVITS_PORT,
                    TTS_DIR, UPLOAD_DIR, VOICES_DIR)

ASR_SCRIPT = r'''# -*- coding: utf-8 -*-
import os, sys, json
# 中文路径在 sentencepiece C++ 层打不开，用 junction 的 ASCII 路径
os.environ["MODELSCOPE_CACHE"] = r"D:\modelscope_cache"
from funasr import AutoModel
audio, lang = sys.argv[1], sys.argv[2]
m = AutoModel(model="iic/SenseVoiceSmall", trust_remote_code=True, device="cuda:0")
r = m.generate(input=audio, language=lang, use_itn=True)
import re as _re
text = _re.sub(r"<[^>]*>", "", r[0]["text"]).strip()
print(json.dumps({"text": text}, ensure_ascii=False))
'''


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def service_status() -> dict:
    up = _port_open(GPT_SOVITS_PORT)
    return {"running": up, "port": GPT_SOVITS_PORT, "root": str(GPT_SOVITS_ROOT)}


def start_service() -> dict:
    """拉起 api_v2.py 后台服务（幂等：已运行则直接返回）"""
    if _port_open(GPT_SOVITS_PORT):
        return service_status()
    if not GPT_SOVITS_VENV_PY.exists():
        return {"running": False, "error": f"venv 不存在: {GPT_SOVITS_VENV_PY}"}
    log = UPLOAD_DIR / "gptsovits.log"
    cmd = [
        str(GPT_SOVITS_VENV_PY), "api_v2.py",
        "-a", "127.0.0.1", "-p", str(GPT_SOVITS_PORT),
        "-c", "GPT_SoVITS/configs/tts_infer.yaml",
    ]
    try:
        subprocess.Popen(cmd, cwd=str(GPT_SOVITS_ROOT),
                         stdout=open(log, "w"), stderr=subprocess.STDOUT,
                         creationflags=0x00000008)  # DETACHED_PROCESS
    except Exception as e:
        return {"running": False, "error": str(e)}
    # 等待就绪（模型加载可能 30-120s）
    for _ in range(60):
        if _port_open(GPT_SOVITS_PORT):
            return {"running": True, "port": GPT_SOVITS_PORT}
        time.sleep(2)
    return {"running": False, "error": "服务启动超时（模型加载中？），查看 logs: " + str(log)}


def _tts_sync(text: str, ref_audio: str, prompt_text: str, speed: float = 1.0,
              out_path: Path = None) -> Path:
    """调本地 /tts 接口合成一段音频"""
    out_path = out_path or (TTS_DIR / f"tts_{uuid.uuid4().hex[:8]}.wav")
    params = {
        "text": text, "text_lang": "zh",
        "ref_audio_path": ref_audio,
        "prompt_lang": "zh", "prompt_text": prompt_text,
        "text_split_method": "cut5", "batch_size": 1,
        "media_type": "wav", "streaming_mode": "false",
        "speed_factor": speed,
    }
    url = f"http://127.0.0.1:{GPT_SOVITS_PORT}/tts?" + urllib.parse.urlencode(params)
    try:
        resp = requests.get(url, timeout=600)
    except requests.exceptions.ConnectionError:
        raise RuntimeError("GPT-SoVITS 服务未运行，请在设置中点击启动")
    if resp.status_code != 200:
        raise RuntimeError(f"TTS 失败 HTTP {resp.status_code}: {resp.text[:300]}")
    if len(resp.content) < 200:
        raise RuntimeError(f"TTS 返回为空/异常: {resp.text[:300]}")
    out_path.write_bytes(resp.content)
    return out_path


# ---------- 音色克隆 ----------

def asr_prompt_text(audio_path: Path) -> str:
    """用 GPT-SoVITS venv 的 SenseVoiceSmall 识别参考文本（子进程隔离）"""
    script = UPLOAD_DIR / "_asr_tmp.py"
    script.write_text(ASR_SCRIPT, encoding="utf-8")
    try:
        r = subprocess.run(
            [str(GPT_SOVITS_VENV_PY), str(script), str(audio_path), "zh"],
            capture_output=True, text=True, timeout=600, encoding="utf-8",
        )
        if r.returncode != 0:
            raise RuntimeError(f"ASR 失败: {r.stderr[-300:]}")
        return json.loads(r.stdout.strip().splitlines()[-1])["text"]
    finally:
        script.unlink(missing_ok=True)


def _trim_to_10s(audio_path: Path) -> Path:
    """裁剪参考音频为 3-10 秒（GPT-SoVITS 硬限制），返回 wav"""
    from config import FFMPEG
    out = UPLOAD_DIR / f"ref_{uuid.uuid4().hex[:8]}.wav"
    subprocess.run(
        [str(FFMPEG), "-y", "-i", str(audio_path), "-t", "10", "-ac", "1",
         "-ar", "24000", str(out)],
        capture_output=True, check=True)
    return out


def clone_voice(audio_path: Path, name: str, prompt_text: str = "") -> dict:
    """上传克隆音色：裁剪 3-10s → ASR → 存音色卡"""
    name = re.sub(r'[<>:"/\\|?*]', "_", name).strip() or f"音色{uuid.uuid4().hex[:4]}"
    vdir = VOICES_DIR / name
    vdir.mkdir(parents=True, exist_ok=True)
    ref = _trim_to_10s(audio_path)
    if not prompt_text.strip():
        prompt_text = asr_prompt_text(ref)
    voice_id = uuid.uuid4().hex[:10]
    card = {
        "id": voice_id, "name": name,
        "ref_audio": str(ref), "prompt_text": prompt_text,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    (vdir / "voice.json").write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
    # 也存一份快捷引用：ref.wav
    (vdir / "ref.wav").write_bytes(ref.read_bytes())
    return card


def list_voices() -> list[dict]:
    voices = []
    for d in sorted(VOICES_DIR.iterdir()):
        f = d / "voice.json"
        if f.exists():
            try:
                voices.append(json.loads(f.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
    return voices


# ---------- 配音 ----------

def split_text(text: str, max_chars: int = 180) -> list[str]:
    """按句切分，长句按 max_chars 硬切（对齐 GPT-SoVITS 稳定性）"""
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


def dub_text(text: str, voice: dict, speed: float = 1.0, tag: str = "dub") -> Path:
    """整段文案配音：分段合成 → 拼接 → 返回 wav 路径"""
    segs = split_text(text)
    if not segs:
        raise RuntimeError("配音文案为空")
    parts = []
    for i, seg in enumerate(segs):
        p = TTS_DIR / f"{tag}_{i:02d}.wav"
        _tts_sync(seg, voice["ref_audio"], voice["prompt_text"], speed, p)
        parts.append(p)
    out = TTS_DIR / f"{tag}_full.wav"
    from config import FFMPEG
    concat = TTS_DIR / f"{tag}_list.txt"
    concat.write_text("\n".join(f"file '{p.as_posix()}'" for p in parts), encoding="utf-8")
    subprocess.run([str(FFMPEG), "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
                    "-c:a", "pcm_s16le", str(out)], capture_output=True, check=True)
    concat.unlink(missing_ok=True)
    return out
