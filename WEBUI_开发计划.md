# ayh-h3 WebUI 开发计划（v2 · 按用户修改更新）

> 项目：爱优护轻便侠 218 电动轮椅 H3 视频生成配套界面
> 根目录：`D:\@kaifa\aiyouhu\ayh-h3\`（现有 SKILL.md + scripts/h3_gen.py + prompts/）
> 目标：零代码小白可用，浏览器打开即生成主图视频/推广视频
> v2 变更：产品图 9 槽 / 配音改本机 GPT-SoVITS / 分镜用 DeepSeek / 增加横竖屏选择

---

## 一、现状梳理（已盘点）

| 现有资产 | 内容 | 复用方式 |
|---|---|---|
| `scripts/h3_gen.py`（205行） | 完整 API 客户端：提交→轮询→下载，含 SSL 重试、.env 鉴权 | **直接 import 复用**，不改动 |
| 4 种工作流 | multi_image（多图1-10s）/ image_audio（对口型1-15s）/ text2video（1-10s）/ first_last（首尾帧1-10s） | 参数面板枚举 |
| 分辨率 6 档 | 480p竖/768p竖/1080p竖/480p横/768p横/1080p横 | 横竖开关 + 清晰度联动 |
| 提示词模板 | 3分镜快节奏 v2（欧洲老爷爷·四大卖点）、版本D洗脑版、10个现成提示词 | 前端示例库一键填入 |
| 本机 GPT-SoVITS | `D:\@佳康顺矩阵\@工具\GPT-SoVITS\`，`api_v2.py -p 9880` 起 HTTP 服务，`run_tts.py` 现成调用模式 | WebUI 自动拉起服务，requests 调 /tts |
| DeepSeek API | `DEEPSEEK_API_KEY` 在 `C:\Users\Administrator\AppData\Local\hermes\.env`，OpenAI 兼容 | AI 分镜生成 |
| 关键坑（实测） | 查询必须 GET；SSL 抖动重试（已内置）；1080p 10s ≈ 12分钟；API 上限 ref_image_0~8（9张） | 后端已处理 |

**缺口**：无 Web 界面；分镜脚本靠手写；配音需手动跑脚本；API key 需手动编辑 .env。

---

## 二、功能需求 → 界面模块映射（v2）

| 用户需求 | 界面模块 | 说明 |
|---|---|---|
| 9张产品参考图上传+预览 | ① 产品参考图区：**9 个上传槽**（正好对齐 API ref_image_0~8），缩略图网格，可删除/拖动排序 | 提交时按序传 ref_image_0~8 |
| 人物模特参考图上传+预览 | ② 模特参考图区：4 个上传槽（老爷爷/年轻女性等），带角色标签 | 与产品图合并（产品图在前，模特图在后） |
| 分镜脚本预览编辑框 | ③ 分镜脚本区：大文本框 +「AI 生成分镜」按钮 +「示例模板」下拉 | AI 生成走 **DeepSeek API**，生成后人工可改 |
| 配音参数可选 | ④ 配音区：开关 + **本机 GPT-SoVITS** 音色库 + **上传克隆音色按钮** + 配音文案 + 语速/音量滑块 | 音色=参考音频(3-10s)+自动ASR文本；生成 wav 后 ffmpeg 混入成片 |
| 视频生成参数可选 | ⑤ 视频参数区：**横屏/竖屏大开关** + 清晰度(480p/768p/1080p) + 工作流类型 + 时长(1-15s) + 并发数(1-10) + 输出命名 | 横竖×清晰度联动成 6 档枚举 |
| 大大的开始生成按钮 | ⑥ 底部通栏渐变「🚀 开始生成」按钮 | 未填必填项自动高亮提示 |
| 成片播放预览 | ⑦ 任务卡片区：实时进度条（提交/排队/生成中/合成配音/下载），完成后内嵌播放器 | 5s 轮询，完成自动播 |
| API 手动填入 | ⑧ 右上角「⚙ 设置」弹窗：AUTODL_API_KEY + GPT-SoVITS 路径/端口 + DeepSeek key | 存 `scripts/.env` 与 CLI 共用，回显脱敏 |

---

## 三、技术选型（零构建、双击即用）

- **后端**：FastAPI + uvicorn（异步，自带文件上传/自动文档）
- **前端**：原生 HTML + CSS + JS 单页（无 node 构建，离线可用）
- **任务模型**：后台线程 + 内存任务表；页面每 5s 轮询进度
- **H3 调用**：直接 `import h3_gen` 的 create_task/query_task/download
- **配音**：WebUI 启动时自动拉起 `api_v2.py`（127.0.0.1:9880，检测已运行则复用）→ requests GET /tts；音色克隆=上传参考音频→自动裁剪 3-10s→SenseVoiceSmall ASR 出 prompt_text→存音色 json；合成后 ffmpeg 混流
- **AI 分镜**：requests 调 DeepSeek（`https://api.deepseek.com`，OpenAI 兼容，DEEPSEEK_API_KEY）
- **一键启动**：根目录 `启动WebUI.bat`（建 venv→装依赖→起 WebUI→自动开浏览器）

