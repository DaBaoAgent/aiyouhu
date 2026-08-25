# -*- coding: utf-8 -*-
"""S1-S9 轻便侠主图视频批量生成：提交全部 → 轮询 → SUCCESS 立即下载 → 断点续传"""
import io, os, re, sys, time, json, glob

SCRIPTS_DIR = r'C:\Users\xxx13\AppData\Local\hermes\skills\media\ayh-h3\scripts'
sys.path.insert(0, SCRIPTS_DIR)
import h3_gen

REF_DIR = r'D:\自动剪辑\爱优护\轻便侠 218'
MD = r'D:\自动剪辑\爱优护\主图视频\轻便侠218_脚本_v3_老爷爷版.md'
OUT_DIR = r'D:\自动剪辑\爱优护\主图视频\video'
STATE = os.path.join(OUT_DIR, '_batch_state.json')
REF_CACHE = os.path.join(OUT_DIR, '_refs')
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(REF_CACHE, exist_ok=True)
h3_gen.load_env_file()


def prepare_ref(name):
    """参考图压到 1536px JPEG（白底产品图 q92 几乎无损），缓存复用；支持绝对路径"""
    src = name if os.path.isabs(name) else os.path.join(REF_DIR, name)
    dst = os.path.join(REF_CACHE, os.path.splitext(os.path.basename(src))[0] + '.jpg')
    if os.path.exists(dst):
        return dst
    from PIL import Image
    im = Image.open(src).convert('RGB')
    if max(im.size) > 1536:
        im.thumbnail((1536, 1536), Image.LANCZOS)
    im.save(dst, 'JPEG', quality=92)
    print('  参考图压缩: %s (%dx%d, %.1fMB->%.2fMB)' % (name, im.size[0], im.size[1],
          os.path.getsize(src) / 1048576, os.path.getsize(dst) / 1048576), flush=True)
    return dst

# ---------- 1. 解析脚本文件提取 S1-S9 ----------
md = io.open(MD, encoding='utf-8').read()
secs = re.split(r'^### (S\d+) (.+)$', md, flags=re.M)
jobs = {}
for i in range(1, len(secs) - 1, 3):
    sid, title, body = secs[i], secs[i + 1], secs[i + 2]
    m_ref = re.search(r'^- 参考图:\s*(.+)$', body, flags=re.M)
    m_p = re.search(r'H3提示词:\s*\n(.*?)(?=^- 文案层:)', body, flags=re.S | re.M)
    if not (m_ref and m_p):
        print('!! 解析失败:', sid); continue
    imgs = [x.strip() for x in m_ref.group(1).split('+') if x.strip()]
    prompt = m_p.group(1).strip().replace('\r\n', '\n').replace('\n', ' ')
    jobs[sid] = {'title': title.strip(), 'imgs': imgs, 'prompt': prompt}
print('解析到 %d 条:' % len(jobs))
for sid, j in jobs.items():
    print('  %s %s | 参考图: %s | 提示词%d字' % (sid, j['title'][:18], j['imgs'], len(j['prompt'])))

# ---------- 2. 状态管理（断点续传） ----------
state = {}
if os.path.exists(STATE):
    state = json.load(io.open(STATE, encoding='utf-8'))

# ---------- 3. 提交所有任务 ----------
def submit(sid, j):
    payload = {'duration': 10, 'prompt': j['prompt'], 'resolution': '1080p竖'}
    for k, img in enumerate(j['imgs']):
        payload['ref_image_%d' % k] = h3_gen.to_data_url(prepare_ref(img))
    import requests
    for attempt in range(5):
        try:
            return h3_gen.create_task('minimax_h3_lightx2v_v5', payload)
        except (requests.exceptions.SSLError, requests.exceptions.ConnectionError,
                requests.exceptions.ReadTimeout) as e:
            print('  提交网络抖动(%s) 第%d/5次重试' % (type(e).__name__, attempt + 1), flush=True)
            time.sleep(10)
    raise RuntimeError('提交失败: %s' % sid)

for sid, j in jobs.items():
    if sid in state and state[sid].get('task_id'):
        continue  # 已提交过
    tid = submit(sid, j)
    state[sid] = {'task_id': tid, 'title': j['title'], 'status': 'QUEUED'}
    json.dump(state, io.open(STATE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('  %s -> %s' % (sid, tid), flush=True)

print('全部提交完成，开始轮询', flush=True)

# ---------- 4. 轮询 + 下载 ----------
pending = {sid: s for sid, s in state.items() if s.get('status') not in ('SUCCESS', 'FAILED')}
start = time.time()
while pending:
    for sid in list(pending):
        s = pending[sid]
        data = h3_gen.query_task(s['task_id'])
        st = data.get('status', '')
        if st in ('SUCCESS', 'FAILED', 'ERROR', 'CANCELLED'):
            if st == 'SUCCESS':
                url = None
                for r in (data.get('results') or []):
                    if r.get('type') == 'video' and r.get('url'):
                        url = r['url']; break
                if url:
                    out = os.path.join(OUT_DIR, '%s_%s.mp4' % (sid, s['title'].split('·')[0].strip()))
                    try:
                        h3_gen.download(url, out)
                        s['status'] = 'SUCCESS'; s['file'] = out
                        print('✅ %s 完成 %.0fMB  %s' % (sid, os.path.getsize(out)/1048576, out), flush=True)
                    except Exception as e:
                        print('!! %s 下载失败: %s（稍后重试）' % (sid, e), flush=True)
                        time.sleep(30)
                        continue
                else:
                    s['status'] = 'FAILED'; print('!! %s 无视频URL: %s' % (sid, data), flush=True)
            else:
                s['status'] = 'FAILED'; print('!! %s 任务失败: %s' % (sid, data.get('msg') or data), flush=True)
            json.dump(state, io.open(STATE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
            del pending[sid]
        else:
            print('  %s status=%s 已等%.0fmin' % (sid, st, (time.time()-start)/60), flush=True)
    json.dump(state, io.open(STATE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    if pending:
        time.sleep(20)

done = sum(1 for s in state.values() if s.get('status') == 'SUCCESS')
print('==== 完成 %d/%d ====' % (done, len(jobs)), flush=True)
for sid in sorted(state):
    s = state[sid]
    print('  %s %s' % (sid, s.get('status')), s.get('file', ''), flush=True)
