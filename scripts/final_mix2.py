# -*- coding: utf-8 -*-
"""成片 v2：9段视频静音拼接 + 大气BGM(50%) + 旁白逐段对齐混音
配音源优先级: 配音_gpt/（GPT-SoVITS）> 配音/（edge）
"""
import glob, json, io, os, subprocess

OUT = r'D:\自动剪辑\爱优护\主图视频\video'
VO_GPT = r'D:\自动剪辑\爱优护\主图视频\配音_gpt'
VO_EDGE = r'D:\自动剪辑\爱优护\主图视频\配音'
BGM = r'D:\自动剪辑\爱优护\大气震撼史诗宣传片.mp3'
BGM_VOLUME = 0.10
FFMPEG = r'C:\Users\xxx13\ffmpeg\ffmpeg-8.1.1-essentials_build\bin\ffmpeg.exe'
FFPROBE = r'C:\Users\xxx13\ffmpeg\ffmpeg-8.1.1-essentials_build\bin\ffprobe.exe'

state = json.load(io.open(os.path.join(OUT, '_batch_state.json'), encoding='utf-8'))
order = ['S%d' % i for i in range(1, 10)]
vids = [state[s]['file'] for s in order]

# 配音源选择
gpt_files = sorted(glob.glob(os.path.join(VO_GPT, '旁白S*.mp3')))
edge_files = sorted(glob.glob(os.path.join(VO_EDGE, '旁白S*.mp3')))
vo_dir, src_name = (VO_GPT, 'GPT-SoVITS') if len(gpt_files) == 9 else (VO_EDGE, 'edge云健')
narr = sorted(glob.glob(os.path.join(vo_dir, '旁白S*.mp3')))
print('视频 %d 条 | 配音源: %s (%d段) | BGM: %s' % (len(vids), src_name, len(narr), os.path.basename(BGM)))
assert len(narr) == 9, '旁白段数 != 9'

# ---------- 1. 静音拼接 ----------
lst = os.path.join(OUT, '_concat.txt')
with open(lst, 'w', encoding='utf-8') as fh:
    for f in vids:
        fh.write("file '%s'\n" % os.path.basename(f))
base = os.path.join(OUT, '_base_muted.mp4')
r = subprocess.run([FFMPEG, '-y', '-f', 'concat', '-safe', '0', '-i', lst,
                    '-an', '-c:v', 'copy', base], capture_output=True)
if r.returncode != 0:
    print('拼接失败:', r.stderr.decode('utf-8', 'replace')[-400:]); raise SystemExit(1)
dur = float(subprocess.run([FFPROBE, '-v', 'error', '-show_entries', 'format=duration',
                            '-of', 'csv=p=0', base], capture_output=True).stdout.decode().strip())
print('✅ 静音拼接 %.1fs' % dur)

# ---------- 2. 音频图：BGM(50%) + 9段旁白对齐 ----------
offsets = [i * 10 + 0.6 for i in range(9)]
inputs = [base, BGM] + narr
fc = []
fc.append('[1:a]volume=%.2f,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,atrim=0:%.1f,afade=t=out:st=%.1f:d=1.0[bgm]' % (BGM_VOLUME, dur, dur - 1.0))
mix_in = ['[bgm]']
for i, (n, off) in enumerate(zip(narr, offsets)):
    ms = int(off * 1000)
    fc.append('[%d:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,adelay=%d|%d[n%d]' % (i + 2, ms, ms, i))
    mix_in.append('[n%d]' % i)
fc.append('%samix=inputs=%d:normalize=0,apad[outa]' % (''.join(mix_in), len(mix_in)))

final = os.path.join(OUT, '轻便侠218_成片_BGM配音_%ds.mp4' % int(dur))
cmd = [FFMPEG, '-y'] + sum((['-i', f] for f in inputs), []) + \
      ['-filter_complex', ';'.join(fc), '-map', '0:v', '-map', '[outa]',
       '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-t', str(int(dur)), final]
print('混音 %d 输入, 开始编码...' % len(mix_in))
r = subprocess.run(cmd, capture_output=True)
if r.returncode != 0:
    print('混音失败:', r.stderr.decode('utf-8', 'replace')[-600:]); raise SystemExit(1)
fdur = float(subprocess.run([FFPROBE, '-v', 'error', '-show_entries', 'format=duration',
                             '-of', 'csv=p=0', final], capture_output=True).stdout.decode().strip())
print('✅ 成片v2: %s | %.1fs | %.1fMB' % (final, fdur, os.path.getsize(final) / 1048576))
