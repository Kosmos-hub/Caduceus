# town_diorama_portal.py
import numpy as np
import pyglet
import moderngl
import os
import threading
import time
import cv2
import mediapipe as mp
import random
import ctypes
import math
from collections import deque
import town_sim as sim

# =========================
# CONFIG
# =========================
CONFIG = {
    'window_width': 1920,
    'window_height': 1080,

    'portal_x': 300,
    'portal_y': 120,
    'portal_width': 900,
    'portal_height': 600,

    'room_depth': 14.0,
    'grid_divisions': 14,
    'grid_color': (0.62, 0.22, 0.88),
    'background_color': (0.01, 0.01, 0.02),

    # Town sim viz
    'sim_seed': 40,
    'sim_agents': 80,
    'sim_tick_hz': 6.0,          # how fast the sim advances (turns/sec)
    'active_region': 0,          # multiverse active region
    'show_all_towns': True,      # render all towns as panels (True) or only active town (False)

    # Map layout (portal is the map)
    'scene_mode': 'map',
    'map_width': 26.0,          # world units across the portal
    'map_height': 16.0,
    'map_margin': 0.9,
    'map_z': -4.0,              # draw depth for lines

    # Desert styling
    'sand_base': (0.20, 0.16, 0.10),
    'sand_lines': (0.85, 0.70, 0.35),
    'oasis_color': (0.35, 1.00, 0.65),
    'route_color': (1.00, 0.78, 0.25),
    'town_color': (0.92, 0.82, 0.55),
    'merchant_color': (1.00, 0.95, 0.55),
    'danger_color': (1.00, 0.35, 0.45),

    # Map detail
    'dune_band_count': 22,
    'dune_wobble': 0.55,
    'dune_density': 48,
    'town_radius': 0.16,
    'agent_radius': 0.07,
}

# =========================
# Shaders
# =========================
VERT_SHADER = """
#version 330
in vec3 in_pos;
in vec3 in_col;
uniform mat4 u_mvp;
out vec3 v_col;
void main() {
    v_col = in_col;
    gl_Position = u_mvp * vec4(in_pos, 1.0);
}
"""

FRAG_SHADER = """
#version 330
in vec3 v_col;
out vec4 f_color;
void main() {
    f_color = vec4(v_col, 1.0);
}
"""

# =========================
# Math helpers
# =========================
def normalize(v):
    n = float(np.linalg.norm(v))
    if n < 1e-9:
        return v
    return v / n

def off_axis_projection(pa, pb, pc, pe, n=0.1, f=100.0):
    vr = normalize(pb - pa)
    vu = normalize(pc - pa)
    vn = normalize(np.cross(vr, vu))

    va = pa - pe
    vb = pb - pe
    vc = pc - pe

    d = -np.dot(va, vn)
    if d < 1e-6:
        d = 1e-6

    l = np.dot(vr, va) * (n / d)
    r = np.dot(vr, vb) * (n / d)
    b = np.dot(vu, va) * (n / d)
    t = np.dot(vu, vc) * (n / d)

    P = np.zeros((4, 4), dtype=np.float32)
    P[0, 0] = 2 * n / (r - l)
    P[1, 1] = 2 * n / (t - b)
    P[0, 2] = (r + l) / (r - l)
    P[1, 2] = (t + b) / (t - b)
    P[2, 2] = -(f + n) / (f - n)
    P[2, 3] = -(2 * f * n) / (f - n)
    P[3, 2] = -1.0
    return P, vr, vu, vn

def view_from_screen_basis(pe, vr, vu, vn):
    R = np.eye(4, dtype=np.float32)
    R[0, :3] = vr
    R[1, :3] = vu
    R[2, :3] = vn

    T = np.eye(4, dtype=np.float32)
    T[:3, 3] = -pe
    return R @ T

def ortho_projection(l, r, b, t, n, f):
    P = np.eye(4, dtype=np.float32)
    P[0, 0] = 2.0 / (r - l)
    P[1, 1] = 2.0 / (t - b)
    P[2, 2] = -2.0 / (f - n)
    P[0, 3] = -(r + l) / (r - l)
    P[1, 3] = -(t + b) / (t - b)
    P[2, 3] = -(f + n) / (f - n)
    return P

