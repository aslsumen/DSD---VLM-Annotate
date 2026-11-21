# 使用与部署说明

[English](USAGE.md) | 简体中文

本文描述当前工程行为。命令均在 `video_grounding/` 下执行；后端适配器使用的 Python API 见 [API.zh-CN.md](API.zh-CN.md)。

## 环境与安装

- Python ≥ 3.11，已验证 GPU 环境使用 Python 3.12。
- 系统 PATH 中需有 `ffmpeg`、`ffprobe`。它们用于读取元数据、切窗口和导出片段。
- VideoJev 需要兼容的 CUDA/PyTorch、FlashAttention 和 causal-conv1d。请按 [COMPATIBILITY.md](COMPATIBILITY.md) 的已验证组合安装，不要仅安装基础包就启动真实模型。
- 基础包只依赖 numpy、PyYAML、Pydantic；可选安装项为 `videojev`、`gemini`。

完成 GPU 依赖安装后：

```bash
uv pip install -p .venv/bin/python -e '.[videojev,gemini]'
ffmpeg -version
ffprobe -version
.venv/bin/video-grounding --help
```

注意后续 `uv sync` 可能重新解析 PyTorch；维护 GPU 主机时，应保留并核对已验证的 CUDA wheel 组合。

## 模型、密钥与本地配置

复制 `configs/default.yaml`（较大显存）或 `configs/rtx3070.yaml`（低显存 CPU offload）为机器专用配置。按实际机器填写模型路径和内存预算。

```yaml
# 合并到配置文件中的对应节，不要重复同名 YAML 节
model:
  id: ZhuYuhan/VideoJev-4B
  revision: b614f1a6248ba1f169cd3bec9e4392758b566e5d
  local_path: /models/VideoJev-4B
verify:
  enabled: true
  model: gemini-decision-1
  fps: 2.0
  max_height: 480
```

没有 `local_path` 时，适配器通过模型 ID 加载，首次运行可能需要联网下载；离线部署应提前准备完整模型。模型加载使用 `trust_remote_code=True`，当前适配器未把配置中的 revision 显式传给 from_pretrained；它参与结果标识与恢复校验，但不能独自保证 Hub 下载版本固定。可复现部署应预先下载指定 revision 的模型快照，将 local_path 指向该快照，并让配置 revision 与之对应。

Gemini 已接入精筛之后。安装 `gemini` extra，并通过进程环境变量 `GEMINI_API_KEY` 或 `.env` 提供密钥；环境变量优先，随后查当前工作目录 `.env`，最后查包所在工程根目录 `.env`。安装为 wheel 时推荐明确注入环境变量，不依赖源码目录位置。密钥不写入任务配置或导出结果。

提供的 `default.yaml` 和 `rtx3070.yaml` 开启核验；不传配置时 `Settings()` 的核验默认关闭。无网络/不需要核验时显式设置 `verify.enabled: false`。模型名不是任意 Gemini 聊天模型都能替换：当前代码调用的是 Decisions API。

## 配置与采帧

YAML 只覆盖写出的字段，其余使用 `settings.py` 默认值；未知字段会被拒绝。当前常用默认值：

| 阶段 | 参数 | 默认值 / 含义 |
|---|---|---|
| 粗筛 | `coarse.window_seconds` / `stride_seconds` | 30 / 20 秒 |
| 粗筛 | `coarse.fps` / `max_frames` | 1.0 / 32 |
| 精筛 | `refine.enabled` | true |
| 精筛 | `refine.fps` / `max_frames` / `window_seconds` | 2.0 / 64 / 30 秒 |
| 精筛 | `expand_min_seconds` / `max_span_seconds` | 5 / 180 秒 |
| 融合 | `fusion.high` / `low` | 0.25 / 0.15，滞回分段阈值 |
| 候选过滤 | `fusion.min_event_score` | 0.5，粗筛候选和最终导出均使用 |
| Gemini | `verify.fps` / `max_height` | 2 帧/秒 / 480 像素高 |
| 导出 | `export.cut_clips` | true；关闭时仍生成事件 JSON |
| 导出 | `pre_roll` / `post_roll` | 各 0.5 秒 |
| 重试 | `retry.max_attempts` / `oom_ladder` | 3 / [48, 32, 24, 16, 12, 8, 4] |
| 特征缓存 | `feature_cache.dir` / `max_gb` | `~/.cache/video_grounding/features` / 50；同一视频换提示词时复用已编码的窗口特征，超过上限先删最久未用的；`dir: null` 关闭。产品后端适配器改放在数据目录下、每个视频一个子目录（`engine/features/video-<id>`，随视频删除），上限仍是全局的。开不开缓存结果都相同 |

VideoJev 的目标帧数同时受窗口时长、fps 和 max_frames 约束：超过上限时在整段内均匀降低有效采样率。提高密度必须同时检查 fps 与帧数上限；保持窗口和步长不变才能比较密度变化。显存不足仍可能降帧，实际情况看 `metrics.json` 的 `oom_downgrades` 和 `window_predictions.jsonl` 的采样元数据。更密集采样不保证更高准确率。

