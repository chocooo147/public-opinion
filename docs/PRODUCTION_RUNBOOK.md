# APEX 受保护生产站运行手册

## 目标

APEX 生产站采用“公网可达、服务端认证后可见”的模式，不再依赖静态
GitHub Pages 中的前端账号逻辑保护数据。完整站点、看板 JSON 和周报下载均由
Nginx 在 HTTPS 层执行账号验证；浏览器端脚本不保存有效凭据。

## 每周一交付时序（Asia/Shanghai）

| 截点 | 生产动作 | 成功门槛 |
|---|---|---|
| 00:15 | 启动上一完整自然周流水线 | 目标周固定为前一周周一至周日 |
| 采集阶段 | 采集 B站有限可见样本与小黑盒公开搜索可见帖子卡片 | 两个平台均完成；登录、验证码、限流或安全验证触发时安全停止 |
| 模型与看板阶段 | 使用冻结 BERTopic、B站领域情感辅助模型、SnowNLP 基线和既有计算规则生成周数据 | 不重训、不改写原始数据；模型哈希、看板数据、来源和样本边界一致 |
| 周报阶段 | 生成稳定双语 Excel 周报和文字摘要 | 工作簿结构、驱动因素去重、叙述规则、禁用表述和证据引用全部通过 |
| 08:45 | 原子发布并完成线上验收 | HTTPS、账号验证、五周窗口、周切换、下载、哈希和只读权限均通过 |
| 09:00 | ChatGPT 网页结果与 Gmail 邮件 | 只读取最终状态；成功或明确失败，不把半成品标为成功 |

## 三个必需业务里程碑

1. `platform_collection`：B站与小黑盒均完成上一自然周采集。
2. `model_and_dashboard`：冻结模型处理、综合计算与看板更新完成。
3. `weekly_report`：规定格式的双语周报和叙述内容通过契约校验。

网站发布属于上述三项完成后的交付门槛。`protected_site_publication` 未通过时，
09:00 必须报告失败，上一版网站保持不变。

## 叙述质量门槛

- 每条驱动因素必须对应可追溯的当周文本证据。
- 默认输出 10 个独立驱动因素；证据不足时允许 8 或 9 个并明确说明，禁止拆分
  或重复话题凑数。
- B站评论数与小黑盒可见帖子数不得相加表述为平台总量。
- 领域情感模型、SnowNLP 基线、风险和冻结 BERTopic 主题均标为模型推断，不表述为人工验证
  事实或正式统计真值。
- B站有效一级评论少于 100、独立视频少于 10、独立作者少于 50、单视频占比
  高于 30%、离群率高于 40%、低归属强度率高于 55%，或作者字段缺失时，
  只能生成低样本内部产物并停止发布；优先目标为 150—200 条有效评论。
- 周报必须使用项目内 `skills/apex-weekly-report-writing/SKILL.md` 和影响力排序
  修订规则；生产构建需要内容负责人给出的 `approved_for_release` 叙述包。
- 禁止把有限样本表述为平台全量、总体趋势或代表性抽样。
- Excel 契约、公式错误扫描、叙述禁用词扫描和视觉渲染任一失败时停止发布。

无人值守系统不能保证每周一定产生一份新的合格报告；它能保证未通过上述门槛的
报告不会替换生产版本。

## 访问与发布

- 生产入口只使用 `https://`。
- 80 端口只用于证书校验和跳转，不提供看板内容。
- Nginx `auth_basic` 或后续独立身份层在服务端验证账号。
- 初始可提供共享 `user` 账号；正式同事使用时推荐改为每人独立账号，以便撤销、
  轮换和审计。
- `/status/weekly.json` 是唯一无需账号的最小状态端点，只包含周次、成功/失败、
  里程碑和产物哈希，不包含报告正文、账号、服务器路径或原始数据。
- 新版本先写入独立 release 目录，通过验收后再原子切换 `current`；失败时保留
  上一版。
- 受保护生产站完成验收后，下线 GitHub Pages 上的完整数据和下载入口。

## 已知困难

- B站或小黑盒登录态可能失效，也可能出现验证码、限流或页面结构变化。
- 冻结模型只能在既有主题注册表范围内解释数据；新主题需要人工审核，不能自动
  改写注册表。
- 小样本可能不足以支持 10 个独立驱动因素。
- 中国内地服务器绑定域名对外提供网站前需要完成 ICP 备案。
- 域名、备案与 SSL 尚未完成前，生产 HTTPS 入口不能正式启用。

## 周次通用化实现

生产编排不再写死 W30。每周一运行时从 `Asia/Shanghai` 当前时间推导上一完整
自然周，并将 `YYYY_WNN`、周一日期和周日日期传给全部阶段。跨年周次使用 ISO
week-year，例如 2027-01-04 的目标周为 `2026_W53`。

七个真实执行阶段为：

1. `collect_bilibili`
2. `collect_heybox`
3. `prepare_release`
4. `build_report`
5. `validate_release`
6. `publish_site`
7. `verify_live`

采集器原始 CSV 由 `run_platform_collector.py` 归一化为统一 JSON 契约。若采集器
尚未提供主题与情感字段，`prepare_weekly_release.py` 只读加载冻结 BERTopic
模型、人工确认的 topic mapping、B站领域情感辅助模型与 SnowNLP 基线进行推断；
小黑盒不跨域套用 B站领域模型。不训练模型、不修改注册表。BERTopic 的
`assignment_confidence` 仅表示 HDBSCAN 聚类归属强度，不是校准后的分类正确概率。

发布验证要求最近五个完整周、无未来周泄漏、两平台计量边界、Excel 契约、报告
预览哈希、全部下载路径和 release manifest 同时通过。`current` 仅在验证成功后
通过符号链接原子切换。

### 隔离模拟联调

模拟模式只生成带 `simulation_only=true` 和 `simulated_fixture` 的确定性输入，
不能被生产模式接受。它执行与生产相同的七阶段编排，但发布到单独临时目录：

```bash
/opt/apex/venv-analysis/bin/python \
  /opt/apex/ops/production/weekly_pipeline.py \
  --root /opt/apex \
  --state-dir /tmp/apex-weekly-sim/state \
  --public-status /tmp/apex-weekly-sim/status/weekly.json \
  --release-root /tmp/apex-weekly-sim/release \
  --site-root /tmp/apex-weekly-sim/site \
  --mode simulate \
  --now 2026-08-03T00:15:00+08:00
```

## 域名与个人备案

2026-07-30 在腾讯云域名购买页核对时，下列 `.com` 与 `.cn` 均显示可立即加购；
域名状态在实际付款前仍可能变化：

- `nessieiscoming.com` / `nessieiscoming.cn`
- `howdoesnessiesay.com` / `howdoesnessiesay.cn`

建议优先使用较短的 `nessieiscoming.com`。备案主体为个人时，腾讯云账号实名、
域名所有者实名和备案主体必须为同一人。域名可以使用英文，但备案表中的“网站
服务名称”不能是纯英文、不能直接使用域名，也不能使用公司或组织性质名称；应
另拟三个字以上、能说明个人数据观察用途的中文名称，并以所在地管局最终要求
为准。
