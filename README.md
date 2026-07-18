# APEX 游戏舆情分析：冻结模型、历史看板与可复现流程

本仓库在不覆盖原始数据、原始模型和原始 HTML 的前提下，提供冻结的探索性 BERTopic 模型、B站 W25—W28 历史看板、小黑盒固定规则模拟数据，以及一键审计与看板生成流程。当前看板的情感与风险采用纯模型输出；BERTopic、SnowNLP、热议度、共识度和风险均不作为未经独立基准验证的正式统计真值。

## 目录

```text
config/                  规则配置
data/raw/                原始 CSV（脚本只读，永不覆盖）
data/example/            小规模演示数据
data/processed/          清洗后的新文件
outputs/quality_reports/ 质量检查报告
models/                  冻结 BERTopic 模型、注册表、映射和版本清单
work/public-opinion/     保留登录/语言/平台切换的生成看板副本
outputs/                 可交付 JSON、HTML、审计清单和运行状态
scripts/                 清洗、质检和一键运行脚本
tests/                   基础规则测试
```

原始字段固定为：

`text_id,publish_time,platform,text,likes,comments,shares,url,source_type`

建议将真实数据复制为 `data/raw/apex_raw_YYYYMMDD.csv`。不要修改或复用清洗输出作为原始文件。

## 当前冻结模型与口径

- 模型：`models/bertopic_apex_exploratory_v1/bertopic_model.pkl`，真实 `BERTopic` 对象，当前状态为 exploratory。
- embedding：模型内保存的项目内 `sklearn TF-IDF + TruncatedSVD (50 components)`；未使用 sentence-transformers 预训练权重。
- 主题注册表和人工确认名称不由看板脚本改写；延后的拆分候选仍保持 deferred。
- 评论分配置信度使用模型保存的 `probabilities_`（HDBSCAN membership probability）。离群文本强制记为 0.0；由于训练时 `calculate_probabilities=False`，不能解释为完整多主题概率分布。
- B站主题声量、评论数、视频数、作者数、关键词和代表文本来自真实模型输出；热议度和共识度为可复算观测指数，风险由模型负面率、趋势和共识度公式派生。2%—5%偏差目标需独立基准，当前不宣称已达标。
- 当前看板情感只使用 SnowNLP 全量模型输出，不读取人工标签、不使用人工校准或人工训练的情感模型；`qualified_for_formal_auxiliary_reporting=false`。
- 小黑盒使用固定 `simulation_seed=2717` 和稳定哈希派生倍率；综合视图明确为真实＋模拟，不属于正式统计。

## 自然周规则

- 一周从周一 00:00:00 开始，到周日 23:59:59 结束。
- 使用 `publish_time` 的本地日历日期划分；默认时区为 `Asia/Shanghai`。
- 例如 `2026-07-06` 到 `2026-07-12` 的标签为 `2026年7.6—7.12`；下一周为 `2026年7.13—7.19`。
- 跨月或跨年时保留完整边界，例如 `2026年12.28—2027年1.3`。
- 无法解析的发布时间不会被猜测，其周字段留空，并在缺失值报告中体现。

## 使用

仅依赖 Python 3 标准库。

```bash
python3 scripts/run_pipeline.py --input data/example/apex_small_sample.csv
```

也可以分步运行：

```bash
python3 scripts/clean_data.py --input data/raw/apex_raw_template.csv
python3 scripts/quality_check.py --input data/processed/<清洗结果.csv>
```

## 一键运行冻结流程

环境检查、自然周审计、BERTopic环境与模型审计、主题分配与置信度清单、W25—W28 看板构建和页面数据一致性检查可一次运行：

```bash
python3 scripts/run_full_workflow.py
```

新电脑首次使用可先运行：

```bash
python3 scripts/init_project.py
python3 scripts/check_environment.py
python3 scripts/build_dashboard.py
```

只更新看板交付文件时运行 `python3 scripts/build_dashboard.py`；需要从新一周输入开始时运行 `python3 scripts/run_full_workflow.py --input data/raw/<new_week.csv>`。

主题详情中的代表性 B 站视频链接由受控的逐评论分配结果生成；如本地存在该审核输出，可运行 `python3 scripts/build_representative_video_links.py` 更新链接映射，再运行 `python3 scripts/build_dashboard.py`。公开仓库只发布脱敏后的链接映射，不发布逐评论审核文件。

如果有新一周原始 CSV，可先清洗、自然周校验并用冻结模型生成候选预测。候选不会自动并入冻结语料，也不会覆盖原始文件：

```bash
python3 scripts/run_full_workflow.py --input data/raw/apex_raw_YYYYMMDD.csv
```

运行产物包括：

- `outputs/bertopic_comment_topic_assignments.csv`：逐评论主题、canonical 映射、真实分配置信度；
- `outputs/bertopic_topic_confidence_distribution.csv`：每个主题的均值、中位数、P10/P90 和低置信度比例；
- `outputs/bertopic_low_confidence_comments.csv`、`bertopic_outlier_comments.csv`、`bertopic_possible_misclassifications.csv`：人工复核清单；
- `outputs/dashboard_data_apex_W25_W28.json`、`outputs/game_sentiment_dashboard_apex_W25_W28_mixed_test.html`：四周看板交付副本；
- `outputs/formal_sentiment_assignments.csv`、`outputs/formal_sentiment_review_queue.csv`、`outputs/formal_sentiment_validation.json`：历史人工审计留档，不被当前纯模型看板读取；
- `outputs/formal_auxiliary_metrics.json`、`reports/formal_auxiliary_metric_calibration.md`：历史口径留档，不被当前纯模型看板读取；
- 若要验证2%—5%偏差，准备独立/双人复核基准后运行 `python3 scripts/evaluate_metric_bias.py --benchmark data/example/metric_benchmark.csv`；没有基准时脚本明确返回 blocked，不会伪造达标。
- `outputs/week_boundary_audit.json`、`reports/week_boundary_audit_2026_W25_W29.md`：W25—W29自然周边界审计；W29截至2026-07-18仍未完成。
- `logs/workflow_<run_id>.log`、`outputs/workflow_last_run.json`：运行日志、版本和错误状态。

