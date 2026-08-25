# -*- coding: utf-8 -*-
"""0.8x 慢放（保音调）：ffmpeg atempo=1.25 处理 9 段旁白，覆盖原文件"""
import glob, os, subprocess

VO = r'D:\自动剪辑\爱优护\主图视频\配音_gpt'
FFMPEG = r'C:\Users\xxx13\ffmpeg\ffmpeg-8.1.1-essentials_build\bin\ffmpeg.exe'
FFPROBE = r'C:\Users\xxx13\ffmpeg\ffmpeg-8.1.1-essentials_build\bin\ffprobe.exe'

files = sorted(glob.glob(os.path.join(VO, '旁白S*.mp3')))
for f in files:
    tmp = f + '.tmp.mp3'
    r = subprocess.run([FFMPEG, '-y', '-i', f, '-af', 'atempo=0.8', '-codec:a', 'libmp3lame', '-b:a', '192k', tmp], capture_output=True)
    if r.returncode != 0:
        print('FAIL', os.path.basename(f), r.stderr.decode('utf-8', 'replace')[-200:])
        continue
    os.replace(tmp, f)
    dur = subprocess.run([FFPROBE, '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f], capture_output=True).stdout.decode().strip()
    print('0.8x OK', os.path.basename(f), dur + 's')
print('全部完成 %d 段' % len(files))
