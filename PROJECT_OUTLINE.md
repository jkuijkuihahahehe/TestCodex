# 项目开发大纲

以下是我们的开发心法大纲：
0 我们是严谨的开发者 具有系统视角 具备一定的审美 超强的逻辑和模块化抽象能力；
1 我们的目标是共同开发一款好玩的游戏 这款游戏名称叫《武侠自走 Build》
3 我们要开发的是一个MVP版本 意味着流程功能要完整 但是不需要太复杂
4 代码结构和风格要极简 模块化 可阅读性要强 不使用奇技淫巧 方便维护人员阅读

以下是我们的玩法大纲：
0. MVP 目标定义（不可扩张）
* 1v1 自动战斗
* 单侠客 vs 单侠客
* 无剧情 / 无世界地图
* 核心体验：内功引擎 × 外功模块 → 自动连锁 → 爽感结算

1. 核心循环（必须先跑通）
开始一局 → 选择 1 个初始内功 → 进入关卡→ 自动战斗→ 胜利 → 3 选 1 外功 → 继续下一关 → 失败 → 结算 / 重开

2. 核心数据结构（Codex 友好）
2.1 侠客（Actor）
Actor { hp: number, maxHp: number, qi: number, maxQi: number, innerSkill: InnerSkill, outerSkills: OuterSkill[], statuses: Status[], }

2.2 内功（InnerSkill = Engine）
特性：
* 每局只能 1 个
* 只改“规则”，不直接打伤害
InnerSkill { id: string, name: string, description: string, hooks: { onTurnStart?: Effect[], onQiOverflow?: Effect[], onHit?: Effect[], onDefense?: Effect[], } } 

MVP 内功清单（5 个）
1. 九阳心法
    * 回合开始：+2 气
    * 气溢出 → 1:1 转化为护体真气
2. 吸星大法
    * 命中：偷取 1 气
    * 自身气低于 30% 时，偷取翻倍
3. 太极心法
    * 防御后：下一次攻击必定反击
4. 血战心诀
    * 生命低于 50%：外功触发率 +50%
5. 枯禅定
    * 连续 2 回合不攻击 → 下次攻击伤害 ×2

3. 外功系统（OuterSkill = Module）
3.1 外功设计原则
* 单一触发条件
* 单一行为
* 可叠加
* 可被其他外功消费

3.2 外功数据结构
OuterSkill { id: string, name: string, trigger: Trigger, effect: Effect, }

3.3 MVP 外功模块池（20 个）
触发型（Trigger）
* onAttack
* onHit
* onCrit
* onDefense
* onTurnStart
效果型（Effect 示例）
* addStatus
* dealDamage
* gainQi
* consumeStatus
* repeatLastAction

示例外功（可直接照抄）
1. 震伤
    * onHit → 给目标 +1 震伤
2. 连击
    * onHit 若目标有震伤 → 再攻击一次（50% 伤害）
3. 化劲
    * onHit 消耗全部震伤 → 每层转为 3 点真实伤害
4. 回气
    * onTurnStart → +1 气
5. 反震
    * onDefense → 给攻击者 1 震伤
（剩余 15 个同构扩展即可）

4. 状态系统（Status）
Status { id: string, stacks: number, } 
MVP 状态列表
* 震伤（可叠加）
* 护体真气
* 易伤
* 狂躁（触发率提升）

5. 自动战斗流程（重点）
每回合固定流程（不可改）
1. 回合开始 → 内功 onTurnStart → 外功 onTurnStart 2. 行动阶段 → 判断是否攻击 / 防御（简单概率） → 执行基础攻击 3. 命中阶段 → onHit 外功链 → 状态叠加 / 消耗 4. 回合结束 → 状态衰减
⚠️ 所有外功按“加入顺序”结算（保证可预期）

6. Roguelike 构筑逻辑
外功获取
* 每场胜利：随机 3 选 1 外功
* 同名外功：
    * 不合并
    * 多个独立触发（指数来源）
7. 敌人设计（极简）
Enemy { hp, attack, behaviorProfile } 
* 只区分：
    * 高攻
    * 高防
    * 高频攻击
8. 爽感来源（必须保留）
* 外功 可无限连锁
* 结算日志可视化（文本即可）
* 允许“离谱强”但限制出现概率
9. MVP 不做清单（强制）
* ❌ PVP
* ❌ 多角色
* ❌ 复杂 UI
* ❌ 数值平衡
* ❌ 美术动画
10. 验收标准（非常重要）
这个 Demo 合格的唯一标准：
你能明确说出：
“这套 build 成型后，系统是怎么自己把对面打死的。”
如果你说不出来，说明设计失败。
