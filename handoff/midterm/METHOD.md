# METHOD：实际方法、训练设置与工作进展

论文：**《基于语义表征与思维链推理协同的智能体恶意指令检测方法》**。实验来源提交：`614b4d40102d78d606a0f37bc8b678d7eec67d4e`；文档整理不是新实验。先读[START_HERE.md](START_HERE.md)。本文件描述实际完成内容，当前主线是普通分类编码器与固定教师协议的受控协同，不能将早期联合训练设计直接移植为当前实现。

## 1. 检测对象、数据与标签

ToolSafe固定上游提交`46358fa424a927a895c6c8322f99032c4eb5155e`，路径`TS-Bench/agentdojo-traj/`。使用原生instruction、history、current_action、env_info；score=0映射safe、1映射unsafe，0.5排除而非abstain。源slack/workspace保留956条，新增banking/travel保留264条；这些文件本次筛选实际没有0.5排除项。官方完整训练划分不是本研究的划分；按任务/轨迹分组做本地探索性划分。

current_action保留Thought、Action与Action Input的完整当前步骤。只给此前history，不输入金标签、攻击目标或当前执行后的Observation。instruction是上游用户任务字段；history是展平字符串，其中自称SYSTEM/管理员/用户的文本不因此变成可信授权。env_info提供工具语义，候选步骤自己的Thought是待评估行为，不是权限证明。本系统未取得所有历史消息的运行时可信来源标记，不能描述成已验证完整来源认证。

官方输入含完整步骤，但score究竟如何划定当前动作与受污染历史/Thought的边界未完全确认。合法候选操作可能伴随已执行攻击的回忆；即使教师按某种安全语义作出合理解释，主评测仍用官方标签。abstain是不可判断/技术失败状态，不是第三种官方恶意标签。依据：[LABEL_INPUT_AUDIT.md](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round2-native-collaboration/LABEL_INPUT_AUDIT.md)；[标签和分组代码（main）](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round2-native-collaboration/code/prepare.py)。

源数据按规范化任务文本、同域轨迹ID、相同四字段输入取连通分组；先处理重复/冲突，再用seed=20260924打乱任务组，按70%/15%/其余分组。实际train657（32组，safe450/unsafe207）、dev158（7组，112/46）、test141（7组，90/51）；任务/组/相同输入跨split重叠记录均为0。数据早已暴露，绝非盲测。LLM旧对子集按标签近似自然比例、组轮转预选dev32/test96；test96不能与test141当同一分母。新域264按固定上游合格记录选取，12组，无训练重叠，不据新域调参。依据：[data_manifest.json](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round2-native-collaboration/data_manifest.json)；[selection.json](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round2-native-collaboration/selection.json)；[data_manifest.json](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round3-transfer-ablation/data_manifest.json)。

## 2. 输入组织及512-token问题

实际打包函数：[train_server.py::pack](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round2-native-collaboration/code/train_server.py)。

1. 小模型必留：完整用户请求、完整current step（标为untrusted candidate）、当前工具对应语义块。工具块从env_info按工具名匹配，找不到匹配时回退全部环境文本。
2. tokenizer计算必留文本；超过510个非特殊token时输出`mandatory_fields_overflow`，不把截断后的残片伪装为完整输入。512上限包含特殊token。
3. 历史按800字符分块；优先尝试最近两块（最近者先），再按请求与当前步骤的词项重叠数降序、相同时偏新排序；去重后尝试整块加入。某块放不下就跳过，不切成零碎片段。词项由正则`[a-z0-9_@.-]{3,}`提取；不是学习式检索。
4. 记录历史总块/可见块、必留字段溢出、当前步骤是否完整可见等。字段优先不等于全部历史都可见；源train/dev/test溢出104/27/23，未入编码器训练/有效验证，但计入完整评估分母。
5. `E_head`是诊断对照：请求→历史→当前步骤→环境串联后取前510 tokens，只运行seed42；为与E_field同一评估子集，仍对相同mandatory-overflow样本暂缓。它不是另一套三种子主模型。

