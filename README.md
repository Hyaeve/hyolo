# Herbal Vision / 智能目标检测工作台

当前版本 V3.2 已完成第一阶段并进入第二阶段，覆盖以下能力：

- x86 Docker 一键部署
- FastAPI 后端服务
- YOLO 模型加载与重载
- YOLO 模型上传、列出与切换
- CPU 图片与视频上传检测
- 目录监控自动检测
- 运行日志独立页面
- RTSP / ONVIF 摄像机接入与实时检测预览
- 中草药识别后联动 DeepSeek 生成介绍与药用功效
- 最简 Web 上传与日志页面

## 目录结构

```text
backend/
frontend/
config/
models/
uploads/
outputs/
watch/
logs/
Dockerfile
docker-compose.yml
requirements.txt
```

## 准备模型

将训练好的模型文件放到 `./models/best.pt`。

如果模型尚未放置，服务仍可启动，但检测接口会返回明确错误信息。

## 启动方式

```bash
docker compose up -d --build
```

浏览器访问：`http://127.0.0.1:8000`

## 主要接口

- `GET /api/status`
- `GET /api/model`
- `GET /api/models`
- `POST /api/models/upload`
- `POST /api/models/select`
- `POST /api/model/reload`
- `POST /api/detect/upload`
- `GET /api/cameras`
- `POST /api/cameras`
- `POST /api/cameras/{camera_id}/start`
- `POST /api/cameras/{camera_id}/stop`
- `GET /api/cameras/{camera_id}/status`
- `GET /api/stream/{camera_id}`
- `POST /api/onvif/resolve`
- `GET /api/logs?lines=200`
- `POST /api/watch/start`
- `POST /api/watch/stop`
- `GET /api/watch/status`

## 本地运行

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

## 第二阶段说明

- 当前版本支持图片和视频检测
- 当前阶段仅支持 `cpu`
- 支持上传用户自训练 YOLO 模型，并在多个模型之间切换
- 支持 RTSP 摄像机实时识别预览
- 支持通过 ONVIF 解析摄像机流地址后接入识别
- 图片结果输出到 `./outputs/images`
- 视频结果输出到 `./outputs/videos`
- 待监控目录为 `./watch`
- 运行日志输出到 `./logs/app.log`

## Docker 内存与性能优化

当前版本已加入一组默认优化，目标是降低 CPU 模式下的内存占用、线程争抢和镜像冗余：

- 构建层优化：
  - 使用 [`.dockerignore`](.dockerignore) 排除 [`models/`](models/)、[`uploads/`](uploads/)、[`outputs/`](outputs/)、[`logs/`](logs/) 与 [`watch/`](watch/) 等运行目录，缩小构建上下文
  - [`Dockerfile`](Dockerfile) 使用 `--no-install-recommends`
  - 去掉不必要的 [`torchaudio`](Dockerfile:20) 安装，仅保留 CPU 版 [`torch`](Dockerfile:21) 与 [`torchvision`](Dockerfile:21)
  - 启用 [`PYTHONDONTWRITEBYTECODE`](Dockerfile:5) 与 pip 无缓存/无编译安装，减少镜像膨胀

- 运行层优化：
  - [`docker-compose.yml`](docker-compose.yml) 默认设置 `CPU_THREADS=2`
  - 默认把 [`MODEL_IMGSZ`](docker-compose.yml) 调整到 `512`
  - 默认把 [`CAMERA_DEFAULT_FPS_LIMIT`](docker-compose.yml) 调整到 `6`
  - 默认加入 `APP_SHM_SIZE=256m`、`APP_MEM_LIMIT=4g`、`APP_CPUS=2.0`、`APP_PIDS_LIMIT=512`
  - 通过 [`OMP_NUM_THREADS`](docker-compose.yml)、[`OPENBLAS_NUM_THREADS`](docker-compose.yml)、[`MKL_NUM_THREADS`](docker-compose.yml)、[`NUMEXPR_NUM_THREADS`](docker-compose.yml) 控制底层线程数量

