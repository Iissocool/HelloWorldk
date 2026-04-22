# NeonPilot Architecture

## 桌面层
- `app/desktop_app.py`
- Tk 桌面程序主入口
- 负责页面、背景动图、导向窗口、Agent 控制台

## 执行层
- `app/executor.py`
- 负责单图、批处理、智能批处理、批量命名、AI 生图调用

## 命令桥
- `app/command_bridge.py`
- 负责把程序能力暴露成 CLI
- 方便 Hermes 或其他自动化系统调用

## Hermes 适配
- `app/hermes_adapter.py`
- 负责 WSL 检测、Hermes 可用性检测、Skill 导出、命令执行

## 配置与状态
- `app/config.py`
- `app/app_settings.py`
- `app/ai_image.py`
- `app/secure_store.py`

## 数据层
- `app/history.py`
- `data/neonpilot/`

## 品牌资源
- `assets/branding/`
- 图标、启动图、默认 GIF 背景

## 打包层
- `NeonPilot.spec`
- `packaging/NeonPilot.iss`
- `scripts/build_windows.ps1`
- `scripts/deploy_w_gemini.ps1`
