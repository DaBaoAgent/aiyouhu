# -*- coding: utf-8 -*-
"""把 9 段 GPT-SoVITS 旁白 MP3 合并为总轨（段间 0.28s 静音）"""
import glob, os, subprocess

VO = r'D:\自动剪辑\爱优护\主图视频\配音_gpt'
FFMPEG = r'C:\Users\xxx13\ffmpeg\ffmpeg-8.1.1-essentials_build\bin\ffmpeg.exe'
order = ['S%d' % i for i in range(1, 10)]

# 每段 mp3 转 wav(32k mono) → 拼接(段间 0.28s 静音)
tmp = os.path.join(VO, '_merge')
os.makedirs(tmp, exist_ok=True)
pieces = []
for sid in order:
    src = glob.glob(os.path.join(VO, '旁白%s_*.mp3' % sid))[0]
    wav = os.path.join(tmp, sid + '.wav')
    subprocess.run([FFMPEG, '-y', '-i', src, '-ar', '32000', '-ac', '1', wav], capture_output=True)
    pieces.append(wav)
    if sid != order[-1]:
        gap = os.path.join(tmp, 'gap.wav')
        if not os.path.exists(gap):
            # 生成 0.28s 静音
            subprocess.run([FFMPEG, '-y', '-f', 'lavfi', '-i', 'anullsrc=r=32000:cl=mono', '-t', '0.28', gap], capture_output=True)
        pieces.append(gap)

lst = os.path.join(tmp, 'list.txt')
with open(lst, 'w', encoding='utf-8') as fh:
    for p in pieces:
        fh.write("file '%s'\n" % os.path.basename(p))
out = os.path.join(VO, '旁白_全9段_合集.mp3')
r = subprocess.run([FFMPEG, '-y', '-f', 'concat', '-safe', '0', '-i', lst,
                    '-codec:a', 'libmp3lame', '-b:a', '192k', out], capture_output=True)
import shutil
shutil.rmtree(tmp, ignore_errors=True)
if r.returncode == 0:
    dur = subprocess.run([r'C:\Users\xxx13\ffmpeg\ffmpeg-8.1.1-essentials_build\bin\ffprobe.exe', '-v', 'error',
                          '-show_entries', 'format=duration', '-of', 'csv=p=0', out],
                         capture_output=True).stdout.decode().strip()
    print('✅ 总轨 %.1fs -> %s' % (float(dur), out))
else:
    print('失败:', r.stderr.decode('utf-8', 'replace')[-300:])
