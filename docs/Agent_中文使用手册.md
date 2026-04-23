# Agent 中文使用手册

## 这个 Agent 是做什么的
NeonPilot 的 Agent 是一个工作流调度终端，用来快速执行固定流程命令，而不是原始的 Docker 或 Hermes 终端。

## 你可以做什么
1. 查看帮助：`workflow help`
2. 查看当前模型配置：`workflow model show`
3. 修改模型与接口：
   `workflow model set --model <模型> --provider <提供方> --base-url <地址> --api-key <密钥>`
4. 运行转高清 -> 调尺寸 -> PS 套图：
   `workflow run upscale-ps --input-dir "W:\images\in" --upscale-dir "W:\images\upscaled" --resize-dir "W:\images\resized" --resize-width 1800 --resize-height 1800 --resize-dpi 300 --ps-output-dir "W:\images\final" --template "C:\Users\F1736\Desktop\模板\昔音浴帘.psd" --droplet "C:\Users\F1736\Desktop\自动套图 图标.exe" --close-photoshop`
5. 单独运行程序内批量调尺寸：
   `resize-batch --input-dir "W:\images\in" --output-dir "W:\images\resized" --width 1800 --height 1800 --dpi 300 --mode contain-pad`
6. 运行保主体换背景：
   `workflow run background-refresh --input-dir "W:\images\source" --output-dir "W:\images\out" --subject "浴帘" --background "北欧奶油风浴室电商场景，柔和自然光，干净高级" --style clean-ecommerce`

## 小组件怎么用
- `Docker / Gateway / 对话`：显示当前运行状态
- `provider / model / Base URL / API Key`：快速修改模型配置
- `保存`：保存当前模型与接口配置
- `测试`：测试当前 API 是否可用
- `手册`：打开这份中文说明

## 推荐工作方式
### 方式一：固定生产流水线
适合重复处理同一类商品图。
1. 准备原图目录
2. 执行 `workflow run upscale-ps`
3. 等待输出目录生成最终文件

### 方式二：按描述批量改背景
适合保留主体、批量换电商背景。
1. 准备原图目录
2. 写清楚主体商品是什么
3. 写清楚你想要的背景风格
4. 执行 `workflow run background-refresh`

## 背景风格预设
- `clean-ecommerce`：干净电商白底/浅色高级感
- `cream-home`：奶油家居风
- `minimal-bathroom`：极简浴室场景
- `outdoor-sunlit`：自然光户外感
- `luxury-dark`：深色高级感
- `custom`：完全按你的描述生成

## 调尺寸模式说明
- `contain-pad`：留比例补边，最终宽高固定，推荐商品图使用
- `cover-crop`：留比例裁切铺满，最终宽高固定
- `stretch`：强制拉伸到目标宽高
- `keep-ratio`：仅留比例缩放，宽高会按比例变化

## 常见问题
### 1. 测试 API 失败
先检查：
- Base URL 是否正确
- API Key 是否正确
- 模型名称是否可用

### 2. 转高清成功，但 PS 没出图
检查：
- 模板 PSD 路径是否正确
- Droplet 程序是否正确
- Photoshop 是否已安装

### 3. 调尺寸这一步是做什么的
这一步现在已经改成程序内原生处理：
- 直接批量改宽度
- 直接批量改高度
- 直接写入 DPI
- 不再依赖 Photoshop 批处理动作
