#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务管理器：队列 / 进度 / 完整成片流水线（分镜→H3视频→配音→拼接→BGM）"""
import json
import os
import re
import sys
import threading
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import h3_gen  # noqa: E402
h3_gen.load_env_file()  # 读 scripts/.env 的 AUTODL_API_KEY 到环境变量

from config import (BGM_DIR, FFMPEG, OUTPUTS_DIR, REPO_DIR, TTS_DIR,  # noqa: E402
                    get_autodl_key)
import tts_client  # noqa: E402

LOCK = threading.RLock()
TASKS: dict[str, dict] = {}
SEM: threading.Semaphore | None = None
TASKS_FILE = Path(__file__).resolve().parent / "data" / "tasks.json"
CURRENT_CONCURRENCY = 1


def _save():
    with LOCK:
        try:
            TASKS_FILE.write_text(json.dumps(TASKS, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass


def _load():
    global TASKS
    if TASKS_FILE.exists():
        try:
            TASKS = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            TASKS = {}


def set_concurrency(n: int):
    global SEM, CURRENT_CONCURRENCY
    SEM = threading.Semaphore(max(1, int(n)))
    CURRENT_CONCURRENCY = max(1, int(n))


def get_tasks() -> list[dict]:
    with LOCK:
        return [dict(t) for t in sorted(TASKS.values(), key=lambda x: x.get("created_at", ""), reverse=True)]


def _update(task_id: str, **kw):
    with LOCK:
        t = TASKS.get(task_id)
        if t:
            t.update(kw)
            _save()


def _log(task_id: str, msg: str):
    """追加操作日志（时间戳 + 消息 + 距上一条耗时秒），上限 1000 条"""
    with LOCK:
        t = TASKS.get(task_id)
        if t is None:
            return
        now = time.time()
        prev = t.get("_last_log_ts", now)
        dur = int(round(now - prev))
        t.setdefault("logs", []).append((time.strftime("%H:%M:%S"), msg, dur))
        t["_last_log_ts"] = now
        if len(t["logs"]) > 1000:
            t["logs"] = t["logs"][-1000:]
        _save()


def parse_script(text: str, num_shots: int) -> list[str]:
    """解析分镜脚本：按【分镜N】分割，兜底按行"""
    shots = re.findall(r"【分镜\d+\s*[·.\-]?\s*[^\n】]*】([\s\S]*?)(?=【分镜\d+【|\Z)", text)
    if not shots:
        shots = [l.strip() for l in text.splitlines() if l.strip()]
    shots = [re.sub(r"\s+", " ", s).strip() for s in shots if s.strip()]
    return shots[:num_shots] if num_shots else shots


def _h3_submit(workflow: str, prompt: str, images: list[str], resolution: str,
               duration: int, out_path: Path, task_id: str = "") -> tuple[str, Path]:
    """提交 H3 任务并同步等待完成，返回 (耗时秒, 下载文件路径)。失败抛 RuntimeError。带细粒度日志"""
    def guard(fn, *a, **kw):
        """h3_gen 用 sys.exit 抛 SystemExit，需转成 RuntimeError"""
        try:
            return fn(*a, **kw)
        except SystemExit as e:
            raise RuntimeError(str(e) or "H3 客户端错误")

    if not get_autodl_key():
        raise RuntimeError("未配置 AUTODL_API_KEY，请在 ⚙API设置 中填写")
    payload = {"duration": duration, "resolution": resolution}
    if workflow != "text2video":
        payload["prompt"] = prompt
        for i, img in enumerate(images[:9]):  # API 上限 ref_image_0~8
            payload[f"ref_image_{i}"] = h3_gen.to_data_url(img)
    else:
        payload["prompt"] = prompt
    _log(task_id, f"⏫ H3提交: 工作流={workflow} 分辨率={resolution} 时长={duration}s 参考图={len(images[:9])}张")
    cloud_id = guard(h3_gen.create_task, h3_gen.WORKFLOWS[workflow], payload)
    _log(task_id, f"→ H3云端任务ID: {cloud_id}")
    # 轮询（带网络重试），同步阻塞；状态变化/每60s心跳记日志
    deadline = time.time() + h3_gen.MAX_WAIT
    url = None
    last_status, last_beat = "", time.time()
    while time.time() < deadline:
        data = guard(h3_gen.query_task, cloud_id)
        st = data.get("status", "")
        if st != last_status:
            dur_msg = f"（云端已耗时{data.get('duration')}s）" if data.get("duration") else ""
            _log(task_id, f"⏳ H3状态: {st}{dur_msg}")
            last_status = st
        elif time.time() - last_beat >= 60:
            _log(task_id, f"⏳ H3轮询中… 状态={st} 云端耗时={data.get('duration', '?')}s")
            last_beat = time.time()
        if st == "SUCCESS":
            for r in (data.get("results") or []):
                if r.get("type") == "video" and r.get("url"):
                    url = r["url"]
                    break
            if not url:
                raise RuntimeError(f"任务成功但无视频URL: {data}")
            break
        if st in ("FAILED", "ERROR", "CANCELLED"):
            raise RuntimeError(f"H3 任务失败: {data.get('msg') or data}")
        time.sleep(h3_gen.POLL_INTERVAL)
    if not url:
        raise RuntimeError(f"H3 等待超时（{h3_gen.MAX_WAIT // 60}分钟）: {cloud_id}")
    _log(task_id, "⬇ H3 视频生成完成，开始下载")
    t0 = time.time()
    guard(h3_gen.download, url, str(out_path))
    _log(task_id, f"✅ H3 下载完成: {out_path.name}（{out_path.stat().st_size / 1048576:.1f}MB，耗时{time.time() - t0:.0f}s）")
    return data.get("duration") or duration, out_path


def _gen_shot(task_id: str, shot_idx: int, params: dict, prompt: str, out_dir: Path) -> None:
    """单个分镜视频（信号量内并发）"""
    global SEM
    sem = SEM or threading.Semaphore(1)
    with sem:
        _update(task_id, stage=f"分镜{shot_idx} 视频生成中")
        _log(task_id, f"▶ 分镜{shot_idx} 提交 H3 任务（{params.get('resolution')} {params.get('duration')}s）")
        t0 = time.time()
        try:
            out = out_dir / f"shot_{shot_idx:02d}.mp4"
            _, _ = _h3_submit(
                params.get("workflow", "multi_image"),
                prompt,
                params.get("images", []),
                params.get("resolution", "1080p竖"),
                int(params.get("duration", 10)),
                out,
                task_id=task_id,
            )
            _log(task_id, f"✅ 分镜{shot_idx} 视频生成完成（{out.stat().st_size / 1048576:.1f}MB，耗时{time.time() - t0:.0f}s）")
            with LOCK:
                for s in TASKS[task_id]["shots"]:
                    if s["idx"] == shot_idx:
                        s.update(status="done", file=str(out))
                done = sum(1 for s in TASKS[task_id]["shots"] if s["status"] == "done")
                total = len(TASKS[task_id]["shots"])
                TASKS[task_id]["progress"] = int(55 + done / total * 35)
                _save()
        except Exception as e:
            _log(task_id, f"❌ 分镜{shot_idx} 失败: {e}")
            with LOCK:
                for s in TASKS[task_id]["shots"]:
                    if s["idx"] == shot_idx:
                        s.update(status="failed", error=str(e))
                _save()
            raise


def _merge_and_mix(task: dict, params: dict, shot_files: list[Path], voice_wav: Path | None) -> Path:
    """拼接分镜视频 → 混入配音+BGM → 成片"""
    tid = task["id"]
    out_dir = OUTPUTS_DIR / tid
    out_dir.mkdir(parents=True, exist_ok=True)

    # 成片输出目录：优先用户选择的目录，否则默认 outputs/<tid>；异常回退默认
    final_dir = None
    od = (params.get("output_dir") or "").strip()
    if od:
        final_dir = Path(od)
        if not final_dir.is_dir():
            _log(tid, f"⚠ 输出目录不可用，回退默认: {OUTPUTS_DIR / tid}")
            final_dir = None
    base = final_dir or out_dir
    final = unique_path(base / f"{task['name']}.mp4")

    _update(tid, stage="拼接分镜视频")
    _log(tid, f"🔗 拼接 {len(shot_files)} 条分镜视频")
    t0 = time.time()
    merged = out_dir / "merged.mp4"
    lst = out_dir / "concat.txt"
    lst.write_text("\n".join(f"file '{p.as_posix()}'" for p in shot_files), encoding="utf-8")
    _run_ff(["-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(merged)])
    _log(tid, f"✅ 拼接完成（{merged.stat().st_size / 1048576:.1f}MB，耗时{time.time() - t0:.0f}s）")

    # 音频轨准备
    audio_inputs, filter_parts, mix_index = [], [], 0
    if voice_wav:
        audio_inputs += ["-i", str(voice_wav)]
        filter_parts.append(f"[{mix_index}:a]volume={params.get('voice_volume', 1.0)}[v{mix_index}]")
        mix_index += 1
    bgm_file = params.get("bgm_file", "")
    if bgm_file and Path(bgm_file).exists():
        audio_inputs += ["-i", str(bgm_file)]
        vol = float(params.get("bgm_volume", 0.3))
        filter_parts.append(f"[{mix_index}:a]volume={vol},aloop=loop=-1:size=2e9,atrim=0:{task['duration_s']}[b{mix_index}]")
        mix_index += 1
    if filter_parts:
        _update(tid, stage="混流配音与BGM")
        parts_desc = []
        if voice_wav:
            parts_desc.append(f"配音×{params.get('voice_volume', 1.0)}")
        if bgm_file and Path(bgm_file).exists():
            parts_desc.append(f"BGM {Path(bgm_file).name}×{vol}")
        _log(tid, f"🎚 混流: {', '.join(parts_desc)}")
        t1 = time.time()
        n = len(filter_parts)
        if n == 2:
            amix = f"[v0][b1]amix=inputs=2:duration=first:dropout_transition=0[aout]"
        else:
            amix = f"[v0]anull[aout]" if n == 1 else "anull[aout]"
        _run_ff(["-y", "-i", str(merged)] + audio_inputs +
                ["-filter_complex", ";".join(filter_parts) + ";" + amix,
                 "-map", "0:v", "-map", "[aout]",
                 "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(final)])
        _log(tid, f"✅ 混流完成（{final.stat().st_size / 1048576:.1f}MB，耗时{time.time() - t1:.0f}s）")
        return final
    # 无配音无BGM：直接返回拼接
    _run_ff(["-y", "-i", str(merged), "-c", "copy", str(final)])
    return final


def _run_ff(args: list):
    r = subprocess_run([str(FFMPEG)] + args)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg 失败: {r.stderr[-400:] if r.stderr else 'unknown'}")


def subprocess_run(cmd, **kw):
    import subprocess
    kw.setdefault("capture_output", True)
    return subprocess.run(cmd, **kw)


def _dub_voice(task_id: str, text: str, voice_id: str, speed: float) -> Path | None:
    """配音（edge-tts，带逐段日志与耗时）"""
    if not text.strip():
        return None
    voices = {v["id"]: v for v in tts_client.list_voices()}
    voice = voices.get(voice_id)
    if not voice:
        raise RuntimeError(f"音色不存在: {voice_id}")
    rate = tts_client._rate_from_speed(float(speed))
    _update(task_id, stage="配音生成中")
    _log(task_id, f"🎙 配音开始: 音色={voice['name']} 语速={speed}×（rate {rate}）")
    t0 = time.time()
    seg_info = {"n": 0}

    def on_seg(i: int, n: int, p: Path):
        seg_info["n"] = n
        _log(task_id, f"🎙 配音段 {i}/{n} 完成（{p.stat().st_size / 1024:.0f}KB）")

    try:
        wav = tts_client.dub_text(text, voice, float(speed), tag=task_id, on_seg=on_seg)
        n = seg_info["n"] or 1
        _log(task_id, f"✅ 配音完成: 共{n}段合成拼接（{wav.stat().st_size / 1048576:.2f}MB，耗时{time.time() - t0:.0f}s）")
        return wav
    except Exception as e:
        _log(task_id, f"❌ 配音失败: {e}")
        raise e


def _run_film(task_id: str, card: dict, params: dict):
    """一条成片完整流程"""
    task = TASKS.get(task_id)
    if not task:
        return
    _update(task_id, status="running")
    out_dir = OUTPUTS_DIR / task_id
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        shots = card.get("shots") or parse_script(card.get("script_text", ""), int(params.get("num_shots", 6)))
        shots = shots[: int(params.get("num_shots", len(shots)))]
        if not shots:
            raise RuntimeError("分镜脚本为空")
        _log(task_id, f"🚀 开始生成：{len(shots)} 个分镜 → H3视频 → 配音 → 拼接")
        with LOCK:
            task["shots"] = [{"idx": i + 1, "status": "pending", "file": "", "error": ""} for i in range(len(shots))]
            _save()
        _update(task_id, stage=f"共{len(shots)}个分镜 · 提交中")

        # 并行：视频生成 与 配音
        results: dict[int, Path] = {}
        errors: list[str] = []
        vthreads = []

        def worker(idx: int, prompt: str):
            try:
                _gen_shot(task_id, idx, params, prompt, out_dir)
                results[idx] = out_dir / f"shot_{idx:02d}.mp4"
            except Exception as e:
                errors.append(f"分镜{idx}: {e}")

        for i, sh in enumerate(shots, start=1):
            t = threading.Thread(target=worker, args=(i, sh), daemon=True)
            vthreads.append(t)
            t.start()

        # 主线程配音（与视频并行）
        voice_wav = None
        if params.get("voice_on") and params.get("dub_text", "").strip():
            _log(task_id, "🎙 配音生成中（edge-tts 云端）")
            try:
                voice_wav = _dub_voice(task_id, card.get("dub") or params["dub_text"],
                                       params["voice_id"], float(params.get("speed", 1.05)))
                _log(task_id, "✅ 配音完成")
            except Exception as e:
                errors.append(f"配音: {e}")
                _log(task_id, f"❌ 配音失败: {e}")

        for t in vthreads:
            t.join()

        if errors:
            raise RuntimeError("；".join(errors[:3]))
        shot_files = [results[i] for i in sorted(results)]
        _update(task_id, progress=92, stage="拼接与混流")
        _log(task_id, "🔗 拼接分镜视频")
        final = _merge_and_mix(task, params, shot_files, voice_wav)
        _update(task_id, status="success", stage="已完成", progress=100,
                out_file=str(final), finished_at=time.strftime("%H:%M:%S"),
                size_mb=round(final.stat().st_size / 1048576, 1))
        _log(task_id, f"🎉 成片完成：{final.name}（{round(final.stat().st_size/1048576,1)}MB）")
    except Exception as e:
        _update(task_id, status="failed", stage="失败", error=str(e), finished_at=time.strftime("%H:%M:%S"))
        _log(task_id, f"❌ 任务失败: {e}")
    _save()


def _submit_task(name: str, params: dict, card: dict) -> str:
    tid = uuid.uuid4().hex[:10]
    name = sanitize_name(name)
    duration_s = len(card.get("shots") or parse_script(card.get("script_text", ""), 99)) * int(params.get("duration", 10))
    with LOCK:
        TASKS[tid] = {
            "id": tid, "name": name, "type": params.get("type", "manual"),
            "status": "queued", "stage": "排队中", "progress": 0,
            "shots": [], "error": "", "out_file": "", "size_mb": 0,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_s": duration_s, "resolution": params.get("resolution"),
            "voice_on": bool(params.get("voice_on")), "bgm": params.get("bgm_name", ""),
            "angle": card.get("angle", ""),
            "output_dir": (params.get("output_dir") or "").strip(),
        }
        _save()
    return tid


def sanitize_name(name: str) -> str:
    """成片文件名清理：去 Windows 非法字符，防空名"""
    name = re.sub(r'[<>:"/\\|?*]', "_", str(name or "")).strip()
    return name or "成片"


def unique_path(p: Path) -> Path:
    """重名自动加 _1/_2 后缀（不覆盖已有成片）"""
    if not p.exists():
        return p
    stem, suffix = p.stem, p.suffix
    for i in range(1, 1000):
        cand = p.with_name(f"{stem}_{i}{suffix}")
        if not cand.exists():
            return cand
    return p.with_name(f"{stem}_{int(time.time())}{suffix}")


def submit_manual(params: dict) -> str:
    """手动模式：用户已填好分镜脚本，生成 1 条成片"""
    tid = _submit_task(params.get("name", "成片"), params, {"script_text": params.get("script_text", "")})
    threading.Thread(target=_run_film, args=(tid, {"script_text": params.get("script_text", "")}, params),
                     daemon=True).start()
    return tid


def submit_ai(params: dict, count: int) -> list[str]:
    """全智能批量：N 条，逐条 AI 生成脚本→完整流程"""
    import storyboard
    tids = []
    for i in range(count):
        name = f"{params.get('name', '成片')}_{i + 1:02d}"
        tid = _submit_task(name, {**params, "type": "ai"}, {"shots": [], "script_text": ""})
        tids.append(tid)

    def coordinator():
        for i, tid in enumerate(tids):
            t = TASKS.get(tid)
            if not t or t["status"] != "queued":
                continue
            _update(tid, stage="AI 创意文案生成中")
            _log(tid, "🤖 AI 创意文案生成中（DeepSeek）")
            try:
                card = storyboard.generate_storyboard(
                    params.get("angle", ""), int(params.get("num_shots", 6)),
                    params.get("product_info", ""), params.get("template", ""))
                _log(tid, f"✅ 文案完成：{card['angle']}（{len(card['shots'])} 分镜）")
            except Exception as e:
                _update(tid, status="failed", stage="失败", error=f"AI 文案: {e}")
                _log(tid, f"❌ AI 文案失败: {e}")
                continue
            with LOCK:
                TASKS[tid]["angle"] = card["angle"]
                _save()
            _run_film(tid, card, params)

    threading.Thread(target=coordinator, daemon=True).start()
    return tids
