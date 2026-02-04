from __future__ import annotations

import random
import select
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional


TriggerType = str
EffectType = str


@dataclass
class Status:
    id: str
    stacks: int = 1


@dataclass
class InnerSkill:
    id: str
    name: str
    description: str
    hooks: Dict[str, List[Dict[str, object]]]


@dataclass
class OuterSkill:
    id: str
    name: str
    description: str
    trigger: TriggerType
    effect: Dict[str, object]
    chance: float = 1.0


@dataclass
class Actor:
    name: str
    hp: int
    max_hp: int
    qi: int
    max_qi: int
    inner_skill: InnerSkill
    outer_skills: List[OuterSkill] = field(default_factory=list)
    statuses: Dict[str, Status] = field(default_factory=dict)
    turns_without_attack: int = 0
    behavior_profile: str = "均衡"
    attack_probability: float = 0.7

    def is_alive(self) -> bool:
        return self.hp > 0

    def add_status(self, status_id: str, stacks: int = 1) -> None:
        if status_id in self.statuses:
            self.statuses[status_id].stacks += stacks
        else:
            self.statuses[status_id] = Status(status_id, stacks)

    def consume_status(self, status_id: str) -> int:
        if status_id not in self.statuses:
            return 0
        stacks = self.statuses[status_id].stacks
        del self.statuses[status_id]
        return stacks

    def get_status_stacks(self, status_id: str) -> int:
        return self.statuses.get(status_id, Status(status_id, 0)).stacks


@dataclass
class BattleContext:
    rng: random.Random
    logs: List[str]


@dataclass
class AttackResult:
    hit: bool
    crit: bool
    damage: int


def log(ctx: BattleContext, message: str) -> None:
    ctx.logs.append(message)
    print(message)


def create_inner_skills() -> List[InnerSkill]:
    return [
        InnerSkill(
            id="nine_sun",
            name="九阳心法",
            description="回合开始+2气，气溢出转化护体真气",
            hooks={
                "onTurnStart": [{"type": "gainQi", "amount": 2}],
                "onQiOverflow": [{"type": "addStatus", "status": "shield_qi", "amount": "overflow"}],
            },
        ),
        InnerSkill(
            id="suction_star",
            name="吸星大法",
            description="命中偷气，低气时翻倍",
            hooks={
                "onHit": [{"type": "stealQi", "amount": 1}],
            },
        ),
        InnerSkill(
            id="taiji",
            name="太极心法",
            description="防御后下一次攻击必定反击",
            hooks={
                "onDefense": [{"type": "addStatus", "status": "counter_ready", "amount": 1}],
            },
        ),
        InnerSkill(
            id="blood_war",
            name="血战心诀",
            description="生命低于50%外功触发率提升",
            hooks={},
        ),
        InnerSkill(
            id="withered_zen",
            name="枯禅定",
            description="连续2回合不攻击，下次攻击伤害翻倍",
            hooks={},
        ),
    ]