Gemini 接收重编码后的事件片段（含前后留白），不是 VideoJev 的粗筛窗口。`verify.fps` 既用于片段重采样，也传给 API 的视频处理参数；没有 Qwen 实验中的 `max_frames` 配置。核验片段超过本地 20 MiB 检查上限时不会发送，保留候选并标记 `not_verified`。

## CLI 使用

### 1. 预检

```bash
.venv/bin/video-grounding probe --video /data/demo.mp4 \
  --config configs/local.yaml --prompt 'A person opens a door'
```

`probe` 会加载真实后端并检查最多前 10 秒，不只是 ffprobe；不执行 Gemini 核验。

### 2. 扫描

单提示词：

```bash
.venv/bin/video-grounding scan --video /data/demo.mp4 \
  --config configs/local.yaml --prompt 'A person opens a door' --out runs/demo
```

多提示词文件 `prompts.json`：

```json
[
  {"query_id": "open_door", "text": "A person opens a door"},
  {"query_id": "sit_down", "text": "A person sits down"}
]
```

```bash
.venv/bin/video-grounding scan --video /data/demo.mp4 \
  --config configs/local.yaml --prompt-file prompts.json --out runs/multi
```

使用唯一、非空的 query_id 和明确描述视觉事件的文本。声音、意图等信息不能只靠画面可靠确认。CLI 使用本地视频。

### 3. 恢复与重新导出

```bash
.venv/bin/video-grounding resume --job runs/demo
.venv/bin/video-grounding export --job runs/demo
# 仅调整融合高/低阈值再导出，不重新推理
.venv/bin/video-grounding export --job runs/demo --threshold 0.3 --low 0.2
```

`resume` 校验源视频指纹、模型 revision 和配置 hash；除 `verify` 节外修改任务配置会被拒绝，应创建新任务目录。保留原视频及原路径。已成功的预测和核验会被复用；恢复仍会加载后端。`export` 不调用 VideoJev 或 Gemini，只根据存储预测和已有 verdict 重新生成输出。

对已完成任务补做 Gemini：任务停止写入后修改该任务 `config.yaml` 中的 `verify` 节，配置密钥，然后用 CLI `resume`。

**缓存限制：** verdict 缓存键只含 query_id、片段起止微秒、模型名和提问文本的哈希，不含 `verify.fps`、`max_height`。因此修改采样参数后 resume 不会重新核验已有 verdict；对照实验请使用新任务目录，不要把缓存命中误认为复测结果。

### 4. 评测

```bash
.venv/bin/video-grounding eval --pred runs/demo/events.json --gt gt.json
```

真值标注格式为 `{"events":[{"query_id":"open_door","start_sec":12.5,"end_sec":18.0}]}`，时间使用原视频秒数。`eval` 输出时间 IoU 召回。

准确率基准脚本在 `scripts/` 下：`composite_bench.py`（留出的 YouCook2 与 BDD-X 复合视频，主要准确率检查）和 `charades_sta.py`（仅作参考：VideoJev 的训练数据包含 Charades-STA）。方法与结果见 [EVALUATION.md](EVALUATION.md)。

## 输出、保留与清理

| 文件 | 用途 |
|---|---|
| `job.sqlite`、`config.yaml` | 恢复所需状态及实际配置 |
| `events.json` | 候选、Gemini 拒绝项、覆盖缺口及模型信息 |
| `window_predictions.jsonl` | 模型窗口预测与实际采样信息 |
| `clips/` | 可播放事件片段（如开启导出） |
| `manifest.json`、`metrics.json` | 来源、版本、配置 hash、阶段耗时和降帧统计 |
| `windows/` | 临时窗口视频，窗口推理完即删除 |

恢复（`resume`）仍依赖原视频。不要删除数据库来“重试”。当前无自动保留期。

## 验证与排障

```bash
uv sync --group dev
uv run pytest
```

| 现象 | 检查方法 |
|---|---|
| 缺 Gemini key，任务立即失败 | 检查进程的环境变量 / .env，或明确关闭 verify |
| completed 但存在 not_verified | API 错误、配额或片段体积导致未核验；检查日志，人工处理或 CLI resume |
| scan_complete=false | 检查 coverage_gaps、永久失败窗口和 metrics；不应展示“完整扫描无结果” |
| 结果为空 | 可能无匹配、VideoJev 阈值过滤或 Gemini 拒绝；同时检查 rejected_events 和覆盖缺口 |
| 事件没有片段文件 | 检查 export.cut_clips、事件是否被 Gemini 拒绝及文件是否存在 |
| resume 配置不匹配 | 恢复原配置，或用新目录创建任务；不要强改数据库 |
| 任务慢或显存不足 | 检查 CPU offload、实际帧数、OOM 次数；参考性能文档 |

评测和兼容性文档记录的是特定环境下的历史观察，不是对所有视频、硬件或云 API 的保证。
