# -*- coding: utf-8 -*-
"""S1 配音加 1s 停顿：两段分开合成（轻便侠二幺八。/轻，是一种品味。）+ 0.8s静音拼接（atempo0.8后=1s停顿）
其余 8 段不变（复用现有 1.0x 产物会再次 atempo，故统一重合成）
"""
import io, os, re, sys, time
from pathlib import Path

ROOT = Path(r'D:\GPT-SoVITS')
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

_orig_taload = torchaudio.load


def _load_wav(path, *a, **k):
    data, sr = sf.read(str(path), dtype='float32', always_2d=True)
    return torch.from_numpy(data.T), sr


torchaudio.load = _load_wav
import fast_langdetect
import split_lang.detect_lang.detector as _sld
_sld.fast_lang_detect = lambda text: str(fast_langdetect.detect(text, model="lite")[0]["lang"])

torch.set_num_threads(min(os.cpu_count() or 1, 16))
torch.set_num_interop_threads(4)
print('加载模型...', flush=True)
config = TTS_Config(str(ROOT / 'GPT_SoVITS' / 'configs' / 'tts_infer.yaml'))
pipeline = TTS(config)
print('模型就绪', flush=True)

parts = ['轻便侠二幺八。', '轻，是一种品味。']
audios = []
sr = 0
for i, text in enumerate(parts, 1):
    request = {
        'text': text, 'text_lang': 'zh',
        'ref_audio_path': REF, 'prompt_lang': 'zh', 'prompt_text': PROMPT_TEXT,
        'top_k': 15, 'top_p': 1.0, 'temperature': 1.0,
        'text_split_method': 'cut0', 'batch_size': 1, 'batch_threshold': 0.75,
        'split_bucket': False, 'speed_factor': 1.0, 'fragment_interval': 0.10,
        'seed': 20260316 + i, 'parallel_infer': False,
        'repetition_penalty': 1.35, 'return_fragment': False, 'streaming_mode': False,
    }
    r_sr, audio = next(pipeline.run(request))
    audio = np.asarray(audio)
    audios.append(audio)
    sr = r_sr
    print('part%d %s %.1fs' % (i, text, len(audio) / sr), flush=True)

# 拼接: part1 + 0.8s静音(atempo后=1s) + part2
gap = np.zeros(int(0.8 * sr), dtype=np.int16)
joined = np.concatenate([audios[0], gap, audios[1]])
# 停顿压缩（长停顿>0.35s会压到0.18s，会吃掉1s停顿→关掉，直接输出原始拼接）
wav = os.path.join(OUT, '_s1_paused.wav')
sf.write(wav, joined, sr, subtype='PCM_16')
mp3 = os.path.join(OUT, '旁白S1_轻便侠二幺八.mp3')
import subprocess
subprocess.run([FFMPEG, '-y', '-i', wav, '-af', 'atempo=0.8', '-codec:a', 'libmp3lame', '-b:a', '192k', mp3], capture_output=True)
os.remove(wav)
d = float(subprocess.run([r'C:\Users\xxx13\ffmpeg\ffmpeg-8.1.1-essentials_build\bin\ffprobe.exe', '-v', 'error',
                          '-show_entries', 'format=duration', '-of', 'csv=p=0', mp3],
                         capture_output=True).stdout.decode().strip())
print('S1 合成完成 %.1fs（1s停顿+0.8x）' % d, flush=True)
