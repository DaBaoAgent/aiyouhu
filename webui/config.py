#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""爱优护全自动视频生成工厂 - 配置与路径管理"""
import os
from pathlib import Path

# 项目根目录（webui/）
BASE_DIR = Path(__file__).resolve().parent
# ayh-h3 仓库根（含 scripts/h3_gen.py）
REPO_DIR = BASE_DIR.parent
H3_SCRIPTS_DIR = REPO_DIR / "scripts"
ENV_FILE = H3_SCRIPTS_DIR / ".env"          # AUTODL_API_KEY（与 CLI 共用）
HERMES_ENV = Path(os.environ.get("HERMES_HOME", str(Path.home() / "AppData/Local/hermes"))) / ".env"

DATA_DIR = BASE_DIR / "data"
REFS_DIR = DATA_DIR / "refs"        # 上传参考图
VOICES_DIR = DATA_DIR / "voices"    # 克隆音色库
TTS_DIR = DATA_DIR / "tts"          # 配音中间产物
OUTPUTS_DIR = DATA_DIR / "outputs"  # 成片
BGM_DIR = DATA_DIR / "bgm"          # 内置 BGM 曲库
UPLOAD_DIR = DATA_DIR / "uploads"   # BGM/音色等临时上传
for d in (REFS_DIR, VOICES_DIR, TTS_DIR, OUTPUTS_DIR, BGM_DIR, UPLOAD_DIR):
    d.mkdir(parents=True, exist_ok=True)

# 外部工具
FFMPEG = Path(r"D:\@佳康顺矩阵\@工具\ffmpeg\ffmpeg.exe")
GPT_SOVITS_ROOT = Path(r"D:\@佳康顺矩阵\@工具\GPT-SoVITS")
GPT_SOVITS_VENV_PY = GPT_SOVITS_ROOT / ".venv/Scripts/python.exe"
GPT_SOVITS_PORT = 9880

# DeepSeek（AI 分镜/文案）
DEEPSEEK_BASE = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"


def read_env_key(env_path: Path, key: str) -> str:
    """从 .env 读取键值"""
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except (OSError, FileNotFoundError):
        pass
    return ""


def write_env_key(env_path: Path, key: str, value: str):
    """写入/更新 .env 键值（保留其他行）"""
    value = value.strip()
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    else:
        lines = []
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(key + "="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def get_autodl_key() -> str:
    return read_env_key(ENV_FILE, "AUTODL_API_KEY")


def get_deepseek_key() -> str:
    return read_env_key(HERMES_ENV, "DEEPSEEK_API_KEY") or read_env_key(ENV_FILE, "DEEPSEEK_API_KEY")


def get_settings() -> dict:
    """设置弹窗数据（key 脱敏）"""
    def mask(v: str) -> str:
        return v[:6] + "****" + v[-4:] if len(v) > 12 else ("****" if v else "")
    return {
        "autodl_key": mask(get_autodl_key()),
        "autodl_key_set": bool(get_autodl_key()),
        "deepseek_key": mask(get_deepseek_key()),
        "deepseek_key_set": bool(get_deepseek_key()),
        "gpt_sovits_root": str(GPT_SOVITS_ROOT),
        "gpt_sovits_port": GPT_SOVITS_PORT,
    }