# =========================
# Head tracker (MediaPipe)
# =========================
class HeadTracker:
    def __init__(self, cam_index=0):
        self.cam_index = cam_index
        self.lock = threading.Lock()
        self.running = False
        self.target_x = 0.0
        self.target_y = 0.0
        self.target_z = 0.6
        self.display_x = 0.0
        self.display_y = 0.0
        self.display_z = 0.6
        self.camera_smoothing = 0.3
        self.display_smoothing = 0.08

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False

    def get(self):
        return self.display_x, self.display_y, self.display_z

    def update_display(self, dt):
        with self.lock:
            tx, ty, tz = self.target_x, self.target_y, self.target_z
        factor = 1.0 - math.pow(1.0 - self.display_smoothing, dt * 60.0)
        self.display_x += (tx - self.display_x) * factor
        self.display_y += (ty - self.display_y) * factor
        self.display_z += (tz - self.display_z) * factor

    def _run(self):
        cap = cv2.VideoCapture(self.cam_index)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        BaseOptions = mp.tasks.BaseOptions
        FaceLandmarker = mp.tasks.vision.FaceLandmarker
        FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
        VisionRunningMode = mp.tasks.vision.RunningMode

        model_path = os.path.join(os.path.dirname(__file__), "face_landmarker.task")
        options = FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=VisionRunningMode.VIDEO,
            num_faces=1,
        )

        smooth_x, smooth_y, smooth_z = 0.0, 0.0, 0.6
        with FaceLandmarker.create_from_options(options) as landmarker:
            timestamp_ms = 0
            last_t = time.time()

            while self.running:
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.01)
                    continue

                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)

                now = time.time()
                dt = now - last_t
                last_t = now
                timestamp_ms += int(max(1, dt * 1000.0))

                result = landmarker.detect_for_video(mp_image, timestamp_ms)

                if result.face_landmarks:
                    lm = result.face_landmarks[0]
                    nose = lm[1]
                    left = lm[234]
                    right = lm[454]

                    cx = nose.x - 0.5
                    cy = nose.y - 0.5

                    face_w = abs(left.x - right.x)
                    if face_w < 1e-4:
                        face_w = 1e-4
                    dz = 0.25 / face_w

                    alpha = self.camera_smoothing
                    smooth_x += (cx - smooth_x) * alpha
                    smooth_y += (cy - smooth_y) * alpha
                    smooth_z += (dz - smooth_z) * alpha
                    with self.lock:
                        self.target_x = smooth_x
                        self.target_y = smooth_y
                        self.target_z = smooth_z

                time.sleep(0.008)

        cap.release()

# =========================
# Town viz (line-art diorama)
# =========================
def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)

def _mix(a, b, t: float):
    return (a[0] + (b[0] - a[0]) * t,
            a[1] + (b[1] - a[1]) * t,
            a[2] + (b[2] - a[2]) * t)

RESOURCE_COLORS = {
    "food": (0.55, 1.00, 0.55),
    "wood": (0.55, 0.95, 0.85),
    "ore": (0.70, 0.75, 1.00),
    "stone": (0.85, 0.85, 0.95),
    "tools": (1.00, 0.80, 0.55),
    "cloth": (1.00, 0.60, 0.85),
}

CLASS_COLORS = {
    "poor": (0.80, 0.80, 0.90),
    "common": (0.70, 0.88, 1.00),
    "comfortable": (0.75, 1.00, 0.78),
    "elite": (1.00, 0.86, 0.45),
}

def job_color(job: str):
    # stable-ish mapping without importing extra junk
    h = 0
    for ch in job:
        h = (h * 131 + ord(ch)) & 0xFFFFFFFF
    t = (h % 1000) / 999.0
    a = (0.55, 0.65, 1.00)
    b = (1.00, 0.55, 0.85)
    c = (0.65, 1.00, 0.80)
    return _mix(_mix(a, b, t), c, 0.35)

