# NeonPilot

> 个人使用的 AI 图片工作台，主要使用 GPT-5.4 协助开发，项目仍在持续更新中。

NeonPilot 把抠图、批处理、批量命名、AI 生图、资源管理和 Docker Hermes Agent 对话整合进同一个 Windows 桌面程序。

## 当前功能
- 单图抠图
- 固定模型批处理
- 智能批处理
- 批量命名
- OpenAI 兼容 AI 生图
- 资源中心
  - 自动补齐最小运行依赖
  - 运行时按需安装 / 卸载
  - 模型按需安装 / 卸载
- Docker Hermes 聊天终端
- 程序 CLI 命令桥

## 启动方式

### 1. 克隆项目
```powershell
git clone https://github.com/Iissocool/NeonPilot.git
cd NeonPilot
```

### 2. 直接启动桌面程序
启动脚本会自动补齐最小可运行依赖，不需要先手动创建 `.venv`。

```powershell
powershell -ExecutionPolicy Bypass -File .\run_desktop_app.ps1
```

### 3. 可选自检
```powershell
powershell -ExecutionPolicy Bypass -File .\run_self_test.ps1
```

### 4. 可选 Web 控制台
```powershell
powershell -ExecutionPolicy Bypass -File .\run_app.ps1
```

## 资源中心
桌面程序里的“资源中心”负责两类可选资源。

### 运行时组件
- `core`：程序最小依赖
- `cpu`：CPU 抠图运行时
- `directml`：AMD / Intel 常用 GPU 路线
- `openvino`：Intel 专项路线
- `nvidia`：CUDA / TensorRT 路线

### 模型资源
- 默认不会一次性下载全部模型
- 用到哪个模型，再安装哪个模型
- 支持一键卸载，方便清理磁盘

## Agent
Agent 页现在只保留三件事：
- 看状态
- 改模型与 API 配置
- 直接和 Hermes 对话

常用按钮：
- `刷新状态`
- `一键准备 Agent`
- `查看日志`
- `测试 API`
- `测试聊天`
- `压缩配置`

Hermes 数据目录固定在：

```text
W:\gemini\data\neonpilot\hermes
```

## CLI 命令桥
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_neonpilot_cli.ps1 health
powershell -ExecutionPolicy Bypass -File .\scripts\run_neonpilot_cli.ps1 hardware
powershell -ExecutionPolicy Bypass -File .\scripts\run_neonpilot_cli.ps1 plan
powershell -ExecutionPolicy Bypass -File .\scripts\run_neonpilot_cli.ps1 runtime-status
powershell -ExecutionPolicy Bypass -File .\scripts\run_neonpilot_cli.ps1 model-status
powershell -ExecutionPolicy Bypass -File .\scripts\run_neonpilot_cli.ps1 hermes-status
```

## 打包
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```

打包完成后：
- 便携版：`dist\NeonPilot\NeonPilot.exe`
- 安装包：`dist\installer\NeonPilot-Setup.exe`

## 部署到 W:\gemini
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\deploy_w_gemini.ps1
```

部署完成后：
- 程序：`W:\gemini\apps\NeonPilot\NeonPilot.exe`
- 安装包：`W:\gemini\apps\NeonPilot\installer\NeonPilot-Setup.exe`
- 启动器：`W:\gemini\run_neonpilot.cmd`
