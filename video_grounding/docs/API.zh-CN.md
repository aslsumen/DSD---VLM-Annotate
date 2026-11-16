# HTTP API 对接协议

[English](API.md) | 简体中文

面向完整系统的业务后端、标注前端及数据集服务。本文对应 `src/video_grounding/server.py` 当前实现；版本前缀为 `/v1`。启动方式见 [USAGE.zh-CN.md](USAGE.zh-CN.md#http-服务部署)。

## 接入约定

- 默认地址 `http://127.0.0.1:8800`；JSON 请求使用 `Content-Type: application/json`，片段下载为 `video/mp4`。
- 当前服务不实现认证。网关/业务后端负责鉴权、租户授权、限流、资源访问和审计。
- 输入视频路径属于**推理服务器文件系统**，不是浏览器或业务服务器本地路径。可以传服务可下载的 HTTP(S) URL；不支持 multipart 上传、对象存储 SDK URI 或直接上传二进制。
- 一个任务对应一个视频和一个或多个提示词。视频、提示词、采样配置不能通过 API 修改；配置是启动服务时给出的 YAML，不支持 POST 逐任务覆盖配置。
- POST 创建任务没有幂等键，每次调用都产生新任务。业务侧应保存 job_id；网络超时不意味着创建失败，不要无条件重复提交。列表可辅助核对，但服务没有 client_request_id 查询功能。
- API 没有回调或事件流；建议每 3–5 秒轮询，业务侧设置可调整的长任务超时。轮询超时不会取消服务中的任务。
- 持久化引用使用 `(job_id, event_id)`；event_id 不包含视频身份，不能单独作为跨视频全局主键。

## 推荐调用顺序

```text
GET health → POST jobs → GET jobs/{id}（轮询）
  → GET events → GET clips/{event_id} → POST reviews
  → POST datasets → GET datasets/{id}（轮询）→ GET manifest / clips
```

业务前端要区分：处理完成、扫描覆盖完整、Gemini 已核验、人工已复核。这四种状态不能合并成同一个“完成”。

## 1. 健康检查

`GET /v1/health` → 200：

```json
{"status":"ok","model_id":"ZhuYuhan/VideoJev-4B","model_revision":"…","model_loaded":false,"queue_length":0}
```

`model_loaded` 在首次扫描前可以是 false；synthetic/replay 后端也不以此判断可用性。queue_length 不含正在处理的任务，可能包括排队的数据集任务。该接口不是 GPU/Gemini 的端到端 readiness 检查。

## 2. 创建任务

`POST /v1/jobs`：

```json
{
  "video": "/data/videos/demo.mp4",
  "prompts": [
    {"query_id":"open_door","text":"A person opens a door"},
    {"query_id":"sit_down","text":"A person sits down"}
  ]
}
```

单提示词简写：`{"video":"/data/videos/demo.mp4","prompt":"A person opens a door"}`，其 query_id 固定为 `q1`。

- `prompts` 与 `prompt` 必须且只能提供一个；prompts 非空、query_id 唯一且非空，text 不能全空白。
- 本地路径须存在；配置 media-root 时必须位于其内（按 resolve 后路径检查）。
- URL 可访问性在后台下载时判断，所以 202 不表示下载或推理成功。签名 URL 有效期要覆盖排队时间，下载不支持附加认证 header。

202 响应：

```json
{"job_id":"job_0123456789ab","state":"queued"}
```

```bash
curl -sS -X POST http://127.0.0.1:8800/v1/jobs \
  -H 'Content-Type: application/json' \
  -d '{"video":"/data/videos/demo.mp4","prompt":"A person opens a door"}'
```

## 3. 状态、列表与重试

`GET /v1/jobs/{job_id}` → 200，示例（progress 的键按实际执行情况出现）：

```json
{
  "job_id":"job_0123456789ab",
  "state":"refining",
  "video":"/data/videos/demo.mp4",
  "queries":[{"query_id":"q1","text":"A person opens a door"}],
  "progress":{"coarse.succeeded":12,"refine.succeeded":3},
  "error":null,
  "scan_complete":null,
  "n_events":null
}
```

`GET /v1/jobs` 返回上述对象组成的**数组**，按请求文件修改时间倒序；目前没有分页、过滤或总数包装对象。

| state | 上层系统建议映射 | 含义 |
|---|---|---|
| queued | 排队中 | 已记录请求 |
| created / probing | 处理中 | 建立任务、下载或视频探测 |
| scanning | 处理中 | 粗筛 |
| refining | 处理中 | 精筛 |
| verifying | 处理中 | Gemini 核验 |
| exporting | 处理中 | 输出 JSON 与片段 |
| completed | 可读取结果 | 不保证覆盖完整或核验全部成功 |
| failed / paused | 失败或待恢复 | error、日志与任务配置用于诊断 |

`progress` 是窗口状态计数，不是百分比或已处理视频秒数；精筛窗口数可动态增长。`scan_complete`、`n_events` 从已有 events.json 读取，输出前为 null；恢复过程中若已有输出，可能暂时是旧值，以 completed 后数据为准。

`POST /v1/jobs/{job_id}/retry` 无请求体，202 返回 `{job_id,state:"queued"}`。只接受 failed/paused 且不在活动队列中的任务，否则 409。它复用原目录恢复，不创建新业务任务。恢复时配置、视频指纹和模型 revision 仍须匹配。

没有取消/删除/暂停接口，也没有 completed 任务的 API 重新核验接口；管理员补核验需按使用说明通过 CLI 操作。

## 4. 读取事件与视频片段

`GET /v1/jobs/{job_id}/events` → 200；任务非 completed 时 409。

返回结构：

| 顶层字段 | 类型 | 含义 |
|---|---|---|
| job_id / video | string | 任务 ID、推理使用的视频路径；URL 任务通常是下载后的本地路径 |
| video_duration_sec | number | 原视频时长 |
| backend / model_id / model_revision | string | 定位后端及模型身份 |
| scan_complete | boolean | 是否不存在扫描覆盖缺口；不表示 Gemini 完成率 |
| queries | array | 每项含 query_id、query、warnings、scan_complete |
| events | array | 保留的事件；包括核验失败但留待人工复核的事件 |
| coverage_gaps | array | 永久失败窗口记录：query_id、window_id、start_sec、end_sec、reason |
| rejected_events | array，可缺省 | 开启 Gemini 时出现；被 Gemini 判否的事件，结构同 Event |

Event 示例（数值仅用于说明字段）：

```json
{
  "event_id":"evt_0123456789ab",
  "query_id":"q1",
  "query":"A person opens a door",
  "event_start_sec":12.5,
  "event_end_sec":18.0,
  "clip_start_sec":12.0,
  "clip_end_sec":18.5,
  "complete":"likely",
  "needs_review":false,
  "review_reasons":[],
  "raw_score_max":0.96,
  "alignment_status":"estimated",
  "evidence_window_ids":["window_example"],
  "clip_path":"clips/evt_0123456789ab.mp4",
  "verdict":{"present":true,"p_present":0.91,"model":"gemini-decision-1"}
}
```

字段语义：

- 所有 `*_sec` 均为**原视频全局秒数**，零点是视频第一帧；不是导出片段的局部时间。播放片段时，事件相对位置为 `event_start_sec - clip_start_sec`。
- `event_*` 为定位边界；`clip_*` 加前后留白并限制到视频范围。人工修正也使用原视频坐标。
- `complete` 为 `likely|unknown`，是边界完整性启发式标记；`needs_review=false` 不是人工接受状态。
- `raw_score_max` 是 VideoJev 未校准原始分数，不是最终正确率。各 query 内按其降序输出，不保证全数组按时间排序。
- `alignment_status` 表示时间映射质量，常见 `exact|estimated|unknown`；`review_reasons`、query warnings 应原样保留，客户端容忍新增值。
- `verdict` 为 null 或 `{present:boolean,p_present:number,model:string}`。当前阈值为固定 0.5；没有 `reason`、`confidence` 字段，也没有配置项修改此阈值。
- 开启 verify 时，核验失败的事件为 `verdict:null`、`needs_review:true` 并含 `not_verified`。关闭 verify 时 null 不代表调用失败。
- Gemini 判否事件只在 rejected_events，不导出其 clip；当前人工 review API 不接受其中的 event_id。
- `clip_path` 是任务目录内相对路径，可能为 null。它不是 HTTP URL，更不能将服务端 video 路径直接交给浏览器播放。

`GET /v1/jobs/{job_id}/clips/{event_id}` 返回 MP4。请求路径里的 event_id **不带 `.mp4`**。文件不存在（含关闭导出、Gemini 拒绝）返回 404。

**核验部分失败：** 单片段异常会保留候选；持续 429 会停止余下核验但继续导出，最终任务仍可能 completed。完整系统必须依据 verdict/not_verified 显示待复核状态，不能把 completed 当成所有 Gemini 请求成功。

## 5. 人工复核

`POST /v1/jobs/{job_id}/reviews`：

```json
{
  "reviews": [
    {"event_id":"evt_0123456789ab","accepted":true,"start_sec":12.8,"end_sec":17.6}
  ]
}
```

只接受已完成任务 events 中的 event_id。start_sec/end_sec 可分别省略，省略的一端沿用原事件值；必须满足 `0 <= start < end <= video_duration_sec`。accepted=false 表示人工拒绝。相同 event_id 最新提交覆盖旧 review，未提交的旧 review 保留。

200 响应直接是复核指标对象：`n_candidates, n_reviewed, n_accepted, accept_rate, complete_clip_rate, boundary_adjust_p50, boundary_adjust_p90, per_query`。无有效样本时部分指标为 null。它不包含召回率。

`GET /v1/jobs/{job_id}/reviews` → `{"reviews":[...],"metrics":{...}}`。复核保存不修改 events.json 或 job 中已导出的片段；修正后的视频在生成数据集时重切。

## 6. 构建与读取数据集

`POST /v1/datasets`：

```json
{"name":"door-events-v1","job_ids":["job_0123456789ab"],"include_rejected":false}
```

name、job_ids 必须非空，所有任务必须 completed；重复 job_id 会去重。202：`{"dataset_id":"ds_0123456789ab","state":"queued"}`。

`GET /v1/datasets/{dataset_id}` → `{dataset_id,state,error,stats}`，state 为 `queued|running|completed|failed`；stats 未完成时通常 null。目前无数据集 retry 接口，失败后排查原因再创建新数据集。

`GET /v1/datasets/{dataset_id}/manifest` → dataset.json，文件尚未生成时 409：

```json
{
  "dataset":"door-events-v1",
  "created_at":"2026-11-12T12:00:00+00:00",
  "model":"ZhuYuhan/VideoJev-4B",
  "model_revision":"…",
  "videos":[{"video":"/data/videos/demo.mp4","job_id":"job_0123456789ab","duration_sec":60.0,"scan_complete":true}],
  "annotations":[{
    "video":"/data/videos/demo.mp4","job_id":"job_0123456789ab","query_id":"q1",
    "prompt":"A person opens a door","start_s":12.8,"end_s":17.6,
    "status":"accepted","engine_event_id":"evt_0123456789ab",
    "clip":"clips/job_0123456789ab_evt_0123456789ab.mp4","adjusted":true,"raw_score_max":0.96
  }],
  "stats":{"n_annotations":1,"n_accepted":1,"n_rejected":0,"n_unreviewed":0}
}
```

- 未人工复核的事件跳过。include_rejected 只控制**人工**拒绝项是否进入 annotations。
- n_rejected 统计人工拒绝总数，即使 include_rejected=false 也可能大于零；不要假定它等于 annotations 中 rejected 的数量。
- annotations 的时间字段为 `start_s/end_s`，仍是原视频时间，注意与 Event 字段名不同。
- 已调整边界会从源视频重切，并加配置的前后留白；需要原视频仍可读。
- 当前混合模型任务未被拒绝，顶层 model 取首个任务。业务侧宜只组合兼容版本的任务。

`GET /v1/datasets/{dataset_id}/clips/{name}` 返回 MP4。name 为 annotations[].clip 的文件名**去掉 `.mp4`**，例如 `job_0123456789ab_evt_0123456789ab`。

## 错误协议与能力边界

| 状态码 | 场景 |
|---|---|
| 200 | 查询、读取 JSON、保存 review、下载片段成功 |
| 202 | 接受创建/重试请求，实际工作异步执行 |
| 400 | 业务输入不合法，如 prompts 组合、视频路径、复核时间范围 |
| 404 | 未知任务/数据集 ID，或片段不存在 |
| 409 | 尚未 completed、状态不允许 retry、manifest 未生成 |
| 422 | FastAPI/Pydantic 请求结构或类型校验失败 |
| 500 | 未处理的服务异常；后台任务异常通常表现为状态 failed 和 error，而非原 POST 的 500 |

业务错误一般为 `{"detail":"说明"}`；422 的 detail 为结构化校验错误数组。客户端不要假定 detail 永远是字符串。

`/docs`、`/redoc`、`/openapi.json` 由 FastAPI 提供。当前路由未声明完整响应模型，OpenAPI 主要描述请求结构及路由，响应语义以本文和实现为准。API 前缀尚未提供更细的兼容版本协商；上线前应固定服务代码版本，并让客户端容忍新增 JSON 字段。
