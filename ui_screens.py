# ui_screens.py
# Minimal pygame UI for town_sim.py (multi-town + travelling merchant market)

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional
import json
import pygame
from sim.config import edible_count, BASE_VALUES, GOODS


# ╔══════════════════════════════════════════════════════════════╗
# ║ UI State                                                     ║
# ╚══════════════════════════════════════════════════════════════╝

@dataclass
class UIState:
    tab: str = "People"
    selected_town: int = 0
    paused: bool = False
    speed: float = .02
    scroll: int = 0
    follow_name: Optional[str] = None
    event_search: str = ""
    agent_panel: str = "Profile"   # Profile | Brain
    brain_scroll: int = 0
    selected_event_i: int = -1
    rumor_subject: str = ""
    selected_region: int = 0
    rumor_claim: str = ""
    rumor_scroll: int = 0
    show_opinions: bool = True
    show_grudges: bool = True
    show_memories: bool = False
    fullscreen: bool = True
    windowed_size: tuple[int, int] = (1180, 760)
    selected_family_id: int = -1
    family_scroll: int = 0


TABS = ("People", "Market", "Economy", "Stats", "Families", "Map", "Towns", "Inn", "Events", "Search", "Rumor", "Agent")


# ╔══════════════════════════════════════════════════════════════╗
# ║ Color palette (desert cartography)                           ║
# ╚══════════════════════════════════════════════════════════════╝

COL_BG       = (22, 20, 16)
COL_PANEL    = (28, 26, 22)
COL_BORDER   = (65, 58, 44)
COL_TEXT     = (220, 212, 195)
COL_DIM      = (150, 140, 120)
COL_GHOST    = (100, 92, 72)
COL_GOLD     = (200, 168, 78)
COL_RUST     = (160, 82, 45)
COL_TEAL     = (42, 107, 94)
COL_RED      = (139, 58, 58)
COL_BLUE     = (58, 90, 139)
COL_TAB_BG   = (45, 40, 32)
COL_TAB_ACT  = (70, 62, 48)
COL_HIGHLIGHT = (50, 48, 38)

CLASS_COLORS = {
    "poor":        COL_RED,
    "common":      COL_DIM,
    "comfortable": COL_BLUE,
    "elite":       COL_GOLD,
}

# line chart colors for tracked goods
CHART_COLORS = {
    "food": (160, 82, 45),
    "wood": (107, 142, 35),
    "ore": (112, 128, 144),
    "stone": (140, 130, 110),
    "tools": (139, 115, 85),
    "cloth": (147, 112, 219),
    "ingot": (184, 134, 11),
    "bread": (210, 105, 30),
}

PRICE_HIST_LEN = 300


# ╔══════════════════════════════════════════════════════════════╗
# ║ Pixel decorations + map generation                           ║
# ╚══════════════════════════════════════════════════════════════╝

def _draw_cactus(surf: pygame.Surface, x: int, y: int, scale: int = 1) -> None:
    """tiny pixel cactus"""
    s = scale
    c = (58, 90, 42)
    cd = (42, 68, 32)
    pygame.draw.rect(surf, c, (x, y - 6*s, 2*s, 8*s))      # trunk
    pygame.draw.rect(surf, c, (x - 3*s, y - 4*s, 3*s, 2*s)) # left arm
    pygame.draw.rect(surf, cd, (x - 3*s, y - 6*s, 2*s, 2*s))
    pygame.draw.rect(surf, c, (x + 2*s, y - 3*s, 3*s, 2*s)) # right arm
    pygame.draw.rect(surf, cd, (x + 3*s, y - 5*s, 2*s, 2*s))

def _draw_palm(surf: pygame.Surface, x: int, y: int, scale: int = 1) -> None:
    """tiny pixel palm tree"""
    s = scale
    trunk = (120, 85, 50)
    leaf = (50, 100, 40)
    leafl = (65, 120, 50)
    pygame.draw.rect(surf, trunk, (x, y - 8*s, 2*s, 10*s))  # trunk
    # fronds
    for dx, dy in [(-4, -8), (-3, -9), (3, -8), (4, -9), (0, -10), (-2, -10), (2, -10)]:
        pygame.draw.rect(surf, leaf, (x + dx*s, y + dy*s, 2*s, s))
    for dx, dy in [(-5, -7), (5, -7), (-1, -11), (1, -11)]:
        pygame.draw.rect(surf, leafl, (x + dx*s, y + dy*s, s, s))

def _draw_castle(surf: pygame.Surface, x: int, y: int, scale: int = 2) -> None:
    """pixel castle icon for towns"""
    s = scale
    wall = (160, 140, 110)
    walld = (120, 105, 80)
    roof = (100, 60, 40)
    # base wall
    pygame.draw.rect(surf, wall, (x - 6*s, y - 4*s, 12*s, 6*s))
    pygame.draw.rect(surf, walld, (x - 6*s, y - 4*s, 12*s, 1*s))
    # towers
    for tx in [x - 6*s, x + 4*s]:
        pygame.draw.rect(surf, wall, (tx, y - 8*s, 3*s, 10*s))
        pygame.draw.rect(surf, roof, (tx - s, y - 9*s, 5*s, 2*s))
    # gate
    pygame.draw.rect(surf, (40, 30, 20), (x - s, y - 1*s, 2*s, 3*s))
    # battlements
    for bx in range(x - 5*s, x + 5*s, 3*s):
        pygame.draw.rect(surf, walld, (bx, y - 5*s, s, s))

def _draw_merchant_sprite(surf: pygame.Surface, x: int, y: int, scale: int = 2) -> None:
    """small caravan/merchant sprite"""
    s = scale
    # camel body
    pygame.draw.rect(surf, (180, 150, 100), (x - 4*s, y - 3*s, 8*s, 4*s))
    # hump
    pygame.draw.rect(surf, (160, 130, 85), (x - s, y - 5*s, 3*s, 2*s))
    # head
    pygame.draw.rect(surf, (170, 140, 95), (x + 3*s, y - 5*s, 2*s, 3*s))
    # legs
    for lx in [x - 3*s, x - s, x + 2*s, x + 4*s]:
        pygame.draw.rect(surf, (140, 115, 75), (lx, y + s, s, 2*s))
    # gold accent on pack
    pygame.draw.rect(surf, COL_GOLD, (x - 3*s, y - 4*s, 2*s, s))

