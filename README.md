# NeonPilot

> 个人使用的 AI 图片工作台，主要使用 GPT-5.4 协助开发，项目仍在持续更新中。

NeonPilot 把抠图、批处理、批量命名、AI 生图、资源管理和 Docker Hermes Agent 对话整合进同一个 Windows 桌面程序。

## 当前功能
- 单图抠图
- 固定模型批处理
- 智能批处理
- 批量命名
- OpenAI 兼容 AI 生图
- Photoshop 自动套图桥接
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

## Photoshop 自动套图桥接
适合你现在这条现成流程：

1. 打开 Photoshop
2. 加载模板 PSD
3. 把整个素材文件夹交给 Adobe Photoshop Droplet
4. 由 Droplet 绑定的 Photoshop 动作自动完成套图和保存

在程序里的 `PS 套图` 页填写：
- `模板 PSD`
- `Droplet 程序`
- `素材目录`
- `Photoshop 程序`
- `执行完成后自动关闭 Photoshop`

说明：
- 程序会先打开模板，再把整个文件夹发送给 Droplet
- 当前最终输出目录仍由这个 Droplet 对应的 Photoshop 动作决定
- 如果 Droplet 在设定等待时间内结束，程序会自动关闭 Photoshop
- 如果 Droplet 还在持续运行，程序会先跳过自动关闭，避免中断当前套图
- 如果后续要让 NeonPilot 直接控制导出目录，下一步应改成 Photoshop JSX / Action 桥接

## Agent 终端
Agent 页现在改成了终端优先。

常用命令：
- `help`
- `status`
- `agent-ready`
- `logs`
- `hermes-config-show`
- `hermes-config-set --model deepseek-reasoner --provider auto --base-url https://api.deepseek.com/v1 --api-key <KEY>`
- `ps-batch --template "..." --droplet "..." --input-dir "..." --close-photoshop`

说明：
- Docker / Hermes 状态仍然保留在终端上方
- 模型、API、工作流通过命令直接执行
- 不再依赖右侧一堆单独的配置按钮

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