def create_outer_pool() -> List[OuterSkill]:
    return [
        OuterSkill("shock", "震伤", "命中后附加1层震伤。", "onHit", {"type": "addStatus", "status": "shock", "amount": 1}),
        OuterSkill(
            "combo",
            "连击",
            "目标有震伤时，追加上次攻击50%伤害。",
            "onHit",
            {"type": "repeatLastAction", "multiplier": 0.5, "requires": "shock"},
            0.7,
        ),
        OuterSkill("consume_shock", "化劲", "消耗目标震伤层数，每层造成3点真实伤害。", "onHit", {"type": "consumeStatus", "status": "shock", "perStackDamage": 3}),
        OuterSkill("recover_qi", "回气", "回合开始时获得1点气。", "onTurnStart", {"type": "gainQi", "amount": 1}),
        OuterSkill("counter_shock", "反震", "防御触发时给对手附加1层震伤。", "onDefense", {"type": "addStatus", "status": "shock", "amount": 1}),
        OuterSkill("quick_strike", "快斩", "出手时追加2点伤害。", "onAttack", {"type": "dealDamage", "amount": 2}, 0.6),
        OuterSkill("bleed", "破甲", "命中后附加1层易伤。", "onHit", {"type": "addStatus", "status": "vulnerable", "amount": 1}, 0.7),
        OuterSkill("drain", "引气", "命中后获得1点气。", "onHit", {"type": "gainQi", "amount": 1}, 0.7),
        OuterSkill("surge", "气爆", "有气时出手追加3点伤害。", "onAttack", {"type": "dealDamage", "amount": 3, "requires": "qi"}, 0.5),
        OuterSkill("steady", "稳守", "防御触发时获得1层护体真气。", "onDefense", {"type": "addStatus", "status": "shield_qi", "amount": 1}, 0.6),
        OuterSkill("frenzy", "狂躁", "回合开始时获得1层狂躁。", "onTurnStart", {"type": "addStatus", "status": "frenzy", "amount": 1}, 0.4),
        OuterSkill("riposte", "回风", "防御触发时反击造成上次攻击40%伤害。", "onDefense", {"type": "repeatLastAction", "multiplier": 0.4}, 0.5),
        OuterSkill("crit_focus", "凝神", "回合开始时获得1层凝神。", "onTurnStart", {"type": "addStatus", "status": "crit_focus", "amount": 1}, 0.6),
        OuterSkill("pierce", "破势", "命中后造成2点真实伤害。", "onHit", {"type": "dealDamage", "amount": 2, "true": True}, 0.6),
        OuterSkill("echo", "回响", "命中后追加上次攻击30%伤害。", "onHit", {"type": "repeatLastAction", "multiplier": 0.3}, 0.5),
        OuterSkill("shield_break", "破盾", "消耗对手护体真气，每层造成2点真实伤害。", "onHit", {"type": "consumeStatus", "status": "shield_qi", "perStackDamage": 2}),
        OuterSkill("focus", "聚气", "回合开始时获得2点气。", "onTurnStart", {"type": "gainQi", "amount": 2}, 0.4),
        OuterSkill("sunder", "碎甲", "命中后附加2层易伤。", "onHit", {"type": "addStatus", "status": "vulnerable", "amount": 2}, 0.4),
        OuterSkill("vitality", "回春", "回合开始时回复2点生命。", "onTurnStart", {"type": "heal", "amount": 2}, 0.5),
        OuterSkill("backlash", "内伤反噬", "防御触发时对对手造成2点伤害。", "onDefense", {"type": "dealDamage", "amount": 2}, 0.6),
    ]


def gain_qi(actor: Actor, amount: int, ctx: BattleContext) -> None:
    if amount <= 0:
        return
    actor.qi += amount
    overflow = max(0, actor.qi - actor.max_qi)
    if overflow > 0:
        actor.qi = actor.max_qi
        for effect in actor.inner_skill.hooks.get("onQiOverflow", []):
            if effect["type"] == "addStatus":
                actor.add_status(str(effect["status"]), overflow)
                log(ctx, f"{actor.name} 气溢出，转换为护体真气+{overflow}。")


def heal(actor: Actor, amount: int, ctx: BattleContext) -> None:
    if amount <= 0:
        return
    before = actor.hp
    actor.hp = min(actor.max_hp, actor.hp + amount)
    log(ctx, f"{actor.name} 回复 {actor.hp - before} 生命。")


def apply_damage(actor: Actor, amount: int, ctx: BattleContext, true_damage: bool = False) -> int:
    if amount <= 0:
        return 0
    damage = amount
    if not true_damage:
        vulnerable = actor.get_status_stacks("vulnerable")
        if vulnerable > 0:
            damage += vulnerable
        shield = actor.get_status_stacks("shield_qi")
        if shield > 0:
            absorbed = min(shield, damage)
            actor.statuses["shield_qi"].stacks -= absorbed
            if actor.statuses["shield_qi"].stacks <= 0:
                del actor.statuses["shield_qi"]
            damage -= absorbed
            log(ctx, f"{actor.name} 护体真气抵消 {absorbed} 伤害。")
    actor.hp = max(0, actor.hp - damage)
    return damage


