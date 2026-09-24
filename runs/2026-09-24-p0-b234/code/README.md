# 本轮算法代码快照

保留规则、数据构造、联合损失及训练代码。pilot/analyze依赖原仓库，训练入口依赖PyTorch/Transformers及缓存编码器；本目录不是重写后的主入口。

公开包数值核查无需原仓库或模型：运行 `python scripts/verify_run.py runs/2026-09-24-p0-b234`。第三方native输入仅提供来源索引，未重新分发；自建诊断输入见diagnostic_data.jsonl。
