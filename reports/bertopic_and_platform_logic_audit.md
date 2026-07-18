# BERTopic 与平台分析逻辑检查报告

## 结论

- 主模型检查：通过加载检查。模型对象为 `bertopic._bertopic.BERTopic`，pickle 可加载，主模型与 `models/bertopic_apex_exploratory_v1/model_manifest.json` 的哈希一致。
- 依赖检查：BERTopic、UMAP、HDBSCAN、scikit-learn、numpy、pandas、jieba 可导入；sentence-transformers 未安装且未被模型使用。embedding 来源为模型内保存的项目内 sklearn TF-IDF + TruncatedSVD。
- 分配检查：语料 1052 条，保留 canonical 主题 646 条，模型离群 245 条，删除主题 161 条，未映射 0 条。
- 置信度来源：`BERTopic model.probabilities_ (HDBSCAN membership probability)`；计算规则：`training-set membership probability; topic=-1 is forced to 0.0; no synthetic normalization`。低置信度阈值为 0.50，复核提示阈值为 0.70。
- 主题名称、人工保留结构和 canonical_topic_id 未在本审计中改写；exp_a 中删除的模型主题仍保留在映射表中，不计入正式主题汇总。

## 已通过项目

- 真实 BERTopic 模型、模型 embedding、主题表示、主题向量和 HDBSCAN membership probability 均可加载。
- `model_topic_id → canonical_topic_id` 映射对保留主题是一对一；主题注册表与映射表集合已核对。
- 主题合并检查：当前 canonical 注册表没有执行中的 merge 操作；exp_c 合并候选仅作为人工候选保存，未自动改变主题结构。已接受的拆分/操作记录仍为 deferred。
- 周度主题结果可由 corpus、模型 topics_ 和映射表重算，W25 使用自然周起点，不生成 W24 环比。
- B站核心计数（评论/主题声量、独立视频、独立作者）与真实模型输出分层保存；小黑盒/综合有独立 provenance 标识。

## 存在的问题

- 当前模型的 `calculate_probabilities=False`，不能声称有完整的多主题概率分布；现有置信度只能解释为 HDBSCAN membership probability。
- 共有 305 条评论低于 0.50，其中 245 条为离群文本；这些记录不应直接用于正式主题结论。
- 19 条评论出现‘分配主题与 embedding 最近主题明显不一致’的自动复核提示；该规则只是审核候选，不是自动改判。
- 看板情感当前仅使用SnowNLP全量模型输出；本审计不读取人工标签、不使用人工校准或人工训练的情感模型。
- 热议度和共识度已改为真实B站计数的可复算观测指数；风险由模型负面率、趋势和共识度公式派生。2%—5%偏差目标没有独立基准，当前不宣称达标。

## 已修复/新增

- 已生成逐评论分配与真实置信度结果、主题置信度分布、低置信度清单、离群清单和可能错分清单。
- 新增平台 provenance 检查约束：B站真实核心字段不由小黑盒模拟回填；小黑盒标为 simulated；综合标为 mixed_real_and_simulated。
- 新增模型全量输出与平台 provenance 检查；离群、删除主题和低置信度评论不进入主主题结论。

## 仍需人工确认

- 低置信度清单：`outputs/bertopic_low_confidence_comments.csv`（305 条）。
- 离群审核清单：`outputs/bertopic_outlier_comments.csv`（245 条）。
- 可能错分清单：`outputs/bertopic_possible_misclassifications.csv`（19 条）。
- 已接受但延后的主题拆分候选仍保持 deferred，不自动改变人工确认主题结构。

## 当前可使用范围

- 整体可信度：**模型辅助模式中等，可追溯使用；不等于独立正式统计真值**。可用于辅助报告、跨周趋势验证、主题发现和审核排序；纯模型情感与风险当前不具备独立正式统计资格。
- 报告可追溯字段限于真实B站主题分配、声量、视频覆盖、作者覆盖、关键词、代表文本及观测指数；小黑盒和综合视图仅用于界面/计算测试。

## 产物

- `outputs/bertopic_comment_topic_assignments.csv`：逐评论主题分配与置信度。
- `outputs/bertopic_topic_confidence_distribution.csv`：按 canonical 主题的置信度分布。
- `outputs/bertopic_low_confidence_comments.csv`、`bertopic_outlier_comments.csv`、`bertopic_possible_misclassifications.csv`：审核清单。
- `outputs/bertopic_mapping_integrity_issues.json`：仅记录未映射或结构性不一致；人工标记为 delete 的模型主题属于预期排除，不计为映射错误。

生成时间：2026-07-18T04:43:06.483331+00:00；模型 SHA-256：`40f0c48d7dee49f2c3f804b3a5a896828c671503708a30f84be5812fc7e463a5`。
