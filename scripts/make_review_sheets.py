# -*- coding: utf-8 -*-
"""逐帧审查：每视频抽 2fps 帧 → 拼 4x5 联系表（每视频一张图）"""
import glob, os, subprocess

VIDEO_DIR = r'D:\自动剪辑\爱优护\主图视频\video'
REVIEW_DIR = r'D:\自动剪辑\爱优护\主图视频\审查'
FFMPEG = r'C:\Users\xxx13\ffmpeg\ffmpeg-8.1.1-essentials_build\bin\ffmpeg.exe'
os.makedirs(REVIEW_DIR, exist_ok=True)

vids = sorted(glob.glob(os.path.join(VIDEO_DIR, 'S*.mp4')))
print('待审查 %d 条' % len(vids))
for v in vids:
    name = os.path.splitext(os.path.basename(v))[0]
    sheet = os.path.join(REVIEW_DIR, name + '_审查.png')
    # 抽 2fps 20帧 → 4x5 拼图（带时间戳）
    r = subprocess.run([
        FFMPEG, '-y', '-i', v,
        '-vf', "fps=2,scale=270:480,drawtext=text='%{pts\:hms}':fontsize=20:fontcolor=white:x=5:y=5:box=1:boxcolor=black@0.6,"
               "tile=4x5",
        '-frames:v', '1', '-q:v', '3', sheet], capture_output=True)
    print(('OK ' if r.returncode == 0 else 'FAIL ') + name, '->', os.path.basename(sheet))
