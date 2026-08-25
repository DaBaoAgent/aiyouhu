# -*- coding: utf-8 -*-
"""GPT-SoVITS CPU 合成轻便侠 9 段旁白（参考音色=护卫神W7磁性男声，零样本克隆）
输出: D:\自动剪辑\爱优护\主图视频\配音_gpt\旁白S*.mp3 + 全9段合集
"""
import io, os, re, sys, time
from pathlib import Path

ROOT = Path(r'D:\GPT-SoVITS')
MD = r'D:\自动剪辑\爱优护\主图视频\轻便侠218_主图视频脚本_审核版.md'
REF = r'D:\自动剪辑\爱优护\大气克隆音色_9s.wav'
PROMPT_TEXT = '十五米手机遥控，一分钟学会。医疗级锂电池，一次充电，最远续航三十九公里。'
OUT = r'D:\自动剪辑\爱优护\主图视频\配音_gpt'
FFMPEG = r'C:\Users\xxx13\ffmpeg\ffmpeg-8.1.1-essentials_build\bin\ffmpeg.exe'

os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'GPT_SoVITS'))
os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'

import numpy as np
import soundfile as sf
import torch
import torchaudio
from scipy.ndimage import uniform_filter1d
from GPT_SoVITS.TTS_infer_pack.TTS import TTS, TTS_Config

# torchaudio 2.9 默认走 torchcodec（本机 DLL 不兼容 torch2.9.1 CPU），改用 soundfile 读参考音频
_orig_taload = torchaudio.load


def _load_wav(path, *a, **k):
    data, sr = sf.read(str(path), dtype='float32', always_2d=True)
    return torch.from_numpy(data.T), sr


torchaudio.load = _load_wav
print('torchaudio.load 已替换为 soundfile 后端', flush=True)

# split_lang 强制 fast_langdetect model="full"（触发下载 130MB 大模型）→ 改为 lite（包内自带 lid.176.ftz）
import fast_langdetect
import split_lang.detect_lang.detector as _sld
_orig_fast_lang_detect = _sld.fast_lang_detect


def _lite_detect(text):
    return str(fast_langdetect.detect(text, model="lite")[0]["lang"])


_sld.fast_lang_detect = _lite_detect
print('fast_langdetect 已切换为 lite（免下载）', flush=True)

# ---------- 9 段旁白文本（与 edge 版一致，数字已转中文） ----------
md = io.open(MD, encoding='utf-8').read()
secs = re.split(r'^### (S\d+) (.+)$', md, flags=re.M)
copy = {}
for i in range(1, len(secs) - 1, 3):
    sid, body = secs[i], secs[i + 2]
    m = re.search(r'旁白「(.+?)」', body)
    if m:
        copy[sid] = m.group(1).strip()

def cn(t):
    for a, b in [('13.8', '十三点八'), ('3.0', '三点零'), ('145', '一百四十五'),
                 ('15米', '十五米'), ('39', '三十九'), ('218', '二幺八'),
                 ('2026', '二零二六'), ('10', '十')]:
        t = t.replace(a, b)
    return t

order = ['S%d' % i for i in range(1, 10)]
texts = {sid: cn(copy[sid]) for sid in order if sid in copy}
assert len(texts) == 9, texts
print('9 段文本就绪:', [texts[s][:12] for s in order])

# ---------- 停顿压缩（照抄 AutoXG） ----------
def silence_envelope(audio_pcm16, sample_rate):
    data = audio_pcm16.astype(np.float32) / 32768.0
    window = max(1, int(sample_rate * 0.015))
    return np.sqrt(uniform_filter1d(data * data, size=window))