def trigger_outer_skills(
    actor: Actor,
    target: Actor,
    trigger: TriggerType,
    ctx: BattleContext,
    last_attack: Optional[AttackResult],
) -> None:
    for skill in actor.outer_skills:
        if skill.trigger != trigger:
            continue
        bonus = 0.0
        if actor.inner_skill.id == "blood_war" and actor.hp <= actor.max_hp * 0.5:
            bonus += 0.5
        bonus += actor.get_status_stacks("frenzy") * 0.1
        chance = min(1.0, skill.chance * (1 + bonus))
        if ctx.rng.random() > chance:
            continue
        execute_effect(actor, target, skill.effect, ctx, last_attack)
        log(ctx, f"{actor.name} 触发外功《{skill.name}》。")


def execute_effect(
    actor: Actor,
    target: Actor,
    effect: Dict[str, object],
    ctx: BattleContext,
    last_attack: Optional[AttackResult],
) -> None:
    effect_type = effect["type"]
    if effect_type == "addStatus":
        status = str(effect["status"])
        amount = int(effect["amount"])
        target.add_status(status, amount)
        log(ctx, f"{target.name} 获得状态 {status} +{amount}。")
    elif effect_type == "dealDamage":
        amount = int(effect["amount"])
        if effect.get("requires") == "qi" and actor.qi <= 0:
            return
        true_damage = bool(effect.get("true", False))
        dealt = apply_damage(target, amount, ctx, true_damage=true_damage)
        log(ctx, f"{target.name} 受到 {dealt} 伤害。")
    elif effect_type == "gainQi":
        amount = int(effect["amount"])
        gain_qi(actor, amount, ctx)
        log(ctx, f"{actor.name} 获得 {amount} 气。")
    elif effect_type == "consumeStatus":
        status = str(effect["status"])
        stacks = target.consume_status(status)
        if stacks > 0:
            damage = stacks * int(effect["perStackDamage"])
            dealt = apply_damage(target, damage, ctx, true_damage=True)
            log(ctx, f"{target.name} 被消耗 {status} {stacks} 层，受到 {dealt} 真实伤害。")
    elif effect_type == "repeatLastAction" and last_attack:
        if effect.get("requires") == "shock" and target.get_status_stacks("shock") <= 0:
            return
        multiplier = float(effect["multiplier"])
        damage = int(last_attack.damage * multiplier)
        dealt = apply_damage(target, damage, ctx)
        log(ctx, f"{actor.name} 连锁攻击造成 {dealt} 伤害。")
    elif effect_type == "heal":
        amount = int(effect["amount"])
        heal(actor, amount, ctx)


def resolve_inner_on_hit(actor: Actor, target: Actor, ctx: BattleContext) -> None:
    for effect in actor.inner_skill.hooks.get("onHit", []):
        if effect["type"] == "stealQi":
            amount = int(effect["amount"])
            if actor.qi < actor.max_qi * 0.3:
                amount *= 2
            stolen = min(target.qi, amount)
            target.qi -= stolen
            gain_qi(actor, stolen, ctx)
            log(ctx, f"{actor.name} 偷取 {stolen} 气。")


def resolve_inner_on_defense(actor: Actor, ctx: BattleContext) -> None:
    for effect in actor.inner_skill.hooks.get("onDefense", []):
        if effect["type"] == "addStatus":
            actor.add_status(str(effect["status"]), int(effect["amount"]))
            log(ctx, f"{actor.name} 进入反击姿态。")


def start_turn(actor: Actor, enemy: Actor, ctx: BattleContext) -> None:
    for effect in actor.inner_skill.hooks.get("onTurnStart", []):
        execute_effect(actor, enemy, effect, ctx, None)
    trigger_outer_skills(actor, enemy, "onTurnStart", ctx, None)


