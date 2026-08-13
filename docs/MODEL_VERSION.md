# 模型版本说明

- `apex_bilibili_bertopic_exploratory_v1`
- 真实对象：`BERTopic 0.16.4`
- 训练语料：1052 条探索性 B站语料；最终保留 canonical 主题分配 646 条。
- embedding：项目内 sklearn TF-IDF + TruncatedSVD，50 维；不依赖 sentence-transformers。
- `calculate_probabilities=False`：可用的是 HDBSCAN 单值 membership probability，不能解释成完整主题概率分布。
- canonical 注册表：`apex_topic_registry_exploratory_v1`，13 个主题；人工确认的主题名称和结构不自动改写。
- 资格：可用于模型辅助看板、主题发现、跨周演化和审核排序；当前BERTopic为exploratory，SnowNLP情感与派生风险未通过独立正式统计基准，不可单独用于正式舆情、情感或风险报告。

当前 B站情感路径使用 `domain_sentiment_apex_v1` 作为辅助主模型，并保留
SnowNLP 作为基线；低置信度结果进入复核。小黑盒不跨域套用 B站领域模型。
两者均不是正式统计真值。风险仍是派生指标，不是 frozen BERTopic 的输出。

Data Topic 口径由 `config/canonical_business_rules.json` 绑定：每条清洗后的真实
文本由冻结 BERTopic 执行只读 `transform`，映射到唯一 canonical topic；未映射项
和 outlier 不进入网站 Data Topics。Data Topic 是网站细粒度数据结构，不等同于
Weekly Report Driver；Driver 由 Data Topic、真实 evidence 和 editorial synthesis
形成，二者不要求标题、数量或粒度一致。

Heat 不是 frozen model 的组成部分。W32 起唯一正式规则为
`config/heat_v1.json` 中的 `apex-heat-v1.0`：讨论强度 35%、讨论广度 30%、
参与深度 20%、触达 10%、升温 5%。Production、Validator 与 Dashboard 均由
`config/canonical_business_rules.json` 的 SHA-256 绑定读取；缺少真实分项时阻断，
不得使用 proxy。W25–W31 保持 Legacy Heat，不回算、不改写。

模型 SHA-256、语料 SHA-256、依赖版本和相对路径见
`models/bertopic_apex_exploratory_v1/model_manifest.json` 与
`environment_manifest_portable.json`。正式 production policy 另外固定 registry 与
mapping 的预期 SHA-256，并在 prepare、validator 和 W33 preflight 独立核对。
