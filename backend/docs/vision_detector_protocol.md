# Vision Detector Protocol

## 目标

该协议用于把 PIAP 后端接入外部专用视觉检测服务。当前主链路顺序为：

1. 若配置 `PIAP_VISION_DETECTOR_URL`，优先调用专用视觉检测服务
2. 若专用服务不可用或返回空结果，回退到火山多模态大模型
3. 若大模型仍无法产出有效结构化结果，使用项目内可变兜底输出

实现位置：
- `backend/agent/vision/detector_client.py`
- `backend/agent/graph/nodes/vision.py`

## 环境变量

- `PIAP_VISION_DETECTOR_URL`
  - 外部视觉检测服务地址
  - 示例：`http://127.0.0.1:9008/detect`
- `PIAP_VISION_DETECTOR_API_KEY`
  - 可选，若配置则以 `Authorization: Bearer <token>` 方式发送
- `PIAP_VISION_DETECTOR_TIMEOUT_SEC`
  - 可选，请求超时时间，默认 `20`

## 请求协议

### Method

`POST`

### Headers

默认：

```http
Content-Type: application/json
```

若配置了 API Key：

```http
Authorization: Bearer <PIAP_VISION_DETECTOR_API_KEY>
```

### Body

```json
{
  "image_urls": [
    "https://example.com/image-a.jpg",
    "data:image/png;base64,..."
  ],
  "product_id": "SCREW-A",
  "spec_id": "SCREW-A-2026-V1"
}
```

### 字段说明

- `image_urls`
  - 必填
  - 支持公网 URL 或 Data URL
- `product_id`
  - 可选
  - 用于让外部检测服务按产品线选择模型或阈值
- `spec_id`
  - 可选
  - 用于让外部检测服务按规格版本加载规则

## 响应协议

服务至少应返回一个 JSON 对象。PIAP 当前可解析以下任一结构：

### 推荐结构

```json
{
  "defects": [
    {
      "type": "surface_scratch",
      "confidence": 0.91,
      "bbox": [0.12, 0.28, 0.24, 0.14],
      "description": "螺杆表面存在连续划痕"
    }
  ],
  "image_summary": "螺钉头部附近检测到轻微划痕"
}
```

### 兼容结构

PIAP 也兼容这些字段别名：

- `defects` / `items` / `detections`
- `type` / `label`
- `confidence` / `score` / `probability`
- `bbox` / `box` / `rect`
- `description` / `detail` / `reason`

例如：

```json
{
  "detections": [
    {
      "label": "dent",
      "score": 0.83,
      "box": [0.31, 0.42, 0.18, 0.16],
      "detail": "凹陷位于边缘区域"
    }
  ]
}
```

## bbox 约定

- `bbox` 必须是 `[x, y, w, h]`
- 当前前端缺陷标注组件默认按归一化坐标解释
- 推荐值域：`0 ~ 1`
- `x, y` 表示左上角
- `w, h` 表示宽和高

示例：

```json
[0.18, 0.26, 0.22, 0.12]
```

表示框位于图像宽 18%、高 26% 处，宽度占图像 22%，高度占图像 12%

## 最小返回要求

如果服务没有检测到明显缺陷，也建议返回：

```json
{
  "defects": [],
  "image_summary": "未检测到明确缺陷"
}
```

不要返回 HTML、Markdown 或纯文本错误页。

## 错误处理约定

若服务异常，建议返回标准 HTTP 错误码：

- `400` 请求格式错误
- `401/403` 鉴权失败
- `429` 限流
- `500` 服务内部错误
- `503` 模型或 GPU 不可用

PIAP 在以下情况下会自动回退到下一级：

- HTTP 请求失败
- 返回非 JSON
- JSON 中没有可解析的缺陷框

## 联调建议

### cURL 示例

```bash
curl -X POST "$PIAP_VISION_DETECTOR_URL" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $PIAP_VISION_DETECTOR_API_KEY" \
  -d '{
    "image_urls": ["https://example.com/part.jpg"],
    "product_id": "SCREW-A",
    "spec_id": "SCREW-A-2026-V1"
  }'
```

### Python 示例

```python
import httpx

payload = {
    "image_urls": ["https://example.com/part.jpg"],
    "product_id": "SCREW-A",
    "spec_id": "SCREW-A-2026-V1",
}

resp = httpx.post("http://127.0.0.1:9008/detect", json=payload, timeout=20)
resp.raise_for_status()
print(resp.json())
```

## 什么时候不需要这个协议

如果你只想使用火山多模态大模型直接看图，可以不配置 `PIAP_VISION_DETECTOR_URL`。
系统会直接走当前的 `vision_chat` 路径。

这个协议的意义在于：当你接入 YOLO、GroundingDINO、工业 AOI、内部 CV 服务时，不需要再改 PIAP 主链路。