- 应用层优化：
  - [`ModelService.initialize()`](backend/services/model_service.py:27) 同时限制 PyTorch 与 OpenCV 线程数
  - [`camera_service`](backend/services/camera_service.py:116) 将摄像头缓冲区限制为 1 帧，减少延迟堆积
  - MJPEG 推流 JPEG 质量从高值下调到更均衡的压缩等级，降低带宽与内存压力

如果机器配置较低，可进一步通过环境变量下调：

```bash
CPU_THREADS=1
MODEL_IMGSZ=416
CAMERA_DEFAULT_FPS_LIMIT=4
APP_MEM_LIMIT=3g
APP_CPUS=1.5
```

如果机器配置较高、你更看重检测精度，可以把 [`MODEL_IMGSZ`](docker-compose.yml) 调回 `640`。

## DeepSeek 配置

使用官方 OpenAI 兼容方式接入 DeepSeek，通过环境变量配置：

```bash
DEEPSEEK_API_KEY=你的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
```

如果未配置 [`DEEPSEEK_API_KEY`](docker-compose.yml)，图片识别仍然可用，但草药介绍会显示未启用提示。

## AI 配置持久化与双保险

- Web 页面中的 AI 配置保存接口会把 [`AI API 地址`](frontend/index.html:1109)、[`AI 模型名称`](frontend/index.html:1118) 和 [`AI 密钥`](frontend/index.html:1133) 持久化到 [`config/config.yaml`](config/config.yaml)
- 容器场景下通过 [`APP_CONFIG_FILE`](docker-compose.yml:11) 固定写入 compose 映射目录 [`./config:/app/config`](docker-compose.yml:43)
- 同时支持通过 [`docker-compose.yml`](docker-compose.yml) 中的环境变量 [`AI_BASE_URL`](docker-compose.yml:21)、[`AI_API_KEY`](docker-compose.yml:22)、[`AI_MODEL`](docker-compose.yml:23)、[`AI_TIMEOUT_SECONDS`](docker-compose.yml:24) 作为回退配置
- 若环境变量与页面保存配置同时存在，运行时优先使用环境变量，避免跨设备或重建容器时丢失关键 AI 参数

## 登录认证

系统现在默认启用登录认证，未登录时访问 Web 控制台会先进入 [`/login`](frontend/login.html) 页面。

- 默认账户：`admin`
- 默认密码：`password`

认证信息会持久化到 [`config/auth.json`](config/auth.json)，因此用户修改账户密码后，重启容器仍会保留。

支持的认证相关接口：

- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/status`
- `POST /api/auth/change-credentials`

## 第二阶段验证

1. 启动服务后访问 `http://127.0.0.1:8000`
2. 上传图片，确认检测结果写入 `./outputs/images`
3. 上传视频，确认检测结果写入 `./outputs/videos`
4. 上传或切换不同的 YOLO 模型，确认顶部模型信息变化
5. 若配置了 [`DEEPSEEK_API_KEY`](docker-compose.yml)，识别图片后确认界面出现草药基本描述与药用功效
6. 点击侧边栏进入“运行日志”，确认日志已独立显示
7. 配置 RTSP 摄像机并启动，确认 Web 实时显示带识别框画面
8. 配置 ONVIF 主机信息并解析，确认可获得 RTSP 地址并用于实时监控
9. 启动目录监控后，将图片或视频放入 `./watch`，确认系统自动处理


## Docker Compose部署安装
```text
services:
  yolo-app:
    image: ghcr.io/hyaeve/hyolo:latest
    container_name: hyolo
    network_mode: bridge
    ports:
      - 8000:8000
    volumes:
      - ./models:/app/models
      - ./uploads:/app/uploads
      - ./outputs:/app/outputs
      - ./watch:/app/watch
      - ./logs:/app/logs
      - ./config:/app/config
    environment:
      APP_CONFIG_FILE: /app/config/config.yaml
      MODEL_PATH: /app/models/best.pt
      DEVICE: cpu
      TZ: Asia/Shanghai
    restart: unless-stopped
```
