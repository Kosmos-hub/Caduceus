# ui_screens.py
# Minimal pygame UI for town_sim.py (multi-town + travelling merchant market)

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional
import json
import pygame
from town_sim import edible_count


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


TABS = ("People", "Market", "Towns", "Inn", "Events", "Search", "Rumor", "Agent")


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

        screen.fill((18, 18, 22))
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
        draw_text(screen, font, merchant_status, 12, HINT_Y, (205, 205, 225))

        hint = f"SPACE pause   1/2/3/4 speed({state.speed}x)   TAB cycle tabs   Scroll wheel / ↑↓"
        draw_text(screen, font, hint, 12, HINT_Y + ROW_H, (170, 170, 190))

        left = pygame.Rect(12, PANEL_Y, 520, H - (PANEL_Y + 12))
        right = pygame.Rect(548, PANEL_Y, W - 560, H - (PANEL_Y + 12))
        pygame.draw.rect(screen, (24, 24, 30), left, border_radius=14)
        pygame.draw.rect(screen, (24, 24, 30), right, border_radius=14)
        pygame.draw.rect(screen, (60, 60, 75), left, 2, border_radius=14)
        pygame.draw.rect(screen, (60, 60, 75), right, 2, border_radius=14)

        left_clip = left.inflate(-16, -16)
        right_clip = right.inflate(-16, -16)

        people = [a for a in world.agents if a.town_id == state.selected_town]
        people.sort(key=lambda a: (-a.gold, a.name))
        y0 = left.y + 10 - state.scroll
        for a in people:
            cls = getattr(a, "social_class", "")
            s100 = int(round((getattr(a, "status", 0.5) - 0.5) * 200.0))
            line = f"{a.name:<14} {a.job:<10} {cls[:4]:<4} s={s100:+4d}  g={a.gold:6.1f} food={edible_count(a.inv):2d}"
            if state.follow_name == a.name:
                highlight = pygame.Rect(left.x + 8, y0 - 2, left.w - 16, 20)
                old_clip = screen.get_clip()
                screen.set_clip(left_clip)
                pygame.draw.rect(screen, (45, 45, 70), highlight, border_radius=8)
                screen.set_clip(old_clip)
            y0 = draw_text(screen, font, line, left.x + 10, y0, clip_rect=left_clip)

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
                        ry = draw_text(screen, font, f"Gold: {a.gold:.2f}", rx, ry, clip_rect=right_clip)
                        ry = draw_text(screen, font, f"Edible food: {edible_count(a.inv)}", rx, ry, clip_rect=right_clip)
                        tags = ", ".join([f"{k}:{v:.2f}" for k, v in sorted(a.tags.items())]) or "none"
                        ry = draw_text(screen, font, f"Tags: {tags}", rx, ry, clip_rect=right_clip)
                        ry += 6
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

                        y = right.y + 170 - state.brain_scroll

                        if state.show_opinions:
                            y = draw_text(screen, font_big, "Opinions (-100..100, |<=15| hidden)", rx, y, clip_rect=right_clip)

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
                                y = draw_text(screen, font, "none", rx, y, clip_rect=right_clip)
                            else:
                                for _, score, who, v in items[:60]:
                                    vibe = "like" if score > 0 else "hate"
                                    y = draw_text(screen, font, f"{who:<14} {vibe:<4} op={score:+4d}", rx, y, clip_rect=right_clip)
                                    if y > right.y + right.h - 18:
                                        break

                            y += 10

                        if state.show_grudges:
                            y = draw_text(screen, font_big, "Grudges", rx, y, clip_rect=right_clip)
                            gs = list(getattr(a, "grudges", {}).values())
                            gs.sort(key=lambda g: (g.strength, g.last_event_t), reverse=True)
                            if not gs:
                                y = draw_text(screen, font, "none", rx, y, clip_rect=right_clip)
                            else:
                                for g in gs[:60]:
                                    y = draw_text(screen, font, f"{g.target:<14} str={g.strength:.2f}  {g.reason}", rx, y, clip_rect=right_clip)
                                    if y > right.y + right.h - 18:
                                        break
                            y += 10

                        if state.show_memories:
                            y = draw_text(screen, font_big, "Memories (recent)", rx, y, clip_rect=right_clip)
                            for m in reversed(getattr(a, "memory", [])[-120:]):
                                y = draw_text(screen, font, f"t{m.t:<4} {m.kind:<12} {m.content}", rx, y, clip_rect=right_clip)
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