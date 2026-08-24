# -*- coding: utf-8 -*-
"""轮询 D4 任务直到完成并下载成片"""
import requests, os, sys, time
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()
key = os.getenv('AUTODL_API_KEY')
tid = '874b74c1-b517-4fe7-ae18-5729ac346de7'
OUT = r'D:/BaiduSyncdisk/10 产品高清图/爱优护详情页/video/D4_领舞巡游.mp4'

deadline = time.time() + 900
video_url = None
while time.time() < deadline:
    for attempt in range(5):
        try:
            r = requests.get(f'https://autodl.art/api/v1/comfyui/comfyui_workflow/result/{tid}',
                             headers={'Authorization': key}, timeout=40)
            body = r.json()
            data = body.get('data', {})
            st = data.get('status')
            print(f"status={st} 耗时={data.get('duration')}s", flush=True)
            if st == 'SUCCESS':
                for res in (data.get('results') or []):
                    if res.get('type') == 'video' and res.get('url'):
                        video_url = res['url']
                break
            if st in ('FAILED', 'ERROR', 'CANCELLED'):
                print('任务失败:', body, flush=True)
                sys.exit(1)
            break
        except Exception as e:
            print(f'重试{attempt+1}: {type(e).__name__}', flush=True)
            time.sleep(10)
    if video_url:
        break
    time.sleep(20)

if not video_url:
    print('等待超时', flush=True)
    sys.exit(1)

print('视频URL:', video_url, flush=True)
# 下载（4次重试）
for i in range(4):
    try:
        r = requests.get(video_url, timeout=300)
        if r.status_code == 200:
            with open(OUT, 'wb') as f:
                f.write(r.content)
            print(f'已保存: {OUT} ({len(r.content)/1024/1024:.1f} MB)', flush=True)
            sys.exit(0)
        print(f'下载HTTP {r.status_code} 重试{i+1}', flush=True)
    except Exception as e:
        print(f'下载异常{i+1}: {type(e).__name__}', flush=True)
    time.sleep(10)
print('下载失败', flush=True)
sys.exit(1)
