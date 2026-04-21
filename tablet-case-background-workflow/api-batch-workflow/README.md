# OpenAI API Batch Workflow

这套工作流是为了解决上一次方案的问题而重做的。

## 这次和上次的关键区别

上次的问题在于：

- 背景虽然换了，但平板壳主体也被一起改动了
- 这对商品图是不可接受的

这次改成了更稳的两段式流程：

1. 先用 `product_masks.json` 指定每张图里“必须保留的商品主体区域”
2. 调用 OpenAI 图片编辑 API 只生成背景
3. API 返回后，再把原图中的商品主体像素重新盖回去

这样即使模型在编辑时轻微改动了壳体，最终导出的成品仍然会使用原图主体像素。

## 文件说明

- `openai_batch_edit.py`
  API 批处理主脚本
- `product_masks.json`
  每张图的主体保留区域配置
- `prompt.txt`
  默认提示词
- `run_api_batch_edit.ps1`
  PowerShell 启动脚本
- `n8n-openai-batch-edit.json`
  可导入 n8n 的示例工作流
- `request-example.json`
  n8n Webhook 请求示例
- `requirements.txt`
  Python 依赖

## 先安装依赖

```powershell
python -m pip install -r "C:\Users\F1736\Documents\New project\tablet-case-background-workflow\api-batch-workflow\requirements.txt"
```

## 设置 API Key

PowerShell 示例：

```powershell
$env:OPENAI_API_KEY = "你的 OpenAI API Key"
```

## 直接命令行批量运行

```powershell
powershell -ExecutionPolicy Bypass -File "C:\Users\F1736\Documents\New project\tablet-case-background-workflow\api-batch-workflow\run_api_batch_edit.ps1"
```

运行后输出在：

- `C:\Users\F1736\Documents\New project\tablet-case-background-workflow\api-batch-workflow\output`

每次运行还会生成：

- `_runs/<时间戳>/run-manifest.json`
- `_runs/<时间戳>/mask-previews/`
- `_runs/<时间戳>/raw-api/`（只在保留中间文件时）

## 只做检查，不调用 API

```powershell
powershell -ExecutionPolicy Bypass -File "C:\Users\F1736\Documents\New project\tablet-case-background-workflow\api-batch-workflow\run_api_batch_edit.ps1" -DryRun
```

这个模式适合先看蒙版是否覆盖正确。

## n8n 用法

1. 导入 `n8n-openai-batch-edit.json`
2. 保证 n8n 运行环境里已经有：
   - `python`
   - `OPENAI_API_KEY`
   - 这个工作区路径可访问
3. 向 Webhook 发送 POST 请求

请求体可参考 `request-example.json`

最少需要传：

- `inputDir`
- `prompt`

你也可以额外传：

- `outputDir`
- `maskConfigPath`
- `model`
- `workers`
- `apiSize`
- `inputFidelity`
- `saveIntermediates`
- `dryRun`

## 适合你这批图的原因

- 你最在意的是“商品主体一点都不能变”
- 单纯靠提示词约束模型不够稳
- 先让 API 生成背景，再回贴原图主体，才是更适合商品图的批处理方案

## 后续怎么扩展

如果你要处理新的图片集，只需要：

1. 换 `input` 目录
2. 更新 `product_masks.json`
3. 改 `prompt.txt` 或 Webhook 里的 `prompt`
4. 重新运行

## 注意

- 这套流程的“主体不变”依赖 `product_masks.json` 的区域质量
- 如果某张图蒙版画得太大，会把旧背景边缘一起保留下来
- 如果某张图蒙版画得太小，可能会截掉商品边缘

所以这套流程最重要的是蒙版配置，而不是提示词本身