教师长输入采用同一原文的宿主span ID：U0原任务、C0完整候选步骤、T工具语义、H历史块。固定字段先放，历史及其他工具块再按共同预算加入。预算估计为`max(1.25×缓存mBERT token数, UTF8字节数/3)+900 ≤ 7500`，并非服务商精确token计数；放不下必留字段则LLM_MANDATORY_OVERFLOW。长教师可见信息一般多于编码器；禁止将长输入收益全归为模型推理能力。

固定64条同信息对照中，短臂只接受E0 span中的**精确E_field field_text**；直接/关系提示保持相同，不追加历史或标签。64条来自banking/travel各32、固定任务轮转，全部可放入小模型窗口；是受限子集而非对全部溢出场景的验证。依据：[information_selection.json](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round3-transfer-ablation/information_selection.json)；[短臂输入构造](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round3-transfer-ablation/code/llm_run.py)；[关系短臂构造](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round4-safety-completion/code/setup.py)。

## 3. 小模型、简单基线与真实训练

准确缓存基座为 **`microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank`**：已经过提示压缩任务微调的多语BERT骨干。第一轮来源配置[training/config.json](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-p0-b234/training/config.json)，第二轮复用同一缓存，[config.json](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round2-native-collaboration/config.json)明确记录LLMLingua-2骨干。不是标准RoBERTa，也不是未微调的通用mBERT，不能把原压缩模型的token分类任务说成已经具备安全检测能力。

第二轮`Model`用AutoModel加载该骨干（不加载pooler，eager attention），取最后一层首token表示`h[0]`，新增线性标量头`z=w·h[0]+b`，`p=sigmoid(z)`。全骨干参数参与训练；损失是二元`BCEWithLogitsLoss`，unsafe目标1。**当前三种子检查点没有加入成对、扰动一致性或证据损失，也没有蒸馏。**代码依据：[Model / train_one / predict](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round2-native-collaboration/code/train_server.py)。

AdamW，lr=2e-5，weight decay=0.01，batch=16，gradient norm clip=1，8轮；553条非溢出训练、131条非溢出dev。seed42/43/44，每轮用seed+epoch打乱；dev上固定分类阈值0.5的covered macro-F1最大者保存，同分留早轮。三个主模型都选第5轮，每个280优化步。完整设置与日志：[config.json](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round2-native-collaboration/config.json)；各模型`training/<model>/status.json`与`curves.jsonl`；[训练CSV](tables/training.csv)。

|模型|种子|训练条数|有效dev|轮数/选中轮|优化步|dev covered macro-F1|另存dev分类阈值|
|---|---|---|---|---|---|---|---|
|E_field_seed42|42|553|131|8/5|280|0.946579|0.15|
|E_field_seed43|43|553|131|8/5|280|0.957742|0.8|
|E_field_seed44|44|553|131|8/5|280|0.946579|0.5|
|E_head_seed42|42|553|131|8/1|280|0.723780|0.6|

学习链先在训练集中按safe/unsafe各16抽32条，lr=5e-5；最多60轮，训练正确率≥95%且loss≤0.2才通过。第5轮32/32、loss从0.69136降到0.19006。**仅是拟合检查，不是泛化证据。**[training/debug_fit32/status.json](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round2-native-collaboration/training/debug_fit32/status.json)。

简单基线：R0复用确定性任务/候选动作规则，实际输入包含任务、解析后工具/参数及工具语义，不完整使用步骤Thought/历史；未知工具/解析失败可暂缓。规则并非学习式安全分类器。R1是TF-IDF（词1–2gram，max_features30000，sublinear_tf=True）+LogisticRegression（C=1，liblinear，max_iter2000，三个random_state），采用相同field_text/溢出规则；向量器只拟合非溢出train。majority按训练多数类恒safe。R1未保存完整向量器/分类器，所以新域未运行，不能填新域成绩。[simple](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round2-native-collaboration/code/train_server.py)；[code/legacy_rule.py](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round2-native-collaboration/code/legacy_rule.py)。

