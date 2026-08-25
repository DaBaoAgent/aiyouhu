# 爱优护全自动视频生成工厂

基于 AutoDL.Art MiniMax H3 + 本机 GPT-SoVITS + DeepSeek 的全自动视频生成界面。上传产品图 → AI 写分镜 → 配音 → 批量生成 60 秒成片。

## 启动

双击 `启动WebUI.bat`（自动建环境、装依赖、开浏览器 http://127.0.0.1:8000）。

或手动：

```bash
cd webui
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

## 使用流程

1. **⚙ API 设置**：填 AUTODL Key（autodl.art 令牌，分组选 ComfyUI）；DeepSeek Key 留空自动用系统默认；GPT-SoVITS 服务未运行时点「启动服务」（模型加载 30-120 秒）
2. **上传产品参考图**（最多 9 张，白底无人物最佳）+ 可选模特参考图（4 张）
3. **分镜脚本**：点「✨ AI 生成分镜」（DeepSeek 自动写，可改）；分镜数量 1-10（默认 6 = 60 秒）；「🤖 全智能」滑块选批量条数 1-200
4. **配音**：开开关 → 上传克隆音色（3-10 秒音频，自动识别文本）→ 填文案 → 🔊 试听 → 调语速/音量
5. **BGM**：无 / 上传 / 曲库三选一 + 音量（默认 30%）
6. **视频参数**：横竖屏、清晰度、工作流、单分镜时长、并发数、命名
7. **🚀 开始生成** → 任务列表实时进度 → 完成后内嵌播放

## 生成流程（每条成片）

分镜解析 → 每分镜提交 1 条 H3 视频（10 秒上限）→ 配音并行生成（GPT-SoVITS）→ ffmpeg 拼接 → 混入配音+BGM → 成片。

- 单条 60 秒成片（6 分镜 × 10s）约 60-90 分钟，费用约 ¥6.00（1080p）
- 全智能 N 条 = 每条 AI 独立生成创意文案，按顺序排队跑，互不影响

## 目录

```
webui/
├── app.py            # FastAPI 入口
├── tasks.py          # 任务队列 + 成片流水线
├── storyboard.py     # DeepSeek AI 分镜
├── tts_client.py     # GPT-SoVITS 服务 + 音色克隆 + 配音
├── config.py         # 路径/密钥配置
├── static/           # 前端（index.html + app.js）
├── data/
│   ├── refs/         # 上传参考图
│   ├── voices/       # 克隆音色库
│   ├── tts/          # 配音 wav
│   ├── bgm/          # 内置 BGM 曲库（放入 mp3 即出现）
│   └── outputs/      # 成片
└── requirements.txt
```

## 注意事项

- API Key 存 `../scripts/.env`，与命令行 h3_gen.py 共用；DeepSeek 默认读 Hermes 的 `.env`
- 中文路径坑：SenseVoiceSmall ASR 需 `D:\modelscope_cache` junction（已建）指向模型缓存
- 任务状态存 `data/tasks.json`，重启服务不丢
- 成片在 `data/outputs/<任务id>/`，命名 `成片名.mp4`
