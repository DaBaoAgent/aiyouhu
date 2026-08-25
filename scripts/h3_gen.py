#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AutoDL.Art MiniMax H3 视频生成通用客户端
=======================================
支持全部 H3 ComfyUI 工作流：
  multi_image  多图参考生成视频 (minimax_h3_lightx2v_v5)  duration 1-10s
  image_audio  图+音频对口型   (minimax_h3_image_audio_to_video)  audio_duration 1-15s
  text2video   文生视频        (minimax_h3_lightx2v_no_pic)      duration 1-10s
  first_last   首尾帧生成      (minimax_h3_lightx2v)             duration 1-10s
  tts          indextts2 TTS   (indextts2-v1)

用法：
  python h3_gen.py -w multi_image --prompt "提示词" -i 图1.jpg -i 图2.jpg -r 1080p竖 -d 10 -o out.mp4
  python h3_gen.py -w image_audio -i 图.jpg -a 音.mp3 -r 768p竖 -d 5 -o out.mp4
  python h3_gen.py -w text2video --prompt "提示词" -r 768p横 -d 8 -o out.mp4

配置：环境变量或同目录 .env 文件 AUTODL_API_KEY（https://autodl.art/large-model/tokens 分组选 ComfyUI）
价格：480p ¥0.04/秒  768p ¥0.06/秒  1080p ¥0.10/秒
"""
import argparse
import base64
import mimetypes
import os
import sys
import time

import requests

BASE_URL = "https://autodl.art"
WORKFLOWS = {
    "multi_image": "minimax_h3_lightx2v_v5",
    "image_audio": "minimax_h3_image_audio_to_video",
    "text2video": "minimax_h3_lightx2v_no_pic",
    "first_last": "minimax_h3_lightx2v",
    "tts": "indextts2-v1",
}
RESOLUTIONS = ["480p竖", "768p竖", "1080p竖", "480p横", "768p横", "1080p横"]
POLL_INTERVAL = 20
MAX_WAIT = 25 * 60


def load_env_file(path=".env"):
    candidates = [path, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")]
    for p in candidates:
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    if k.strip() == "AUTODL_API_KEY":
                        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def to_data_url(path_or_url: str) -> str:
    if path_or_url.startswith(("http://", "https://", "data:")):
        return path_or_url
    if not os.path.exists(path_or_url):
        sys.exit(f"错误: 文件不存在: {path_or_url}（可传公网URL，本地文件自动转base64）")
    mime, _ = mimetypes.guess_type(path_or_url)
    mime = mime or "application/octet-stream"
    with open(path_or_url, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:{mime};base64,{b64}"


def headers():
    key = os.environ.get("AUTODL_API_KEY", "")
    if not key:
        sys.exit("错误: 未设置 AUTODL_API_KEY（https://autodl.art/large-model/tokens 创建，分组选 ComfyUI）")
    return {"Authorization": key, "Content-Type": "application/json"}


def create_task(workflow_id: str, payload: dict):
    url = f"{BASE_URL}/api/v1/comfyui/comfyui_workflow/{workflow_id}"
    print(f"[1/3] 提交任务 -> {url}")
    resp = requests.post(url, headers=headers(), json=payload, timeout=180)
    try:
        body = resp.json()
    except ValueError:
        sys.exit(f"提交失败 HTTP {resp.status_code}，非 JSON: {resp.text[:300]}")
    if body.get("code") != "Success":
        sys.exit(f"提交失败: {body.get('msg') or body}")
    task_id = body["data"]["task_id"]
    print(f"     task_id={task_id}  status={body['data'].get('status')}")
    return task_id


def query_task(task_id: str) -> dict:
    url = f"{BASE_URL}/api/v1/comfyui/comfyui_workflow/result/{task_id}"
    for attempt in range(5):
        try:
            resp = requests.get(url, headers=headers(), timeout=30)
            break
        except (requests.exceptions.SSLError, requests.exceptions.ConnectionError):
            print(f"    网络抖动(第{attempt+1}次重试)", flush=True)
            time.sleep(10)
    else:
        sys.exit(f"查询失败(网络): {task_id}")
    try:
        body = resp.json()
    except ValueError:
        sys.exit(f"查询失败 HTTP {resp.status_code}: {resp.text[:300]}")
    if body.get("code") != "Success":
        sys.exit(f"查询失败: {body.get('msg') or body}")
    return body.get("data", {})


def poll_task(task_id: str) -> str:
    deadline = time.time() + MAX_WAIT
    while time.time() < deadline:
        data = query_task(task_id)
        status = data.get("status", "")
        print(f"     status={status}  耗时={data.get('duration')}s")
        if status == "SUCCESS":
            for r in (data.get("results") or []):
                if r.get("type") == "video" and r.get("url"):
                    return r["url"]
            sys.exit(f"任务完成但无视频 URL: {data}")
        if status in ("FAILED", "ERROR", "CANCELLED"):
            sys.exit(f"任务失败: {data}")
        time.sleep(POLL_INTERVAL)
    sys.exit(f"等待超时（{MAX_WAIT//60} 分钟）: {task_id}")


def download(url: str, out_path: str):
    print(f"[3/3] 下载成片 -> {out_path}")
    resp = requests.get(url, timeout=300, stream=True)
    resp.raise_for_status()
    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 16):
            f.write(chunk)
    print(f"     完成: {out_path} ({os.path.getsize(out_path)/1024/1024:.1f} MB)")


def build_payload(args) -> dict:
    w = args.workflow
    if w == "image_audio":
        return {
            "audio_duration": args.duration,
            "ref_audio_0": to_data_url(args.audio),
            "ref_image_0": to_data_url(args.images[0]),
            "resolution": args.resolution,
        }
    if w == "multi_image":
        payload = {
            "duration": args.duration,
            "prompt": args.prompt,
            "resolution": args.resolution,
        }
        for i, img in enumerate(args.images):
            payload[f"ref_image_{i}"] = to_data_url(img)
        return payload
    if w == "text2video":
        return {
            "duration": args.duration,
            "prompt": args.prompt,
            "resolution": args.resolution,
        }
    if w == "first_last":
        payload = {
            "duration": args.duration,
            "prompt": args.prompt,
            "resolution": args.resolution,
        }
        for i, img in enumerate(args.images):
            payload[f"ref_image_{i}"] = to_data_url(img)
        return payload
    if w == "tts":
        return {"prompt": args.prompt, "ref_audio_0": to_data_url(args.audio)}
    sys.exit(f"未知工作流: {w}")


def main():
    ap = argparse.ArgumentParser(description="AutoDL.Art MiniMax H3 视频生成（多工作流）")
    ap.add_argument("-w", "--workflow", default="multi_image", choices=list(WORKFLOWS),
                    help="工作流类型，默认 multi_image")
    ap.add_argument("--prompt", help="提示词（multi_image/text2video/first_last 必填）")
    ap.add_argument("-i", "--images", action="append", help="参考图片（可多次传，multi_image 必填至少1张）")
    ap.add_argument("-a", "--audio", help="参考音频（image_audio 必填）")
    ap.add_argument("-r", "--resolution", default="768p竖", choices=RESOLUTIONS)
    ap.add_argument("-d", "--duration", type=int, default=5,
                    help="时长秒数：multi_image/text2video/first_last 1-10，image_audio 1-15")
    ap.add_argument("-o", "--out", default="output.mp4")
    args = ap.parse_args()

    load_env_file()
    if args.workflow == "image_audio" and not (args.images and args.audio):
        sys.exit("image_audio 需要 -i 图片 和 -a 音频")
    if args.workflow == "multi_image" and not args.images:
        sys.exit("multi_image 需要至少一张 -i 参考图")
    if args.workflow in ("text2video", "first_last", "tts") and not args.prompt:
        sys.exit(f"{args.workflow} 需要 --prompt")

    payload = build_payload(args)
    task_id = create_task(WORKFLOWS[args.workflow], payload)
    print(f"[2/3] 轮询任务状态（每 {POLL_INTERVAL}s，最长 {MAX_WAIT//60} 分钟）...")
    url = poll_task(task_id)
    download(url, args.out)


if __name__ == "__main__":
    main()
