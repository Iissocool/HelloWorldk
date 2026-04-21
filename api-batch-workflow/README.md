# OpenAI API Batch Workflow

这套流程用于批量替换产品图背景，同时尽量保护商品主体不被改坏。

## 这套流程做什么

1. 读取 `product_masks.json` 里定义的商品主体保护区域
2. 调用 OpenAI 图像编辑接口生成新背景
3. 将原图主体重新合成回结果图，降低商品主体被模型改动的风险

## 目录说明

- `openai_batch_edit.py`: API 批处理主脚本
- `product_masks.json`: 每张图的主体保护区域配置
- `prompt.txt`: 默认提示词
- `run_api_batch_edit.ps1`: PowerShell 启动脚本
- `n8n-openai-batch-edit.json`: n8n 示例流程
- `request-example.json`: Webhook 请求示例
- `requirements.txt`: 这个子流程单独的 Python 依赖

## 安装依赖

在仓库根目录执行：

```powershell
python -m pip install -r .\api-batch-workflow\requirements.txt
```

## 设置 API Key

```powershell
$env:OPENAI_API_KEY = "你的 OpenAI API Key"
```

## 直接运行

在仓库根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\api-batch-workflow\run_api_batch_edit.ps1
```

默认输入输出路径：

- 输入目录：`.\input`
- 输出目录：`.\api-batch-workflow\output`

每次运行还会生成：

- `_runs/<timestamp>/run-manifest.json`
- `_runs/<timestamp>/mask-previews/`
- `_runs/<timestamp>/raw-api/`（当保留中间文件时）

## 只做预检查

```powershell
powershell -ExecutionPolicy Bypass -File .\api-batch-workflow\run_api_batch_edit.ps1 -DryRun
```

这个模式适合先检查蒙版覆盖是否正确。

## 自定义输入输出目录

```powershell
powershell -ExecutionPolicy Bypass -File .\api-batch-workflow\run_api_batch_edit.ps1 `
  -InputDir .\input `
  -OutputDir .\api-batch-workflow\output `
  -MaskConfig .\api-batch-workflow\product_masks.json `
  -PromptFile .\api-batch-workflow\prompt.txt
```

## n8n 用法

1. 导入 `n8n-openai-batch-edit.json`
2. 在请求体里传入 `repoRoot` 或显式传 `scriptPath`
3. 最少提供 `inputDir` 和 `prompt`

可选字段：

- `outputDir`
- `maskConfigPath`
- `model`
- `workers`
- `apiSize`
- `inputFidelity`
- `saveIntermediates`
- `dryRun`

## 注意

- 主体保护效果依赖 `product_masks.json` 的质量
- 蒙版太大可能把旧背景边缘一起保留
- 蒙版太小可能裁掉商品边缘
- 这套流程的关键不是提示词，而是保护区域配置
