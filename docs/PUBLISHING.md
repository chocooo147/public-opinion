# GitHub 发布清单

发布前在仓库根目录运行：

```bash
python3 scripts/check_release.py
```

`outputs/release_check.json` 应显示 `publish_ready=true`。提交时保留脚本、配置示例、锁定依赖、冻结模型版本清单、脱敏看板结果和报告；不要提交 `data/raw`、`data/processed`、浏览器缓存、Cookie、Token、人工审核原始包或带个人绝对路径的旧日志。

当前发布仓库为 `chocooo147/public-opinion`，默认分支为 `main`。发布前先确认本地工作树只包含本轮文件，再运行 `scripts/check_release.py`、完整工作流和测试；随后提交并推送到远程仓库。GitHub Pages 入口为仓库根目录的 `index.html`，看板数据与HTML为脱敏交付副本。

推送后不能只以 commit 成功作为发布完成依据，还要验证：

- Pages 页面已出现本轮界面文案和持续主题专属抽屉；
- 综合、B站、小黑盒三种视图的抽屉内容与平台筛选一致；
- `apex` 只读账号不显示报告下载和 JSON 导入入口；
- 浏览器控制台无错误，近5周趋势折线可辨识波动；
- 页面中的 Word、JSON 与叙述规则下载路径可访问；仓库内的 Word 与 Excel 二进制文件可正常解压或打开；
- 本地、GitHub 仓库与 Pages 提供的关键 HTML 文件校验值一致。

发布边界：不提交 `data/raw`、个人路径、Cookie、Token、浏览器缓存、含作者/评论原文的审核清单、人工审核原始包或未脱敏日志。冻结模型只有在许可证和仓库大小允许时才上传；否则新电脑需通过配置提供模型路径，不能声称可在无模型文件时重建模型。