def end_turn(actor: Actor, ctx: BattleContext) -> None:
    if "vulnerable" in actor.statuses:
        actor.statuses["vulnerable"].stacks = max(0, actor.statuses["vulnerable"].stacks - 1)
        if actor.statuses["vulnerable"].stacks == 0:
            del actor.statuses["vulnerable"]
    if "frenzy" in actor.statuses:
        actor.statuses["frenzy"].stacks = max(0, actor.statuses["frenzy"].stacks - 1)
        if actor.statuses["frenzy"].stacks == 0:
            del actor.statuses["frenzy"]
    if "crit_focus" in actor.statuses:
        actor.statuses["crit_focus"].stacks = max(0, actor.statuses["crit_focus"].stacks - 1)
        if actor.statuses["crit_focus"].stacks == 0:
            del actor.statuses["crit_focus"]


def perform_attack(attacker: Actor, defender: Actor, ctx: BattleContext) -> AttackResult:
    base_damage = 5
    crit_chance = 0.1 + (0.05 if attacker.get_status_stacks("crit_focus") > 0 else 0)
    crit = ctx.rng.random() < crit_chance
    multiplier = 2 if crit else 1
    if attacker.get_status_stacks("double_strike") > 0:
        multiplier *= 2
        attacker.consume_status("double_strike")
        log(ctx, f"{attacker.name} 枯禅定触发，伤害翻倍！")
    damage = base_damage * multiplier
    dealt = apply_damage(defender, damage, ctx)
    log(ctx, f"{attacker.name} 攻击命中，造成 {dealt} 伤害。")
    if crit:
        log(ctx, f"{attacker.name} 暴击！")
    return AttackResult(hit=True, crit=crit, damage=damage)


def action_phase(actor: Actor, enemy: Actor, ctx: BattleContext) -> None:
    action_attack = ctx.rng.random() < actor.attack_probability
    if action_attack:
        actor.turns_without_attack = 0
        trigger_outer_skills(actor, enemy, "onAttack", ctx, None)
        last_attack = perform_attack(actor, enemy, ctx)
        resolve_inner_on_hit(actor, enemy, ctx)
        trigger_outer_skills(actor, enemy, "onHit", ctx, last_attack)
        if last_attack.crit:
            trigger_outer_skills(actor, enemy, "onCrit", ctx, last_attack)
        handle_counter(enemy, actor, ctx)
    else:
        actor.turns_without_attack += 1
        log(ctx, f"{actor.name} 选择防御。")
        resolve_inner_on_defense(actor, ctx)
        trigger_outer_skills(actor, enemy, "onDefense", ctx, None)
        if actor.inner_skill.id == "withered_zen" and actor.turns_without_attack >= 2:
            actor.add_status("double_strike", 1)
            log(ctx, f"{actor.name} 枯禅定蓄力完成。")


def choose_player_intent() -> str:
    print("\n请选择出招意图：1【进】2【守】3【化】")
    print("PC: 1/2/3 | 手柄: X/Y/B | 手机: 点击按钮")
    choice = input("请输入选择: ").strip()
    if choice not in {"1", "2", "3"}:
        choice = "1"
    return choice


def show_battle_status(player: Actor, enemy: Actor, ctx: BattleContext) -> None:
    log(
        ctx,
        (
            f"{player.name} 生命:{player.hp}/{player.max_hp} 气:{player.qi}/{player.max_qi}"
            f" | {enemy.name} 生命:{enemy.hp}/{enemy.max_hp} 气:{enemy.qi}/{enemy.max_qi}"
        ),
    )


