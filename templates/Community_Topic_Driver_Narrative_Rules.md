# 社区话题驱动因素表单叙述规则

## 1. 规则目的

本规则用于指导社区舆情分析人员或自动化模型，将一周内分散的玩家讨论整理为表单中的话题级摘要。

目标是让每一条内容清晰回答：

1. 玩家在讨论什么；
2. 玩家对该话题持什么态度；
3. 该态度由什么具体因素形成；
4. 该讨论是否影响体验、期待、信任、参与或消费行为。

---

## 2. 表单结构锁定原则

本规则不得改变现有表单结构。

现有结构保持为：

| 层级 | 当前字段 / 内容 | 功能 |
|---|---|---|
| 区域层 | CHINA | 界定分析市场 |
| 数据层 | Weekly Conversations | 说明本周社区讨论规模 |
| 数据层 | Engagements | 说明本周互动热度 |
| 话题层 | TOPIC / DRIVER | 概括社区讨论对象 |
| 判断层 | Positive / Neutral / Negative | 标记话题情绪方向 |
| 解释层 | Narrative / Summary | 用1—2句话解释玩家反应及原因 |

不得新增、删除或调整表单中的现有字段。

允许补强的内容仅包括：

- 字段填写规则；
- 话题选择逻辑；
- 叙述顺序；
- 用词标准；
- 情绪判断标准；
- 数据质量检查；
- 自动化生成约束。

---

## 3. 表单整体写作逻辑

表单的核心叙述链路为：

> 话题对象 → 玩家反应 → 具体原因 → 比较或转折 → 结果影响

表单采用：

> 标签负责给出结论，正文负责解释结论。

因此正文不应机械重复 Positive、Neutral 或 Negative，而应说明为什么形成该情绪判断。

---

## 4. 话题排序规则

### 4.1 第一层：核心驱动因素

优先呈现本周最具代表性的三个话题：

1. 核心正向驱动；
2. 核心中性驱动；
3. 核心负向驱动。

核心驱动因素应综合考虑：

- 讨论规模；
- 互动热度；
- 业务影响；
- 玩家体验影响；
- 赛事或版本重要性；
- 是否具有跨周延续性。

### 4.2 第二层：补充驱动因素

核心驱动因素之后，补充其他具有分析价值的话题，包括但不限于：

- 游戏体验；
- 新模式；
- 英雄平衡；
- 赛事讨论；
- 联动内容；
- 皮肤评价；
- 商业化机制；
- 反作弊；
- BUG与技术问题；
- 高价值玩家消费意愿。

补充话题应按影响力排序，而不是按正负情绪简单分组。

### 4.3 话题数量规则

每周表单默认必须输出10个互不重复的话题：

1. 前3个为核心驱动因素，固定依次呈现核心正向、核心中性和核心负向驱动；
2. 后7个为补充驱动因素，按综合影响力从高到低排列；
3. 只有当本周经过聚类、去重和质量检查后，合格的独立话题不足10个时，才允许少于10个；
4. 话题不足时，应输出全部合格话题，并在生成记录中注明实际数量及不足原因；
5. 不得通过拆分同一话题、重复相近标题、降低代表性标准或加入噪声内容来凑满10个。

“合格的独立话题”必须同时满足：对象明确、具有真实文本依据、能够判断情绪方向、至少存在一个具体原因，并通过代表性与置信度检查。

---

## 5. TOPIC / DRIVER 标题规则

### 5.1 标题功能

标题只负责概括讨论对象，不负责表达情绪。

### 5.2 标题要求

标题应：

- 使用2—5个英文单词；
- 使用名词或名词短语；
- 与社区实际讨论对象一致；
- 避免同时包含两个无关话题；
- 避免使用情绪化形容词。

### 5.3 推荐写法

- EWC Performance
- Collaboration Content
- D+ Solo Queue
- Anti-Cheat
- Mythic Skippy Alternator
- Cyberpunk Weapon Skins
- Heirloom Shards

