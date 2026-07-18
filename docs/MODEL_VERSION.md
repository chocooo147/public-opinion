# 模型版本说明

- `apex_bilibili_bertopic_exploratory_v1`
- 真实对象：`BERTopic 0.16.4`
- 训练语料：1052 条探索性 B站语料；最终保留 canonical 主题分配 646 条。
- embedding：项目内 sklearn TF-IDF + TruncatedSVD，50 维；不依赖 sentence-transformers。
- `calculate_probabilities=False`：可用的是 HDBSCAN 单值 membership probability，不能解释成完整主题概率分布。
- canonical 注册表：`apex_topic_registry_exploratory_v1`，13 个主题；人工确认的主题名称和结构不自动改写。
- 资格：可用于模型辅助看板、主题发现、跨周演化和审核排序；当前BERTopic为exploratory，SnowNLP情感与派生风险未通过独立正式统计基准，不可单独用于正式舆情、情感或风险报告。

当前情感路径：`SnowNLP_model_only`。看板不读取人工标签、人工校准或人工训练的情感模型。风险路径：`model_only_derived`，由模型负面率、正向趋势和共识度派生；负面率达到60%时触发高风险下限，避免高负面但下降主题被隐藏。

模型 SHA-256、语料 SHA-256、依赖版本和相对路径见 `models/bertopic_apex_exploratory_v1/model_manifest.json` 与 `environment_manifest_portable.json`。
