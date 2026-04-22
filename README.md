# NeonPilot

> 个人使用的 AI 图像工作台，主要使用 GPT-5.4 协助开发，项目仍在持续更新中。

NeonPilot 把图片抠图、批处理、批量命名、AI 生图和 Docker Hermes Agent 控制台整合进同一个 Windows 桌面程序。

## 主要功能

- 单图抠图
- 固定模型批处理
- 智能批处理
- 批量命名
- OpenAI 兼容 AI 生图
- Docker Hermes 控制台
- 程序 CLI 命令桥

## Docker Hermes 路线

程序现在优先使用 Docker 运行 Hermes。
这样做的好处是：

- 不需要额外弹出 Ubuntu 终端窗口
- Hermes 启动、停止、日志查看都可以留在程序内部完成
- Hermes 数据目录固定在 `W:\gemini\data\neonpilot\hermes`
- Skill 会直接导出到 Hermes 数据目录下的 `skills` 目录

Hermes 相关资料：
- [Hermes Agent GitHub](https://github.com/NousResearch/hermes-agent)
- [Hermes Docker 文档](https://hermes-agent.nousresearch.com/docs/user-guide/docker/)

## 主界面

### 1. 仪表盘
- 查看硬件信息
- 查看推荐后端栈
- 查看模型目录
- 查看 Docker Hermes 状态摘要

### 2. 单图处理
- 适合先验证模型、后端和输出质量

### 3. 批处理
- 固定批处理：整个目录统一使用一个模型
- 智能批处理：按图片内容自动挑模型

### 4. 批量命名
- `template`：按模板生成新文件名
- `replace`：查找替换
- `fresh`：直接全新覆盖命名

### 5. AI 生图
- 自填 OpenAI 兼容地址
- API Key 加密保存
- 支持测试连接
- 支持程序内预览
- 支持批量保存到指定目录

### 6. Agent
- 启动 Docker
- 启动 Hermes
- 停止 Hermes
- 查看容器日志
- 导出 Hermes Skill
- 读取和保存 Hermes 模型配置
- 直接在程序里执行 Hermes 命令

## CLI 命令桥

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_neonpilot_cli.ps1 health
powershell -ExecutionPolicy Bypass -File .\scripts\run_neonpilot_cli.ps1 hardware
powershell -ExecutionPolicy Bypass -File .\scripts\run_neonpilot_cli.ps1 plan
powershell -ExecutionPolicy Bypass -File .\scripts\run_neonpilot_cli.ps1 hermes-status
powershell -ExecutionPolicy Bypass -File .\scripts\run_neonpilot_cli.ps1 hermes-start
powershell -ExecutionPolicy Bypass -File .\scripts\run_neonpilot_cli.ps1 hermes-logs --tail 200
powershell -ExecutionPolicy Bypass -File .\scripts\run_neonpilot_cli.ps1 hermes-exec --text "hermes --help"
```

## 安装与运行

### 1. 克隆项目

```powershell
git clone https://github.com/Iissocool/NeonPilot.git
cd NeonPilot
```

### 2. 创建虚拟环境

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-app.txt
```

### 3. 初始化运行环境

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows_runtime.ps1
```

### 4. 启动桌面程序

```powershell
powershell -ExecutionPolicy Bypass -File .\run_desktop_app.ps1
```

### 5. 运行自检

```powershell
powershell -ExecutionPolicy Bypass -File .\run_self_test.ps1
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
- Hermes 数据：`W:\gemini\data\neonpilot\hermes`