def shorten_long_pauses(audio, sample_rate, silence_threshold_db=-46.0,
                        min_long_pause=0.35, target_pause=0.18):
    envelope = silence_envelope(audio, sample_rate)
    threshold = 10 ** (silence_threshold_db / 20)
    silent = envelope < threshold
    changes = np.diff(np.r_[False, silent, False].astype(np.int8))
    starts = np.where(changes == 1)[0]
    ends = np.where(changes == -1)[0]
    target_samples = int(target_pause * sample_rate)
    pieces, cursor = [], 0
    for start, end in zip(starts, ends):
        if start == 0 or end == len(audio):
            continue
        pause_samples = end - start
        if pause_samples < int(min_long_pause * sample_rate):
            continue
        left_keep = target_samples // 2
        right_keep = target_samples - left_keep
        pieces.append(audio[cursor:start + left_keep])
        pieces.append(audio[end - right_keep:end])
        cursor = end
    pieces.append(audio[cursor:])
    result = np.concatenate(pieces) if len(pieces) > 1 else audio
    envelope = silence_envelope(result, sample_rate)
    voiced = np.flatnonzero(envelope >= threshold)
    if len(voiced):
        begin = max(0, int(voiced[0]) - int(0.04 * sample_rate))
        finish = min(len(result), int(voiced[-1]) + 1 + int(0.08 * sample_rate))
        result = result[begin:finish]
    return result

# ---------- 推理 ----------
torch.set_num_threads(min(os.cpu_count() or 1, 16))
torch.set_num_interop_threads(4)
print('加载模型 (v2 CPU)...', flush=True)
config = TTS_Config(str(ROOT / 'GPT_SoVITS' / 'configs' / 'tts_infer.yaml'))
print('device:', config.device, '| version:', config.version, flush=True)
assert str(config.device) == 'cpu', config.device
pipeline = TTS(config)
print('模型加载完成', flush=True)

os.makedirs(OUT, exist_ok=True)
speed = 1.0  # 音色保真；0.8x 由外部 atempo 实现（speed_factor 会变调）
started = time.time()
mp3s = []
for i, sid in enumerate(order, start=1):
    text = texts[sid]
    request = {
        'text': text, 'text_lang': 'zh',
        'ref_audio_path': REF, 'prompt_lang': 'zh', 'prompt_text': PROMPT_TEXT,
        'top_k': 15, 'top_p': 1.0, 'temperature': 1.0,
        'text_split_method': 'cut0', 'batch_size': 1, 'batch_threshold': 0.75,
        'split_bucket': False, 'speed_factor': speed, 'fragment_interval': 0.10,
        'seed': 20260316 + i, 'parallel_infer': False,
        'repetition_penalty': 1.35, 'return_fragment': False, 'streaming_mode': False,
    }
    t0 = time.time()
    sr, audio = next(pipeline.run(request))
    audio = np.asarray(audio)
    audio = shorten_long_pauses(audio, sr)
    wav = os.path.join(OUT, '_seg_%s.wav' % sid)
    sf.write(wav, audio, sr, subtype='PCM_16')
    mp3 = os.path.join(OUT, '旁白%s_%s.mp3' % (sid, text[:6].replace('，', '')))
    import subprocess
    subprocess.run([FFMPEG, '-y', '-i', wav, '-codec:a', 'libmp3lame', '-b:a', '192k', mp3],
                   capture_output=True)
    os.remove(wav)
    mp3s.append(mp3)
    print('✅ %s %.1fs文本 合成%.1fs/耗时%.1fs -> %s' % (
        sid, len(text) / 3.5, (len(audio) / sr), time.time() - t0, os.path.basename(mp3)), flush=True)

# 合并总轨（段间 0.28s）
gap = np.zeros(int(0.28 * sr), dtype=np.int16)
pieces = []
for i, sid in enumerate(order):
    wav = mp3s[i].replace('.mp3', '.wav')
    if not os.path.exists(wav):
        continue
    a, s = sf.read(wav, dtype='int16')
    pieces.append(a)
    if i < len(order) - 1:
        pieces.append(gap)
full = np.concatenate(pieces)
full_wav = os.path.join(OUT, '_full.wav')
sf.write(full_wav, full, s, subtype='PCM_16')
full_mp3 = os.path.join(OUT, '旁白_全9段_合集.mp3')
subprocess.run([FFMPEG, '-y', '-i', full_wav, '-codec:a', 'libmp3lame', '-b:a', '192k', full_mp3],
               capture_output=True)
os.remove(full_wav)
print('✅ 总轨 %.1fs -> %s' % (len(full) / s, full_mp3))
print('==== 全部完成, 总耗时 %.1f 分钟 ====' % ((time.time() - started) / 60))
