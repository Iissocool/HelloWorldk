# CutCanvas

> 说明：这是一个以个人使用为定位、由纯 AI 辅助制作与开发的项目，主要使用 GPT-5.4 进行设计、代码生成和迭代。项目目前仍在持续更新中。

这个项目现在包含两部分：

1. 原有的平板壳背景替换工作流
2. 新增的本地个人使用抠图桌面程序

## 目标

把 `rembg + ONNX Runtime` 封装成一个以个人使用为主的 Windows-first 桌面工具，能够：

- 自动识别 GPU 厂商
- 自动选择更适合的执行后端
- 支持 Intel / AMD / NVIDIA 的差异化路线
- 提供单图、批处理、智能批处理和任务历史

## 当前后端路线

### Windows

- Intel: `DirectML -> OpenVINO -> CPU`
- AMD: `DirectML -> CPU`
- NVIDIA: `TensorRT -> CUDA -> DirectML -> CPU`

### Linux

- Intel: `OpenVINO -> CPU`
- AMD: `MIGraphX -> CPU`
- NVIDIA: `TensorRT -> CUDA -> CPU`

说明：

- Windows 上的 AMD GPU 当前主推荐路线是 `DirectML`
- ONNX Runtime 官方仍支持 DirectML，但新的 Windows 特性开发重心已经转向 WinML
- Linux AMD 的 `MIGraphX` 路线在文档中已经纳入，但本仓库当前交付重点还是 Windows 桌面版

## 项目结构

- `app/`: 桌面程序与 Web 控制台源码
- `runtime/rembg/`: 与后端相关的运行脚本
- `scripts/setup_windows_runtime.ps1`: Windows 初始化脚本
- `patches/rembg/`: 对 rembg 的本地补丁
- `docs/`: 架构说明和详细使用手册
- `run_desktop_app.ps1`: 启动桌面程序
- `run_app.ps1`: 启动 Web 控制台
- `run_self_test.ps1`: 自检与烟雾测试

## 快速开始

### 1. 克隆项目

由于 GitHub 仓库名结尾带 `.`，Windows 默认目录名不太友好，建议克隆时显式指定本地目录名：

```powershell
git clone https://github.com/Iissocool/CutCanvas.git CutCanvas
cd CutCanvas
```

### 2. 准备本地 `.venv`

如果你还没有项目级 Python 环境：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-app.txt
```

### 3. 初始化运行时

AMD Windows 推荐：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows_runtime.ps1
```

如果你也要准备 NVIDIA 路线：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows_runtime.ps1 -IncludeNvidia
```

### 4. 启动桌面程序

```powershell
powershell -ExecutionPolicy Bypass -File .\run_desktop_app.ps1
```

### 5. 运行自检

```powershell
powershell -ExecutionPolicy Bypass -File .\run_self_test.ps1
```

如果你想顺手做一张图的烟雾测试：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_self_test.ps1 --input .\some.jpg --output .\some.out.png --backend auto
```

## AMD 机器使用建议

如果你的另一台机器是 AMD GPU 并且运行 Windows：

1. 先运行 `setup_windows_runtime.ps1`
2. 再运行 `run_self_test.ps1`
3. 若检测正常，桌面程序里优先使用 `auto` 或 `amd`
4. 当前 `amd` 实际会走 `DirectML`

## Intel / AMD / NVIDIA 说明

- `auto`: 按当前机器硬件自动选路
- `amd`: 显式要求 AMD Windows 路线，当前实现为 `DirectML`
- `directml`: 适合 Intel / AMD Windows GPU 的通用路线
- `openvino`: 适合 Intel 专项加速
- `cuda`: NVIDIA 通用 GPU 路线
- `tensorrt`: NVIDIA 更高性能路线
- `cpu`: 通用兜底路线

## 个人使用提醒

当前仓库定位为个人使用，模型权重和数据来源仍然建议逐项了解清楚。

尤其是：

- `rembg` 代码本身较宽松，但不同模型的权重来源并不完全一致
- 不同模型的数据集、权重和再分发条件不相同
- `BRIA RMBG` 等模型在更广泛使用前，建议先确认其官方条款

## 文档

- 详细使用手册：`docs/桌面程序详细使用手册.md`
- 架构说明：`docs/architecture.md`

