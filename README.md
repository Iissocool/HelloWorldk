# NeonPilot

个人使用的 AI 图片工作台，主要使用 GPT-5.4 协助开发，项目仍在持续更新中。

NeonPilot 把抠图、批量命名、AI 生图、高清增强、原生批量调尺寸、Photoshop 套图、资源管理和 Hermes Agent 工作流终端整合在同一个 Windows 桌面程序里。

## 当前主线能力
- 单图抠图
- 固定模型批处理
- 智能批处理
- 批量命名
- OpenAI 兼容 AI 生图
- Real-ESRGAN ncnn Vulkan 高清增强
- 程序内原生批量调尺寸
  - 批量改宽度
  - 批量改高度
  - 批量写入 DPI
  - 模式：留比例补边 / 留比例裁切 / 强制拉伸 / 仅留比例缩放
- Photoshop 自动套图桥接
- 资源中心
  - 自动补齐最小运行依赖
  - 运行时按需安装 / 卸载
  - 模型按需安装 / 卸载
- Hermes Agent 工作流终端

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

## 推荐工作流

### 工作流 1：转高清 -> 调尺寸 -> PS 套图
适合重复处理同一类商品图。

```text
workflow run upscale-ps --input-dir "W:\images\in" --upscale-dir "W:\images\upscaled" --resize-dir "W:\images\resized" --resize-width 1800 --resize-height 1800 --resize-dpi 300 --ps-output-dir "W:\images\final" --template "C:\Users\F1736\Desktop\模板\昔音浴帘.psd" --droplet "C:\Users\F1736\Desktop\自动套图 图标.exe" --close-photoshop
```

### 工作流 2：保主体批量换背景
适合按主体商品和背景意愿批量改图。

```text
workflow run background-refresh --input-dir "W:\images\source" --output-dir "W:\images\out" --subject "浴帘" --background "北欧奶油风浴室电商场景，柔和自然光，干净高级" --style clean-ecommerce
```

## 原生批量调尺寸 CLI
现在调尺寸不再依赖 Photoshop，可以直接走程序内引擎。

### PowerShell 脚本
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_resize_batch.ps1 -InputDir "W:\images\in" -OutputDir "W:\images\resized" -Width 1800 -Height 1800 -Dpi 300 -Mode contain-pad
```

### 命令桥
```powershell
.\.venv\Scripts\python.exe -m app.command_bridge resize-batch --input-dir "W:\images\in" --output-dir "W:\images\resized" --width 1800 --height 1800 --dpi 300 --mode contain-pad
```

## Photoshop 自动套图桥接
适合你现在这条现成流程：

1. 打开 Photoshop
2. 加载模板 PSD
3. 把整个素材文件夹交给 Adobe Photoshop Droplet
4. 由 Droplet 绑定的 Photoshop 动作自动完成套图和保存

程序里的 `PS 套图` 页会填写：
- 模板 PSD
- Droplet 程序
- 素材目录
- Photoshop 程序
- 结果收集目录
- 执行完成后自动关闭 Photoshop

## Agent
Agent 页现在只保留三件事：
- 看简洁状态
- 改模型与 API 配置
- 直接执行工作流命令

常用命令：
- `workflow help`
- `workflow model show`
- `workflow model set --model <模型> --provider <提供方> --base-url <地址> --api-key <密钥>`
- `workflow run upscale-ps ...`
- `workflow run background-refresh ...`

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
