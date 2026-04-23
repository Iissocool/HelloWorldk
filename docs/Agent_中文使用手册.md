# Agent 中文使用手册

## 这个 Agent 是做什么的
NeonPilot 的 Agent 是一个工作流调度终端，用来快速执行固定流程命令，而不是原始的 Docker 或 Hermes 终端。

## 你可以做什么
1. 查看帮助：`workflow help`
2. 查看当前模型配置：`workflow model show`
3. 修改模型与接口：
   `workflow model set --model <模型> --provider <提供方> --base-url <地址> --api-key <密钥>`
4. 运行转高清 -> 调尺寸 -> PS 套图：
   `workflow run upscale-ps --input-dir "W:\images\in" --upscale-dir "W:\images\upscaled" --resize-dir "W:\images\resized" --ps-output-dir "W:\images\final" --template "C:\Users\F1736\Desktop\模板\昔音浴帘.psd" --droplet "C:\Users\F1736\Desktop\自动套图 图标.exe" --close-photoshop`
5. 单独运行 Photoshop 批处理调尺寸：
   `ps-resize --input-dir "W:\images\in" --output-dir "W:\images\resized" --photoshop "C:\Program Files\Adobe\Adobe Photoshop (Beta)" --action-set "默认动作" --action-name "高透三折叠套图-透明图"`
6. 运行保主体换背景：
   `workflow run background-refresh --input-dir "W:\images\source" --output-dir "W:\images\out" --subject "浴帘" --background "北欧奶油风浴室电商场景，柔和自然光，干净高级" --style clean-ecommerce`

## 工具栏怎么用
- Docker / Gateway / 对话：显示当前可用状态
- provider / model / Base URL / API Key：快速修改模型配置
- 保存：保存当前模型与接口配置
- 测试：测试当前 API 是否可用
- 手册：打开这份中文说明

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
- 批处理动作组和动作名是否正确

### 3. 调尺寸这一步是做什么的
这一步调用 Photoshop 的“文件 -> 自动 -> 批处理”，按你设置的动作组和动作名批量修改图片尺寸，然后再把调好尺寸的图交给模板套图。

当前默认值：
- 动作组：`默认动作`
- 动作名：`高透三折叠套图-透明图`

Photoshop 路径可以直接填写目录：

```text
C:\Program Files\Adobe\Adobe Photoshop (Beta)
```