### 5.4 不推荐写法

- Bad Solo Queue Experience
- Disappointing Cyberpunk Skins
- Players Hate the New Skin
- Good Tournament Content

原因：标题不应预先替正文完成情绪判断。

---

## 6. Sentiment 情绪判断规则

表单继续使用现有三类标签：

- Positive
- Neutral
- Negative

不得改变字段或新增标签，但可以在内部判断时区分不同类型。

---

### 6.1 Positive

满足以下任一条件时可判断为 Positive：

- 玩家明确认可内容质量；
- 玩家主动分享、推荐或参与；
- 玩家对后续内容形成期待；
- 赛事或活动提升社区关注；
- 内容强化角色、品牌或版本认同；
- 讨论主要由积极体验驱动。

正文应重点解释：

- 玩家认可什么；
- 为什么认可；
- 是否带来期待、参与或传播。

---

### 6.2 Neutral

Neutral包含两种情况。

#### 类型A：正负评价相互抵消

玩家同时认可某些方面，也批评另一些方面，整体情绪没有明显倒向。

#### 类型B：讨论以分析、争议或问题定义为主

玩家主要讨论：

- 问题真正原因；
- 规则解释；
- 技术机制；
- 官方说法是否准确；
- 不同解决方案的有效性。

这类讨论可能存在情绪，但情绪不是主要内容。

正文必须明确该 Neutral 属于：

- 正负并存；
- 原因争议；
- 信息讨论；
- 结论尚未形成。

---

### 6.3 Negative

满足以下任一条件时可判断为 Negative：

- 玩家体验明显受损；
- 内容低于预期；
- 公平性或信任受影响；
- 玩家频繁与更优内容进行负面对比；
- 购买、参与或使用意愿下降；
- 问题引发持续投诉；
- 讨论主要由失望、挫败或不满驱动。

正文应说明：

- 玩家不满意什么；
- 具体原因是什么；
- 是否存在对比基准；
- 是否影响行为或认知。

---

## 7. 单个话题的标准叙述结构

每个话题正文使用1—2句话，按照以下顺序书写：

> 玩家范围 + 评价对象 + 直接反应 + 具体原因 + 比较或转折 + 结果影响

并非每一条都必须出现全部六项，但至少必须包含：

1. 评价对象；
2. 玩家反应；
3. 一个具体原因；
4. 一个结果或判断。

---

## 8. 通用叙述公式

### 8.1 英文公式

```text
[Player scope] + [reaction verb] + [topic] + [clear evaluation].
[Evidence / cause / comparison], resulting in [experience, perception, anticipation, participation or purchase impact].
```

### 8.2 中文理解

> 【玩家范围】认为【话题对象】呈现出【明确评价】。讨论主要集中在【具体原因或证据】，并进一步影响了玩家的【体验、认知、期待、参与或购买行为】。

---

## 9. 正向话题叙述规则

### 9.1 核心结构

> 具体亮点 → 玩家认可 → 后续期待或参与

### 9.2 英文模板

```text
Players found [topic] highly engaging, particularly because of [specific highlight], building stronger anticipation for [future content or event].
```

### 9.3 中文规则

> 玩家认为【内容】具有【正向特征】，其中【具体亮点】获得较多认可，进一步提升了玩家对【后续内容、赛事或模式】的期待。

### 9.4 推荐动词

- praised
- welcomed
- enjoyed
- highlighted
- appreciated
- found engaging
- responded positively to
- showed interest in

### 9.5 结果表达

- building anticipation
- driving interest
- increasing participation
- reinforcing positive perception
- encouraging sharing
- supporting viewership growth

---

## 10. 中性话题叙述规则

### 10.1 正负并存型

结构：

> 正向部分 → 转折 → 负向部分 → 综合判断

英文模板：

```text
Players welcomed [positive aspect], but concerns remained around [negative aspect]. [Compensating factor] partly offset the criticism, resulting in an overall balanced response.
```

