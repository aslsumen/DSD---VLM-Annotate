# DSD — VLM Annotate

[English](README.md) | 简体中文

基于自然语言的视频事件定位与标注后端。输入视频和事件描述，输出事件时间段、可播放片段及核验信息；支持人工复核后构建数据集。

当前工程实现位于 [`video_grounding/`](video_grounding/)。它提供 Python CLI 和 HTTP API，可作为完整标注系统的推理服务；本仓库不包含完整业务前端、用户权限或对象存储服务。

## 当前处理流程

```text
视频 + 提示词 → 视频探测 → VideoJev 粗筛 → 候选融合 → VideoJev 精筛
           → Gemini 核验（可配置关闭） → 事件与片段导出
           → 人工接受/拒绝、调整边界 → 已复核数据集
```

- **VideoJev-4B**：定位一个或多个事件时间段。支持多提示词、断点恢复和显存不足时降帧重试。
- **Gemini**：已经集成。对精筛后的候选片段进行 yes/no 核验；当前适配器调用 Decisions API，配置模型为 `gemini-decision-1`。否定结果进入审计记录；核验失败的候选保留并标记待人工复核。
- **人工复核**：接受、拒绝或修正事件边界。只有经过人工复核的事件进入数据集。
- Qwen3-VL-4B 独立核验实验不属于当前产品流程，无须下载其模型。VideoJev 自身使用的处理器与依赖仍需保留。

## 文档导航

| 文档 | 面向读者 / 内容 |
|---|---|
| [使用与部署](video_grounding/docs/USAGE.zh-CN.md) | 环境安装、配置、CLI、服务启动、恢复和排障 |
| [HTTP 对接协议](video_grounding/docs/API.zh-CN.md) | 完整系统集成、请求响应、状态与错误、事件和数据集字段 |
| [内部工程契约](video_grounding/docs/CONTRACTS.md) | 时间语义、模型适配器、融合、持久化与模块接口 |
| [兼容性记录](video_grounding/docs/COMPATIBILITY.md) | 已验证 GPU、依赖组合及平台问题 |
| [评测记录](video_grounding/docs/EVALUATION.md) | 测试方法、真实数据实验与已知质量局限 |
| [性能记录](video_grounding/docs/PERFORMANCE.md) | 已测耗时、显存、CPU offload 情况 |

API 的在线请求结构以服务的 `/openapi.json` 为准，交互页面为 `/docs`。响应字段和业务语义见 [API.md](video_grounding/docs/API.zh-CN.md)。

## 快速开始

所有以下命令从仓库根目录进入工程后执行：

```bash
cd video_grounding
```

1. 按 [兼容性安装说明](video_grounding/docs/COMPATIBILITY.md#install) 安装 GPU 依赖、匹配的 FlashAttention/causal-conv1d，以及 ffmpeg/ffprobe。
2. 安装 HTTP 服务依赖，并配置 Gemini 密钥：

   ```bash
   uv pip install -p .venv/bin/python -e '.[server,gemini]'
   cp .env.example .env
   # 编辑 .env，填写 GEMINI_API_KEY；不要提交到版本库
   ```

3. 创建机器专用配置：

   ```bash
   cp configs/rtx3070.yaml configs/local.yaml
   # 按实际机器调整 local.yaml 中 model.local_path、runtime.max_memory
   # default.yaml 适用于较大显存；verify.enabled: false 可关闭 Gemini
   ```

4. 执行一个任务，或启动服务：

   ```bash
   .venv/bin/video-grounding scan --video /data/demo.mp4 \
     --prompt 'A person opens a door' --config configs/local.yaml --out runs/demo

   .venv/bin/video-grounding serve --config configs/local.yaml \
     --jobs-root /data/grounding --media-root /data/videos \
     --host 127.0.0.1 --port 8800
   ```

`runs/demo/events.json` 为事件结果，`clips/` 为导出片段。每个任务使用独立目录，重复运行已有任务应使用 `resume`。

## 完整系统如何接入

业务后端向 `POST /v1/jobs` 提交**推理主机可访问**的视频路径或 HTTP(S) URL，记录返回的 `job_id`，轮询任务状态；完成后读取事件和片段，提交人工复核，再创建数据集。不要让浏览器直接依赖推理服务器的本地文件路径。

一个服务进程串行执行推理和数据集任务。鉴权、租户隔离、上传、URL 访问控制、业务任务去重、通知和对象存储由上层系统负责。当前服务应放在可信网络或受控网关之后。

## 开发验证

```bash
cd video_grounding
uv sync --group dev
uv run pytest
```

测试覆盖合成/回放后端、时间映射、恢复、融合、接口及模拟 Gemini 核验；通过这些测试不等同于真实 GPU 或线上 Gemini 可用性验证。真实模型和 API 联调步骤见 [使用说明](video_grounding/docs/USAGE.zh-CN.md#验证与排障)。