def resolve_transmute(actor: Actor, enemy: Actor, ctx: BattleContext) -> None:
    conversions = [
        {"status": "shock", "value": 3, "type": "damage"},
        {"status": "vulnerable", "value": 2, "type": "damage"},
        {"status": "frenzy", "value": 1, "type": "qi"},
        {"status": "shield_qi", "value": 1, "type": "heal"},
    ]
    best = None
    best_score = 0
    for conversion in conversions:
        stacks = actor.get_status_stacks(conversion["status"])
        score = stacks * conversion["value"]
        if score > best_score:
            best_score = score
            best = {"conversion": conversion, "stacks": stacks}
    if not best or best_score == 0:
        log(ctx, f"{actor.name} 化劲失败，没有可用状态。")
        return
    status = best["conversion"]["status"]
    stacks = best["stacks"]
    actor.consume_status(status)
    if best["conversion"]["type"] == "damage":
        damage = stacks * best["conversion"]["value"]
        dealt = apply_damage(enemy, damage, ctx, true_damage=True)
        log(ctx, f"{actor.name} 化劲消耗 {status} {stacks} 层，造成 {dealt} 真实伤害。")
    elif best["conversion"]["type"] == "qi":
        gain_qi(actor, stacks, ctx)
        log(ctx, f"{actor.name} 化劲转化气 +{stacks}。")
    elif best["conversion"]["type"] == "heal":
        heal(actor, stacks, ctx)
        log(ctx, f"{actor.name} 化劲转化护体，回复 {stacks} 生命。")


def player_action_phase(actor: Actor, enemy: Actor, ctx: BattleContext) -> None:
    show_battle_status(actor, enemy, ctx)
    intent = choose_player_intent()
    apply_player_intent(actor, enemy, ctx, intent)
    show_battle_status(actor, enemy, ctx)


def apply_player_intent(actor: Actor, enemy: Actor, ctx: BattleContext, intent: str) -> None:
    if intent == "1":
        actor.turns_without_attack = 0
        if actor.qi > 0:
            actor.qi -= 1
            log(ctx, f"{actor.name} 选择【进】，消耗 1 气。")
        else:
            log(ctx, f"{actor.name} 选择【进】，但气不足。")
        trigger_outer_skills(actor, enemy, "onAttack", ctx, None)
        last_attack = perform_attack(actor, enemy, ctx)
        resolve_inner_on_hit(actor, enemy, ctx)
        trigger_outer_skills(actor, enemy, "onHit", ctx, last_attack)
        if last_attack.crit:
            trigger_outer_skills(actor, enemy, "onCrit", ctx, last_attack)
        handle_counter(enemy, actor, ctx)
    elif intent == "2":
        actor.turns_without_attack += 1
        gain_qi(actor, 1, ctx)
        log(ctx, f"{actor.name} 选择【守】，回复 1 气。")
        resolve_inner_on_defense(actor, ctx)
        trigger_outer_skills(actor, enemy, "onDefense", ctx, None)
        if actor.inner_skill.id == "withered_zen" and actor.turns_without_attack >= 2:
            actor.add_status("double_strike", 1)
            log(ctx, f"{actor.name} 枯禅定蓄力完成。")
    else:
        actor.turns_without_attack += 1
        log(ctx, f"{actor.name} 选择【化】，开始转化状态。")
        resolve_transmute(actor, enemy, ctx)
        if actor.inner_skill.id == "withered_zen" and actor.turns_without_attack >= 2:
            actor.add_status("double_strike", 1)
            log(ctx, f"{actor.name} 枯禅定蓄力完成。")


def handle_counter(defender: Actor, attacker: Actor, ctx: BattleContext) -> None:
    if defender.get_status_stacks("counter_ready") <= 0:
        return
    defender.consume_status("counter_ready")
    log(ctx, f"{defender.name} 反击发动！")
    last_attack = perform_attack(defender, attacker, ctx)
    resolve_inner_on_hit(defender, attacker, ctx)
    trigger_outer_skills(defender, attacker, "onHit", ctx, last_attack)


def create_enemy(stage: int, rng: random.Random) -> Actor:
    profiles = [
        ("高攻", 18 + stage * 2, 0.75),
        ("高防", 26 + stage * 3, 0.55),
        ("高频", 20 + stage * 2, 0.85),
    ]
    name, hp, attack_probability = rng.choice(profiles)
    inner_skills = create_inner_skills()
    inner_skill = rng.choice(inner_skills)
    return Actor(
        name=f"敌人-{name}",
        hp=hp,
        max_hp=hp,
        qi=2,
        max_qi=6,
        inner_skill=inner_skill,
        outer_skills=[],
        behavior_profile=name,
        attack_probability=attack_probability,
    )


