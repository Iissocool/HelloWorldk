# Commercial Background Desktop Architecture

这份文档记录当前桌面版的实际结构。目标不是把现有脚本做成一个临时小工具，而是逐步推进为一个可商用、可分发、能自动识别硬件并最大化利用 GPU 的本地抠图产品。

## 当前版本已经落地的模块

1. 硬件探测：识别 OS、CPU、内存、GPU 厂商与显卡名
2. 后端规划：根据 NVIDIA / AMD / Intel 与 Windows / Linux 自动生成推荐后端顺序
3. 模型注册表：为 16 个 rembg 模型记录类别、质量、速度与商用状态
4. 多后端执行器：统一调度 `DirectML / OpenVINO / CUDA / TensorRT / CPU`
5. AMD Windows 路线：显式 `amd` 后端，当前落到 `DirectML`
6. 历史记录：把任务摘要、stdout、stderr、报告路径写入 SQLite
7. 智能批处理：按图片特征判断类别并自动选模型
8. 桌面程序：`tkinter + ttk` 本地 GUI
9. 辅助 Web 控制台：`FastAPI + Jinja2`
10. 自检工具：快速输出硬件画像、推荐后端和烟雾测试结果

## 路径设计

程序不再把 `W:\gemini` 写死在源码里，而是采用：

- 仓库版：默认以项目根目录作为工作区
- 部署版：通过 `GEMINI_ROOT` 环境变量指定工作区根目录

这样同一套代码既可以：

- 在 `W:\gemini` 部署运行
- 也可以被 GitHub 克隆到其他路径后继续使用

## 当前运行结构

```text
Desktop UI (tkinter)
    -> LocalExecutor
        -> Runtime Planner
        -> Hardware Detector
        -> Selection Engine
        -> HistoryStore (SQLite)
        -> runtime/rembg backend runners

Web Console (FastAPI)
    -> LocalExecutor

Self Test
    -> Hardware Detector
    -> Runtime Planner
    -> LocalExecutor
```

## 后端策略

### Windows

- NVIDIA: `TensorRT -> CUDA -> DirectML -> CPU`
- Intel: `DirectML -> OpenVINO -> CPU`
- AMD: `DirectML -> CPU`

### Linux

- NVIDIA: `TensorRT -> CUDA -> CPU`
- Intel: `OpenVINO -> CPU`
- AMD: `MIGraphX -> CPU`

## 为什么 AMD Windows 当前用 DirectML

这是工程权衡，不是偷懒：

- ONNX Runtime 在 Windows 上对 AMD 最现实的通用路线是 `DirectML`
- DirectML 覆盖面广，部署成本低，适合桌面商用品
- Linux AMD 的高阶路线会更偏向 `MIGraphX`

## 初始化流程

`scripts/setup_windows_runtime.ps1` 会负责：

1. 获取 rembg 源码（如缺失）
2. 应用本地补丁
3. 创建桌面程序 `.venv`
4. 创建 `venvs/rembg-dml`
5. 创建 `venvs/rembg-cpu`
6. 可选创建 `venvs/rembg-openvino`
7. 可选创建 `venvs/rembg-nvidia`

## 历史记录设计

数据库：`data/background-desktop/history.sqlite3`

表：`job_history`

核心字段：

- `job_type`
- `backend`
- `model`
- `input_ref`
- `output_ref`
- `ok`
- `return_code`
- `summary`
- `stdout`
- `stderr`
- `report_path`

## 当前已完成的核心交付

1. Windows 本地桌面程序
2. Intel / AMD / NVIDIA 分层后端策略
3. AMD Windows 专用 `amd` 路由别名
4. 统一运行时脚本目录
5. 自检脚本
6. 历史与日志面板
7. `W:\gemini` 部署目录整理

## 下一步优先事项

1. 打包成 `exe / 安装器`
2. 首次启动微基准校准器
3. 更细的 NVIDIA / Intel / AMD 参数模板
4. Linux AMD 的 MIGraphX 实机集成
5. 模型下载、校验和授权开关