第一轮历史B2/B3/B4在另一组构造数据上做同数据84条训练、24条探索评估，三种子、8轮、最终轮检查点；B3加margin=1的成对约束和无关扰动一致性，B4再加部分AI审核silver证据损失。42条接受证据仅覆盖u1正例/o_noise负例，不足以监督完整关系。该轮负结果保留，但不能称当前主模型在用这些损失或已建立完整证据链蒸馏。[training/config.json](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-p0-b234/training/config.json)；[ablation.csv](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-p0-b234/ablation.csv)。

## 4. 分数、分类阈值与送审门控

为避免历史名称混淆：第一轮B2只用分类损失，B3/B4在其上增加约束；这些名称不能与第二轮普通E_field检查点互换。

以固定源dev中131条非溢出样本的`d_i=abs(p_i−0.5)`排序，用线性插值分位数`q_(seed,b)=quantile(d,b)`，b只取0.1/0.25/0.5。缓存恢复重新保存dev预测，沿用同一口径。**这是dev分位数预算规则，不是温度缩放、Platt校准、共形风险保证或学习路由器。**

```text
if mandatory_fields_overflow:
    small_decision = abstain
    send_to_teacher = True
else:
    p = sigmoid(linear(CLS(encoder(field_text))))
    small_decision = unsafe if p >= 0.5 else safe
    send_to_teacher = abs(p - 0.5) <= q[seed, budget]
final = teacher_effective_decision if send_to_teacher else small_decision
safe -> ALLOW; unsafe -> BLOCK; abstain -> ASK (do not dispatch)
```

名义b是非溢出源dev的送审分位数，实际调用率还含必留输入溢出以及域分布变化，绝不是固定10%/25%/50%。分类阈值始终0.5用于本协同主线。训练另在0.05至0.95网格保存`threshold_dev`（主三种子0.15/0.8/0.5），仅作为`dev_threshold`基线参照；不将其混进当前门控。源dev选点又是后续策略层的约束筛选，不等于重新训练/调阈值。

|seed|q(0.1)|q(0.25)|q(0.5)|
|---|---|---|---|
|42|0.49731374881230295|0.4980308711528778|0.49955508578568697|
|43|0.4993842840194702|0.4994451403617859|0.4998165482538752|
|44|0.4994882552418858|0.499650239944458|0.49979880926548503|

公式定位：[quantile](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round2-native-collaboration/code/common.py)，[train_one阈值保存](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round2-native-collaboration/code/train_server.py)，[compute的route构造](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round3-transfer-ablation/code/compare.py)，[真实入口main](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round4-safety-completion/code/integration.py)。阈值见[config.json](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-scheme-selection-closeout/config.json)。同调用量随机策略保留全部溢出样本，剩余可放入窗口样本按域随机选同样数量，原20个随机种子0–19；每个模型种子内部求均值/标准差，不挑最好随机抽样。

## 5. 教师模型与两种固定协议

请求名`deepseek-v4-flash`，实际返回名`deepseek-flash`；已记录补跑/第三/第四轮system_fingerprint为`aeb56401ca74e127821c4f9126dcb669`。别名及相同指纹不证明服务端权重永久不变，未获不可变模型快照ID。这里仅调用服务，**没有对教师微调**。

temperature=0，stream=False，thinking={type:disabled}。旧第二轮及补跑max_tokens=800，新域/全dev/短输入/第四轮接口为2048，分表保留。输入相同的直接/关系两臂不给官方标签、攻击成功字段或小模型分数。每个样本×臂的成功响应跨种子/预算复用；技术错误与正常abstain分开，不把判断错误响应重跑成正确。

直接协议输出decision、简短理由、span引用、缺失事实；关系协议额外逐一核对operation/object/destination/authorization，记录applicable、required、status及引用。必要关系mismatch→unsafe；无mismatch但必要unknown→abstain；否则保留整体decision。引用必须非空且全为输入已有span ID，schema或引用无效→技术暂缓。引用存在只验证可追溯，不证明语义正确；此实现没有完整原文引语一致性或授权真实性证明。

