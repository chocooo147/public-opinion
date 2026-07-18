# 数据字段说明

## 逐评论主题分配

`outputs/bertopic_comment_topic_assignments.csv` 的关键字段：

- `text_id`：评论稳定标识；`week_id`：自然周标签。
- `model_topic_id`：冻结 BERTopic 的原始主题编号；`canonical_topic_id` / `canonical_topic_name`：人工确认注册表映射。
- `assignment_confidence`：模型 `probabilities_` 中的 HDBSCAN membership probability；离群为 0.0，不是人工分数。
- `is_outlier`：原始模型是否分到 -1；`low_confidence_flag`：低于 0.50；`possible_wrong_classification`：仅为 embedding 近邻差异审核候选。

## 看板主题与平台

- `platform_metrics.B站`：B站真实主题声量、独立视频、独立作者和评论计数；`data_type=real`、`simulated=false`。
- `platform_metrics.小黑盒`：公开搜索可见帖子样本；`data_type=real_sample`、`metrics_source=heybox_public_search_visible_sample`、`sample_limited=true`。`count` 为可见帖子数，`comment_count` 为帖子卡片显示评论数之和。
- `combined_metrics`：B站评论与小黑盒可见帖子单位不同；`metrics_source=mixed_real_and_real_sample_incomparable_units`，仅用于界面探索，不得解释为跨平台总量。
- `heat_score`、`consensus_score`、`risk_score`：当前为测试估算；B站情感来自未通过正式校验的 SnowNLP 输出。