def choose_inner_skill(rng: random.Random) -> InnerSkill:
    skills = create_inner_skills()
    return rng.choice(skills)


def choose_outer_skill(pool: List[OuterSkill], rng: random.Random, ctx: BattleContext) -> OuterSkill:
    options = pick_outer_skill_options(pool, rng, ctx)
    choice = ""
    while choice not in {"1", "2", "3"}:
        choice = input("请选择外功 (1/2/3): ").strip()
    return options[int(choice) - 1]


def pick_outer_skill_options(pool: List[OuterSkill], rng: random.Random, ctx: BattleContext) -> List[OuterSkill]:
    options = rng.sample(pool, 3)
    log(ctx, "可选外功：")
    for index, skill in enumerate(options, start=1):
        log(ctx, f"{index}) {skill.name} - {skill.description}")
    return options


def battle(player: Actor, enemy: Actor, ctx: BattleContext) -> bool:
    turn = 1
    while player.is_alive() and enemy.is_alive():
        log(ctx, f"\n=== 回合 {turn} ===")
        start_turn(player, enemy, ctx)
        start_turn(enemy, player, ctx)
        player_action_phase(player, enemy, ctx)
        if not enemy.is_alive():
            break
        action_phase(enemy, player, ctx)
        end_turn(player, ctx)
        end_turn(enemy, ctx)
        turn += 1
    return player.is_alive()


def show_instructions() -> None:
    print(
        """
=== 说明 ===
每回合开始时，暂停战斗。
玩家从【进 / 守 / 化】三种出招意图中选择其一。
该选择将决定本回合可触发的外功触发器集合。
具体招式不由玩家选择，而由其已构筑的外功模块链自动执行。

出招意图系统（MVP）
1️⃣【进】
* 主动出招
* 高频触发 onHit / onAttack 外功
* 气消耗 +1
👉 赌快、赌爆发
2️⃣【守】
* 本回合防御
* 高概率触发 onDefense 外功
* 气恢复 +1
👉 赌反制、赌连锁
3️⃣【化】
* 不直接攻击
* 消耗已有状态
* 将状态转为：伤害 / 气 / 护体
👉 赌转换效率

操作方式：
* PC：1 / 2 / 3
* 手柄：X / Y / B
* 手机：三个大按钮
无连按，无时机判定。
"""
    )
    input("按回车返回主菜单...")


def run_game(seed: Optional[int] = None) -> None:
    rng = random.Random(seed)
    ctx = BattleContext(rng=rng, logs=[])
    outer_pool = create_outer_pool()

    while True:
        print("\n=== 主菜单 ===")
        print("1) 开始游戏")
        print("2) 说明")
        print("3) 结束游戏")
        choice = input("请选择: ").strip()
        if choice == "2":
            show_instructions()
            continue
        if choice == "3":
            print("感谢游玩，游戏结束。")
            return
        if choice != "1":
            print("无效选择，请重试。")
            continue
        ctx.logs.clear()
        inner_skill = choose_inner_skill(rng)
        player = Actor(
            name="侠客",
            hp=30,
            max_hp=30,
            qi=3,
            max_qi=8,
            inner_skill=inner_skill,
            outer_skills=[],
            attack_probability=0.7,
        )
        log(ctx, f"\n新局开始：内功选择《{inner_skill.name}》")
        stage = 1
        while player.is_alive():
            enemy = create_enemy(stage, rng)
            log(ctx, f"\n进入关卡 {stage}，遭遇 {enemy.name}。")
            win = battle(player, enemy, ctx)
            if not win:
                break
            log(ctx, f"\n胜利！进入奖励阶段。")
            reward = choose_outer_skill(outer_pool, rng, ctx)
            player.outer_skills.append(reward)
            log(ctx, f"获得外功《{reward.name}》。")
            stage += 1
        log(ctx, "\n战斗失败，结算结束。")
        restart = input("是否重开？(y/n): ").strip().lower()
        if restart != "y":
            print("返回主菜单。")


if __name__ == "__main__":
    run_game()