评论审核清单含原始评论文本与作者字段，仅保留在本地受控目录，不随公开仓库发布；公开仓库发布的是脱敏主题/看板结果、模型清单和可复现脚本。

W25 是基准周，数据中不会生成不存在的 W24 环比；W28 保留为当前测试/最新周。历史周切换、主题详情、关键词、代表文本、主题演化、平台切换、JSON 导入、登录和中英文界面均保留在生成 HTML 中。

## 新电脑部署

1. 安装 Python 3.12（或与锁定文件兼容的版本），复制仓库到任意目录。
2. 创建虚拟环境并安装依赖（建议使用项目固定名称）：

   ```bash
   python3 -m venv .venv-bertopic
   . .venv-bertopic/bin/activate
   pip install -r requirements-bertopic.lock.txt
   ```

3. 运行 `python3 scripts/check_environment.py`，确认模型、注册表和依赖可加载。
4. 运行 `python3 scripts/run_full_workflow.py` 生成看板和审计产物。

所有运行时路径均相对仓库根目录解析；`config/project_paths.example.json` 可作为路径配置模板。不要上传账号、Token、Cookie、个人绝对路径或未经脱敏的原始 B站 JSONL/CSV。

## GitHub 发布边界

仓库可发布内容是脚本、配置示例、锁定依赖、冻结模型清单、脱敏后的主题/看板结果和文档。原始采集文件、Cookie、浏览器缓存、个人路径和敏感日志应留在本地，并由 `.gitignore` 拦截。当前版本可在本机完成一键验证；跨电脑运行依赖可公开获取的冻结模型文件或由使用者按项目授权提供，不能在没有模型文件的全新环境中凭空重建正式模型。

详细审计结论见 `reports/bertopic_and_platform_logic_audit.md`、`reports/dashboard_W25_W28_mixed_data_report.md`；小黑盒及综合结果仍不得写入正式统计或正式报告，B站情感与风险需按模型估计状态解释。

默认每次生成带 UTC 时间戳的新目录或文件；若目标已存在会自动增加序号，绝不覆盖原始文件或既有结果。清洗脚本会在结束时核对原始文件的 SHA-256，确认它没有变化。

## 清洗规则

- 保留九个原始字段，并新增 `publish_datetime`、`week_start`、`week_end`、`week_label`、`clean_text`、`text_length`、`is_short`、`duplicate_group_size` 和 `is_duplicate`。
- 文本统一换行和空白，去除首尾空格；原始 `text` 字段仍保留。
- 互动量转为非负整数；空值保留为空，非法值记录在清洗日志中。
- 重复判断基于规范化后的文本（去空白、转小写）；同一文本从第二条起标记 `is_duplicate=1`。
- 默认少于 10 个有效字符视为短文本，阈值见 `config/quality_rules.json`。
- 高频词使用轻量级中英文分词；中文无空格句子采用 2 字词片段，适合前期质检，不替代正式 NLP 分词。

## 质量报告

每次检查生成一个独立目录，包含：

- `summary.csv`：总文本量、重复率、短文本率等核心指标
- `weekly_text_volume.csv`：每周文本量
- `platform_distribution.csv`：总体及分周平台分布
- `duplicate_rate.csv`：总体及分周重复率
- `short_text_rate.csv`：总体及分周短文本率
- `missing_values.csv`：各字段缺失数量和比例
- `high_frequency_words.csv`：总体及分周高频词/词片段
- `random_samples.csv`：固定随机种子的总体及分周样本
- `quality_report.md`：便于阅读的汇总
- `run_metadata.json`：输入文件、校验值和规则快照

## B站公开数据试采集

试采集模块位于 `crawler/bilibili_apex_collector.py`，目标周自动取“当前日期之前最近一个完整的周一至周日”。

```bash
# 查看目标周和配置，不访问网页
python3 crawler/bilibili_apex_collector.py --dry-run

# 使用本地保存的少量页面验证解析器
python3 crawler/bilibili_apex_collector.py --parse-html tests/fixtures/bilibili_video_sample.html \
  --url https://www.bilibili.com/video/BV1Ab411c7Xy --keyword Apex英雄

# 实时试采集。若 Python Playwright 不存在，会自动使用项目附带的
# Node Playwright 后端和系统 Chrome，无需另行安装 Python 包。
python3 crawler/bilibili_apex_collector.py
```

实时模式只读取公开搜索和公开视频页面，不使用 B站官方 API。检测到登录、验证码、安全验证或访问频率限制时会立刻停止。原始 JSONL 采用追加写入，`checkpoint_YYYY_WXX.json` 用于断点续采，统一 CSV 若已存在会自动增加序号。

如果在受限沙箱中出现 Chrome 启动后立即退出，请在普通 macOS 终端进入项目目录后运行上述命令。该限制来自运行命令的沙箱权限，不代表 Chrome 或 Playwright 未安装；采集器会自动定位 Codex 附带的 Node 运行时和 `/Applications/Google Chrome.app`。