## 四、目录结构

```
ayh-h3/webui/
├── app.py              # FastAPI 入口 + 路由
├── tasks.py            # 任务队列/状态/进度管理
├── settings.py         # API key/配置读写 scripts/.env、参数校验
├── storyboard.py       # DeepSeek AI 分镜生成
├── tts_client.py       # GPT-SoVITS 服务管理 + 音色克隆 + 配音合成
├── static/
│   ├── index.html      # 单页界面
│   ├── style.css       # 大按钮/卡片/预览网格样式
│   └── app.js          # 上传预览/参数收集/轮询播放
├── data/
│   ├── refs/           # 上传参考图（产品/模特）
│   ├── voices/         # 克隆音色库（音频 + voice_<id>.json）
│   ├── tts/            # 配音中间产物 wav
│   └── outputs/        # 成片（含配音混流版）
└── requirements.txt    # fastapi, uvicorn, requests
```

---

## 五、后端 API 设计（共 11 个接口）

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/` | 托管单页界面 |
| POST | `/api/upload` | 上传图片/音频 → data/refs/，返回 URL |
| POST | `/api/settings` | 保存 AUTODL_API_KEY / DeepSeek key / GPT-SoVITS 配置 |
| GET | `/api/tts/status` | GPT-SoVITS 服务状态（运行中/端口/GPU可用） |
| POST | `/api/tts/start` | 拉起 api_v2 服务（后台） |
| POST | `/api/voices` | **上传克隆音色**：参考音频→裁剪3-10s→ASR→建音色（名称+音频+prompt_text） |
| GET | `/api/voices` | 音色库列表（选中即用） |
| POST | `/api/storyboard` | 输入卖点/场景 → **DeepSeek** 生成 3 分镜脚本 |
| POST | `/api/generate` | 提交生成：参数+分镜脚本+图序+配音选项 → 建任务后台跑 |
| GET | `/api/tasks` | 任务列表（状态/进度/耗时/视频URL/错误） |
| GET | `/api/tasks/{id}/video` | 读取成片（视频流，支持 range 拖动播放） |

**生成流程**：
1. 参数校验（时长按工作流：图类1-10s/对口型1-15s；横竖×清晰度合成 resolution）
2. 合并 9 产品图 + 模特图 → ref_image_0~N（产品图在前）
3. 若开配音：选音色 → GPT-SoVITS /tts 合成配音 wav（按文案分段）→ 存入 data/tts/
4. 按工作流提交 H3 任务 → 后台轮询（复用 h3_gen）→ 下载成片
5. 若有配音：ffmpeg 把配音 wav 混入成片音轨 → 存 data/outputs/完成版
6. 状态置完成，前端自动播放

---

## 六、开发里程碑（4 步，约 3 天）

1. **M1 骨架+上传（0.5天）**：FastAPI 服务、单页框架、9 产品图 + 4 模特图上传预览、设置弹窗、启动 bat
2. **M2 生成闭环（1天）**：/api/generate + 任务队列 + 进度轮询 + 横竖/清晰度/时长/并发参数面板 + 大按钮 + 成片播放器 ← 核心
3. **M3 AI 分镜 + GPT-SoVITS 配音（1天）**：DeepSeek 分镜生成、音色克隆上传、配音合成+混流
4. **M4 打磨验收（0.5天）**：示例模板库、小白引导、真机验证（1 条 768p 短任务全链路）

---

## 七、风险与对策

| 风险 | 对策 |
|---|---|
| 单条 1080p 10s 约 12 分钟，用户以为卡死 | 进度条分阶段显示（提交✓→生成中 Xs→配音→下载）+ "约10-12分钟"提示 |
| API 费用（¥0.10/秒×10s×10并发=¥10/批） | 界面显示预估费用 + 默认并发1 |
| GPT-SoVITS 服务未起/端口占用 | 设置里可配路径端口；自动检测 9880 已运行则复用；失败则提示一键启动 |
| 参考音频超 10s 报错（GPT-SoVITS 硬限制） | 上传后自动裁剪 3-10s 并提示 |
| prompt_text 与参考音频不匹配→吞字 | SenseVoiceSmall 自动 ASR；手动可改；音色库存绑定好的配置 |
| 配音与视频时长不匹配 | ffmpeg 混流时自动 loop/silence 补齐，音量滑块可调 |
| 生成的视频被媒体预览锁（WinError 32） | 下载到 outputs 用新文件名，完成后即释放 |
| DeepSeek 网络抖动 | 重试 3 次；失败允许手动填写分镜 |
| 无显卡也能用 H3（云端 API），但 GPT-SoVITS 配音需本机 GPU | 无 GPU 时配音区降级提示"跳过配音只出视频" |

---

## 八、交付物清单

- `webui/` 全部源码（随仓库提交，.env 不入库）
- `启动WebUI.bat`（双击：装依赖→起 GPT-SoVITS→起 WebUI→开浏览器）
- 使用说明 `webui/README.md`（带截图位）
- 验收记录：至少 1 条真实任务全链路出片（含配音版）