中文规则：

> 玩家认可【正向元素】，但对【负向元素】存在不满；由于【补偿因素】在一定程度上缓解了问题，因此整体反应保持中性。

---

### 10.2 原因争议型

结构：

> 讨论对象 → 否定表面原因 → 指出玩家认定的核心原因

英文模板：

```text
Players discussed [issue], arguing that [factor A] was not the core problem. Instead, they identified [factor B] as the primary concern.
```

中文规则：

> 玩家围绕【问题】展开讨论，并认为【表面原因】并非核心问题；相比之下，【玩家认定的原因】才是更主要的风险。

---

### 10.3 信息讨论型

结构：

> 玩家关注某项信息 → 尚未形成明显价值判断 → 讨论集中于理解和验证

英文模板：

```text
Discussion focused on how [feature or policy] works, with players comparing different interpretations. No clear positive or negative consensus had formed.
```

中文规则：

> 讨论主要集中在【功能或政策】的具体机制与不同解释上，当前尚未形成明确的正向或负向共识。

---

## 11. 负向话题叙述规则

### 11.1 体验受损型

结构：

> 负面体验 → 具体原因 → 更广泛的负面认知

英文模板：

```text
Players described [feature or mode] as [negative experience]. Discussion centered on [specific causes], reinforcing the perception that [broader negative conclusion].
```

中文规则：

> 玩家将【功能或模式】形容为【负向体验】。讨论主要集中在【具体原因】，进一步强化了玩家对【更广泛问题】的负面认知。

---

### 11.2 期待落差型

结构：

> 实际表现不足 → 与玩家期待不符 → 与对标内容比较 → 失望放大

英文模板：

```text
Players felt [product] lacked [expected qualities]. Comparisons with [benchmark] further amplified disappointment.
```

中文规则：

> 玩家认为【内容】缺少预期中的【关键特征】。与【同类产品或历史内容】的比较进一步放大了期待落差。

---

### 11.3 横向比较型

结构：

> 内容表现平淡 → 不符合活动规格 → 与其他内容比较 → 负面评价加深

英文模板：

```text
Players viewed [content] as underwhelming for [content level or event scale] and frequently compared it unfavorably with [comparison objects].
```

中文规则：

> 玩家认为【内容】未达到【活动规模或产品定位】应有的表现，并在与【对标内容】的比较中形成了更明显的负面评价。

---

### 11.4 商业行为影响型

结构：

> 特定玩家群体 → 机制变化 → 购买或参与意愿下降 → 提出解决诉求

英文模板：

```text
[Specific player group] said [change] reduced their interest in [purchase or participation behavior]. They also called for [requested solution].
```

中文规则：

> 【特定玩家群体】表示，【机制变化】降低了其进行【购买或参与行为】的意愿，并进一步提出【解决方案或功能诉求】。

---

## 12. 玩家范围限定规则

正文必须明确观点来自什么范围的玩家。

### 12.1 推荐表达

- Players...
- Some players...
- Ranked players...
- Controller players...
- High-spending players...
- Players who own all Mythic items...
- Tournament viewers...
- Content creators...

### 12.2 判断原则

使用 Players 作为泛指主体时，必须满足：

- 该观点在样本中具有明显一致性；
- 不是单一帖子或少量评论；
- 没有明显的相反意见占据较大比例。

当观点来自有限群体时，必须增加范围限定。

### 12.3 禁止泛化

不得将以下情况直接写成 Players：

- 单个高互动帖子；
- 少量高消费玩家；
- 单个平台用户；
- 单一创作者粉丝；
- 特定段位玩家；
- 特定输入设备玩家。

---

## 13. 语言风格规则

### 13.1 使用社区作为叙述主体

推荐：

- Players felt...
- Players found...
- Players described...
- Players viewed...
- Players discussed...
- Players argued...
- Players said...
- Players called for...

作用是明确：

> 正文表达的是社区反馈，而不是分析师个人判断。

---

