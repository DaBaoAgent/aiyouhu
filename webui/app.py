#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""爱优护全自动视频生成工厂 - FastAPI 入口
启动: uvicorn app:app --host 127.0.0.1 --port 8000
"""
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import config
import storyboard
import tasks
import tts_client
from config import BGM_DIR, DATA_DIR, REFS_DIR, UPLOAD_DIR, VOICES_DIR

app = FastAPI(title="爱优护全自动视频生成工厂")
STATIC_DIR = Path(__file__).resolve().parent / "static"

ALLOWED_IMG = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_AUDIO = {".mp3", ".wav", ".m4a", ".flac"}

# 静态资源
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/files", StaticFiles(directory=str(DATA_DIR)), name="files")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "version": "0.1"}


# ---------- 上传 ----------

@app.post("/api/upload")
async def upload(file: UploadFile = File(...), kind: str = Form("ref_image")):
    """kind: ref_image(参考图) / voice_audio(克隆音色) / bgm(背景音乐)"""
    ext = Path(file.filename or "x").suffix.lower()
    if kind in ("ref_image",):
        if ext not in ALLOWED_IMG:
            raise HTTPException(400, f"仅支持图片格式: {ALLOWED_IMG}")
        dest_dir, prefix = REFS_DIR, "img"
    elif kind == "voice_audio":
        if ext not in ALLOWED_AUDIO:
            raise HTTPException(400, f"仅支持音频格式: {ALLOWED_AUDIO}")
        dest_dir, prefix = UPLOAD_DIR, "vo"
    elif kind == "bgm":
        if ext not in ALLOWED_AUDIO:
            raise HTTPException(400, f"仅支持音频格式: {ALLOWED_AUDIO}")
        dest_dir, prefix = BGM_DIR, "bgm"
    else:
        raise HTTPException(400, f"未知 kind: {kind}")
    fname = f"{prefix}_{uuid.uuid4().hex[:8]}{ext}"
    dest = dest_dir / fname
    if kind == "ref_image":
        # 压缩参考图：最长边1200 + JPEG q85，避免 H3 API 50MB 请求体超限
        from PIL import Image
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        try:
            im = Image.open(dest)
            im.thumbnail((1200, 1200), Image.LANCZOS)
            if im.mode in ("RGBA", "P"):
                bg = Image.new("RGB", im.size, (255, 255, 255))
                bg.paste(im, mask=im.split()[-1] if im.mode == "RGBA" else None)
                im = bg
            else:
                im = im.convert("RGB")
            jpg = dest.with_name(dest.stem + "_c.jpg")
            im.save(jpg, "JPEG", quality=85)
            dest.unlink(missing_ok=True)
            dest = jpg
        except Exception as e:
            raise HTTPException(400, f"图片处理失败: {e}")
    else:
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    return {"url": f"/files/{dest.relative_to(DATA_DIR).as_posix()}", "server_path": str(dest), "name": dest.name}


# ---------- 设置 ----------

@app.get("/api/settings")
def get_settings():
    return config.get_settings()


@app.post("/api/settings")
def post_settings(body: dict):
    if body.get("autodl_key"):
        config.write_env_key(config.ENV_FILE, "AUTODL_API_KEY", body["autodl_key"].strip())
    if body.get("deepseek_key"):
        config.write_env_key(config.ENV_FILE, "DEEPSEEK_API_KEY", body["deepseek_key"].strip())
    return config.get_settings()


# ---------- GPT-SoVITS ----------

@app.get("/api/tts/status")
def tts_status():
    return tts_client.service_status()


@app.post("/api/tts/start")
def tts_start():
    return tts_client.start_service()


@app.post("/api/tts/test")
def tts_test(body: dict):
    """试听配音：用文案前 10 个字生成，返回 wav URL"""
    text = (body.get("text") or "").strip()[:10]
    if not text:
        raise HTTPException(400, "文案为空")
    voices = {v["id"]: v for v in tts_client.list_voices()}
    voice = voices.get(body.get("voice_id", ""))
    if not voice:
        raise HTTPException(400, "音色不存在，请先上传/选择音色")
    if not tts_client.service_status()["running"]:
        raise HTTPException(500, "配音引擎不可用（需联网）")
    try:
        wav = tts_client._tts_sync(text, voice, float(body.get("speed", 1.05)))
        return {"url": f"/files/tts/{wav.name}", "text": text, "file": str(wav)}
    except RuntimeError as e:
        raise HTTPException(500, str(e))


# ---------- 音色库 ----------

@app.get("/api/voices")
def list_voices():
    return tts_client.list_voices()


@app.post("/api/voices")
async def clone_voice(file: UploadFile = File(...), name: str = Form("新音色"),
                      prompt_text: str = Form("")):
    """已切换 edge-tts（免费内置音色），不再支持上传克隆"""
    raise HTTPException(400, "配音引擎已切换为免费 edge-tts，请直接在下拉框选择内置音色")


# ---------- BGM 曲库 ----------

@app.get("/api/bgm")
def list_bgm():
    items = []
    for f in sorted(BGM_DIR.glob("*")):
        if f.suffix.lower() in ALLOWED_AUDIO:
            items.append({"name": f.name, "path": str(f),
                          "url": f"/files/bgm/{f.name}", "size_mb": round(f.stat().st_size / 1048576, 1)})
    return items


# ---------- AI 分镜 ----------

@app.post("/api/storyboard")
def gen_storyboard(body: dict):
    try:
        card = storyboard.generate_storyboard(
            body.get("angle", ""), int(body.get("num_shots", 6)),
            body.get("product_info", ""), body.get("template", ""))
        return {"ok": True, **card}
    except RuntimeError as e:
        raise HTTPException(500, str(e))


# ---------- 生成 ----------

@app.post("/api/generate")
def generate(body: dict):
    params = {
        "name": (body.get("name") or "轻便侠218_成片").strip(),
        "type": body.get("type", "manual"),
        "script_text": body.get("script_text", ""),
        "num_shots": int(body.get("num_shots", 6)),
        "duration": int(body.get("duration", 10)),
        "resolution": body.get("resolution", "1080p竖"),
        "workflow": body.get("workflow", "multi_image"),
        "images": body.get("images", []),
        "concurrency": int(body.get("concurrency", 1)),
        "voice_on": bool(body.get("voice_on", False)),
        "voice_id": body.get("voice_id", ""),
        "dub_text": body.get("dub_text", ""),
        "speed": float(body.get("speed", 1.0)),
        "voice_volume": float(body.get("voice_volume", 1.0)),
        "bgm_mode": body.get("bgm_mode", "none"),
        "bgm_file": body.get("bgm_file", ""),
        "bgm_name": body.get("bgm_name", ""),
        "bgm_volume": float(body.get("bgm_volume", 0.3)),
        "product_info": body.get("product_info", ""),
        "template": body.get("template", ""),
    }
    # 校验
    if params["resolution"] not in h3_resolutions():
        raise HTTPException(400, f"分辨率非法: {params['resolution']}")
    if params["workflow"] not in ("multi_image", "text2video", "first_last", "image_audio"):
        raise HTTPException(400, f"工作流非法: {params['workflow']}")
    if not params["images"] and params["workflow"] != "text2video":
        raise HTTPException(400, "请至少上传 1 张产品参考图")
    if params["voice_on"] and not params["voice_id"]:
        raise HTTPException(400, "请选择配音音色")
    if params["voice_on"] and not params["dub_text"].strip():
        raise HTTPException(400, "请填写配音文案")
    tasks.set_concurrency(params["concurrency"])

    if body.get("type") == "ai":
        count = max(1, min(200, int(body.get("ai_count", 1))))
        tids = tasks.submit_ai(params, count)
        return {"ok": True, "tasks": tids, "count": count}
    if not params["script_text"].strip():
        raise HTTPException(400, "分镜脚本为空，请填写或点击 AI 生成")
    tid = tasks.submit_manual(params)
    return {"ok": True, "tasks": [tid], "count": 1}


def h3_resolutions():
    import h3_gen
    return h3_gen.RESOLUTIONS


# ---------- 任务 ----------

@app.get("/api/tasks")
def get_tasks():
    return {"tasks": tasks.get_tasks()}


@app.get("/api/logs")
def get_logs(limit: int = 200):
    """聚合所有任务的操作日志（按时间倒序）"""
    entries = []
    for t in tasks.get_tasks():
        for e in (t.get("logs") or [])[-limit:]:
            entries.append({"task": t["name"], "time": e[0], "msg": e[1], "task_id": t["id"]})
    entries.sort(key=lambda x: x["time"], reverse=True)
    return {"logs": entries[:limit]}


@app.get("/api/tasks/{tid}/video")
def task_video(tid: str):
    t = tasks.TASKS.get(tid)
    if not t or not t.get("out_file") or not Path(t["out_file"]).exists():
        raise HTTPException(404, "成片不存在或未完成")
    return FileResponse(t["out_file"], media_type="video/mp4", filename=Path(t["out_file"]).name)


@app.get("/api/tasks/{tid}/log")
def task_log(tid: str):
    t = tasks.TASKS.get(tid)
    if not t:
        raise HTTPException(404, "任务不存在")
    return t


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