实际冻结提示：[800-token原提示全文](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round2-native-collaboration/prompts_frozen.json)；[2048配置与相同系统提示全文](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round3-transfer-ablation/request_config.json)。解析器：[interpret（含最终有效决定覆盖）](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round2-native-collaboration/code/llm_compare.py)；请求/停止机制：[send / prediction](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round4-safety-completion/code/requests_run.py)。主指标使用最终有效prediction，不盲用教师raw_decision。HTTP402停后续请求，传输/429/部分5xx最多额外一次；不因普通abstain或解析输出错误自动重问。

论文题目中的“语义表征”对应编码器表示与分类；“思维链推理”在本实现中对应**短、可核对的结构化关系分析**，不读取隐藏私有CoT；“协同”对应固定门控与执行前决策连接。两协议共用同一大模型，输入长度另有64条控制。不能把提示设计本身当已验证原创，不能把长上下文和路由效果写成CoT独立增益。

## 6. 执行前接口与实现状态

复用既有`GuardedToolsExecutor`，在每个候选工具派发前调用检测策略：ALLOW按原参数调用、BLOCK/ASK不调用；策略异常fail-closed。12条按seed42原0.1的4条路径各预选3条，不使用标签选例；真实小模型前向9次、溢出3条，两臂共12次必要教师调用。下游`Recorder.run_function`仅记录工具及参数并返回recorded，不产生业务写入。代码：[choose / Recorder / main](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round4-safety-completion/code/integration.py)；[GuardedToolsExecutor.query](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round4-safety-completion/code/reused_gate_e2_adapter.py)；[冻结检查点前向](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round4-safety-completion/code/live_score.py)。

这验证了小模型→门控→必要教师→执行前拦截接口的连接，不是自主Agent完成多步业务的攻击实验。已有adapter内部审计字段是历史实现，不是本次新加的哈希框架。主入口未重写。24/24接口遵从、22/24检测正确，banking_0002在两臂错误allow到记录替身，不能以接口正确掩盖检测失败。

|模块/原任务书目标|当前状态|可核实完成与未完成边界|
|---|---|---|
|原生数据/标签审计与分组|已实现并验证|956源域+264新域，本地探索划分；非官方完整基准，非人工gold|
|字段优先窗口/普通编码器/规则/TF-IDF|已实现并验证|拟合检查和源test运行；历史仍可能缺失，TF-IDF迁移未运行|
|固定教师直接/关系协议与协同门控|已实现并验证运行；效果受限|配对、同门控及随机/溢出/全量对照完成；稳定关系优势、跨域安全目标未获支持|
|成对语义/扰动/证据联合目标|第一轮已实现但优势未验证|有三种子负结果；当前普通主模型不含这些损失，合格关系证据监督未进行|
|执行前接口|已实现并验证连接|12例记录式替身，不能称完整Agent闭环|
|独立人工标注/关系证据gold|未完成|AI核对仅辅助，保留待人审与歧义|
|真实闭环、RL、GUI、完整ShieldAgent|未运行/超出本阶段|没有攻击成功率、业务落地或完整复现结论|

原目标映射来自仓库[初始实施任务书](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/Codex_毕设实施与实验任务书.md)§2–5，以及[ROUND2_PLAN.md](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round2-native-collaboration/ROUND2_PLAN.md)与后续各轮PLAN。**未取得正式开题报告，不能称这张表已覆盖开题全部承诺。**初始任务书曾提出校准双阈值、证据监督和后续AgentDojo闭环，本表按实际代码澄清未完成部分。

上述代码都是公开仓库路径，可在线核查。训练权重和完整原生轨迹未打包；不承诺脱离原环境直接重训复现，但方法、配置、日志、原始预测和数学计算均可追溯。没有可核实的个人分工、导师指导记录、企业部署、论文录用或专利记录，写作时不得补造。运行记录标注日期保留原2026-09-24，不能反推整个课题历时或填入学校时间线。

文献处理：本次仅整理已使用的代码/数据来源（ToolSafe、LLMLingua-2缓存模型、既有AgentDojo接口）。未核实完整论文题名/作者/卷页的历史链接不生成正式参考文献；需参考文献表时使用用户开题报告中可核实的条目或由后续会话单独核查。他人论文分数不计入本人实验。