### 13.2 先给评价，再解释原因

推荐：

```text
Players described Diamond Ranked as a punishing experience. Discussion centered on uneven lobby quality and inconsistent teammate skill levels.
```

不推荐：

```text
Lobby quality was uneven, teammate skill levels varied, and matchmaking caused many problems. Players therefore disliked Diamond Ranked.
```

原因：表单需要快速传达情绪结论。

---

### 13.3 使用具体评价词

推荐：

- engaging
- entertaining
- underwhelming
- punishing
- unfair
- repetitive
- well-designed
- lacking personality
- disappointing
- visually inconsistent
- difficult to justify
- rewarding

避免：

- good
- bad
- nice
- terrible
- amazing
- awful

具体评价词应明确指出问题属于：

- 游戏体验；
- 审美；
- 公平性；
- 价值感；
- 内容深度；
- 角色塑造；
- 商业机制。

---

### 13.4 使用逻辑连接词

| 逻辑 | 推荐表达 |
|---|---|
| 转折 | but, although, while |
| 替代判断 | instead |
| 因果 | because of, driven by |
| 结果 | resulting in, leading to |
| 认知强化 | reinforcing |
| 情绪放大 | further amplified |
| 对比 | compared with, comparisons with |
| 诉求 | called for |
| 限定 | particularly, mainly, primarily |

正文不能只是观点堆叠，必须形成因果、转折或比较关系。

---

## 14. 篇幅规则

每个话题正文建议：

- 1—2句话；
- 20—40个英文单词；
- 只解释一个核心结论；
- 不重复标题；
- 不重复情绪标签；
- 不加入无关背景信息。

当话题过于复杂时，应优先保留：

1. 玩家核心反应；
2. 最主要原因；
3. 最重要影响。

---

## 15. 原始评论处理规则

表单采用分析师转述，不直接复制原始评论。

不得直接使用：

- 玩家完整原话；
- 网络流行语；
- 侮辱性表达；
- 情绪化引用；
- 单条帖子细节；
- 缺乏代表性的极端说法。

应将原始反馈整理为：

> 共同评价 + 主要原因 + 结果影响

---

## 16. 话题归纳规则

### 16.1 一个话题只表达一个核心对象

不得将以下内容混写在同一条中：

- 反作弊与皮肤；
- 赛事结果与匹配机制；
- 英雄平衡与商城价格；
- BUG与联动审美。

### 16.2 相同问题合并

当多个评论围绕同一个核心问题时，应合并为一个话题。

例如：

- 队友段位差异；
- 大师玩家匹配钻石队友；
- 对局质量波动；

可归纳为：

> D+ Solo Queue

并在正文中解释具体原因。

### 16.3 表面话题与深层问题区分

标题使用社区直接讨论对象，正文说明其背后的深层原因。

例如：

- 标题：Anti-Cheat
- 正文：玩家认为RC Filter不是核心问题，输入适配器才是主要风险。

---

## 17. 比较逻辑规则

当玩家评价建立在比较基础上时，正文必须写明对标对象。

可使用的比较对象包括：

- 上一周；
- 上一个版本；
- 同类型皮肤；
- 其他大型联动；
- 官方宣传预期；
- 历史赛事；
- 正常对局体验；
- 同价格产品。

比较的作用不是增加描述，而是解释：

> 为什么玩家认为当前内容好或差。

---

## 18. 行为影响规则

当讨论已经影响玩家行为时，应优先写出。

可观察的行为包括：

- 期待增加；
- 分享增加；
- 观看增加；
- 参与增加；
- 使用意愿下降；
- 购买意愿下降；
- 放弃排位；
- 请求退款或补偿；
- 转向其他模式；
- 呼吁官方说明；
- 建议增加功能。

不得在没有证据时推断：

- 销售一定下降；
- 大量玩家流失；
- 品牌信任完全崩塌；
- 活跃用户必然减少。

可使用谨慎表达：

