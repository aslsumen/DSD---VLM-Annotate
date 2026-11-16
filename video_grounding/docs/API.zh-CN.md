# Python API

[English](API.md) | 简体中文

引擎是一个库。在产品中，后端 worker 通过 `backend/app/adapters/videojev.py` 调用它：一个任务 = 一个视频 × 一个动作（一条 query），预览片段由后端自己切，所以适配器设置 `export.cut_clips=false`。安装和调试 CLI 见 [USAGE.zh-CN.md](USAGE.zh-CN.md)。

## 入口（`video_grounding.scheduler`）

```python
run_scan(video: str, queries: list[Query], settings: Settings, out_dir: str | Path, *,
         video_info: VideoInfo | None = None, backend=None, job_id: str | None = None,
         keep_loaded: bool = False, verifier=None,
         progress: Callable[[float], None] | None = None) -> dict

resume(out_dir: str | Path, *, backend=None, video_info: VideoInfo | None = None,
       keep_loaded: bool = False, verifier=None,
       progress: Callable[[float], None] | None = None) -> dict

export(out_dir: str | Path, *, high: float | None = None, low: float | None = None) -> dict
```

- `Query(query_id, text)` 在 `video_grounding.models`；`Settings` 和 `load_settings(path)` 在 `video_grounding.settings`。
- `run_scan` 在新的 `out_dir` 中开始任务；`resume` 继续被中断的任务（校验源视频指纹、模型 revision 和配置 hash，不一致抛 `ResumeMismatch`）；`export` 用存储的预测按可选的新阈值重新融合，不调用模型。
- 三者都返回 `events.json` 文档（字段见下）。`backend` / `verifier` 默认按配置创建；需要跨任务复用已加载的模型时自行传入，并设 `keep_loaded=True`。

### 进度

`progress(fraction)` 在调用线程上执行，值在 [0, 1]，同一次 `run_scan` / `resume` 调用内不递减：

- 粗筛：每个窗口完成后报告 `0.8 * 已完成窗口 / 总窗口`（恢复时已完成的窗口也计入）；
- 精筛：每条 query 完成后报告 `0.8 + 0.2 * 已完成 query / 总 query`；
- `events.json` 写完后报告 `1.0`。

回调抛出的异常会从 `run_scan` / `resume` 中传出，可用来中止任务。已完成的窗口已落盘，`resume` 会从这里继续。

## `events.json`

| 顶层字段 | 含义 |
|---|---|
| `job_id`、`video`、`video_duration_sec` | 任务标识与源视频 |
| `backend`、`model_id`、`model_revision` | 定位后端及模型身份 |
| `scan_complete` | 不存在永久失败窗口；不表示 Gemini 完成率 |
| `queries` | 每项含 `query_id`、`query`、`warnings`、`scan_complete` |
| `events` | 保留的事件，包括核验失败的候选 |
| `coverage_gaps` | 永久失败窗口：`query_id`、`window_id`、`start_sec`、`end_sec`、`reason` |
| `rejected_events` | 仅开启 Gemini 时出现：被 Gemini 判否的事件，结构同 `events` |

事件示例（数值仅用于说明字段）：

```json
{
  "event_id": "evt_0123456789ab", "query_id": "q1", "query": "A person opens a door",
  "event_start_sec": 12.5, "event_end_sec": 18.0, "clip_start_sec": 12.0, "clip_end_sec": 18.5,
  "complete": "likely", "needs_review": false, "review_reasons": [],
  "raw_score_max": 0.96, "alignment_status": "estimated",
  "evidence_window_ids": ["window_example"], "clip_path": "clips/evt_0123456789ab.mp4",
  "verdict": {"present": true, "p_present": 0.91, "model": "gemini-decision-1"}
}
```

- 所有 `*_sec` 都是**原视频全局秒数**（0 为第一帧），不是片段内时间。在片段播放器里，事件起点为 `event_start_sec - clip_start_sec`。
- `event_*` 是预测边界；`clip_*` 加了前后缓冲，并限制在视频范围内。
- `complete` 为 `likely|unknown`，是边界完整性启发式标记。
- `raw_score_max` 是未校准的 VideoJev 分数，不是概率。同一 query 的事件按分数降序排列，不是按时间。
- `alignment_status` 通常为 `exact|estimated|unknown`；应保留 `review_reasons` 和 query `warnings`，并容忍新增值。
- `verdict` 为 null 或 `{present, p_present, model}`；阈值固定 0.5。开启核验时，调用失败会得到 `verdict=null`、`needs_review=true`，且 `review_reasons` 含 `not_verified`。
- `clip_path` 相对任务目录；`export.cut_clips=false` 时为 null。
- 事件 ID 不含视频标识，引用事件时使用 `(job_id, event_id)`。
- 已完成的任务仍可能有覆盖缺口或未核验候选：分别读取 `scan_complete`、`coverage_gaps`、`verdict` 和 `review_reasons`。
