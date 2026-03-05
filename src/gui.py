from __future__ import annotations

import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List

import pygame

from roguelike import (
    Actor,
    BattleContext,
    action_phase,
    apply_player_intent,
    choose_inner_skill,
    create_enemy,
    create_outer_pool,
    end_turn,
    log,
    pick_outer_skill_options,
    show_battle_status,
    start_turn,
)


SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
LOG_AREA_RECT = pygame.Rect(20, 380, 760, 200)
MAX_LOG_LINES = 10

COLOR_BG = (20, 24, 36)
COLOR_PANEL = (30, 40, 60)
COLOR_TEXT = (230, 230, 230)
COLOR_BUTTON = (70, 90, 130)
COLOR_BUTTON_HOVER = (100, 120, 160)
COLOR_PLAYER = (80, 180, 120)
COLOR_ENEMY = (180, 80, 80)

SCENE_MENU = "menu"
SCENE_INSTRUCTIONS = "instructions"
SCENE_BATTLE = "battle"
SCENE_REWARD = "reward"
SCENE_GAME_OVER = "game_over"

INSTRUCTIONS_TEXT = (
    "=== 说明 ===\n"
    "每回合开始时，战斗暂停。\n"
    "玩家从【进 / 守 / 化】三种出招意图中选择其一。\n"
    "该选择会影响本回合可触发的外功类型。\n"
    "具体招式由已构筑的外功链自动执行。\n\n"
    "出招意图系统（MVP）：\n"
    "1. 进：主动攻击，高频触发 onHit / onAttack，消耗 1 气。\n"
    "2. 守：本回合防守，高概率触发 onDefense，恢复 1 气。\n"
    "3. 化：不直接攻击，消耗已有状态并转化为收益。\n\n"
    "操作方式：点击按钮选择。"
)


@dataclass
class Button:
    rect: pygame.Rect
    label: str
    on_click: Callable[[], None]

    def draw(self, surface: pygame.Surface, font: pygame.font.Font, mouse_pos: tuple[int, int]) -> None:
        is_hover = self.rect.collidepoint(mouse_pos)
        color = COLOR_BUTTON_HOVER if is_hover else COLOR_BUTTON
        pygame.draw.rect(surface, color, self.rect, border_radius=6)
        text_surface = font.render(self.label, True, COLOR_TEXT)
        text_rect = text_surface.get_rect(center=self.rect.center)
        surface.blit(text_surface, text_rect)


@dataclass
class UIResources:
    font: pygame.font.Font
    title_font: pygame.font.Font
    log_font: pygame.font.Font