- reduced interest in
- may weaken purchase intent
- appears to have discouraged participation
- contributed to lower enthusiasm

---

## 19. 补强的内部判断规则

以下规则用于提高叙述准确性，但不得改变表单结构。

### 19.1 讨论规模检查

在确定话题是否进入表单前，应检查：

- 帖子数量；
- 评论数量；
- 互动量；
- 是否由单一高热帖子主导；
- 是否跨多个社区出现。

### 19.2 代表性检查

判断内容是否代表社区趋势，而非个别意见。

建议内部区分：

- 高代表性：多个来源、观点一致；
- 中代表性：讨论量有限但方向清晰；
- 低代表性：单一来源或样本过少。

低代表性内容如必须写入，应使用：

- Some players...
- A smaller group of players...
- Discussion among [specific segment]...

### 19.3 置信度检查

自动化或人工填写时，应内部检查：

- 话题归类是否明确；
- 情绪方向是否稳定；
- 是否存在大量相反意见；
- 原因是否来自真实文本；
- 结论是否超出样本。

置信度不直接新增到表单字段中，但应影响措辞强度。

高置信度：

- Players viewed...
- Discussion centered on...

中置信度：

- Many players appeared to...
- Discussion generally focused on...

低置信度：

- Some players suggested...
- A smaller set of comments raised...

### 19.4 跨周变化检查

若话题延续自上周，应在正文中说明新变化，而不是重复旧结论。

可关注：

- 讨论升温；
- 讨论降温；
- 由期待转为实际评价；
- 由体验问题转为原因归因；
- 官方澄清后观点变化；
- 问题是否已解决。

跨周信息应融入现有正文，不新增字段。

---

## 20. 数据层补强规则

### 20.1 Weekly Conversations

该数据用于说明：

- 本周总体讨论规模；
- 样本基础；
- 社区是否出现明显升温或降温。

不得仅凭总讨论量判断情绪好坏。

### 20.2 Engagements

该数据用于说明：

- 内容传播强度；
- 玩家互动意愿；
- 话题是否形成高参与讨论。

高互动不等于正向情绪。

负向争议同样可能带来高互动。

### 20.3 数据与正文关系

正文不得机械引用总量数据，而应利用数据判断：

- 哪些话题值得进入表单；
- 哪些话题只是少量噪声；
- 哪些观点具有更高代表性。

---

## 21. 自动化生成规则

当模型自动填写该表单时，必须执行以下步骤。

### 第一步：话题聚类

将相似讨论归为同一 Topic / Driver。

### 第二步：识别玩家群体

判断讨论来自：

- 全体玩家；
- 段位玩家；
- 控制器玩家；
- 高消费玩家；
- 赛事观众；
- 内容创作者；
- 特定角色玩家。

### 第三步：判断情绪方向

根据主要观点判断 Positive、Neutral 或 Negative。

### 第四步：提取形成原因

每条至少提取一个具体原因。

### 第五步：识别比较对象

判断玩家是否与：

- 历史内容；
- 同类产品；
- 其他联动；
- 官方承诺；
- 玩家预期；

进行了比较。

### 第六步：识别结果影响

判断是否影响：

- 体验；
- 认知；
- 期待；
- 信任；
- 参与；
- 观看；
- 购买。

### 第七步：压缩成1—2句话

删除：

- 重复信息；
- 原始评论；
- 无关背景；
- 未经支持的推断。

### 第八步：执行数量与排序检查

1. 对聚类后的独立话题进行去重；
2. 选出核心正向、核心中性和核心负向驱动各1个；
3. 从其余合格话题中按影响力选出7个补充驱动因素；
4. 默认输出总计10个话题；
5. 若合格话题不足10个，则仅输出实际合格数量，不得补写、拆分或重复话题。

---

## 22. 强制质检清单

### 22.1 结构检查