class MapViz:
    def __init__(self, room_w, room_h, room_d):
        self.room_w = float(room_w)
        self.room_h = float(room_h)
        self.room_d = float(room_d)

    def _add_line(self, verts, p1, p2, c):
        verts.extend([p1[0], p1[1], p1[2], c[0], c[1], c[2]])
        verts.extend([p2[0], p2[1], p2[2], c[0], c[1], c[2]])

    def _add_rect(self, verts, x0, y0, x1, y1, z, c):
        self._add_line(verts, (x0, y0, z), (x1, y0, z), c)
        self._add_line(verts, (x1, y0, z), (x1, y1, z), c)
        self._add_line(verts, (x1, y1, z), (x0, y1, z), c)
        self._add_line(verts, (x0, y1, z), (x0, y0, z), c)

    def _add_x(self, verts, x, y, z, r, c):
        self._add_line(verts, (x - r, y - r, z), (x + r, y + r, z), c)
        self._add_line(verts, (x - r, y + r, z), (x + r, y - r, z), c)

    def build_geometry(self, multiverse, recent_events=None):
        # choose which worlds to draw
        if CONFIG.get("show_all_towns", False) and hasattr(multiverse, "regions"):
            worlds = list(multiverse.regions)
        else:
            worlds = [multiverse.current()]

        # panel layout (2x2 for 4 regions)
        cols = 2
        rows = 2
        gap = 0.55

        verts = []
        mw = float(CONFIG['map_width']) * 0.5
        md = float(CONFIG['room_depth'])  # reuse room_depth as map depth into screen
        margin = float(CONFIG['map_margin'])

        # total drawable area inside the frame
        xL, xR = (-mw + margin), (mw - margin)
        zF, zB = (-md + margin), (-margin)

        panel_w = (xR - xL - gap * (cols - 1)) / cols
        panel_h = (zB - zF - gap * (rows - 1)) / rows


        # map plane in XZ, sitting slightly above the sand plane
        y0 = -float(CONFIG['map_height']) * 0.5 + 0.35

        def add_line(p1, p2, c):
            self._add_line(verts, (p1[0], y0, p1[1]), (p2[0], y0, p2[1]), c)

        def add_circle(cx, cy, r, c, steps=16):
            ang0 = 0.0
            for i in range(steps):
                a0 = (i / steps) * math.tau
                a1 = ((i + 1) / steps) * math.tau
                x0 = cx + math.cos(a0) * r
                y0 = cy + math.sin(a0) * r
                x1 = cx + math.cos(a1) * r
                y1 = cy + math.sin(a1) * r
                add_line((x0, y0), (x1, y1), c)

        def town_xy(town, idx, n):
            # Try common town position fields; fallback to a nice desert ring layout
            p = getattr(town, "pos", None)
            if p is not None and len(p) >= 2:
                x, y = float(p[0]), float(p[1])
                return x, y

            x = getattr(town, "x", None)
            y = getattr(town, "y", None)
            if x is not None and y is not None:
                return float(x), float(y)

            wp = getattr(town, "world_pos", None)
            if wp is not None and len(wp) >= 2:
                return float(wp[0]), float(wp[1])

            # fallback: ring + jitter
            t = 0.0 if n <= 1 else (idx / max(1, n))
            ang = t * math.tau
            rr = 0.72
            return math.cos(ang) * mw * rr, math.sin(ang) * md * rr

        # MAP FRAME
        frame_c = CONFIG['sand_lines']
        # frame in XZ plane
        xA, xB = -mw + margin, mw - margin
        zA, zB = -md + margin, -margin
        add_line((xA, zA), (xB, zA), frame_c)
        add_line((xB, zA), (xB, zB), frame_c)
        add_line((xB, zB), (xA, zB), frame_c)
        add_line((xA, zB), (xA, zA), frame_c)

        # DUNE CONTOUR BANDS
        dune_c = CONFIG['sand_lines']
        bands = int(CONFIG['dune_band_count'])
        steps = int(CONFIG['dune_density'])
        wob = float(CONFIG['dune_wobble'])
        for bi in range(bands):
            zline = -md + margin + (bi / max(1, bands - 1)) * (md - margin)
            phase = bi * 0.65
            last = None
            for si in range(steps + 1):
                x = -mw + margin + (si / steps) * (2 * (mw - margin))
                zz = zline + math.sin((x * 0.55) + phase) * wob + math.sin((x * 0.18) - phase * 1.7) * (wob * 0.55)
                p = (x, zz)
                if last is not None:
                    add_line(last, p, dune_c)
                last = p

        for rid, w in enumerate(worlds):
            towns = list(getattr(w, "towns", []))
            agents = list(getattr(w, "agents", []))
            merchant_tid = int(getattr(w, "merchant_town_id", 0))

            # pick which panel this region goes in
            c = rid % cols
            r = rid // cols
            px0 = xL + c * (panel_w + gap)
            px1 = px0 + panel_w
            pz0 = zF + r * (panel_h + gap)
            pz1 = pz0 + panel_h

            # optional: panel frame so you can SEE the 4 regions
            panel_c = _mix(CONFIG['sand_lines'], CONFIG['sand_base'], 0.35)
            add_line((px0, pz0), (px1, pz0), panel_c)
            add_line((px1, pz0), (px1, pz1), panel_c)
            add_line((px1, pz1), (px0, pz1), panel_c)
            add_line((px0, pz1), (px0, pz0), panel_c)

            # local town positions -> normalized into this panel
            n = len(towns)
            town_pos = {}

            raw = [town_xy(towns[i], i, n) for i in range(n)] if n else []
            if raw:
                xs = [p[0] for p in raw]
                ys = [p[1] for p in raw]
                minx, maxx = min(xs), max(xs)
                miny, maxy = min(ys), max(ys)
                spanx = max(1e-6, maxx - minx)
                spany = max(1e-6, maxy - miny)

                for i, town in enumerate(towns):
                    tid = int(getattr(town, "town_id", i))
                    rx, ry = raw[i]
                    nx = (rx - minx) / spanx
                    ny = (ry - miny) / spany

                    x = px0 + nx * (px1 - px0)
                    z = pz0 + (1.0 - ny) * (pz1 - pz0)
                    town_pos[tid] = (x, z)

            # ROUTES (inside this region only)
            route_c = CONFIG['route_color']
            if n >= 2:
                edges = getattr(w, "routes", None)
                if edges is None:
                    edges = getattr(w, "trade_routes", None)

                if edges:
                    for e in edges:
                        a = int(getattr(e, "a", getattr(e, "src", getattr(e, "from_id", -1))))
                        b = int(getattr(e, "b", getattr(e, "dst", getattr(e, "to_id", -1))))
                        if a in town_pos and b in town_pos:
                            add_line(town_pos[a], town_pos[b], route_c)
                else:
                    loop_c = _mix(route_c, CONFIG['sand_base'], 0.55)
                    ids = sorted(list(town_pos.keys()))
                    if len(ids) >= 2:
                        for i in range(len(ids)):
                            a0 = ids[i]
                            b0 = ids[(i + 1) % len(ids)]
                            add_line(town_pos[a0], town_pos[b0], loop_c)

                    if merchant_tid in town_pos:
                        for tid, p in town_pos.items():
                            if tid != merchant_tid:
                                add_line(town_pos[merchant_tid], p, route_c)

            # TOWNS
            tr = float(CONFIG['town_radius'])
            base_goods = ["food", "wood", "ore", "stone", "tools", "cloth"]

            town_by_id = {int(getattr(tw, "town_id", -1)): tw for tw in towns}

            for tid, (x, y) in town_pos.items():
                is_merchant = (tid == merchant_tid)
                core_c = CONFIG['merchant_color'] if is_merchant else CONFIG['town_color']
                add_circle(x, y, tr, core_c, steps=18)

                wall = tr * 1.25
                add_line((x - wall, y - wall), (x + wall, y - wall), core_c)
                add_line((x + wall, y - wall), (x + wall, y + wall), core_c)
                add_line((x + wall, y + wall), (x - wall, y + wall), core_c)
                add_line((x - wall, y + wall), (x - wall, y - wall), core_c)

                tw = town_by_id.get(tid)
                res = set(getattr(tw, "resources", set())) if tw is not None else set()

                for i, g in enumerate(base_goods):
                    ang = (i / len(base_goods)) * math.tau + 0.25
                    has = (g in res)
                    inner = tr * 1.10
                    outer = tr * (2.30 if has else 1.55)

                    col = RESOURCE_COLORS.get(g, core_c)
                    if not has:
                        col = _mix(col, CONFIG['sand_base'], 0.70)

                    x0 = x + math.cos(ang) * inner
                    y0 = y + math.sin(ang) * inner
                    x1 = x + math.cos(ang) * outer
                    y1 = y + math.sin(ang) * outer
                    add_line((x0, y0), (x1, y1), col)

                if is_merchant:
                    add_circle(x, y, tr * 2.8, CONFIG['route_color'], steps=22)

            # AGENTS
            ar = float(CONFIG['agent_radius'])
            for a in agents:
                tid = int(getattr(a, "town_id", 0))
                x, y = town_pos.get(tid, (0.0, 0.0))

                if getattr(a, "traveling", False):
                    dtid = getattr(a, "dest_town_id", None)
                    if dtid is None:
                        dtid = getattr(a, "destination_town_id", None)
                    if dtid is not None and int(dtid) in town_pos:
                        dx, dy = town_pos[int(dtid)]
                        prog = getattr(a, "travel_progress", None)
                        if prog is None:
                            prog = getattr(a, "travel_t", None)
                        if prog is None:
                            prog = 0.5
                        prog = _clamp01(float(prog))
                        x = x + (dx - x) * prog
                        y = y + (dy - y) * prog

                sc = getattr(a, "social_class", "common")
                cc = CLASS_COLORS.get(sc, (0.70, 0.88, 1.00))
                jc = job_color(getattr(a, "job", "trader"))
                ccol = _mix(cc, jc, 0.60)
                add_circle(x, y, ar, ccol, steps=10)


        # little compass / north marker
        comp_c = dune_c
        cx = mw - margin * 1.25
        cy = -margin * 1.25
        add_line((cx, cy - 0.7), (cx, cy + 0.7), comp_c)
        add_line((cx - 0.35, cy + 0.35), (cx, cy + 0.7), comp_c)
        add_line((cx + 0.35, cy + 0.35), (cx, cy + 0.7), comp_c)

        return np.array(verts, dtype=np.float32)

