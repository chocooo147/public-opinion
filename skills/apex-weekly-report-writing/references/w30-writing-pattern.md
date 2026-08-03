# W30 writing pattern

## Driver count

The standard weekly report contains 10 distinct, evidence-qualified drivers. Use 8 or 9 only when 10 cannot be supported without splitting, duplication, or noise, and record the evidence-based reduction audit required by `SKILL.md`. Never produce fewer than 8 drivers.

## Editorial model

The W30 report converts bounded evidence into an editorial finding with this sequence:

`bounded audience or source → evaluated object → reaction → concrete reason → observed impact or confidence limit`

The narrative is usually two sentences. It is specific enough to be useful, but its subject and certainty remain bounded by the evidence.

## Approved examples from W30

### Positive

**PLQ赛制科普内容**

> 新赛事观众认可对PLQ、ALGS与ENC的科普，尤其是资格赛缩写和名额结构的解释。更清晰的背景信息帮助观众理解赛事，并提升了对后续直播的关注。

Why it works: identifies the audience, the content evaluated, the specific useful details, and the effect on understanding and future interest.

### Neutral because evidence is incomplete

**30赛季前瞻**

> 一篇公开搜索可见帖子围绕传闻中的传奇调整、R-301皮肤与8月更新获得较高互动。由于未采集评论正文，且内容尚未经证实，目前无法形成可靠的正向或负向共识。

Why it works: reports the observed interaction, names the discussed details, and turns missing comment bodies into a confidence limit instead of generic methodology boilerplate.

### Negative

**排位服务器稳定性**

> 部分排位玩家认为本周服务器体验缺乏稳定性。对局中断、匹配队列停滞、严重延迟与异常数据更新界面打断了正常游玩，并促使玩家询问其他服务器是否更稳定。

Why it works: combines multiple concrete symptoms into one experience-level finding and explains the practical effect.

### Neutral because reactions conflict

**排位单排体验**

> 排位玩家对单排体验的评价差异明显：有人认为钻石及以上对局具有较强回报感，也有人因大厅实力不均、语言障碍和队友过于保守而受挫。两类经历相互抵消，尚未形成明确共识。

Why it works: preserves both sides of the evidence and uses the disagreement to justify the neutral label.

### Negative with a bounded trust implication

**反作弊信任**

> 部分观众将快速扫描全圈、瞬间提升护甲与隐蔽的瞄准辅助视为可疑操作。强势表现是否真实合规难以判断，削弱了对局公平性的信任，也增加了对更严格审查的诉求。

Why it works: distinguishes perceived suspicious signals from verified cheating and states the effect on trust rather than claiming an incident rate.

## Rejected W31 pattern

> 在本周有限样本中，2条B站评论与0篇小黑盒公开搜索可见帖子被归入“英雄与武器强度”。代表性观察涉及“重回超长tkk时代吧”。该正向方向来自模型推断，仅用于探索，不代表平台总体情绪，也不是经正式验证的统计事实。

Why it fails:

- It describes pipeline assignment instead of the community conversation.
- It repeats sample counts and disclaimers that belong in the overview or methodology.
- It substitutes one raw quotation for synthesis.
- It never explains what players liked, why it mattered, or what changed in their expectations.
- It accepts the model sentiment without reconciling contradictory evidence.

## Evidence-led rewrite of the rejected W31 example

**战斗节奏与战利品复杂度 / Combat Pace and Loot Complexity**

Chinese:

> 部分玩家期待更长的击杀时间能够重新拉开武器操作与交战决策的差异；与此同时，也有玩家担心新增战利品词条会增加舔包负担并打断连续作战节奏。讨论同时体现了对战斗深度的期待与对流程复杂化的顾虑，尚未形成单一正向共识。

English:

> Some players welcomed a longer time-to-kill as a way to restore more room for weapon control and fight decisions, while others worried that additional loot modifiers would make post-fight looting slower and more cumbersome. The discussion combined interest in deeper combat with concern over added friction, so it did not support a single positive verdict.

Editorial decision: use Neutral or Mixed, not Positive. Keep the underlying canonical topic ID in evidence metadata or comments, not in the visible headline.

## Drafting checklist

- Does the first sentence contain a bounded actor and a clear reaction?
- Does the narrative name at least two concrete details when multiple records are available?
- Does the final clause state an effect or a justified confidence limit?
- Does the sentiment follow the written evidence rather than the model majority?
- Is the text a paraphrased synthesis rather than a copied comment?
- Are counts, provenance labels, URLs, model status, and repeated disclaimers outside the driver body?
- Can a reader understand the weekly issue without seeing the raw evidence?