- [ ] 保留现有表单结构；
- [ ] 未新增或删除字段；
- [ ] 每个话题均包含标题、情绪标签和正文；
- [ ] 核心话题位于表格前部。
- [ ] 默认共输出10个互不重复的话题，其中3个核心驱动、7个补充驱动；
- [ ] 少于10个时，已确认合格独立话题确实不足，并记录实际数量及原因；
- [ ] 未通过拆分、重复、降级代表性标准或加入噪声内容凑数。

### 22.2 标题检查

- [ ] 标题为2—5个英文单词；
- [ ] 标题仅描述对象；
- [ ] 标题不包含情绪结论；
- [ ] 一个标题只对应一个核心话题。

### 22.3 情绪检查

- [ ] Positive有明确认可依据；
- [ ] Neutral说明了正负平衡或讨论性质；
- [ ] Negative说明了具体问题；
- [ ] 情绪标签与正文一致。

### 22.4 叙述检查

- [ ] 开头明确玩家反应；
- [ ] 至少包含一个具体原因；
- [ ] 存在比较时写明比较对象；
- [ ] 存在行为影响时写明影响；
- [ ] 未重复标题或标签；
- [ ] 每条不超过两句话。

### 22.5 代表性检查

- [ ] 少量观点使用范围限定；
- [ ] 特定玩家群体未被泛化；
- [ ] 单一高热帖子未被误写为社区共识；
- [ ] 结论强度与样本置信度一致。

### 22.6 语言检查

- [ ] 使用具体评价词；
- [ ] 使用因果、转折或比较逻辑；
- [ ] 未使用情绪化或绝对化表达；
- [ ] 未直接复制玩家原话；
- [ ] 未出现分析师个人判断口吻。

---

## 23. 禁止使用的叙述方式

不得：

- 只写话题名称，不解释原因；
- 只重复 Positive、Neutral 或 Negative；
- 将两个无关问题放入同一话题；
- 将少量玩家意见写成全体共识；
- 使用 everyone、all players 等绝对表达；
- 使用 good、bad 等模糊评价代替具体判断；
- 在无证据时断言销售、流失或收入变化；
- 用高互动量直接证明正向或负向情绪；
- 直接复制原始评论；
- 改变表单现有字段和排列结构。

---

## 24. 最终填写标准

一条合格的表单内容应同时满足：

> 看标题知道玩家在讨论什么；  
> 看标签知道总体情绪方向；  
> 看正文知道玩家为什么这样评价；  
> 看结尾知道该讨论可能影响什么。

最终叙述链路应为：

> 话题规模判断 → 玩家群体识别 → 情绪结论 → 具体原因 → 比较基准 → 行为影响

其中：

- 话题规模与置信度用于内部判断；
- 不新增到表单结构中；
- 最终仍以现有 Topic / Driver、Sentiment 和 Narrative 形式输出。
- 每周默认输出10个话题，即3个核心驱动因素和7个补充驱动因素；仅在合格独立话题不足时允许减少数量。

---

## 25. 标准输出示例

### Positive

**Topic / Driver:** Creator Wildcard Preview  
**Sentiment:** Positive

```text
Players found the Creator Wildcard preview highly entertaining, particularly because of the mode’s unpredictable team interactions, building stronger anticipation for its official release.
```

### Neutral

**Topic / Driver:** Collaboration Content  
**Sentiment:** Neutral

```text
Players welcomed the collaboration concept and several visual details, but concerns remained around the Legend’s facial model. Stronger weapon and hand-model design partly offset the criticism.
```

### Negative

**Topic / Driver:** D+ Solo Queue  
**Sentiment:** Negative

```text
Players described Diamond Ranked as a punishing experience. Discussion centered on uneven lobby quality and inconsistent teammate skill levels, reinforcing the perception that Ranked felt exhausting rather than competitive.
```

### Negative — 特定玩家群体

**Topic / Driver:** Heirloom Shards  
**Sentiment:** Negative

```text
Some high-spending players said the updated guarantee mechanism reduced their interest in purchasing additional packs. They also called for a more flexible shard exchange option.
```