def _extract_meta(line: str):
    tag = "⟦META:"
    i = line.find(tag)
    if i < 0:
        return None
    j = line.rfind("⟧")
    if j < 0:
        return None
    payload = line[i + len(tag):j]
    try:
        import json
        return json.loads(payload)
    except Exception:
        return None


# =========================
# Town sim adapter
# =========================
def _call_first(obj, names, *args, default=None, **kwargs):
    for n in names:
        fn = getattr(obj, n, None)
        if callable(fn):
            return fn(*args, **kwargs)
    return default

class TownSimAdapter:
    def __init__(self, *, seed: int, n_agents: int, active_region: int = 0):
        rng = random.Random(int(seed))
        self.multi = sim.make_multiverse(rng, total_pop=int(n_agents))
        self.multi.active_region = int(active_region)

        self._accum = 0.0
        self._tick_dt = 1.0 / max(1e-6, float(CONFIG['sim_tick_hz']))
        self.recent_events = deque(maxlen=240)
        self.last_logs = []

    def update(self, dt):
        self._accum += dt
        # advance in discrete turns so behavior matches your sim
        while self._accum >= self._tick_dt:
            self._accum -= self._tick_dt
            logs = self.multi.tick()
            self.last_logs = logs

            # parse META payloads embedded in log strings
            for line in logs:
                meta = _extract_meta(line)
                if meta is not None:
                    self.recent_events.append(meta)


    def get_world(self):
        return self.multi