def generate_map_surface(rng_seed: int, w: int, h: int, num_towns: int) -> tuple:
    """generate a static background map with terrain, river, and town positions"""
    import random as _rng_mod
    rng = _rng_mod.Random(rng_seed)

    surf = pygame.Surface((w, h))

    # base sand terrain
    for py in range(h):
        for px in range(w):
            base = 34 + rng.randint(-3, 3)
            g_off = rng.randint(-2, 2)
            surf.set_at((px, py), (base + 4, base + g_off, base - 8 + rng.randint(0, 3)))

    # dunes (lighter streaks)
    for _ in range(12):
        dx = rng.randint(0, w)
        dy = rng.randint(0, h)
        dw = rng.randint(40, 120)
        dh = rng.randint(6, 18)
        for iy in range(dh):
            for ix in range(dw):
                px = dx + ix
                py = dy + iy
                if 0 <= px < w and 0 <= py < h:
                    r, g, b = surf.get_at((px, py))[:3]
                    surf.set_at((px, py), (min(255, r + 8), min(255, g + 6), min(255, b + 3)))

    # place towns along a winding river path
    # river runs roughly top-to-bottom with curves
    margin = 60
    town_positions = []

    # generate river path as a series of control points
    river_pts = []
    ry_step = (h - 2 * margin) // (num_towns + 1)
    rx_center = w // 2
    for i in range(num_towns + 2):
        ry = margin + i * ry_step
        rx = rx_center + rng.randint(-w // 5, w // 5)
        rx = max(margin, min(w - margin, rx))
        river_pts.append((rx, ry))

    # interpolate river between points
    river_pixels = []
    for i in range(len(river_pts) - 1):
        x0, y0 = river_pts[i]
        x1, y1 = river_pts[i + 1]
        steps = max(abs(x1 - x0), abs(y1 - y0), 1)
        for t in range(steps + 1):
            frac = t / steps
            px = int(x0 + (x1 - x0) * frac)
            py = int(y0 + (y1 - y0) * frac)
            river_pixels.append((px, py))

    # draw river (wide, with bank colors)
    river_color = (35, 65, 85)
    river_light = (45, 80, 100)
    bank_color = (50, 70, 48)
    for px, py in river_pixels:
        for dx in range(-5, 6):
            for dy in range(-1, 2):
                nx, ny = px + dx, py + dy
                if 0 <= nx < w and 0 <= ny < h:
                    dist = abs(dx)
                    if dist <= 3:
                        c = river_light if (px + py) % 7 < 2 else river_color
                        surf.set_at((nx, ny), c)
                    elif dist <= 5:
                        surf.set_at((nx, ny), bank_color)

    # place towns near river points (skip first and last which are edges)
    for i in range(1, min(num_towns + 1, len(river_pts) - 1)):
        rx, ry = river_pts[i]
        # offset town slightly from river
        side = 1 if rng.random() > 0.5 else -1
        tx = rx + side * rng.randint(25, 45)
        ty = ry + rng.randint(-10, 10)
        tx = max(40, min(w - 40, tx))
        ty = max(40, min(h - 40, ty))
        town_positions.append((tx, ty))

    # pad if we didn't get enough towns
    while len(town_positions) < num_towns:
        town_positions.append((rng.randint(60, w - 60), rng.randint(60, h - 60)))

    # draw decorations: cacti and palms
    for _ in range(18):
        cx = rng.randint(10, w - 10)
        cy = rng.randint(10, h - 10)
        # don't place on river
        near_river = any(abs(cx - rpx) < 12 and abs(cy - rpy) < 8 for rpx, rpy in river_pixels[::10])
        near_town = any(abs(cx - tx) < 30 and abs(cy - ty) < 25 for tx, ty in town_positions)
        if not near_river and not near_town:
            if rng.random() < 0.6:
                _draw_cactus(surf, cx, cy, scale=1)
            else:
                _draw_palm(surf, cx, cy, scale=1)

    # draw palms near river (oasis feel)
    for rpx, rpy in river_pixels[::40]:
        if rng.random() < 0.5:
            side = 8 if rng.random() > 0.5 else -8
            _draw_palm(surf, rpx + side + rng.randint(-3, 3), rpy + rng.randint(-3, 3), scale=1)

    # draw castles at town positions
    for tx, ty in town_positions:
        _draw_castle(surf, tx, ty, scale=2)

    return surf, town_positions, river_pixels


# ╔══════════════════════════════════════════════════════════════╗
# ║ Helpers                                                      ║
# ╚══════════════════════════════════════════════════════════════╝

def draw_text(
    surf: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    x: int,
    y: int,
    color=(235, 235, 235),
    clip_rect: pygame.Rect | None = None,
) -> int:
    img = font.render(text, True, color)
    old_clip = surf.get_clip()
    if clip_rect is not None:
        surf.set_clip(clip_rect)
    surf.blit(img, (x, y))
    if clip_rect is not None:
        surf.set_clip(old_clip)
    return y + img.get_height() + 2

def draw_button(surf: pygame.Surface, font: pygame.font.Font, rect: pygame.Rect, label: str, *, active: bool=False) -> None:
    bg = (65, 65, 80) if active else (45, 45, 55)
    pygame.draw.rect(surf, bg, rect, border_radius=10)
    pygame.draw.rect(surf, (95, 95, 115), rect, 2, border_radius=10)
    img = font.render(label, True, (240, 240, 240))
    old_clip = surf.get_clip()
    surf.set_clip(rect)
    surf.blit(img, (rect.x + 10, rect.y + (rect.h - img.get_height()) // 2))
    surf.set_clip(old_clip)

def draw_wrapped_text(
    surf: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    x: int,
    y: int,
    max_width: int,
    color=(235, 235, 235),
    clip_rect: pygame.Rect | None = None,
) -> int:
    words = text.split()
    if not words:
        return y

    old_clip = surf.get_clip()
    if clip_rect is not None:
        surf.set_clip(clip_rect)

    line = words[0]
    for word in words[1:]:
        test = line + " " + word
        if font.size(test)[0] <= max_width:
            line = test
        else:
            img = font.render(line, True, color)
            surf.blit(img, (x, y))
            y += img.get_height() + 2
            line = word

    img = font.render(line, True, color)
    surf.blit(img, (x, y))

    if clip_rect is not None:
        surf.set_clip(old_clip)

    return y + img.get_height() + 2


# ╔══════════════════════════════════════════════════════════════╗
# ║ Main UI                                                      ║
# ╚══════════════════════════════════════════════════════════════╝

def run_pygame_ui(world, step_once: Callable[[], List[str]], *, title: str = "Town Sim") -> None:
    pygame.init()
    pygame.display.set_caption(title)

    W, H = 1180, 760
    screen = pygame.display.set_mode((W, H), pygame.FULLSCREEN | pygame.SCALED)
    clock = pygame.time.Clock()

    font = pygame.font.SysFont("consolas", 16)
    font_big = pygame.font.SysFont("consolas", 20, bold=True)

    state = UIState()
    events_log: List[str] = []
    events_all: List[str] = []

    # matching metadata arrays
    events_log_meta: List[Optional[dict]] = []
    events_all_meta: List[Optional[dict]] = []

    # price + wealth history for charts
    price_history: dict[str, list[float]] = {g: [] for g in CHART_COLORS}
    wealth_history: list[dict] = []  # {"t", "gini", "top10pct", "total"}

    # map state
    map_surface = None
    map_town_pos: list[tuple[int, int]] = []
    map_river_pts: list[tuple[int, int]] = []
    map_trade_lines: list[dict] = []  # {"src", "dst", "age", "color"}
    MAP_W, MAP_H = 520, 400

    def _split_meta(line: str) -> tuple[str, Optional[dict]]:
        mark = " ⟦META:"
        i = line.rfind(mark)
        if i == -1:
            return line, None
        j = line.rfind("⟧")
        if j == -1 or j < i:
            return line, None
        payload = line[i + len(mark): j]
        try:
            meta = json.loads(payload)
        except Exception:
            return line, None
        return line[:i], meta

    def _apply_display_mode() -> None:
        nonlocal screen, W, H
        if state.fullscreen:
            screen = pygame.display.set_mode((W, H), pygame.FULLSCREEN | pygame.SCALED)
        else:
            screen = pygame.display.set_mode(state.windowed_size, pygame.SCALED)
        W, H = screen.get_size()

    sim_acc = 0.0

    def merchant_eta(town_id: int) -> int:
        m = world.merchant_town_id
        n = max(1, len(world.towns))
        if town_id == m:
            return 0
        if town_id > m:
            return town_id - m
        return (n - m) + town_id

    while True:
        clock.tick(60)
        W, H = screen.get_size()

        TAB_Y = 12
        ROW_H = font.get_height() + 2
        BIG_H = font_big.get_height() + 2

        HEADER_Y = TAB_Y + 34 + 8
        TOWN_Y = HEADER_Y + BIG_H + 10
        HINT_Y = TOWN_Y + 30 + 6
        PANEL_Y = HINT_Y + ROW_H + ROW_H + 10

        left = pygame.Rect(12, PANEL_Y, 520, H - (PANEL_Y + 12))
        right = pygame.Rect(548, PANEL_Y, W - 560, H - (PANEL_Y + 12))

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit()
                return

            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_SPACE:
                    state.paused = not state.paused
                if ev.key == pygame.K_F11:
                    state.fullscreen = not state.fullscreen
                    _apply_display_mode()
                    state.scroll = 0
                    state.brain_scroll = 0
                    state.rumor_scroll = 0
                if ev.key == pygame.K_TAB:
                    i = TABS.index(state.tab)
                    state.tab = TABS[(i + 1) % len(TABS)]
                    state.scroll = 0
                if ev.key == pygame.K_1:
                    state.speed = .02
                if ev.key == pygame.K_2:
                    state.speed = .8
                if ev.key == pygame.K_3:
                    state.speed = 1.25
                if ev.key == pygame.K_4:
                    state.speed = 8
                if ev.key == pygame.K_UP:
                    if state.tab == "Rumor":
                        state.rumor_scroll = max(0, state.rumor_scroll - 30)
                        continue
                    if state.tab == "Agent" and getattr(state, "agent_panel", "Profile") == "Brain":
                        state.brain_scroll = max(0, state.brain_scroll - 30)
                    else:
                        state.scroll = max(0, state.scroll - 30)

                if ev.key == pygame.K_DOWN:
                    if state.tab == "Rumor":
                        state.rumor_scroll += 30
                        continue
                    if state.tab == "Agent" and getattr(state, "agent_panel", "Profile") == "Brain":
                        state.brain_scroll += 30
                    else:
                        state.scroll += 30

                if state.tab == "Search":
                    if ev.key == pygame.K_BACKSPACE:
                        state.event_search = state.event_search[:-1]
                    elif ev.key == pygame.K_ESCAPE:
                        if state.tab == "Search":
                            state.event_search = ""
                        elif state.fullscreen:
                            state.fullscreen = False
                            _apply_display_mode()
                            state.scroll = 0
                            state.brain_scroll = 0
                            state.rumor_scroll = 0
                    elif ev.key == pygame.K_RETURN:
                        pass
                    else:
                        if ev.unicode and ev.unicode.isprintable():
                            state.event_search += ev.unicode

            if ev.type == pygame.MOUSEWHEEL:
                mx, my = pygame.mouse.get_pos()
                over_left = left.collidepoint((mx, my))
                over_right = right.collidepoint((mx, my))

                if state.tab == "Rumor":
                    if over_right:
                        state.rumor_scroll = max(0, state.rumor_scroll - ev.y * 30)
                    elif over_left:
                        state.scroll = max(0, state.scroll - ev.y * 30)
                    continue

                if state.tab == "Agent" and getattr(state, "agent_panel", "Profile") == "Brain":
                    if over_right:
                        state.brain_scroll = max(0, state.brain_scroll - ev.y * 30)
                    elif over_left:
                        state.scroll = max(0, state.scroll - ev.y * 30)
                elif state.tab == "Families":
                    if over_right:
                        state.family_scroll = max(0, state.family_scroll - ev.y * 30)
                    elif over_left:
                        state.scroll = max(0, state.scroll - ev.y * 30)
                else:
                    if over_left or over_right:
                        state.scroll = max(0, state.scroll - ev.y * 30)

            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                mx, my = ev.pos

                tab_x = 12
                for tname in TABS:
                    rect = pygame.Rect(tab_x, TAB_Y, 120, 34)
                    if rect.collidepoint((mx, my)):
                        state.tab = tname
                        state.scroll = 0
                    tab_x += 130

                nreg = len(getattr(world, "regions", [None]))
                rx0 = W - 12 - nreg * 54
                ry0 = TAB_Y + 42
                for i in range(nreg):
                    rect = pygame.Rect(rx0 + i * 54, ry0, 50, 34)
                    if rect.collidepoint((mx, my)):
                        state.selected_region = i
                        if hasattr(world, "active_region"):
                            world.active_region = i
                        state.selected_town = 0
                        state.scroll = 0

                tx = 12
                ty = TOWN_Y
                for i, town in enumerate(world.towns):
                    rect = pygame.Rect(tx, ty, 120, 30)
                    if rect.collidepoint((mx, my)):
                        state.selected_town = i
                        state.scroll = 0
                    tx += 128

                if state.tab in ("People", "Agent"):
                    list_rect = pygame.Rect(left.x, left.y, left.w, left.h)
                    if list_rect.collidepoint((mx, my)):
                        row = (my - (list_rect.y + 10) + state.scroll) // ROW_H
                        people = [a for a in world.agents if a.town_id == state.selected_town]
                        people.sort(key=lambda a: (-a.gold, a.name))
                        if 0 <= row < len(people):
                            state.follow_name = people[int(row)].name
                            state.tab = "Agent"
                            state.scroll = 0
                            state.agent_panel = "Profile"
                            state.brain_scroll = 0
                            state.show_opinions = True
                            state.show_grudges = True
                            state.show_memories = False

                if state.tab == "Agent" and state.follow_name:
                    right_rect = pygame.Rect(548, PANEL_Y, W - 560, H - (PANEL_Y + 12))
                    rx2 = right_rect.x + 12

                    profile_btn = pygame.Rect(rx2, right_rect.y + 44, 120, 30)
                    brain_btn   = pygame.Rect(rx2 + 128, right_rect.y + 44, 120, 30)

                    if profile_btn.collidepoint((mx, my)):
                        state.agent_panel = "Profile"
                        state.scroll = 0
                    if brain_btn.collidepoint((mx, my)):
                        state.agent_panel = "Brain"
                        state.brain_scroll = 0

                    if state.agent_panel == "Brain":
                        opinions_hdr = pygame.Rect(rx2, right_rect.y + 84, 260, 24)
                        grudges_hdr  = pygame.Rect(rx2, right_rect.y + 112, 260, 24)
                        memories_hdr = pygame.Rect(rx2, right_rect.y + 140, 260, 24)

                        if opinions_hdr.collidepoint((mx, my)):
                            state.show_opinions = not state.show_opinions
                            state.brain_scroll = 0
                        if grudges_hdr.collidepoint((mx, my)):
                            state.show_grudges = not state.show_grudges
                            state.brain_scroll = 0
                        if memories_hdr.collidepoint((mx, my)):
                            state.show_memories = not state.show_memories
                            state.brain_scroll = 0

                    # click on family link in Agent Profile
                    if state.agent_panel == "Profile":
                        a = next((x for x in world.agents if x.name == state.follow_name), None)
                        if a:
                            fam_id = getattr(a, "family_id", -1)
                            fam = world.families.get(fam_id) if hasattr(world, "families") else None
                            if fam:
                                # family link is roughly at y=right_rect.y + 84 + ~6 lines of text
                                fam_link_y = right_rect.y + 84 + ROW_H * 5
                                fam_link_rect = pygame.Rect(rx2, fam_link_y, 300, ROW_H + 4)
                                if fam_link_rect.collidepoint((mx, my)):
                                    state.selected_family_id = fam_id
                                    state.tab = "Families"
                                    state.family_scroll = 0
                                    state.scroll = 0

                # Families tab click handling -- click on family row to select
                if state.tab == "Families" and hasattr(world, "families"):
                    right_rect = pygame.Rect(548, PANEL_Y, W - 560, H - (PANEL_Y + 12))
                    rx2 = right_rect.x + 12
                    if state.selected_family_id >= 0:
                        # back button
                        back_rect = pygame.Rect(rx2, right_rect.y + 10, 80, 24)
                        if back_rect.collidepoint((mx, my)):
                            state.selected_family_id = -1
                            state.family_scroll = 0
                        # click on member name to open their Agent tab
                        fam = world.families.get(state.selected_family_id)
                        if fam:
                            members = sorted(
                                [a for a in world.agents if a.name in fam.members and getattr(a, "alive", True)],
                                key=lambda a: -a.gold
                            )
                            member_start_y = right_rect.y + 200  # approximate start of member list
                            for i, a in enumerate(members[:20]):
                                row_y = member_start_y + i * ROW_H - state.family_scroll
                                row_rect = pygame.Rect(rx2, row_y, right_rect.w - 24, ROW_H)
                                if row_rect.collidepoint((mx, my)):
                                    state.follow_name = a.name
                                    state.tab = "Agent"
                                    state.agent_panel = "Profile"
                                    state.scroll = 0
                                    break
                    else:
                        # click on family list to select one
                        fams = sorted(
                            [f for f in world.families.values() if f.living_count() > 0],
                            key=lambda f: -f.living_count()
                        )
                        list_start_y = right_rect.y + 10 + BIG_H + 8
                        row_h = ROW_H * 3 + 8  # each family card is ~3 rows tall
                        for i, fam in enumerate(fams):
                            row_y = list_start_y + i * row_h - state.family_scroll
                            row_rect = pygame.Rect(rx2, row_y, right_rect.w - 24, row_h)
                            if row_rect.collidepoint((mx, my)):
                                state.selected_family_id = fam.family_id
                                state.family_scroll = 0
                                break

                if state.tab == "Events":
                    right_rect = pygame.Rect(548, PANEL_Y, W - 560, H - (PANEL_Y + 12))
                    list_y0 = right_rect.y + 10 + BIG_H + 6
                    line_h = ROW_H

                    if right_rect.collidepoint((mx, my)) and my >= list_y0:
                        row = int((my - list_y0 + state.scroll) // line_h)

                        base = max(0, len(events_log) - 400)
                        count = len(events_log) - base
                        if 0 <= row < count:
                            idx = (len(events_log) - 1) - row
                            if idx >= base:
                                state.selected_event_i = idx

                                meta = events_log_meta[idx] if idx < len(events_log_meta) else None
                                if meta and meta.get("kind") == "gossip":
                                    btn = pygame.Rect(right_rect.x + right_rect.w - 44, list_y0 + row * line_h - state.scroll, 34, 18)
                                    if btn.collidepoint((mx, my)):
                                        state.rumor_subject = str(meta.get("subject", ""))
                                        state.rumor_claim = str(meta.get("claim", ""))
                                        state.rumor_scroll = 0
                                        state.tab = "Rumor"

        if not state.paused:
            sim_acc += state.speed
            steps = int(sim_acc)
            sim_acc -= steps

            for _ in range(steps):
                new_events = step_once()
                if new_events:
                    for raw in new_events:
                        line, meta = _split_meta(raw)
                        events_log.append(line)
                        events_log_meta.append(meta)
                        events_all.append(line)
                        events_all_meta.append(meta)

                    if len(events_log) > 8000:
                        events_log[:] = events_log[-6000:]
                        events_log_meta[:] = events_log_meta[-6000:]

                    if len(events_all) > 20000000000:
                        events_all[:] = events_all[-18000000000:]
                        events_all_meta[:] = events_all_meta[-18000000000:]

                # record price snapshot
                for g in CHART_COLORS:
                    try:
                        price_history[g].append(world.market.mid_price(g))
                        if len(price_history[g]) > PRICE_HIST_LEN:
                            price_history[g] = price_history[g][-PRICE_HIST_LEN:]
                    except Exception:
                        pass

                # spawn trade lines on map from trade events
                if new_events and map_town_pos:
                    for raw in new_events:
                        if "bought" in raw and "from" in raw:
                            # any P2P trade or market trade spawns a visual line
                            for raw2 in new_events:
                                _, meta = _split_meta(raw2)
                                if meta and meta.get("kind") in ("trade", "trade_credit"):
                                    bt = meta.get("buyer_town", 0)
                                    st = meta.get("seller_town", 0)
                                    if bt != st and bt < len(map_town_pos) and st < len(map_town_pos):
                                        map_trade_lines.append({
                                            "src": map_town_pos[st],
                                            "dst": map_town_pos[bt],
                                            "age": 0,
                                            "color": COL_GOLD,
                                        })
                            break  # only scan once per batch

                # generate map on first tick if not done yet
                if map_surface is None and len(world.towns) > 0:
                    map_surface, map_town_pos, map_river_pts = generate_map_surface(
                        42, MAP_W, MAP_H, len(world.towns)
                    )

                # record wealth snapshot (every 5 ticks to save memory)
                if world.t % 5 == 0:
                    golds = sorted([a.gold for a in world.agents])
                    n = len(golds)
                    total = sum(golds)
                    if n > 1 and total > 0:
                        num = sum((2*(i+1) - n - 1) * golds[i] for i in range(n))
                        gini = num / (n * total)
                        top10 = sum(golds[-max(1, n//10):])
                        wealth_history.append({"t": world.t, "gini": gini, "top10pct": top10/total, "total": total})
                        if len(wealth_history) > PRICE_HIST_LEN:
                            wealth_history[:] = wealth_history[-PRICE_HIST_LEN:]

        screen.fill(COL_BG)
        town = world.towns[state.selected_town]

        rtag = f"Region {getattr(world, 'active_region', 0)+1}/{len(getattr(world, 'regions', [None]))}"
        header = f"{rtag}   Turn {world.t}   Merchant @ {world.towns[world.merchant_town_id].name}   Market Gold {world.market.gold:.1f}"
        draw_text(screen, font_big, header, 12, HEADER_Y, (245, 245, 245))

        tab_x = 12
        for tname in TABS:
            rect = pygame.Rect(tab_x, TAB_Y, 120, 34)
            draw_button(screen, font_big, rect, tname, active=(tname == state.tab))
            tab_x += 130

        nreg = len(getattr(world, "regions", [None]))
        rx0 = W - 12 - nreg * 54
        ry0 = TAB_Y + 42
        for i in range(nreg):
            rect = pygame.Rect(rx0 + i * 54, ry0, 50, 34)
            draw_button(screen, font_big, rect, f"R{i+1}", active=(i == getattr(world, "active_region", 0)))

        tx = 12
        ty = TOWN_Y
        for i, town_btn in enumerate(world.towns):
            rect = pygame.Rect(tx, ty, 120, 30)
            draw_button(screen, font, rect, town_btn.name, active=(i == state.selected_town))
            eta = merchant_eta(i)
            badge = "HERE" if eta == 0 else f"{eta}d"
            draw_text(screen, font, badge, rect.x + rect.w - 38, rect.y + 7, (220, 220, 220))
            tx += 128

        merchant_status = (
            f"Merchant status: HERE in {town.name}"
            if world.merchant_town_id == state.selected_town
            else f"Merchant status: away from {town.name}"
        )
        draw_text(screen, font, merchant_status, 12, HINT_Y, COL_DIM)

        hint = f"SPACE pause   1/2/3/4 speed({state.speed}x)   TAB cycle tabs   Scroll wheel / \u2191\u2193"
        draw_text(screen, font, hint, 12, HINT_Y + ROW_H, COL_GHOST)

        # decorative carpet border between header area and panels
        border_y = PANEL_Y - 4
        for bx in range(12, W - 12, 8):
            c = COL_GOLD if (bx // 8) % 3 == 0 else COL_RUST if (bx // 8) % 3 == 1 else COL_BORDER
            pygame.draw.rect(screen, c, (bx, border_y, 4, 2))

        left = pygame.Rect(12, PANEL_Y, 520, H - (PANEL_Y + 12))
        right = pygame.Rect(548, PANEL_Y, W - 560, H - (PANEL_Y + 12))
        pygame.draw.rect(screen, COL_PANEL, left, border_radius=14)
        pygame.draw.rect(screen, COL_PANEL, right, border_radius=14)
        pygame.draw.rect(screen, COL_BORDER, left, 2, border_radius=14)
        pygame.draw.rect(screen, COL_BORDER, right, 2, border_radius=14)

        left_clip = left.inflate(-16, -16)
        right_clip = right.inflate(-16, -16)

        people = [a for a in world.agents if a.town_id == state.selected_town and getattr(a, "alive", True)]
        people.sort(key=lambda a: (-a.gold, a.name))
        y0 = left.y + 10 - state.scroll
        for a in people:
            cls = getattr(a, "social_class", "")
            s100 = int(round((getattr(a, "status", 0.5) - 0.5) * 200.0))
            age_y = getattr(a, "age", 0) // 12
            if a.job == "child":
                line = f"{a.name:<14} {'child':<10} {age_y:3d}y"
                row_color = COL_GHOST
            else:
                line = f"{a.name:<14} {a.job:<10} {cls[:4]:<4} {age_y:2d}y  g={a.gold:6.1f} f={edible_count(a.inv):2d}"
                row_color = CLASS_COLORS.get(cls, COL_TEXT)
            if state.follow_name == a.name:
                highlight = pygame.Rect(left.x + 8, y0 - 2, left.w - 16, 20)
                old_clip = screen.get_clip()
                screen.set_clip(left_clip)
                pygame.draw.rect(screen, COL_HIGHLIGHT, highlight, border_radius=8)
                screen.set_clip(old_clip)
            y0 = draw_text(screen, font, line, left.x + 10, y0, row_color, clip_rect=left_clip)

        rx = right.x + 12

        if state.tab == "People":
            ry = right.y + 10
            ry = draw_text(screen, font_big, f"{town.name} overview", rx, ry, clip_rect=right_clip)
            res = ", ".join(sorted(list(town.resources)))
            ry = draw_wrapped_text(screen, font, f"Resources: {res}", rx, ry, right.w - 24, clip_rect=right_clip)
            eta = merchant_eta(state.selected_town)
            ry = draw_wrapped_text(screen, font, f"Merchant ETA: {'HERE' if eta==0 else str(eta)+' days'}", rx, ry, right.w - 24, clip_rect=right_clip)
            ry = draw_wrapped_text(screen, font, "Tip: click a person on the left to open Agent tab.", rx, ry, right.w - 24, clip_rect=right_clip)

        elif state.tab == "Market":
            ry = right.y + 10
            ry = draw_text(screen, font_big, "Merchant Guild Market", rx, ry, clip_rect=right_clip)
            if world.merchant_town_id != state.selected_town:
                ry = draw_wrapped_text(
                    screen, font,
                    "Merchant is not in this town right now, so locals cannot trade with the market.",
                    rx, ry, right.w - 24, (220, 190, 190), clip_rect=right_clip
                )
            else:
                ry = draw_wrapped_text(
                    screen, font,
                    "Merchant is HERE. Locals can buy and sell with the global stock.",
                    rx, ry, right.w - 24, (190, 220, 190), clip_rect=right_clip
                )
            ry += 6
            show = ["food","wood","ore","stone","tools","cloth","bread","plank","ingot","garment","furniture","ring","scimitar","wagon","lockbox"]
            for g in show:
                if g not in world.market.stock:
                    continue
                s = world.market.stock[g]
                mid = world.market.mid_price(g)
                bp = world.market.buy_price(g)
                sp = world.market.sell_price(g)
                line = f"{g:<10} stock={s:4d}  mid={mid:6.2f}  buy={bp:6.2f}  sell={sp:6.2f}"
                ry = draw_text(screen, font, line, rx, ry, clip_rect=right_clip)

        elif state.tab == "Families":
            ry = right.y + 10 - state.family_scroll

            if not hasattr(world, "families") or not world.families:
                ry = draw_text(screen, font_big, "No families yet", rx, ry, COL_GHOST, clip_rect=right_clip)

            elif state.selected_family_id >= 0:
                fam = world.families.get(state.selected_family_id)
                if fam is None:
                    state.selected_family_id = -1
                else:
                    # back button
                    back_rect = pygame.Rect(rx, right.y + 10, 80, 24)
                    draw_button(screen, font, back_rect, "< Back", active=False)
                    ry = right.y + 40

                    # family header
                    old_clip = screen.get_clip()
                    screen.set_clip(right_clip)

                    ry = draw_text(screen, font_big, f"The {fam.surname} Family", rx, ry, COL_GOLD, clip_rect=right_clip)
                    ry += 4

                    # stats row
                    members_alive = [a for a in world.agents if a.name in fam.members and getattr(a, "alive", True)]
                    members_dead = [a for a in world.agents if a.name in fam.deceased or (a.name in fam.members and not getattr(a, "alive", True))]
                    total_gold = sum(a.gold for a in members_alive)
                    total_food = sum(edible_count(a.inv) for a in members_alive)

                    ry = draw_text(screen, font, f"Living: {len(members_alive)}   Deceased: {len(members_dead)}   Head: {fam.head}", rx, ry, COL_TEXT, clip_rect=right_clip)
                    ry = draw_text(screen, font, f"Total gold: {total_gold:.0f}   Pool: {fam.wealth_pool:.0f}   Reputation: {fam.reputation:.2f}", rx, ry, COL_RUST, clip_rect=right_clip)
                    ry = draw_text(screen, font, f"Town: {world.towns[fam.town_id].name if fam.town_id < len(world.towns) else '?'}", rx, ry, COL_DIM, clip_rect=right_clip)

                    # alliances and feuds
                    if fam.alliances:
                        allies = []
                        for fid, strength in sorted(fam.alliances.items(), key=lambda kv: -kv[1])[:5]:
                            afam = world.families.get(fid)
                            if afam:
                                allies.append(f"{afam.surname} ({strength:.1f})")
                        if allies:
                            ry = draw_text(screen, font, f"Allies: {', '.join(allies)}", rx, ry, COL_TEAL, clip_rect=right_clip)
                    if fam.feuds:
                        feuds = []
                        for fid, intensity in sorted(fam.feuds.items(), key=lambda kv: -kv[1])[:5]:
                            ffam = world.families.get(fid)
                            if ffam:
                                feuds.append(f"{ffam.surname} ({intensity:.1f})")
                        if feuds:
                            ry = draw_text(screen, font, f"Feuds: {', '.join(feuds)}", rx, ry, COL_RED, clip_rect=right_clip)
                    ry += 8

                    # notable members section
                    ry = draw_text(screen, font_big, "Notable Members", rx, ry, clip_rect=right_clip)
                    ry += 2

                    if members_alive:
                        # richest
                        richest = max(members_alive, key=lambda a: a.gold)
                        cls_c = CLASS_COLORS.get(getattr(richest, "social_class", ""), COL_TEXT)
                        ry = draw_text(screen, font, f"Wealthiest: {richest.name} ({richest.job}) {richest.gold:.0f}g", rx, ry, cls_c, clip_rect=right_clip)

                        # highest status
                        highest = max(members_alive, key=lambda a: a.status)
                        cls_c = CLASS_COLORS.get(getattr(highest, "social_class", ""), COL_TEXT)
                        ry = draw_text(screen, font, f"Highest status: {highest.name} ({highest.social_class}) {highest.status:.2f}", rx, ry, cls_c, clip_rect=right_clip)

                        # oldest
                        oldest = max(members_alive, key=lambda a: a.age)
                        ry = draw_text(screen, font, f"Eldest: {oldest.name} age {oldest.age // 12}y ({oldest.job})", rx, ry, COL_DIM, clip_rect=right_clip)

                        # most children
                        most_kids = max(members_alive, key=lambda a: len(getattr(a, "children", [])))
                        nkids = len(getattr(most_kids, "children", []))
                        if nkids > 0:
                            ry = draw_text(screen, font, f"Most children: {most_kids.name} ({nkids} children)", rx, ry, COL_DIM, clip_rect=right_clip)

                        # biggest producer (most gold earned ~ highest gold among workers)
                        workers = [a for a in members_alive if a.job != "child"]
                        if workers:
                            top_earner = max(workers, key=lambda a: a.gold)
                            ry = draw_text(screen, font, f"Top earner: {top_earner.name} ({top_earner.job}) {top_earner.gold:.0f}g", rx, ry, COL_TEAL, clip_rect=right_clip)
                    ry += 8

                    # member list
                    ry = draw_text(screen, font_big, "Members (click to inspect)", rx, ry, clip_rect=right_clip)
                    ry += 2
                    members_sorted = sorted(members_alive, key=lambda a: -a.gold)
                    for a in members_sorted[:20]:
                        cls_c = CLASS_COLORS.get(getattr(a, "social_class", ""), COL_TEXT)
                        age_y = getattr(a, "age", 0) // 12
                        spouse_str = f"m:{a.spouse[:8]}" if getattr(a, "spouse", None) else ""
                        line = f"{a.name:<14} {a.job:<10} {age_y:3d}y  g={a.gold:7.1f}  {spouse_str}"
                        # highlight row on hover (approximate)
                        ry = draw_text(screen, font, line, rx, ry, cls_c, clip_rect=right_clip)
                    if len(members_sorted) > 20:
                        ry = draw_text(screen, font, f"... {len(members_sorted) - 20} more", rx, ry, COL_GHOST, clip_rect=right_clip)

                    screen.set_clip(old_clip)

            else:
                # family list view
                ry = draw_text(screen, font_big, "Families (click to inspect)", rx, ry, COL_GOLD, clip_rect=right_clip)
                ry += 8

                fams = sorted(
                    [f for f in world.families.values() if f.living_count() > 0],
                    key=lambda f: -f.living_count()
                )

                old_clip = screen.get_clip()
                screen.set_clip(right_clip)

                for fam in fams:
                    members_alive = [a for a in world.agents if a.name in fam.members and getattr(a, "alive", True)]
                    total_gold = sum(a.gold for a in members_alive)
                    town_name = world.towns[fam.town_id].name if fam.town_id < len(world.towns) else "?"

                    # family card background
                    card_h = ROW_H * 3 + 4
                    card_rect = pygame.Rect(rx - 4, ry - 2, right.w - 28, card_h)
                    pygame.draw.rect(screen, COL_HIGHLIGHT, card_rect, border_radius=6)
                    pygame.draw.rect(screen, COL_BORDER, card_rect, 1, border_radius=6)

                    # reputation bar
                    rep_w = int(60 * fam.reputation)
                    pygame.draw.rect(screen, COL_BORDER, (rx + right.w - 100, ry + 2, 60, 8), border_radius=3)
                    pygame.draw.rect(screen, COL_GOLD, (rx + right.w - 100, ry + 2, max(1, rep_w), 8), border_radius=3)

                    ry = draw_text(screen, font_big, f"{fam.surname}", rx, ry, COL_GOLD, clip_rect=right_clip)
                    ry = draw_text(screen, font, f"{fam.living_count()} living   {len(fam.deceased)} deceased   {town_name}   gold: {total_gold:.0f}", rx, ry, COL_DIM, clip_rect=right_clip)
                    ry = draw_text(screen, font, f"Head: {fam.head}   Rep: {fam.reputation:.2f}   Pool: {fam.wealth_pool:.0f}", rx, ry, COL_GHOST, clip_rect=right_clip)
                    ry += 8

                    if ry > right.y + right.h:
                        break

                screen.set_clip(old_clip)

        elif state.tab == "Map":
            ry = right.y + 10
            ry = draw_text(screen, font_big, "Trade Map", rx, ry, COL_GOLD, clip_rect=right_clip)
            ry += 4

            # generate map if needed
            if map_surface is None and len(world.towns) > 0:
                map_surface, map_town_pos, map_river_pts = generate_map_surface(
                    42, MAP_W, MAP_H, len(world.towns)
                )

            if map_surface is not None:
                old_clip = screen.get_clip()
                screen.set_clip(right_clip)

                # blit the static background
                map_x = rx
                map_y = ry
                screen.blit(map_surface, (map_x, map_y))

                # age and draw trade lines
                alive = []
                for tl in map_trade_lines:
                    tl["age"] += 1
                    if tl["age"] > 60:
                        continue
                    alive.append(tl)
                    alpha = max(0, 255 - tl["age"] * 4)
                    fade = (
                        min(255, COL_GOLD[0] * alpha // 255),
                        min(255, COL_GOLD[1] * alpha // 255),
                        min(255, COL_GOLD[2] * alpha // 255),
                    )
                    sx, sy = tl["src"]
                    dx, dy = tl["dst"]
                    pygame.draw.line(screen, fade, (map_x + sx, map_y + sy), (map_x + dx, map_y + dy), 1)
                map_trade_lines[:] = alive[-80:]  # cap

                # draw merchant sprite at current town
                mt = world.merchant_town_id
                if mt < len(map_town_pos):
                    mx, my = map_town_pos[mt]
                    _draw_merchant_sprite(screen, map_x + mx, map_y + my - 18, scale=1)

                # draw town names
                for i, (tx, ty) in enumerate(map_town_pos):
                    if i < len(world.towns):
                        tname = world.towns[i].name
                        pop = len([a for a in world.agents if a.town_id == i])
                        # highlight selected town
                        if i == state.selected_town:
                            pygame.draw.circle(screen, COL_GOLD, (map_x + tx, map_y + ty), 22, 1)
                        # merchant here indicator
                        if i == world.merchant_town_id:
                            draw_text(screen, font, "M", map_x + tx + 12, map_y + ty - 16, COL_GOLD, clip_rect=right_clip)
                        label_color = COL_TEXT if i == state.selected_town else COL_DIM
                        draw_text(screen, font, f"{tname} ({pop})", map_x + tx - 20, map_y + ty + 14, label_color, clip_rect=right_clip)

                # draw traveling agents as small dots on the map
                for a in world.agents:
                    if not getattr(a, "traveling", False):
                        continue
                    src_id = getattr(a, "travel_src", 0)
                    dst_id = getattr(a, "travel_dst", 0)
                    if src_id < len(map_town_pos) and dst_id < len(map_town_pos):
                        sx, sy = map_town_pos[src_id]
                        dx, dy = map_town_pos[dst_id]
                        eta = getattr(a, "travel_eta", 1)
                        dist = max(1, abs(dst_id - src_id))
                        progress = max(0.0, min(1.0, 1.0 - eta / dist))
                        px = int(sx + (dx - sx) * progress)
                        py = int(sy + (dy - sy) * progress)
                        pygame.draw.circle(screen, COL_TEXT, (map_x + px, map_y + py), 2)

                screen.set_clip(old_clip)
                ry = map_y + MAP_H + 8

                # map legend
                draw_text(screen, font, "Castles = towns  Gold lines = trades  Dot = traveler  M = merchant", rx, ry, COL_GHOST, clip_rect=right_clip)

        elif state.tab == "Towns":
            ry = right.y + 10 - state.scroll
            ry = draw_text(screen, font_big, "Towns + expedition stock", rx, ry, clip_rect=right_clip)
            for i, twn in enumerate(world.towns):
                eta = merchant_eta(i)
                tag = "HERE" if eta == 0 else f"ETA {eta}d"
                line = f"{twn.name:<10}  {tag:<6}  resources: {', '.join(sorted(twn.resources))}"
                ry = draw_wrapped_text(screen, font, line, rx, ry, right.w - 24, clip_rect=right_clip)
                base = ["food","wood","ore","stone","tools","cloth"]
                s2 = "  ".join([f"{g}:{twn.local_stock.get(g,0)}" for g in base])
                ry = draw_text(screen, font, "    local_stock: " + s2, rx, ry, clip_rect=right_clip)

                town_agents_here = [a for a in world.agents if a.town_id == i and not getattr(a, "traveling", False)]
                edible_total = sum(edible_count(a.inv) for a in town_agents_here)
                ry = draw_text(screen, font, f"    edible carried by residents: {edible_total}", rx, ry, clip_rect=right_clip)

        elif state.tab == "Economy":
            ry = right.y + 10
            ry = draw_text(screen, font_big, "Price History", rx, ry, COL_GOLD, clip_rect=right_clip)
            ry += 4

            # draw line chart of price history
            chart_x = rx
            chart_y = ry
            chart_w = right.w - 32
            chart_h = 200

            old_clip = screen.get_clip()
            screen.set_clip(right_clip)
            pygame.draw.rect(screen, (32, 30, 24), (chart_x, chart_y, chart_w, chart_h), border_radius=6)
            pygame.draw.rect(screen, COL_BORDER, (chart_x, chart_y, chart_w, chart_h), 1, border_radius=6)

            # find global min/max across all tracked goods
            all_prices = []
            for g, hist in price_history.items():
                all_prices.extend(hist)
            if all_prices:
                p_min = max(0, min(all_prices) * 0.8)
                p_max = max(all_prices) * 1.1
                if p_max <= p_min:
                    p_max = p_min + 1

                # y-axis labels
                for i in range(5):
                    val = p_min + (p_max - p_min) * (1 - i / 4)
                    ly = chart_y + 4 + int((chart_h - 8) * i / 4)
                    draw_text(screen, font, f"{val:.1f}", chart_x + 2, ly - 6, COL_GHOST, clip_rect=right_clip)
                    pygame.draw.line(screen, (40, 38, 30), (chart_x + 38, ly), (chart_x + chart_w - 4, ly), 1)

                # draw each good's line
                for g, color in CHART_COLORS.items():
                    hist = price_history.get(g, [])
                    if len(hist) < 2:
                        continue
                    pts = []
                    for i, p in enumerate(hist):
                        px = chart_x + 40 + int((chart_w - 48) * i / max(1, len(hist) - 1))
                        py = chart_y + 4 + int((chart_h - 8) * (1 - (p - p_min) / (p_max - p_min)))
                        pts.append((px, py))
                    if len(pts) >= 2:
                        pygame.draw.lines(screen, color, False, pts, 2)

            screen.set_clip(old_clip)
            ry = chart_y + chart_h + 8

            # legend -- draw horizontally with manual text width measurement
            old_clip2 = screen.get_clip()
            screen.set_clip(right_clip)
            lx = rx
            for g, color in CHART_COLORS.items():
                label = f" {g}"
                label_w = font.size(label)[0]
                if lx + 14 + label_w > rx + chart_w:
                    lx = rx
                    ry += ROW_H
                pygame.draw.rect(screen, color, (lx, ry + 3, 10, 10))
                draw_text(screen, font, label, lx + 12, ry, COL_DIM, clip_rect=right_clip)
                lx += 14 + label_w + 8
            screen.set_clip(old_clip2)
            ry += ROW_H + 10

            # wealth inequality chart
            ry = draw_text(screen, font_big, "Wealth Inequality", rx, ry, COL_GOLD, clip_rect=right_clip)
            ry += 4

            chart_y2 = ry
            chart_h2 = 140
            old_clip = screen.get_clip()
            screen.set_clip(right_clip)
            pygame.draw.rect(screen, (32, 30, 24), (chart_x, chart_y2, chart_w, chart_h2), border_radius=6)
            pygame.draw.rect(screen, COL_BORDER, (chart_x, chart_y2, chart_w, chart_h2), 1, border_radius=6)

            if len(wealth_history) >= 2:
                # Gini line (0..1)
                pts_gini = []
                pts_top10 = []
                for i, w in enumerate(wealth_history):
                    px = chart_x + 40 + int((chart_w - 48) * i / max(1, len(wealth_history) - 1))
                    gy = chart_y2 + 4 + int((chart_h2 - 8) * (1 - w["gini"]))
                    ty = chart_y2 + 4 + int((chart_h2 - 8) * (1 - w["top10pct"]))
                    pts_gini.append((px, gy))
                    pts_top10.append((px, ty))
                if len(pts_gini) >= 2:
                    pygame.draw.lines(screen, COL_RUST, False, pts_gini, 2)
                if len(pts_top10) >= 2:
                    pygame.draw.lines(screen, COL_BLUE, False, pts_top10, 2)

                # axis labels
                for i in range(5):
                    val = 1.0 - i / 4
                    ly = chart_y2 + 4 + int((chart_h2 - 8) * i / 4)
                    draw_text(screen, font, f"{val:.1f}", chart_x + 2, ly - 6, COL_GHOST, clip_rect=right_clip)

            screen.set_clip(old_clip)
            ry = chart_y2 + chart_h2 + 6

            # legend
            pygame.draw.rect(screen, COL_RUST, (rx, ry + 2, 10, 10))
            draw_text(screen, font, " Gini", rx + 12, ry, COL_DIM, clip_rect=right_clip)
            pygame.draw.rect(screen, COL_BLUE, (rx + 80, ry + 2, 10, 10))
            draw_text(screen, font, " Top 10% share", rx + 92, ry, COL_DIM, clip_rect=right_clip)

        elif state.tab == "Stats":
            ry = right.y + 10 - state.scroll
            ry = draw_text(screen, font_big, f"Stats \u2022 {town.name}", rx, ry, COL_GOLD, clip_rect=right_clip)
            ry += 6

            town_agents = [a for a in world.agents if a.town_id == state.selected_town]
            classes = {"poor": 0, "common": 0, "comfortable": 0, "elite": 0}
            jobs: dict[str, int] = {}
            total_gold = 0.0
            total_food = 0
            for a in town_agents:
                cls_name = getattr(a, "social_class", "common")
                classes[cls_name] = classes.get(cls_name, 0) + 1
                jobs[a.job] = jobs.get(a.job, 0) + 1
                total_gold += a.gold
                total_food += edible_count(a.inv)

            n_agents = len(town_agents)
            avg_gold = total_gold / n_agents if n_agents > 0 else 0

            # summary cards
            ry = draw_text(screen, font, f"Population: {n_agents}", rx, ry, COL_TEXT, clip_rect=right_clip)
            ry = draw_text(screen, font, f"Total gold: {total_gold:.0f}   Avg: {avg_gold:.1f}", rx, ry, COL_RUST, clip_rect=right_clip)
            ry = draw_text(screen, font, f"Total food: {total_food}", rx, ry, COL_TEAL, clip_rect=right_clip)

            # Gini
            golds = sorted([a.gold for a in town_agents])
            if n_agents > 1 and total_gold > 0:
                num = sum((2*(i+1) - n_agents - 1) * golds[i] for i in range(n_agents))
                gini = num / (n_agents * total_gold)
                ry = draw_text(screen, font, f"Gini coefficient: {gini:.3f}", rx, ry, COL_DIM, clip_rect=right_clip)
            ry += 8

            # class breakdown
            ry = draw_text(screen, font_big, "Social Classes", rx, ry, clip_rect=right_clip)
            old_clip = screen.get_clip()
            screen.set_clip(right_clip)
            for cls_name in ("poor", "common", "comfortable", "elite"):
                count = classes.get(cls_name, 0)
                color = CLASS_COLORS.get(cls_name, COL_TEXT)
                bar_w = int((right.w - 80) * count / max(1, n_agents))
                pygame.draw.rect(screen, color, (rx + 100, ry + 2, max(1, bar_w), 12), border_radius=3)
                ry = draw_text(screen, font, f"{cls_name:<12} {count:3d}", rx, ry, color, clip_rect=right_clip)
            screen.set_clip(old_clip)
            ry += 8

            # job breakdown
            ry = draw_text(screen, font_big, "Jobs", rx, ry, clip_rect=right_clip)
            old_clip = screen.get_clip()
            screen.set_clip(right_clip)
            for job, count in sorted(jobs.items(), key=lambda kv: -kv[1]):
                bar_w = int((right.w - 120) * count / max(1, n_agents))
                pygame.draw.rect(screen, COL_BORDER, (rx + 120, ry + 2, max(1, bar_w), 12), border_radius=3)
                ry = draw_text(screen, font, f"{job:<14} {count:3d}", rx, ry, COL_DIM, clip_rect=right_clip)
            screen.set_clip(old_clip)

            ry += 8

            # top 5 richest
            ry = draw_text(screen, font_big, "Wealthiest", rx, ry, clip_rect=right_clip)
            richest = sorted(town_agents, key=lambda a: -a.gold)[:5]
            for i, a in enumerate(richest):
                cls_c = CLASS_COLORS.get(getattr(a, "social_class", ""), COL_TEXT)
                ry = draw_text(screen, font, f"{i+1}. {a.name:<14} {a.job:<10} {a.gold:8.1f}g", rx, ry, cls_c, clip_rect=right_clip)

            ry += 8

            # top 5 poorest
            ry = draw_text(screen, font_big, "Poorest", rx, ry, clip_rect=right_clip)
            poorest = sorted(town_agents, key=lambda a: a.gold)[:5]
            for i, a in enumerate(poorest):
                cls_c = CLASS_COLORS.get(getattr(a, "social_class", ""), COL_TEXT)
                ry = draw_text(screen, font, f"{i+1}. {a.name:<14} {a.job:<10} {a.gold:8.1f}g", rx, ry, cls_c, clip_rect=right_clip)

        elif state.tab == "Inn":
            ry = right.y + 10 - state.scroll
            ry = draw_text(screen, font_big, f"Inn • {town.name}", rx, ry, clip_rect=right_clip)
            ry += 6

            visitors = [
                a for a in world.agents
                if (not getattr(a, "traveling", False))
                and a.town_id == state.selected_town
                and getattr(a, "native_town_id", a.town_id) != a.town_id
            ]
            arriving = [
                a for a in world.agents
                if getattr(a, "traveling", False)
                and getattr(a, "travel_dst", -1) == state.selected_town
            ]
            departing = [
                a for a in world.agents
                if getattr(a, "traveling", False)
                and getattr(a, "travel_src", -1) == state.selected_town
            ]

            ry = draw_text(screen, font, f"Visitors here: {len(visitors)}", rx, ry, clip_rect=right_clip)
            for a in sorted(visitors, key=lambda x: (-x.gold, x.name))[:24]:
                src = world.towns[getattr(a, "native_town_id", a.town_id)].name
                ry = draw_text(screen, font, f"{a.name:<14} ({a.job:<10}) g={a.gold:6.1f}  from {src}", rx, ry, clip_rect=right_clip)

            ry += 8
            ry = draw_text(screen, font, f"Arriving soon: {len(arriving)}", rx, ry, clip_rect=right_clip)
            for a in sorted(arriving, key=lambda x: (getattr(x, "travel_eta", 999), x.name))[:24]:
                eta = getattr(a, "travel_eta", 0)
                src = world.towns[getattr(a, "travel_src", a.town_id)].name
                ry = draw_text(screen, font, f"{a.name:<14} ETA {eta:2d}d  from {src}", rx, ry, clip_rect=right_clip)

            ry += 8
            ry = draw_text(screen, font, f"Departed / en route: {len(departing)}", rx, ry, clip_rect=right_clip)
            for a in sorted(departing, key=lambda x: (getattr(x, "travel_eta", 999), x.name))[:18]:
                eta = getattr(a, "travel_eta", 0)
                dst = world.towns[getattr(a, "travel_dst", a.town_id)].name
                ry = draw_text(screen, font, f"{a.name:<14} ETA {eta:2d}d  to {dst}", rx, ry, clip_rect=right_clip)

        elif state.tab == "Events":
            ry = right.y + 10 - state.scroll
            ry = draw_text(screen, font_big, "Recent events (global)", rx, ry, clip_rect=right_clip)
            ry += 6
            base = max(0, len(events_log) - 400)
            indices = list(range(base, len(events_log)))
            indices.reverse()

            y = ry
            for idx in indices:
                line = events_log[idx]
                meta = events_log_meta[idx] if idx < len(events_log_meta) else None

                line_rect = pygame.Rect(rx, y - 2, right.w - 24, ROW_H)

                if idx == state.selected_event_i:
                    old_clip = screen.get_clip()
                    screen.set_clip(right_clip)
                    pygame.draw.rect(screen, (45, 45, 70), line_rect, border_radius=8)
                    screen.set_clip(old_clip)

                    if meta and meta.get("kind") == "gossip":
                        btn = pygame.Rect(right.x + right.w - 44, y - 1, 34, 18)
                        draw_button(screen, font, btn, "≡", active=False)

                y = draw_text(screen, font, line, rx, y, clip_rect=right_clip)
                if y > right.y + right.h - 18:
                    break

        elif state.tab == "Search":
            ry = right.y + 10
            ry = draw_text(screen, font_big, "Event search (newest → oldest)", rx, ry, clip_rect=right_clip)
            ry = draw_text(screen, font, f"Query: {state.event_search}", rx, ry, clip_rect=right_clip)
            ry = draw_text(screen, font, "Type to search • BACKSPACE delete • ESC clear", rx, ry, clip_rect=right_clip)
            ry += 8

            q = state.event_search.strip().lower()
            hay = list(reversed(events_all))
            if q:
                hay = [ln for ln in hay if q in ln.lower()]

            y = ry - state.scroll
            for line in hay[:1200]:
                y = draw_text(screen, font, line, rx, y, clip_rect=right_clip)
                if y > right.y + right.h - 18:
                    break

        elif state.tab == "Rumor":
            ry = right.y + 10
            if not state.rumor_subject or not state.rumor_claim:
                ry = draw_text(screen, font_big, "Rumor genealogy", rx, ry, clip_rect=right_clip)
                ry = draw_text(screen, font, "Select a gossip event in Events, then click ≡.", rx, ry, clip_rect=right_clip)
            else:
                ry = draw_text(screen, font_big, "Rumor genealogy", rx, ry, clip_rect=right_clip)
                ry = draw_text(screen, font, f"Subject: {state.rumor_subject}", rx, ry, clip_rect=right_clip)
                ry = draw_text(screen, font, f"Claim:   {state.rumor_claim}", rx, ry, clip_rect=right_clip)
                ry = draw_text(screen, font, "Oldest → newest (scroll)", rx, ry, clip_rect=right_clip)
                ry += 8

                rows = []
                for meta in events_all_meta:
                    if not meta or meta.get("kind") != "gossip":
                        continue
                    if str(meta.get("subject", "")) != state.rumor_subject:
                        continue
                    if str(meta.get("claim", "")) != state.rumor_claim:
                        continue
                    rows.append(meta)

                rows.sort(key=lambda m: int(m.get("t", 0)))

                y = ry - state.rumor_scroll
                for m in rows:
                    t = int(m.get("t", 0))
                    sp = str(m.get("speaker", "?"))
                    ls = str(m.get("listener", "?"))
                    st = int(m.get("speaker_town", -1))
                    lt = int(m.get("listener_town", -1))
                    st_name = world.towns[st].name if 0 <= st < len(world.towns) else f"Town{st}"
                    lt_name = world.towns[lt].name if 0 <= lt < len(world.towns) else f"Town{lt}"

                    y = draw_text(screen, font, f"t{t:<4} {sp} → {ls}   ({st_name} → {lt_name})", rx, y, clip_rect=right_clip)
                    if y > right.y + right.h - 18:
                        break

        elif state.tab == "Agent":
            ry = right.y + 10
            name = state.follow_name
            if not name:
                ry = draw_text(screen, font, "Click a person on the left to inspect.", rx, ry, clip_rect=right_clip)
            else:
                a = next((x for x in world.agents if x.name == name), None)
                if a is None:
                    state.follow_name = None
                else:
                    ry = draw_text(screen, font_big, f"{a.name}  ({a.job})  {world.towns[a.town_id].name}", rx, ry, clip_rect=right_clip)
                    profile_btn = pygame.Rect(rx, right.y + 44, 120, 30)
                    brain_btn   = pygame.Rect(rx + 128, right.y + 44, 120, 30)
                    draw_button(screen, font, profile_btn, "Profile", active=(state.agent_panel == "Profile"))
                    draw_button(screen, font, brain_btn, "Brain", active=(state.agent_panel == "Brain"))
                    ry = right.y + 84

                    if state.agent_panel == "Profile":
                        # lifecycle info
                        age_y = getattr(a, "age", 0) // 12
                        age_m = getattr(a, "age", 0) % 12
                        alive_str = "alive" if getattr(a, "alive", True) else f"dead ({getattr(a, 'cause_of_death', '?')})"
                        ry = draw_text(screen, font, f"Age: {age_y}y {age_m}m  ({alive_str})", rx, ry, clip_rect=right_clip)
                        ry = draw_text(screen, font, f"Gold: {a.gold:.2f}   Food: {edible_count(a.inv)}", rx, ry, COL_RUST, clip_rect=right_clip)

                        # spouse
                        spouse = getattr(a, "spouse", None)
                        if spouse:
                            ry = draw_text(screen, font, f"Spouse: {spouse}", rx, ry, COL_TEAL, clip_rect=right_clip)

                        # children
                        kids = getattr(a, "children", [])
                        if kids:
                            ry = draw_text(screen, font, f"Children: {', '.join(kids[:6])}" + (f" +{len(kids)-6}" if len(kids) > 6 else ""), rx, ry, COL_DIM, clip_rect=right_clip)

                        # parents
                        parents = getattr(a, "parents", None)
                        if parents:
                            ry = draw_text(screen, font, f"Parents: {parents[0]}, {parents[1]}", rx, ry, COL_DIM, clip_rect=right_clip)

                        # family link (clickable)
                        fam_id = getattr(a, "family_id", -1)
                        fam = world.families.get(fam_id) if hasattr(world, "families") else None
                        if fam:
                            fam_rect = pygame.Rect(rx, ry, 300, ROW_H + 2)
                            ry = draw_text(screen, font, f"Family: {fam.surname} ({fam.living_count()} living)  [click to view]", rx, ry, COL_GOLD, clip_rect=right_clip)
                        ry += 4

                        # tags
                        tags = ", ".join([f"{k}:{v:.2f}" for k, v in sorted(a.tags.items())]) or "none"
                        ry = draw_text(screen, font, f"Tags: {tags}", rx, ry, clip_rect=right_clip)
                        ry += 6

                        # inventory
                        inv_items = [(g, q) for g, q in a.inv.items() if q > 0]
                        inv_items.sort(key=lambda kv: (-kv[1], kv[0]))
                        ry = draw_text(screen, font_big, "Inventory", rx, ry, clip_rect=right_clip)
                        for g, q in inv_items[:28]:
                            ry = draw_text(screen, font, f"{g:<10} x{q}", rx, ry, clip_rect=right_clip)
                        if len(inv_items) > 28:
                            ry = draw_text(screen, font, f"... {len(inv_items)-28} more", rx, ry, clip_rect=right_clip)
                    else:
                        def hdr(label: str, on: bool, y0: int) -> None:
                            rect = pygame.Rect(rx, y0, 260, 24)
                            draw_button(screen, font, rect, ("▾ " if on else "▸ ") + label, active=False)

                        hdr("Opinions", state.show_opinions, right.y + 84)
                        hdr("Grudges",  state.show_grudges,  right.y + 112)
                        hdr("Memories", state.show_memories, right.y + 140)

                        # clip brain content below the toggle headers
                        brain_content_top = right.y + 168
                        brain_clip = pygame.Rect(right_clip.x, brain_content_top, right_clip.w, right.y + right.h - brain_content_top - 8)

                        y = brain_content_top - state.brain_scroll

                        if state.show_opinions:
                            y = draw_text(screen, font_big, "Opinions (-100..100, |<=15| hidden)", rx, y, clip_rect=brain_clip)

                            items = []
                            for who, v in a.trust.items():
                                if who == a.name:
                                    continue
                                score = int(round((v - 0.50) * 200.0))
                                if abs(score) <= 15:
                                    continue
                                items.append((abs(score), score, who, v))

                            items.sort(reverse=True)

                            if not items:
                                y = draw_text(screen, font, "none", rx, y, clip_rect=brain_clip)
                            else:
                                for _, score, who, v in items[:60]:
                                    vibe = "like" if score > 0 else "hate"
                                    y = draw_text(screen, font, f"{who:<14} {vibe:<4} op={score:+4d}", rx, y, clip_rect=brain_clip)
                                    if y > right.y + right.h - 18:
                                        break

                            y += 10

                        if state.show_grudges:
                            y = draw_text(screen, font_big, "Grudges", rx, y, clip_rect=brain_clip)
                            gs = list(getattr(a, "grudges", {}).values())
                            gs.sort(key=lambda g: (g.strength, g.last_event_t), reverse=True)
                            if not gs:
                                y = draw_text(screen, font, "none", rx, y, clip_rect=brain_clip)
                            else:
                                for g in gs[:60]:
                                    y = draw_text(screen, font, f"{g.target:<14} str={g.strength:.2f}  {g.reason}", rx, y, clip_rect=brain_clip)
                                    if y > right.y + right.h - 18:
                                        break
                            y += 10

                        if state.show_memories:
                            y = draw_text(screen, font_big, "Memories (recent)", rx, y, clip_rect=brain_clip)
                            for m in reversed(getattr(a, "memory", [])[-120:]):
                                y = draw_text(screen, font, f"t{m.t:<4} {m.kind:<12} {m.content}", rx, y, clip_rect=brain_clip)
                                if y > right.y + right.h - 18:
                                    break

                    if state.agent_panel == "Profile":
                        ry += 6
                        active = [g for g in a.goals if not g.resolved]
                        active.sort(key=lambda g: g.deadline_t)
                        ry = draw_text(screen, font_big, "Goals", rx, ry, clip_rect=right_clip)
                        for g in active[:10]:
                            have = a.inv.get(g.good, 0)
                            line = f"[{g.size}] {g.good} x{g.qty}  (have {have})  due t={g.deadline_t}"
                            ry = draw_text(screen, font, line, rx, ry, clip_rect=right_clip)
                        if not active:
                            ry = draw_text(screen, font, "none right now", rx, ry, clip_rect=right_clip)

        pygame.display.flip()