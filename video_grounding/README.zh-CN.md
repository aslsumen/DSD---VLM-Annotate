# 视频事件定位引擎

[English](README.md) | 简体中文

VLM Annotate 的零样本事件定位引擎：输入视频和事件描述，输出事件时间段和片段。它是一个库加调试/评测 CLI。在产品中，它运行在后端 worker 内，通过 `../backend/app/adapters/videojev.py` 调用（一个任务 = 1 个视频 × 1 个动作；预览片段由后端自己切，所以适配器设置 `export.cut_clips=false`）。任务排队、人工复核和数据集导出由后端负责。

## 当前处理流程

```text
视频 + 提示词 → 视频探测 → VideoJev 粗筛 → 候选融合 → VideoJev 精筛
           → Gemini 核验（可配置关闭） → 事件与片段导出
```

- **VideoJev-4B**：定位一个或多个事件时间段。支持多提示词、断点恢复和显存不足时降帧重试。
- **Gemini**：已经集成。对精筛后的候选片段进行 yes/no 核验；当前适配器调用 Decisions API，配置模型为 `gemini-decision-1`。否定结果进入审计记录；核验失败的候选保留并标记待人工复核（复核在后端完成）。
- Qwen3-VL-4B 独立核验实验不属于当前产品流程，无须下载其模型。VideoJev 自身使用的处理器与依赖仍需保留。

## 文档导航

| 文档 | 面向读者 / 内容 |
|---|---|
| [使用与部署](docs/USAGE.zh-CN.md) | 环境安装、配置、CLI、恢复和排障 |
| [Python API](docs/API.zh-CN.md) | `run_scan` / `resume` / `export`、进度回调、`events.json` 字段 |
| [内部工程契约](docs/CONTRACTS.md) | 时间语义、模型适配器、融合、持久化与模块接口 |
| [兼容性记录](docs/COMPATIBILITY.md) | 已验证 GPU、依赖组合及平台问题 |
| [评测记录](docs/EVALUATION.md) | 测试方法、真实数据实验与已知质量局限 |
| [性能记录](docs/PERFORMANCE.md) | 已测耗时、显存、CPU offload 情况 |

## 快速开始

所有以下命令从仓库根目录进入工程后执行：

```bash
cd video_grounding
```

1. 按 [兼容性安装说明](docs/COMPATIBILITY.md#install) 安装 GPU 依赖、匹配的 FlashAttention/causal-conv1d，以及 ffmpeg/ffprobe。
2. 安装可选依赖，并配置 Gemini 密钥：

   ```bash
   uv pip install -p .venv/bin/python -e '.[videojev,gemini]'
   cp .env.example .env
   # 编辑 .env，填写 GEMINI_API_KEY；不要提交到版本库
   ```

3. 创建机器专用配置：

   ```bash
   cp configs/rtx3070.yaml configs/local.yaml
   # 按实际机器调整 local.yaml 中 model.local_path、runtime.max_memory
   # default.yaml 适用于较大显存；verify.enabled: false 可关闭 Gemini
   ```

4. 执行一个任务：

   ```bash
   .venv/bin/video-grounding scan --video /data/demo.mp4 \
     --prompt 'A person opens a door' --config configs/local.yaml --out runs/demo
   ```

`runs/demo/events.json` 为事件结果，`clips/` 为导出片段。每个任务使用独立目录，重复运行已有任务应使用 `resume`。

## 在产品中的位置

后端 worker 调用 `video_grounding.scheduler` 的 `run_scan` / `resume`，并传入 `progress=` 更新任务进度，见 [API.md](docs/API.zh-CN.md)。引擎本身不含 HTTP 服务、复核界面或数据集构建。

## 开发验证

```bash
cd video_grounding
uv sync --group dev
uv run pytest
```

测试覆盖合成/回放后端、时间映射、恢复、融合、进度回调及模拟 Gemini 核验；通过这些测试不等同于真实 GPU 或线上 Gemini 可用性验证。真实模型和 API 联调步骤见 [使用说明](docs/USAGE.zh-CN.md#验证与排障)。
