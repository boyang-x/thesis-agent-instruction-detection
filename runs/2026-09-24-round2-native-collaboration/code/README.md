本轮算法快照；复用原仓库 provider 与缓存编码器，未重写 main.py。公开重算使用根目录 scripts/verify_run.py，不需模型。live_router 的 infrastructure.local.json 不公开；其中仅含已有SSH目标和运行命令。

执行后修复：llm_compare 增加 HTTP402 全局熔断（原配对批次未有该保护，185次真实失败完整保留）。不重跑或替换原批次。