# =========================
# Main Application
# =========================
class TownDioramaPortal(pyglet.window.Window):
    def __init__(self):
        config = pyglet.gl.Config(
            double_buffer=True,
            depth_size=24,
            sample_buffers=1,
            samples=4,
            alpha_size=8,
        )

        try:
            super().__init__(
                CONFIG['window_width'],
                CONFIG['window_height'],
                "Town Diorama Portal",
                style=pyglet.window.Window.WINDOW_STYLE_BORDERLESS,
                config=config
            )
        except:
            super().__init__(
                CONFIG['window_width'],
                CONFIG['window_height'],
                "Town Diorama Portal",
                style=pyglet.window.Window.WINDOW_STYLE_BORDERLESS
            )

        self._make_transparent()

        self.switch_to()
        self.ctx = moderngl.create_context(require=330)
        self.ctx.enable(moderngl.DEPTH_TEST)
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self.ctx.viewport = (0, 0, self.width, self.height)
        self.ctx.line_width = 2.0

        self.prog = self.ctx.program(vertex_shader=VERT_SHADER, fragment_shader=FRAG_SHADER)

        self.portal_x = CONFIG['portal_x']
        self.portal_y = CONFIG['portal_y']
        self.portal_width = CONFIG['portal_width']
        self.portal_height = CONFIG['portal_height']

        aspect = self.portal_width / self.portal_height

        # screen plane size (the "window" you look through)
        map_height = float(CONFIG['map_height'])
        map_width = map_height * aspect

        self.map_depth = float(CONFIG['room_depth'])  # reuse config key as map depth
        self.map_width = map_width
        self.map_height = map_height

        self.screen_half_width = self.map_width / 2
        self.screen_half_height = self.map_height / 2

        self.pa = np.array([-self.screen_half_width, -self.screen_half_height, 0], dtype=np.float32)
        self.pb = np.array([ self.screen_half_width, -self.screen_half_height, 0], dtype=np.float32)
        self.pc = np.array([-self.screen_half_width,  self.screen_half_height, 0], dtype=np.float32)

        self.pe = np.array([0, 0, 6], dtype=np.float32)

        self.bounds_inside = (
            np.array([-self.screen_half_width, -self.screen_half_height, -self.map_depth], dtype=np.float32),
            np.array([ self.screen_half_width,  self.screen_half_height,  0.0], dtype=np.float32)
        )

        self.bounds_outside = (
            np.array([-self.screen_half_width * 1.6, -self.screen_half_height * 1.6, 0.0], dtype=np.float32),
            np.array([ self.screen_half_width * 1.6,  self.screen_half_height * 1.6, self.map_depth * 0.5], dtype=np.float32)
        )

        self.t = 0.0

        self.sim = TownSimAdapter(
            seed=CONFIG['sim_seed'],
            n_agents=CONFIG['sim_agents'],
            active_region=CONFIG['active_region'],
        )
        self.viz = MapViz(self.map_width, self.map_height, self.map_depth)

        self.tracker = HeadTracker(cam_index=0)
        self.tracker.start()

        pyglet.clock.schedule_interval(self.update, 1 / 60.0)

        self.dragging = False

    def _make_transparent(self):
        try:
            hwnd = ctypes.windll.user32.GetActiveWindow()
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x80000
            LWA_COLORKEY = 0x1

            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)
            ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0x00000000, 0, LWA_COLORKEY)
        except Exception as e:
            print(f"Could not make window transparent: {e}")

    def on_mouse_press(self, x, y, button, modifiers):
        if button == pyglet.window.mouse.LEFT:
            self.dragging = True

    def on_mouse_release(self, x, y, button, modifiers):
        if button == pyglet.window.mouse.LEFT:
            self.dragging = False

    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        if self.dragging:
            win_x, win_y = self.get_location()
            self.set_location(win_x + dx, win_y + dy)

    def update(self, dt):
        self.t += dt

        self.tracker.update_display(dt)
        tx, ty, tz = self.tracker.get()
        self.pe[0] = -tx * 12.0
        self.pe[1] = -ty * 8.0
        self.pe[2] = 3.0 + tz * 4.0

        self.sim.update(dt)

    def on_resize(self, width, height):
        super().on_resize(width, height)
        self.ctx.viewport = (0, 0, width, height)

    def on_close(self):
        if hasattr(self, "tracker"):
            self.tracker.stop()
        super().on_close()

    def on_draw(self):
        self.ctx.clear(0.0, 0.0, 0.0, 0.0)

        P, vr, vu, vn = off_axis_projection(self.pa, self.pb, self.pc, self.pe, n=0.1, f=100.0)
        V = view_from_screen_basis(self.pe, vr, vu, vn)
        M = np.eye(4, dtype=np.float32)
        MVP = P @ V @ M

        portal_y_gl = self.height - self.portal_y - self.portal_height
        self.ctx.viewport = (self.portal_x, portal_y_gl, self.portal_width, self.portal_height)

        self.prog["u_mvp"].write(MVP.T.tobytes())

        bg = CONFIG['sand_base']
        hw, hh = self.screen_half_width, self.screen_half_height
        z0 = 0.0
        z1 = -self.map_depth
        y = -hh + 0.15

        bg_verts = np.array([
            -hw, y, z0, bg[0], bg[1], bg[2],
             hw, y, z0, bg[0], bg[1], bg[2],
             hw, y, z1, bg[0], bg[1], bg[2],

            -hw, y, z0, bg[0], bg[1], bg[2],
             hw, y, z1, bg[0], bg[1], bg[2],
            -hw, y, z1, bg[0], bg[1], bg[2],
        ], dtype=np.float32)

        bg_vbo = self.ctx.buffer(bg_verts.tobytes())
        bg_vao = self.ctx.vertex_array(self.prog, [(bg_vbo, "3f 3f", "in_pos", "in_col")])
        bg_vao.render(mode=moderngl.TRIANGLES)
        bg_vbo.release()

        inside_verts = []
        geom = self.viz.build_geometry(self.sim.get_world(), recent_events=self.sim.recent_events)
        if len(geom) > 0:
            inside_verts = geom.tolist()

        if inside_verts:
            data = np.array(inside_verts, dtype=np.float32)
            vbo = self.ctx.buffer(data.tobytes())
            vao = self.ctx.vertex_array(self.prog, [(vbo, "3f 3f", "in_pos", "in_col")])
            vao.render(mode=moderngl.LINES, vertices=len(inside_verts) // 6)
            vbo.release()

        self.ctx.viewport = (0, 0, self.width, self.height)

    def on_key_press(self, symbol, modifiers):
        if symbol == pyglet.window.key.ESCAPE:
            self.close()

if __name__ == "__main__":
    app = TownDioramaPortal()
    pyglet.app.run()
