# 常见错误处理

## `ModuleNotFoundError: bertopic`

确认已激活虚拟环境并执行 `pip install -r requirements-bertopic.lock.txt`，然后运行 `python3 scripts/check_environment.py`。

## pickle 加载失败或找不到 `run_bertopic_exploratory_baseline`

必须从仓库根目录运行脚本；一键流程会自动以仓库根目录作为工作目录。不要移动模型文件或改写其相对路径。

## 浏览器页面只显示旧数据

打开 `outputs/game_sentiment_dashboard_apex_W25_W28_mixed_test.html`，或重新运行 `python3 scripts/build_public_opinion_mixed_test.py`。浏览器 localStorage 只接受同一 `data_version` 的历史数据。

## 新周候选大量为离群

这是冻结模型的审核信号，不应自动改主题或重训模型。查看 `outputs/bertopic_low_confidence_comments.csv`、`bertopic_outlier_comments.csv` 和 `bertopic_possible_misclassifications.csv`，人工确认后再形成下一版本语料。

## 看到绝对路径或敏感文件

不要将本机生成的旧日志、原始 JSONL/CSV、浏览器缓存、Cookie 或带个人路径的历史审计文件提交。使用相对路径配置模板，并检查 `.gitignore` 与 `git status --ignored`。