class GameUI:
    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        self.clock = pygame.time.Clock()
        self.resources = UIResources(
            font=self.load_font(24),
            title_font=self.load_font(40),
            log_font=self.load_font(20),
        )
        self.buttons: List[Button] = []

        self.scene = SCENE_MENU
        self.rng = random.Random()
        self.ctx = BattleContext(rng=self.rng, logs=[])
        self.outer_pool = create_outer_pool()

        self.player: Actor | None = None
        self.enemy: Actor | None = None
        self.stage = 1
        self.turn = 1
        self.reward_options = []

        self.scene_button_builders = {
            SCENE_MENU: self.build_menu_buttons,
            SCENE_INSTRUCTIONS: self.build_instructions_buttons,
            SCENE_BATTLE: self.build_battle_buttons,
            SCENE_REWARD: self.build_reward_buttons,
            SCENE_GAME_OVER: self.build_game_over_buttons,
        }
        self.scene_renderers = {
            SCENE_MENU: self.render_menu_scene,
            SCENE_INSTRUCTIONS: self.render_instructions_scene,
            SCENE_BATTLE: self.render_battle_scene,
            SCENE_REWARD: self.render_reward_scene,
            SCENE_GAME_OVER: self.render_game_over_scene,
        }

        self.set_scene(SCENE_MENU)

    @staticmethod
    def load_font(size: int) -> pygame.font.Font:
        font_path = Path(__file__).resolve().parent / "assets" / "fonts" / "SourceHanSansCN-VF.otf"
        try:
            return pygame.font.Font(str(font_path), size)
        except (FileNotFoundError, OSError, pygame.error):
            print(f"[WARN] 无法加载字体文件: {font_path}，将回退到系统默认字体。")
            return pygame.font.SysFont(None, size)

    def set_scene(self, scene: str) -> None:
        self.scene = scene
        self.buttons = self.scene_button_builders.get(scene, lambda: [])()

    def build_menu_buttons(self) -> List[Button]:
        return [
            Button(pygame.Rect(300, 220, 200, 50), "开始游戏", self.start_game),
            Button(pygame.Rect(300, 290, 200, 50), "说明", self.show_instructions),
            Button(pygame.Rect(300, 360, 200, 50), "结束游戏", self.exit_game),
        ]

    def build_instructions_buttons(self) -> List[Button]:
        return [
            Button(pygame.Rect(300, 500, 200, 50), "返回", lambda: self.set_scene(SCENE_MENU)),
        ]

    def build_battle_buttons(self) -> List[Button]:
        return [
            Button(pygame.Rect(140, 330, 140, 40), "进", lambda: self.handle_intent("1")),
            Button(pygame.Rect(330, 330, 140, 40), "守", lambda: self.handle_intent("2")),
            Button(pygame.Rect(520, 330, 140, 40), "化", lambda: self.handle_intent("3")),
        ]

    def build_reward_buttons(self) -> List[Button]:
        buttons: List[Button] = []
        for index, option in enumerate(self.reward_options):
            buttons.append(
                Button(
                    pygame.Rect(180, 240 + index * 70, 440, 50),
                    f"{option.name} - {option.description}",
                    lambda opt=option: self.select_reward(opt),
                )
            )
        return buttons

    def build_game_over_buttons(self) -> List[Button]:
        return [
            Button(pygame.Rect(260, 320, 280, 50), "重新开始", self.start_game),
            Button(pygame.Rect(260, 390, 280, 50), "返回主菜单", lambda: self.set_scene(SCENE_MENU)),
        ]

    def start_game(self) -> None:
        self.ctx.logs.clear()
        inner_skill = choose_inner_skill(self.rng)
        self.player = Actor(
            name="侠客",
            hp=30,
            max_hp=30,
            qi=3,
            max_qi=8,
            inner_skill=inner_skill,
            outer_skills=[],
            attack_probability=0.7,
        )
        log(self.ctx, f"\n新局开始：内功选择《{inner_skill.name}》。")

        self.stage = 1
        self.turn = 1
        self.enemy = create_enemy(self.stage, self.rng)
        log(self.ctx, f"\n进入关卡 {self.stage}，遭遇 {self.enemy.name}。")

        self.start_turn()
        self.set_scene(SCENE_BATTLE)

    def start_turn(self) -> None:
        if not self.player or not self.enemy:
            return
        log(self.ctx, f"\n=== 回合 {self.turn} ===")
        start_turn(self.player, self.enemy, self.ctx)
        start_turn(self.enemy, self.player, self.ctx)

    def handle_intent(self, intent: str) -> None:
        if not self.player or not self.enemy:
            return

        show_battle_status(self.player, self.enemy, self.ctx)
        apply_player_intent(self.player, self.enemy, self.ctx, intent)
        show_battle_status(self.player, self.enemy, self.ctx)

        if self.enemy.is_alive():
            action_phase(self.enemy, self.player, self.ctx)

        end_turn(self.player, self.ctx)
        end_turn(self.enemy, self.ctx)

        if not self.player.is_alive():
            log(self.ctx, "\n战斗失败，结算结束。")
            self.set_scene(SCENE_GAME_OVER)
            return

        if not self.enemy.is_alive():
            log(self.ctx, "\n胜利，进入奖励阶段。")
            self.reward_options = pick_outer_skill_options(self.outer_pool, self.rng, self.ctx)
            self.set_scene(SCENE_REWARD)
            return

        self.turn += 1
        self.start_turn()

    def select_reward(self, reward) -> None:
        if not self.player:
            return

        self.player.outer_skills.append(reward)
        log(self.ctx, f"获得外功《{reward.name}》。")

        self.stage += 1
        self.turn = 1
        self.enemy = create_enemy(self.stage, self.rng)
        log(self.ctx, f"\n进入关卡 {self.stage}，遭遇 {self.enemy.name}。")

        self.start_turn()
        self.set_scene(SCENE_BATTLE)

    def show_instructions(self) -> None:
        self.set_scene(SCENE_INSTRUCTIONS)

    def exit_game(self) -> None:
        pygame.quit()
        sys.exit(0)

    def wrap_text(self, text: str, font: pygame.font.Font, max_width: int) -> List[str]:
        lines: List[str] = []
        current = ""
        for char in text:
            test_line = f"{current}{char}"
            if font.size(test_line)[0] <= max_width:
                current = test_line
            else:
                if current:
                    lines.append(current)
                current = char
        if current:
            lines.append(current)
        return lines

    def build_log_lines(self) -> List[str]:
        lines: List[str] = []
        for entry in self.ctx.logs:
            split_lines = entry.splitlines() or [""]
            for line in split_lines:
                cleaned = line.strip("\n")
                if cleaned == "" and lines:
                    lines.append(" ")
                else:
                    lines.append(cleaned)

        wrapped_lines: List[str] = []
        for line in lines:
            if not line:
                wrapped_lines.append(" ")
                continue
            wrapped_lines.extend(self.wrap_text(line, self.resources.log_font, LOG_AREA_RECT.width - 10))

        return wrapped_lines[-MAX_LOG_LINES:]

    def draw_logs(self) -> None:
        pygame.draw.rect(self.screen, COLOR_PANEL, LOG_AREA_RECT, border_radius=8)
        lines = self.build_log_lines()
        for index, line in enumerate(lines):
            text_surface = self.resources.log_font.render(line, True, COLOR_TEXT)
            self.screen.blit(text_surface, (LOG_AREA_RECT.x + 10, LOG_AREA_RECT.y + 10 + index * 18))

    def draw_battle_base(self) -> None:
        if not self.player or not self.enemy:
            return

        player_rect = pygame.Rect(120, 120, 80, 120)
        enemy_rect = pygame.Rect(600, 120, 80, 120)
        pygame.draw.rect(self.screen, COLOR_PLAYER, player_rect)
        pygame.draw.rect(self.screen, COLOR_ENEMY, enemy_rect)

        player_text = self.resources.font.render(
            f"{self.player.name} HP:{self.player.hp}/{self.player.max_hp} 气:{self.player.qi}/{self.player.max_qi}",
            True,
            COLOR_TEXT,
        )
        enemy_text = self.resources.font.render(
            f"{self.enemy.name} HP:{self.enemy.hp}/{self.enemy.max_hp} 气:{self.enemy.qi}/{self.enemy.max_qi}",
            True,
            COLOR_TEXT,
        )

        self.screen.blit(player_text, (50, 60))
        self.screen.blit(enemy_text, (420, 60))

        stage_text = self.resources.font.render(f"关卡 {self.stage} | 回合 {self.turn}", True, COLOR_TEXT)
        self.screen.blit(stage_text, (300, 20))

        self.draw_logs()

    def render_menu_scene(self) -> None:
        title = self.resources.title_font.render("武学回合战", True, COLOR_TEXT)
        subtitle = self.resources.font.render("选择开始游戏或查看说明", True, COLOR_TEXT)
        self.screen.blit(title, (280, 20))
        self.screen.blit(subtitle, (260, 80))

    def render_instructions_scene(self) -> None:
        title = self.resources.title_font.render("说明", True, COLOR_TEXT)
        self.screen.blit(title, (350, 20))
        y = 90
        for line in INSTRUCTIONS_TEXT.splitlines():
            text_surface = self.resources.font.render(line, True, COLOR_TEXT)
            self.screen.blit(text_surface, (60, y))
            y += 26

    def render_battle_scene(self) -> None:
        self.draw_battle_base()

    def render_reward_scene(self) -> None:
        self.draw_battle_base()
        text = self.resources.font.render("胜利奖励：选择一门外功", True, COLOR_TEXT)
        self.screen.blit(text, (260, 200))

    def render_game_over_scene(self) -> None:
        self.draw_battle_base()
        text = self.resources.font.render("战斗失败，结算结束。", True, COLOR_TEXT)
        self.screen.blit(text, (280, 260))

    def draw(self) -> None:
        self.screen.fill(COLOR_BG)
        scene_renderer = self.scene_renderers.get(self.scene)
        if scene_renderer:
            scene_renderer()

        mouse_pos = pygame.mouse.get_pos()
        for button in self.buttons:
            button.draw(self.screen, self.resources.font, mouse_pos)

    def handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.exit_game()

            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                if self.scene in {SCENE_BATTLE, SCENE_REWARD, SCENE_GAME_OVER}:
                    self.set_scene(SCENE_MENU)
                else:
                    self.exit_game()

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for button in self.buttons:
                    if button.rect.collidepoint(event.pos):
                        button.on_click()
                        break

    def run(self) -> None:
        while True:
            self.handle_events()
            self.draw()
            pygame.display.flip()
            self.clock.tick(60)


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("武学回合战 GUI")
    ui = GameUI(screen)
    ui.run()


if __name__ == "__main__":
    main()
