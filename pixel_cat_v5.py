#!/usr/bin/env python3
"""
COZY CAT - a pixel-art cat (Pet Cats Pack) living in a cozy room (cozy pack) with a hill view (Free Pixel Art Hill).
Chat with it using Ollama (text or voice).

Install:   pip install pygame
Voice in:  pip install SpeechRecognition pyaudio              (talk to the cat with your mic)
Voice out: pip install edge-tts                               (natural, different voice per cat - needs internet)
           (no install needed for the offline 'cat-ese' chirp voice;  pip install pyttsx3 for your system voice)
Ollama:    https://ollama.com  ->  ollama pull llama3.2

Put the art next to this script (extract the zips/rar there):
    Pet Cats Pack/        (from Pet_Cats_Pack.zip)       <- required, CC0
    cozy/                 (from cozy.zip)                <- props: bookshelves, bed, coffee, bread...
    Free Pixel Art Hill/  (extract the .rar with 7-Zip)  <- scrolling hills in the window

Run:       python pixel_cat_v5.py
           python pixel_cat_v5.py --cat 3 --model qwen2.5:3b --voice edge
Test AI:   python pixel_cat_v5.py --test

Controls
  Enter  talk (TEXT: type + Enter / VOICE: speak)     Tab  TEXT <-> VOICE     S  cat voice on/off
  V change voice style   M mic   F treat   B ball   Hold Space = laser pointer   R reconnect to Ollama
  Left click: pet the cat / drag+throw the ball     Right click: drop a ball     1-6: change cat     Esc: quit
"""
import argparse, json, math, os, queue, random, re, subprocess, sys, threading, time
import urllib.error, urllib.request
from array import array
from collections import deque
import pygame

W, H = 192, 108            # pixel-art canvas: art is drawn 1:1 (scaled up on screen)
FLOOR = 100                # y where the cat's feet touch the floor
GRAV = 380.0
TAU = math.tau
Q = queue.Queue()          # messages from background threads -> main loop
HERE = os.path.dirname(os.path.abspath(__file__))


def clamp(v, a, b):
    return max(a, min(b, v))


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def R(s, c, x, y, w, h):
    pygame.draw.rect(s, c, (x, y, w, h))


# ============================================================================
# THE SIX CATS (Pet Cats Pack: Cat-1 .. Cat-6) + their personalities
# ============================================================================
CATS = {
    1: dict(name="Mango", color=(230, 150, 70),      # ginger
            trait="goofy, endlessly hungry and hyper. Thinks about food constantly, loves everyone, not very bright but very happy.",
            speed=1.2, play=0.9, lazy=0.2, hungry=0.008,
            lines=["is it snack time??", "FOOD?", "*zoomies*", "i love you. also, food.", "mew mew mew!"]),
    2: dict(name="Shadow", color=(150, 120, 190),    # black
            trait="mysterious night owl with dry humor. Loves dark corners, speaks in short cool lines, secretly a softie.",
            speed=1.05, play=0.6, lazy=0.5, hungry=0.005,
            lines=["i was here the whole time.", "*yellow eyes in the dark*", "night is the best part.", "mrr.", "don't tell anyone i purred."]),
    3: dict(name="Duchess", color=(110, 150, 200),   # siamese
            trait="royal, vocal and demanding. Talks like a queen to her servant (the human), loud opinions, secretly loving.",
            speed=1.0, play=0.5, lazy=0.5, hungry=0.005,
            lines=["MROW. attend to me.", "you may pet me. briefly.", "*regal stare*", "the window sill is MY throne.", "meeeow."]),
    4: dict(name="Biscuit", color=(220, 150, 150),   # sphynx
            trait="a dramatic wrinkly little diva with no fur who is always cold. Sassy, loves blankets and warm spots, has strong opinions.",
            speed=1.1, play=0.7, lazy=0.4, hungry=0.006,
            lines=["it is FREEZING in here.", "*judging you silently*", "mrow! (blanket. now.)", "i am not fat, i am fluffy. (i have no fluff)", "look at me. no, LOOK."]),
    5: dict(name="Snow", color=(150, 190, 230),      # white fluffy
            trait="gentle, shy and sweet, a fluffy cloud of a cat. Speaks softly, startles easily, adores cuddles and quiet naps.",
            speed=0.9, play=0.4, lazy=0.7, hungry=0.004,
            lines=["...mew?", "*blinks slowly*", "mrrp.", "*tiny purr*", "can i sit by you?"]),
    6: dict(name="Smokey", color=(130, 140, 160),    # gray tabby
            trait="calm, wise and a little sarcastic. A tiny philosopher with dry one-liners who rarely gets excited.",
            speed=0.85, play=0.35, lazy=0.8, hungry=0.004,
            lines=["hm.", "naps are a form of wisdom.", "*slow blink*", "everything is fine. probably.", "..."]),
}


# ============================================================================
# LEVEL: platforms the cat can stand on / jump between (cat's feet y)
# ============================================================================
class Plat:
    def __init__(self, name, x1, x2, y):
        self.name, self.x1, self.x2, self.y = name, x1, x2, y


PLATS = [
    Plat("the floor", 0, W, FLOOR),
    Plat("the tall bookshelf", 8, 24, 71),
    Plat("the bookshelf", 30, 52, 76),
    Plat("the table", 64, 102, 80),
    Plat("the window sill", 108, 166, 54),
    Plat("the cozy bed", 167, 188, 86),
]
FLOOR_P, SILL = PLATS[0], PLATS[4]
CLIMB_X = 108                                   # the curtain: floor -> window sill
SLEEP_SPOTS = [(PLATS[5], 178), (PLATS[4], 140), (PLATS[1], 16), (PLATS[3], 84), (PLATS[0], 150)]
MAX_UP = 40


def hop_info(P, Q_, kind, ref_x, cat_x):
    if kind == "climb":
        return CLIMB_X, CLIMB_X
    if Q_.y <= P.y:
        lx = clamp(ref_x, Q_.x1 + 4, Q_.x2 - 4)
        return clamp(lx, P.x1 + 3, P.x2 - 3), lx
    best = None
    for side, e in ((-1, P.x1), (1, P.x2)):
        lx, tx = e + side * 7, e - side * 2
        if Q_.x1 + 4 <= lx <= Q_.x2 - 4 and 6 <= lx <= W - 6:
            if best is None or abs(tx - cat_x) < abs(best[0] - cat_x):
                best = (tx, lx)
    return best


def edges(P):
    out = []
    if P is FLOOR_P:
        out.append((SILL, "climb"))
    for Q_ in PLATS:
        if Q_ is P or (P is FLOOR_P and Q_ is SILL) or P.y - Q_.y > MAX_UP:
            continue
        info = hop_info(P, Q_, "jump", (Q_.x1 + Q_.x2) / 2, (P.x1 + P.x2) / 2)
        if info and abs(info[0] - info[1]) <= 34:
            out.append((Q_, "jump"))
    return out


def next_hop(P, G):
    if P is G:
        return None
    prev, dq = {P: None}, deque([P])
    while dq:
        c = dq.popleft()
        for Q_, k in edges(c):
            if Q_ not in prev:
                prev[Q_] = (c, k); dq.append(Q_)
    if G not in prev:
        return None
    node = G
    while prev[node][0] is not P:
        node = prev[node][0]
    return node, prev[node][1]


class Goal:
    def __init__(self, plat, x, then=None, run=False):
        self.plat, self.x, self.then, self.run = plat, x, then, run


# ============================================================================
# ASSETS: finds the packs next to the script and loads sprites
# ============================================================================
def find_file(name, roots, depth=4):
    seen = set()
    for root in roots:
        root = os.path.abspath(root)
        if root in seen or not os.path.isdir(root): continue
        seen.add(root)
        base = root.rstrip(os.sep).count(os.sep)
        for d, dirs, files in os.walk(root):
            if d.count(os.sep) - base >= depth: dirs[:] = []
            if name in files: return os.path.join(d, name)
    return None


SHEETS = ["Idle", "Sitting", "Walk", "Run", "Laying", "Sleeping1", "Sleeping2",
          "Licking 1", "Licking 2", "Itch", "Meow", "Stretching"]


class CatSprites:
    """all animation strips (50x50 frames, facing right) for one cat"""

    def __init__(self, root, idx):
        self.f, self._flip, self._rot = {}, {}, {}
        for n in SHEETS:
            p = os.path.join(root, f"Cat-{idx}", f"Cat-{idx}-{n}.png")
            if not os.path.exists(p): continue
            im = pygame.image.load(p).convert_alpha()
            w, h = im.get_size()
            self.f[n] = [im.subsurface((i * h, 0, h, h)).copy() for i in range(max(1, w // h))]
        if "Idle" not in self.f:
            raise FileNotFoundError(f"Cat-{idx}-Idle.png not found in {root}")

    def has(self, n):
        return n in self.f

    def count(self, n):
        return len(self.f.get(n) or self.f["Idle"])

    def get(self, n, i, flip=False):
        lst = self.f.get(n) or self.f["Idle"]
        i = i % len(lst)
        if not flip: return lst[i]
        key = (n if n in self.f else "Idle", i)
        if key not in self._flip: self._flip[key] = pygame.transform.flip(lst[i], True, False)
        return self._flip[key]

    def rot(self, n, i):
        key = (n, i)
        if key not in self._rot: self._rot[key] = pygame.transform.rotate(self.get(n, i), 90)
        return self._rot[key]


class Assets:
    def __init__(self, a):
        roots = [a.assets or HERE, os.getcwd(), os.path.join(HERE, "assets")]
        p = os.path.join(a.cats_dir, "Cat-1", "Cat-1-Idle.png") if a.cats_dir else find_file("Cat-1-Idle.png", roots)
        self.cats_root = os.path.dirname(os.path.dirname(p)) if p and os.path.exists(p) else None
        q = os.path.join(a.cozy_dir, "bookshelf_1.png") if a.cozy_dir else find_file("bookshelf_1.png", roots)
        self.cozy_dir = os.path.dirname(q) if q and os.path.exists(q) else None
        h = os.path.join(a.hills_dir, "Hills Layer 01.png") if a.hills_dir else find_file("Hills Layer 01.png", roots)
        self.hills_dir = os.path.dirname(h) if h and os.path.exists(h) else None
        v = find_file("Meow-VFX.png", [self.cats_root] if self.cats_root else roots)
        self.vfx = None
        if v:
            im = pygame.image.load(v).convert_alpha()
            self.vfx = [im.subsurface((i * 16, 0, 16, 16)).copy() for i in range(im.get_width() // 16)]
        self._cats, self._props = {}, {}

    def cat(self, idx):
        if idx not in self._cats: self._cats[idx] = CatSprites(self.cats_root, idx)
        return self._cats[idx]

    def prop(self, name):
        """a cozy-pack sprite cropped to its visible pixels (or None)"""
        if name in self._props: return self._props[name]
        out = None
        if self.cozy_dir:
            p = os.path.join(self.cozy_dir, name + ".png")
            if os.path.exists(p):
                im = pygame.image.load(p).convert_alpha()
                out = im.subsurface(im.get_bounding_rect()).copy()
        self._props[name] = out
        return out

    def hill_layers(self):
        if not self.hills_dir: return []
        names = sorted(n for n in os.listdir(self.hills_dir) if n.lower().startswith("hills layer") and n.lower().endswith(".png"))
        return [pygame.image.load(os.path.join(self.hills_dir, n)).convert_alpha() for n in names]


# ============================================================================
# THE ROOM (1:1 pixel art, matches the packs' pixel size)
# ============================================================================
WIN = (115, 13, 44, 40)       # glass area of the window (x, y, w, h)


def shadow(s, x, y, w, h, a=70):
    sh = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(sh, (30, 14, 34, a), (0, 0, w, h))
    s.blit(sh, (x, y))


def place(s, img, x, bottom, fallback=None):
    """blit a prop with its bottom edge at `bottom`; returns its rect"""
    if img is None:
        if fallback: fallback()
        return None
    s.blit(img, (x, bottom - img.get_height()))
    return pygame.Rect(x, bottom - img.get_height(), img.get_width(), img.get_height())


def build_room(A):
    s = pygame.Surface((W, H))
    for y in range(86):                                               # wall + soft stripes
        t = y / 86
        base = (int(122 - 30 * t), int(152 - 34 * t), int(152 - 30 * t))
        R(s, base, 0, y, W, 1)
        light = tuple(min(255, c + 8) for c in base)
        for x in range(0, W, 12): R(s, light, x, y, 2, 1)
    R(s, (86, 70, 86), 0, 64, W, 22); R(s, (222, 196, 160), 0, 62, W, 2); R(s, (172, 146, 116), 0, 64, W, 1)
    for x in range(0, W, 10): R(s, (70, 56, 72), x, 67, 1, 19)       # wainscot
    R(s, (60, 46, 60), 0, 84, W, 2)
    R(s, (176, 122, 82), 0, 86, W, H - 86)                           # floor
    for r, y in enumerate(range(86, H, 7)):
        R(s, (186, 134, 92), 0, y + 1, W, 1); R(s, (140, 92, 62), 0, y, W, 1)
        for x in range((r * 17) % 30, W, 34): R(s, (140, 92, 62), x, y, 1, 7)
    R(s, (150, 100, 68), 0, 86, W, 2)
    pygame.draw.ellipse(s, (200, 110, 120), (56, 90, 84, 14)); pygame.draw.ellipse(s, (228, 150, 150), (62, 92, 72, 10))
    pygame.draw.ellipse(s, (200, 110, 120), (72, 95, 52, 4), 1)
    # window: frame, sill, curtains, rod
    R(s, (120, 80, 60), 112, 10, 50, 46); R(s, (150, 200, 230), *WIN)
    R(s, (150, 104, 76), 112, 10, 50, 1)
    R(s, (214, 170, 120), 108, 54, 58, 3); R(s, (150, 108, 76), 108, 57, 58, 1)
    for x0 in (104, 162):
        R(s, (220, 120, 140), x0, 10, 8, 46); R(s, (200, 100, 124), x0 + 2, 10, 1, 46); R(s, (200, 100, 124), x0 + 5, 10, 1, 46)
        R(s, (240, 150, 166), x0 + 1, 10, 1, 46); R(s, (250, 210, 150), x0, 36, 8, 2)
    R(s, (110, 76, 56), 102, 8, 70, 2); R(s, (230, 190, 120), 100, 7, 3, 4); R(s, (230, 190, 120), 171, 7, 3, 4)
    # wall decor
    for (x, y, w, h, c) in ((14, 16, 20, 16, (120, 160, 190)), (44, 22, 12, 12, (200, 120, 110)), (176, 20, 10, 14, (150, 190, 130))):
        R(s, (220, 190, 150), x, y, w, h); R(s, c, x + 2, y + 2, w - 4, h - 4); R(s, (240, 226, 200), x + 2, y + 2, w - 4, 1)
    pygame.draw.circle(s, (110, 76, 56), (84, 28), 6); pygame.draw.circle(s, (246, 236, 214), (84, 28), 5)
    pygame.draw.line(s, (60, 40, 40), (84, 28), (84, 25)); pygame.draw.line(s, (60, 40, 40), (84, 28), (86, 29))
    # floor shadows under furniture
    for (x, w) in ((4, 52), (62, 44), (164, 28)): shadow(s, x, 95, w, 5, 70)
    # table (procedural) with coffee + bread on top
    R(s, (150, 102, 70), 64, 80, 38, 3); R(s, (176, 126, 90), 64, 80, 38, 1)
    R(s, (120, 80, 56), 66, 83, 34, 2); R(s, (110, 72, 50), 66, 83, 3, 15); R(s, (110, 72, 50), 97, 83, 3, 15)
    place(s, A.prop("coffee_3"), 66, 80); place(s, A.prop("bread_2"), 84, 80)
    # bookshelves + bed (cozy pack)
    def shelf_fb(x, y, w, h):
        def f():
            R(s, (96, 56, 60), x, y, w, h); R(s, (50, 30, 40), x + 2, y + 2, w - 4, h - 4)
            for k in range(3): R(s, (200, 150, 90), x + 3, y + 5 + k * 7, w - 6, 2)
        return f
    place(s, A.prop("bookshelf_2"), 6, 98, shelf_fb(6, 71, 20, 27))
    place(s, A.prop("bookshelf_1"), 28, 98, shelf_fb(28, 76, 26, 22))
    place(s, A.prop("bed_1"), 165, 98, lambda: (R(s, (200, 70, 90), 165, 86, 25, 12), R(s, (240, 220, 220), 165, 86, 8, 12)))
    return s


class WindowView:
    """the window: scrolling parallax hills (from the Hill pack) or a painted fallback"""

    def __init__(self, A):
        x, y, w, h = WIN
        self.surf = pygame.Surface((w, h))
        self.layers = []
        for img in A.hill_layers():
            sc = h / img.get_height()
            nw = max(w, int(img.get_width() * sc))
            img = (pygame.transform.smoothscale if sc < 1 else pygame.transform.scale)(img, (nw, h))
            self.layers.append(img)
        self.base = pygame.Surface((w, h))
        for j in range(h): R(self.base, mix((120, 176, 226), (206, 230, 240), j / h), 0, j, w, 1)
        pygame.draw.polygon(self.base, (118, 178, 112), [(0, h), (0, 26), (14, 20), (28, 26), (44, 18), (44, h)])
        pygame.draw.polygon(self.base, (84, 150, 100), [(0, h), (0, 32), (18, 28), (34, 33), (44, 30), (44, h)])
        self.over = pygame.Surface((w, h), pygame.SRCALPHA)
        R(self.over, (120, 80, 60), w // 2 - 1, 0, 2, h); R(self.over, (120, 80, 60), 0, h // 2 - 1, w, 2)
        pygame.draw.polygon(self.over, (255, 255, 255, 34), [(4, 0), (10, 0), (0, 12), (0, 6)])
        pygame.draw.polygon(self.over, (255, 255, 255, 24), [(14, 0), (17, 0), (0, 24), (0, 20)])

    def draw(self, s, t):
        x, y, w, h = WIN
        if self.layers:
            self.surf.fill((150, 200, 230))
            for k, img in enumerate(self.layers):
                iw = img.get_width()
                off = int(t * (0.6 + 0.7 * k)) % iw
                px = -off
                while px < w:
                    self.surf.blit(img, (px, 0)); px += iw
        else:
            self.surf.blit(self.base, (0, 0))
            for k in range(2):
                cx = int(t * (1.5 + k)) % (w + 20) - 10
                pygame.draw.ellipse(self.surf, (250, 250, 252), (cx, 6 + k * 8, 14, 4))
        s.blit(self.surf, (x, y)); s.blit(self.over, (x, y))


class RoomFX:
    """coffee steam, warm sunbeam from the window, soft vignette"""

    def __init__(self):
        self.beam = pygame.Surface((W, H), pygame.SRCALPHA)
        pygame.draw.polygon(self.beam, (255, 238, 190, 22), [(116, 54), (158, 54), (150, 108), (72, 108)])
        pygame.draw.polygon(self.beam, (255, 238, 190, 16), [(124, 54), (150, 54), (128, 108), (96, 108)])
        self.vign = pygame.Surface((W, H), pygame.SRCALPHA)
        for y in range(H):
            for x in range(W):
                d = math.hypot((x - W / 2) / (W / 2), (y - H / 2) / (H / 2))
                a = int(clamp((d - 0.7) * 1.4, 0, 1) ** 2 * 120)
                if a: self.vign.set_at((x, y), (30, 14, 40, a))

    def back(self, s, t):
        for k in range(3):                                            # steam over the coffee cup
            ph = (t * 5 + k * 3) % 9
            a = int(200 * (1 - ph / 9))
            if a > 40: s.set_at((74 + int(math.sin(t * 2 + k * 2) * 1.5), 60 - int(ph)), (a, a, min(255, a + 20)))

    def front(self, s):
        s.blit(self.beam, (0, 0)); s.blit(self.vign, (0, 0))


# ============================================================================
# WORLD OBJECTS: ball, treat, particles, speech
# ============================================================================
Z_GLYPH = ["oooo", "..o.", ".o..", "oooo"]
HEART = [".o.o.", "ooooo", "ooooo", ".ooo.", "..o.."]


def stamp(s, pat, x, y, color, outline=None):
    if outline:
        for j, row in enumerate(pat):
            for i, ch in enumerate(row):
                if ch == "o":
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)): s.set_at((x + i + dx, y + j + dy), outline)
    for j, row in enumerate(pat):
        for i, ch in enumerate(row):
            if ch == "o": s.set_at((x + i, y + j), color)


class Ball:
    def __init__(self, x, y):
        self.x, self.y, self.vx, self.vy = x, y, random.uniform(-20, 20), 0.0
        self.grab = False
        self.color = random.choice([(224, 70, 90), (90, 160, 240), (240, 200, 70), (120, 210, 130)])

    def update(self, dt):
        if self.grab: return
        prev = self.y
        self.vy += GRAV * dt
        self.x += self.vx * dt; self.y += self.vy * dt
        if self.x < 4: self.x, self.vx = 4, -self.vx * 0.7
        if self.x > W - 4: self.x, self.vx = W - 4, -self.vx * 0.7
        if self.vy > 0:
            for p in sorted(PLATS, key=lambda p: p.y):
                if p.x1 <= self.x <= p.x2 and prev <= p.y <= self.y:
                    self.y = p.y; self.vy = -self.vy * 0.55; self.vx *= 0.85
                    if abs(self.vy) < 25: self.vy = 0
                    break
        if self.vy == 0: self.vx *= max(0, 1 - 1.4 * dt)


class World:
    def __init__(self):
        self.ball = None
        self.treat = None           # dict(x, food, name)
        self.laser = None
        self.particles = []
        self.bubble = None
        self.thinking = False
        self.hold_until = 0

    def support(self, x, y):
        c = [p for p in PLATS if p.x1 <= x <= p.x2 and p.y >= y - 2]
        return min(c, key=lambda p: p.y) if c else FLOOR_P

    def say(self, text, secs=None):
        self.bubble = (text, time.time() + (secs or max(4.0, len(text) * 0.07)))

    def spawn_ball(self, x=None, y=None):
        self.ball = Ball(x if x is not None else random.randint(20, 170), y if y is not None else 12)

    def feed(self):
        self.treat = dict(x=random.choice([112, 126, 142, 154]), food=1.0, name=random.choice(["bread_1", "cake_1", "cake_2", "bread_4"]))

    def puff(self, kind, x, y):
        self.particles.append(dict(k=kind, x=x, y=y, vx=random.uniform(-4, 4), vy=-random.uniform(8, 14), life=1.7))


def draw_objects(s, world, A):
    tr = world.treat
    if tr:
        img = A.prop(tr["name"])
        if img:
            h = img.get_height(); vis = max(1, int(h * tr["food"]))
            s.blit(img, (int(tr["x"] - img.get_width() / 2), 99 - vis), (0, h - vis, img.get_width(), vis))
        else:
            x = int(tr["x"]); R(s, (200, 90, 100), x - 5, 96, 10, 3)
            if tr["food"] > 0: R(s, (170, 110, 60), x - 3, 94, 6, 2)
    b = world.ball
    if b:
        cx, cy = int(b.x), int(b.y) - 3
        pygame.draw.circle(s, (50, 26, 40), (cx, cy), 4)
        pygame.draw.circle(s, b.color, (cx, cy), 3)
        s.set_at((cx - 1, cy - 1), (255, 255, 255)); s.set_at((cx + 1, cy + 1), tuple(int(c * 0.6) for c in b.color))
    if world.laser:
        lx, ly = world.laser
        pygame.draw.circle(s, (130, 20, 30), (int(lx), int(ly)), 2)
        s.set_at((int(lx), int(ly)), (255, 120, 120))
    for p in world.particles:
        if p["k"] == "heart": stamp(s, HEART, int(p["x"]), int(p["y"]), (240, 84, 118), (110, 30, 54))
        elif p["k"] == "z": stamp(s, Z_GLYPH, int(p["x"]), int(p["y"]), (240, 244, 255), (80, 90, 150))


# ============================================================================
# THE CAT: behaviour + physics + which animation strip to play
# ============================================================================
ANIM = {   # name: (sheet, fps, loop)
    "idle": ("Idle", 8, True), "sit": ("Sitting", 1, True), "walk": ("Walk", 10, True), "run": ("Run", 14, True),
    "lick": ("Licking 1", 7, True), "lick2": ("Licking 2", 7, True), "itch": ("Itch", 5, True),
    "meow": ("Meow", 6, True), "stretch": ("Stretching", 9, False),
}
ANCHOR_X, FEET_ROW = 25, 32      # in a 50x50 frame the cat's feet are at row 32, body centred on x=25


class Cat:
    def __init__(self, idx, A):
        self.A = A
        self.set_cat(idx)
        self.x, self.y, self.vx, self.vy = 150.0, float(FLOOR), 0.0, 0.0
        self.plat = FLOOR_P
        self.face, self.state, self.timer, self.t = 1, "idle", 1.0, 0.0
        self.goal = None
        self.hunger, self.energy, self.joy = 0.3, 0.8, 0.6
        self.ret_state, self.running, self.moving = "idle", False, False
        self.kick_cd = self.pounce_cd = 0.0
        self.anim, self.anim_t = "idle", 0.0
        self.idle_kind, self.sleep_sheet, self.groom_kind = "idle", "Sleeping1", "lick"
        self.talking = False

    def set_cat(self, idx):
        self.idx, self.pers = idx, CATS[idx]
        self.spr = self.A.cat(idx)

    @property
    def grounded(self):
        return self.state not in ("air", "climb")

    # ---- movement helpers
    def go(self, plat, x, then=None, run=False):
        self.goal = Goal(plat, clamp(x, plat.x1 + 3, plat.x2 - 3), then, run)
        self.state = "goto"

    def wake(self, instant=False):
        if self.state == "sleep":
            if instant or self.anim_t < 1.0: self.state, self.timer = "idle", 0.4
            else: self.state, self.timer = "wake", 1.0

    def start_jump(self, tx, ty):
        dh = self.y - ty
        vy0 = -math.sqrt(2 * GRAV * (max(dh, 0) + 9))
        t = (-vy0 + math.sqrt(max(vy0 * vy0 - 2 * GRAV * dh, 0))) / GRAV
        self.vx = clamp((tx - self.x) / max(t, 0.05), -110, 110)
        self.vy = vy0
        if abs(self.vx) > 1: self.face = 1 if self.vx > 0 else -1
        self.ret_state = self.state if self.state in ("goto", "play") else "idle"
        self.state, self.plat, self.moving = "air", None, False

    def walk_to(self, tx, dt, run):
        d = tx - self.x
        self.running = run
        step = (46 if run else 20) * self.pers["speed"] * dt
        if abs(d) <= step:
            self.x = tx; self.moving = False
            return True
        self.x += math.copysign(step, d)
        self.face = 1 if d > 0 else -1
        self.moving = True
        return False

    def follow(self, dt, run=False):
        g = self.goal
        if self.plat is g.plat:
            return self.walk_to(g.x, dt, run)
        hop = next_hop(self.plat, g.plat)
        if not hop: return True
        Q_, k = hop
        info = hop_info(self.plat, Q_, k, g.x if Q_ is g.plat else self.x, self.x)
        if info is None: return True
        tx, lx = info
        if abs(self.x - tx) > 1.2:
            self.walk_to(tx, dt, run); return False
        self.moving = False
        if k == "climb": self.state, self.x, self.face = "climb", CLIMB_X, 1
        else: self.start_jump(lx, Q_.y)
        return False

    def arrive(self):
        then = self.goal.then if self.goal else None
        self.goal = None
        if then == "sleep":
            self.state, self.timer = "sleep", random.uniform(25, 60)
            self.sleep_sheet = random.choice(["Sleeping1", "Sleeping2"])
        elif then == "eat": self.state, self.timer = "eat", 4.0
        else:
            self.state, self.timer = "idle", random.uniform(1, 4)
            self.idle_kind = random.choice(["idle", "idle", "sit"])

    # ---- commands (from chat / the LLM)
    def do(self, action, world):
        if not self.grounded or not action: return
        a = action.lower()
        if a == "play":
            if not world.ball: world.spawn_ball()
            self.state, self.timer = "play", 15.0
        elif a == "sleep":
            p, x = random.choice(SLEEP_SPOTS); self.go(p, x, "sleep")
        elif a == "jump": self.start_jump(self.x + self.face * 18, self.y)
        elif a == "climb": self.go(SILL, 150)
        elif a == "eat":
            if not world.treat: world.feed()
            self.go(FLOOR_P, world.treat["x"] - 10, "eat")
        elif a == "groom": self.state, self.timer, self.groom_kind = "groom", 3.0, "lick"

    def pet(self, world):
        if not self.grounded: return
        self.wake(True)
        self.state, self.timer, self.moving = "pet", 1.6, False
        self.joy = min(1, self.joy + 0.12)
        for _ in range(3): world.puff("heart", self.x + random.uniform(-6, 4), self.y - 24)
        if random.random() < 0.5: world.say(random.choice(self.pers["lines"]), 3)

    def think(self, world):
        P, r = self.pers, random.random()
        if random.random() < 0.18 and not world.bubble: world.say(random.choice(P["lines"]), 3.5)
        if world.treat and world.treat["food"] > 0 and self.hunger > 0.4 and r < 0.8:
            self.go(FLOOR_P, world.treat["x"] - 10, "eat")
        elif self.energy < 0.3 or r < P["lazy"] * 0.2:
            p, x = random.choice(SLEEP_SPOTS); self.go(p, x, "sleep")
        elif world.ball and r < 0.35 + P["play"] * 0.5:
            self.state, self.timer = "play", random.uniform(10, 20)
        elif r < 0.58:
            p = random.choice(PLATS); self.go(p, random.uniform(p.x1 + 4, p.x2 - 4))
        elif r < 0.66: self.go(SILL, 150)
        elif r < 0.75: self.state, self.timer = "stretch", 1.5
        elif r < 0.83:
            self.state, self.timer = "groom", 3.0
            self.groom_kind = random.choice(["lick", "lick", "lick2"])
        elif r < 0.89:
            self.state, self.timer = ("itch", 1.2) if self.spr.has("Itch") else ("stretch", 1.5)
        else:
            self.idle_kind = random.choice(["idle", "idle", "sit"])
            self.timer = random.uniform(2, 5)

    # ---- per-frame
    def update(self, dt, world):
        self.t += dt
        self._step(dt, world)
        want = self.want_anim()
        if want != self.anim: self.anim, self.anim_t = want, 0.0
        else: self.anim_t += dt

    def want_anim(self):
        st = self.state
        if st == "air": return "jump_up" if self.vy < 0 else "jump_down"
        if st in ("climb", "sleep", "wake", "stretch", "itch"): return st
        if st == "eat": return "lick"
        if st == "groom": return self.groom_kind
        if st == "pet": return "meow"
        if self.moving: return "run" if self.running else "walk"
        if self.talking: return "meow"
        return self.idle_kind

    def frame(self):
        """-> (surface, rotated?)  for the current animation"""
        a, t, sp, fl = self.anim, self.anim_t, self.spr, self.face < 0
        if a == "jump_up": return sp.get("Run", 3, fl)
        if a == "jump_down": return sp.get("Run", 5, fl)
        if a == "climb": return sp.rot("Walk", int(t * 9) % sp.count("Walk"))
        if a == "sleep":
            if t < 1.0: return sp.get("Laying", min(sp.count("Laying") - 1, int(t * 8)), fl)
            return sp.get(self.sleep_sheet, 0, fl)
        if a == "wake": return sp.get("Laying", max(0, sp.count("Laying") - 1 - int(t * 8)), fl)
        if a == "stretch":
            return sp.get("Stretching", min(sp.count("Stretching") - 1, int(t * 9)), fl)
        if a == "itch":
            return sp.get("Itch", int(t * 5), fl)
        sheet, fps, loop = ANIM.get(a, ANIM["idle"])
        n = sp.count(sheet)
        i = int(t * fps)
        return sp.get(sheet, i % n if loop else min(i, n - 1), fl)

    def _step(self, dt, world):
        P = self.pers
        self.hunger = min(1, self.hunger + dt * P["hungry"])
        if self.state != "sleep": self.energy = max(0, self.energy - dt * 0.003)
        self.joy = max(0, self.joy - dt * 0.002)
        self.kick_cd -= dt; self.pounce_cd -= dt
        self.x = clamp(self.x, 8, W - 8)

        if self.state == "air":
            prev = self.y
            self.vy += GRAV * dt
            self.x += self.vx * dt; self.y += self.vy * dt
            self.x = clamp(self.x, 8, W - 8)
            if self.vy > 0:
                best = None
                for p in PLATS:
                    if p.x1 - 1 <= self.x <= p.x2 + 1 and prev <= p.y + 0.01 and self.y >= p.y:
                        if best is None or p.y < best.y: best = p
                if best:
                    self.y, self.vx, self.vy, self.plat = best.y, 0, 0, best
                    self.state = self.ret_state
                    if self.state == "idle": self.timer = 0.3
            return
        if self.state == "climb":
            self.y -= 24 * dt
            self.moving = False
            if self.y <= SILL.y:
                self.y, self.plat = SILL.y, SILL
                self.state = "goto" if self.goal else "idle"
                self.timer = 1.0
            return

        self.moving = False
        if world.laser:
            self.wake(True)
            if self.state in ("wake", "pet", "stretch", "itch", "groom", "eat", "sleep"): self.state = "idle"
            lx, ly = world.laser
            sup = world.support(lx, ly)
            self.goal = Goal(sup, clamp(lx, sup.x1 + 3, sup.x2 - 3))
            arrived = self.follow(dt, True)
            if self.state == "goto": self.state = "idle"
            if arrived and abs(self.x - lx) < 8 and self.pounce_cd <= 0 and self.grounded:
                self.pounce_cd = 0.9
                self.start_jump(lx + random.uniform(-5, 5), self.y)
                self.joy = min(1, self.joy + 0.03)
            return

        st = self.state
        if st == "goto":
            if self.follow(dt, self.goal.run if self.goal else False): self.arrive()
        elif st == "play":
            b = world.ball
            self.timer -= dt
            if not b or self.timer <= 0:
                self.state, self.timer = "idle", 1.0
            else:
                sup = world.support(b.x, b.y)
                self.goal = Goal(sup, clamp(b.x - self.face * 5, sup.x1 + 3, sup.x2 - 3))
                self.follow(dt, True)
                if self.state == "play" and self.grounded and self.plat is sup and abs(self.x - b.x) < 9 \
                        and self.y - 11 <= b.y <= self.y + 3 and self.kick_cd <= 0 and not b.grab:
                    d = 1 if b.x >= self.x else -1
                    b.vx, b.vy = d * random.uniform(40, 90), -random.uniform(60, 110)
                    self.face, self.kick_cd = d, 0.6
                    self.joy = min(1, self.joy + 0.02)
        elif st == "sleep":
            self.energy = min(1, self.energy + dt * 0.03)
            self.timer -= dt
            if random.random() < dt * 0.5: world.puff("z", self.x + 8, self.y - 16)
            if self.timer <= 0 or self.energy >= 1: self.wake()
        elif st == "eat":
            self.timer -= dt
            tr = world.treat
            if tr and abs(self.x - tr["x"]) < 16 and tr["food"] > 0:
                self.hunger = max(0, self.hunger - dt * 0.15)
                tr["food"] = max(0, tr["food"] - dt * 0.2)
                self.face = 1 if tr["x"] >= self.x else -1
                if tr["food"] <= 0: world.treat = None
            if self.timer <= 0: self.state, self.timer = "idle", 1.5
        elif st in ("groom", "pet", "wake", "stretch", "itch"):
            self.timer -= dt
            if self.timer <= 0: self.state, self.timer = "idle", 1.0
        else:
            if time.time() < world.hold_until or world.thinking: return
            self.timer -= dt
            if self.timer <= 0: self.think(world)


_shadow = None


def draw_cat(s, cat, A):
    global _shadow
    if _shadow is None:
        _shadow = pygame.Surface((16, 4), pygame.SRCALPHA)
        pygame.draw.ellipse(_shadow, (30, 14, 34, 80), (0, 0, 16, 4))
    img = cat.frame()
    if cat.anim == "climb":
        s.blit(img, (int(cat.x) - 25, int(cat.y) - 38))
        return
    if cat.state != "air": s.blit(_shadow, (int(cat.x) - 8, int(cat.y) - 2))
    s.blit(img, (int(cat.x) - ANCHOR_X, int(cat.y) - FEET_ROW))
    if cat.anim == "meow" and A.vfx:                     # little "meow" puffs from the pack
        v = A.vfx[int(cat.anim_t * 8) % len(A.vfx)]
        if cat.face < 0: v = pygame.transform.flip(v, True, False)
        s.blit(v, (int(cat.x) + cat.face * 11 - 8, int(cat.y) - 27))


# ============================================================================
# OLLAMA  (bypasses Windows proxy + IPv6 'localhost' problems, streams the reply)
# ============================================================================
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_json(url, data=None, timeout=5):
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with OPENER.open(req, timeout=timeout) as r:
        return json.load(r)


def ollama_alive(host):
    try:
        http_json(host + "/api/version", timeout=2); return True
    except Exception:
        return False


def start_ollama():
    try:
        kw = {"creationflags": 0x08000000} if os.name == "nt" else {}
        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
    except Exception:
        pass


def find_model(names, want):
    for n in names:
        if n == want or n == want + ":latest": return n
    for n in names:
        if n.split(":")[0] == want.split(":")[0]: return n
    return None


def check_brain(host, model, autostart=True):
    """returns dict(ok, model, msg)"""
    if not ollama_alive(host):
        if autostart:
            Q.put(("sys", "Ollama is not running - trying to start it..."))
            start_ollama()
            for _ in range(24):
                time.sleep(0.6)
                if ollama_alive(host): break
        if not ollama_alive(host):
            return dict(ok=False, model=model, msg=f"Can't reach Ollama at {host}. Install it from ollama.com and run `ollama serve`.")
    try:
        names = [m["name"] for m in http_json(host + "/api/tags").get("models", [])]
    except Exception as e:
        return dict(ok=False, model=model, msg=f"Ollama answered but listing models failed: {e}")
    if not names:
        return dict(ok=False, model=model, msg=f"Ollama has no models yet. Run: ollama pull {model}")
    m = find_model(names, model)
    if m: return dict(ok=True, model=m, msg=f"Brain connected ({m})")
    return dict(ok=True, model=names[0], msg=f"'{model}' not installed - using '{names[0]}'. (ollama pull {model})")


def brain_thread(host, model, autostart=True):
    Q.put(("brain", check_brain(host, model, autostart)))


def clean_reply(text):
    text = re.sub(r"<think>.*?(</think>|$)", "", text, flags=re.S | re.I)
    text = re.sub(r"\[ACTION:[^\]]*\]?", "", text, flags=re.I)
    text = re.sub(r"^\s*(\w+):\s+", "", text) if re.match(r"^\s*[A-Z][a-z]+:\s", text) else text
    return text.strip().strip('"').strip()


def llm_thread(host, model, system, history):
    body = json.dumps({
        "model": model, "stream": True, "keep_alive": "30m",
        "messages": [{"role": "system", "content": system}] + history,
        "options": {"temperature": 0.9, "num_predict": 120},
    }).encode()
    req = urllib.request.Request(host + "/api/chat", data=body, headers={"Content-Type": "application/json"})
    acc = ""
    try:
        with OPENER.open(req, timeout=300) as r:
            for raw in r:
                raw = raw.strip()
                if not raw: continue
                j = json.loads(raw)
                if "error" in j: raise RuntimeError(j["error"])
                acc += j.get("message", {}).get("content", "")
                Q.put(("partial", clean_reply(acc)))
                if j.get("done"): break
        m = re.search(r"\[ACTION:\s*(\w+)", acc, re.I)
        text = clean_reply(acc) or "mew."
        Q.put(("reply", text, m.group(1).lower() if m else None))
    except urllib.error.HTTPError as e:
        detail = ""
        try: detail = json.loads(e.read().decode()).get("error", "")
        except Exception: pass
        Q.put(("fail", f"Ollama error {e.code}: {detail or 'model missing? run: ollama pull ' + model}"))
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
        Q.put(("fail", f"Can't reach Ollama ({getattr(e, 'reason', e)}). Press R to reconnect."))
        Q.put(("brain", dict(ok=False, model=model, msg="offline")))
    except Exception as e:
        Q.put(("fail", f"Brain error: {e}"))


def listen_thread():
    try:
        import speech_recognition as sr
    except ImportError:
        Q.put(("sys", "Voice input needs: pip install SpeechRecognition pyaudio")); return
    try:
        r = sr.Recognizer()
        with sr.Microphone() as src:
            Q.put(("sys", "Listening... speak now"))
            r.adjust_for_ambient_noise(src, 0.3)
            audio = r.listen(src, timeout=6, phrase_time_limit=10)
        Q.put(("heard", r.recognize_google(audio)))      # needs internet; swap for whisper/vosk to go offline
    except Exception as e:
        Q.put(("sys", f"Didn't catch that ({type(e).__name__})"))


# ============================================================================
# CAT VOICES - every cat talks differently
#   edge      : natural neural voices (pip install edge-tts, needs internet)   <- best quality
#   animalese : a cute "cat-ese" chirp voice made in code (works offline, no install)
#   system    : your computer's own voice (pip install pyttsx3, offline, robotic)
# ============================================================================
HAS_EDGE = False
try:
    import edge_tts  # noqa: F401
    HAS_EDGE = True
except Exception:
    pass

# edge   = Microsoft neural voice name   (list them all with:  edge-tts --list-voices)
# pitch/rate/vol = how the voice is bent to match the personality
# base   = pitch in Hz of the chirpy cat-ese voice,  spd = its speed,  fem = which system voice to prefer
VOICES = {
    1: dict(edge="en-US-AnaNeural",         pitch="+30Hz", rate="+18%", vol="+0%",  base=560, spd=1.15, fem=True,  sapi=215),  # Mango: hyper kid
    2: dict(edge="en-GB-RyanNeural",        pitch="-8Hz",  rate="-6%",  vol="+0%",  base=300, spd=0.90, fem=False, sapi=165),  # Shadow: dry + low
    3: dict(edge="en-GB-SoniaNeural",       pitch="+4Hz",  rate="-4%",  vol="+0%",  base=450, spd=0.95, fem=True,  sapi=170),  # Duchess: regal
    4: dict(edge="en-US-AriaNeural",        pitch="+14Hz", rate="+8%",  vol="+0%",  base=520, spd=1.05, fem=True,  sapi=200),  # Biscuit: diva
    5: dict(edge="en-GB-MaisieNeural",      pitch="+12Hz", rate="-12%", vol="-15%", base=620, spd=0.85, fem=True,  sapi=160),  # Snow: shy + soft
    6: dict(edge="en-US-ChristopherNeural", pitch="-4Hz",  rate="-12%", vol="+0%",  base=340, spd=0.80, fem=False, sapi=155),  # Smokey: calm + wise
}


def clean_for_speech(t):
    t = re.sub(r"\*[^*]*\*", " ", t)                    # *actions* are not spoken
    t = re.sub(r"\[ACTION:[^\]]*\]?", " ", t, flags=re.I)
    t = re.sub(r"\bm+r+[a-z]*\b", "mew", t, flags=re.I)  # mrow / mrrp / mrr -> mew
    t = re.sub(r"[^\w\s.,!?'\-]", " ", t)
    t = re.sub(r"\.{2,}", ",", t)
    return re.sub(r"\s+", " ", t).strip()


def _tone(out, sr, f0, dur, vol=0.3, glide=0.0):
    n = max(1, int(sr * dur)); ph = 0.0
    for i in range(n):
        t = i / max(n - 1, 1)
        ph += TAU * f0 * (1 + glide * t) / sr
        env = min(1.0, t * 14) * (1 - t) ** 1.3
        v = (math.sin(ph) * 0.62 + math.sin(2 * ph) * 0.25 + math.sin(3 * ph) * 0.13) * env * vol
        out.append(int(clamp(v, -1, 1) * 32767))


def _pause(out, sr, dur):
    out.extend([0] * int(sr * dur))


def _norm(out, peak):
    m = max((abs(v) for v in out), default=0)
    if m:
        k = peak * 32767 / m
        for i in range(len(out)): out[i] = int(out[i] * k)
    return out


def gen_mew(sr, base):
    out, n, ph = array("h"), int(sr * 0.38), 0.0
    for i in range(n):
        t = i / n
        f = base * (0.95 + 0.75 * math.sin(math.pi * t) ** 0.8) * (1 + 0.012 * math.sin(i / sr * 55))
        ph += TAU * f / sr
        env = min(1, t * 20) * (1 - t) ** 0.8
        mid = 0.5 + 0.5 * math.sin(math.pi * t)
        v = (math.sin(ph) * 0.5 + math.sin(2 * ph) * 0.3 * mid + math.sin(3 * ph) * 0.2) * env * 0.32
        out.append(int(v * 32767))
    return out


def gen_cat_talk(text, sr, base, spd):
    """'animalese': one little pitched chirp per syllable, a mew at the end"""
    out = array("h")
    for w in re.findall(r"[A-Za-z']+|[.!?,]", text[:220]):
        if w in ".!?,":
            _pause(out, sr, 0.15 if w == "," else 0.26); continue
        syl = max(1, len(re.findall(r"[aeiouy]+", w.lower())))
        h = sum(ord(c) for c in w)
        for k in range(min(syl, 3)):
            f = base * 2 ** ((((h * (k + 3)) % 9) - 3) / 12)
            _tone(out, sr, f, (0.075 if k < syl - 1 else 0.10) / spd, 0.30, 0.06 if (h + k) % 3 == 0 else -0.04)
            _pause(out, sr, 0.012)
        _pause(out, sr, 0.05 / spd)
    end = text.strip()[-1:] if text.strip() else "."
    if end == "?": _tone(out, sr, base * 1.25, 0.2, 0.3, 0.5)
    elif end == "!": _tone(out, sr, base * 1.45, 0.16, 0.34, 0.15)
    _pause(out, sr, 0.05)
    out.extend(gen_mew(sr, base))
    return _norm(out, 0.7)


def gen_purr(sr, dur=1.5):
    out, lp, n = array("h"), 0.0, int(sr * dur)
    for i in range(n):
        t = i / n
        lp = lp * 0.96 + random.uniform(-1, 1) * 0.04
        am = 0.55 + 0.45 * math.sin(TAU * 24 * i / sr)
        env = min(1, t * 6) * min(1, (1 - t) * 6)
        out.append(int(lp * am * env * 1000))
    return _norm(out, 0.45)


class Voice:
    """speaks in a background thread; `busy` is True while sound is playing (the cat 'meows' in sync)"""
    ORDER = ["auto", "edge", "animalese", "system"]

    def __init__(self, engine="auto"):
        self.engine, self.enabled, self.busy, self.gen = engine, False, False, 0
        self._edge_fail = False

    def resolve(self):
        if self.engine != "auto": return self.engine
        if HAS_EDGE and not self._edge_fail: return "edge"
        import importlib.util
        return "system" if importlib.util.find_spec("pyttsx3") else "animalese"

    def label(self):
        e = self.resolve()
        return {"edge": "natural", "animalese": "cat-ese", "system": "system"}.get(e, e) if self.engine != "off" else "off"

    def cycle(self):
        self.engine = self.ORDER[(self.ORDER.index(self.engine) + 1) % len(self.ORDER)] if self.engine in self.ORDER else "auto"
        self._edge_fail = False

    # ---- sounds
    def _sound(self, samples):
        ch = pygame.mixer.get_init()[2]
        if ch == 2:
            st = array("h")
            for v in samples: st.append(v); st.append(v)
            samples = st
        return pygame.mixer.Sound(buffer=samples.tobytes())

    def _rate(self):
        return pygame.mixer.get_init()[0]

    def purr(self):
        if not (self.enabled and self.engine != "off"): return
        try:
            s = self._sound(gen_purr(self._rate())); s.set_volume(0.5); s.play()
        except Exception:
            pass

    def say(self, text, prof):
        if not (self.enabled and self.engine != "off"): return
        text = clean_for_speech(text)
        if not text: return
        self.gen += 1
        threading.Thread(target=self._run, args=(text, prof, self.gen), daemon=True).start()

    def _run(self, text, prof, g):
        self.busy = True
        try:
            eng = self.resolve()
            if eng == "edge":
                if not self._edge(text, prof, g):
                    Q.put(("sys", "Natural voice needs internet + `pip install edge-tts` - using the cat-ese voice instead"))
                    self._edge_fail = True; eng = "animalese"
            elif eng == "system":
                if not self._system(text, prof, g):
                    Q.put(("sys", "System voice needs `pip install pyttsx3` - using the cat-ese voice instead")); eng = "animalese"
            if eng == "animalese":
                self._animalese(text, prof, g)
        except Exception as e:
            Q.put(("sys", f"Voice error: {e}"))
        finally:
            if g == self.gen: self.busy = False

    def _wait(self, ch, g):
        while ch is not None and ch.get_busy() and g == self.gen: time.sleep(0.03)

    def _animalese(self, text, prof, g):
        sr = self._rate()
        snd = self._sound(gen_cat_talk(text, sr, prof["base"], prof["spd"]))
        snd.set_volume(0.8)
        self._wait(snd.play(), g)

    def _edge(self, text, prof, g):
        if not HAS_EDGE: return False
        import asyncio, tempfile
        fd, path = tempfile.mkstemp(suffix=".mp3"); os.close(fd)
        try:
            try:                                            # a little 'mew' plays while the voice is being made
                m = self._sound(gen_mew(self._rate(), prof["base"])); m.set_volume(0.6); m.play()
            except Exception:
                pass

            async def go():
                await edge_tts.Communicate(text, prof["edge"], rate=prof["rate"], pitch=prof["pitch"], volume=prof["vol"]).save(path)
            asyncio.run(go())
            if g != self.gen: return True
            pygame.mixer.music.load(path); pygame.mixer.music.play()
            while pygame.mixer.music.get_busy() and g == self.gen: time.sleep(0.05)
            try: pygame.mixer.music.unload()
            except Exception: pass
            return True
        except Exception:
            return False
        finally:
            try: os.remove(path)
            except Exception: pass

    def _system(self, text, prof, g):
        try:
            import pyttsx3
        except ImportError:
            return False
        e = pyttsx3.init(); e.setProperty("rate", prof["sapi"])
        want = ("zira", "hazel", "susan", "female", "samantha") if prof["fem"] else ("david", "mark", "george", "male", "daniel")
        for v in e.getProperty("voices"):
            if any(w in (v.name or "").lower() for w in want):
                e.setProperty("voice", v.id); break
        e.say(text); e.runAndWait()
        return True


# ============================================================================
# UI
# ============================================================================
def wrap(font, text, maxw):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if font.size(t)[0] <= maxw: cur = t
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines or [""]


def panel(screen, rect, fill=(52, 32, 46, 230), border=(236, 184, 140)):
    x, y, w, h = rect
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(s, fill, (0, 0, w, h), border_radius=9)
    pygame.draw.rect(s, border, (0, 0, w, h), 2, border_radius=9)
    screen.blit(s, (x, y))


def draw_bubble(screen, font, small, name, color, text, ax, ay):
    lines = wrap(font, text, 330)[:8]
    lh = font.get_linesize()
    w = max(font.size(l)[0] for l in lines) + 24
    h = lh * len(lines) + 24
    x = clamp(ax - w // 2, 10, screen.get_width() - w - 10)
    y = max(30, ay - h - 20)
    pygame.draw.rect(screen, (48, 28, 36), (x - 3, y - 3, w + 6, h + 6), border_radius=12)
    pygame.draw.rect(screen, (255, 247, 234), (x, y, w, h), border_radius=10)
    tipx = clamp(ax, x + 18, x + w - 18)
    pygame.draw.polygon(screen, (48, 28, 36), [(tipx - 10, y + h), (tipx + 10, y + h), (tipx, y + h + 18)])
    pygame.draw.polygon(screen, (255, 247, 234), [(tipx - 7, y + h - 2), (tipx + 7, y + h - 2), (tipx, y + h + 12)])
    tag = small.render(name, True, (255, 255, 255))
    pygame.draw.rect(screen, color, (x + 10, y - 12, tag.get_width() + 14, 20), border_radius=8)
    pygame.draw.rect(screen, (48, 28, 36), (x + 10, y - 12, tag.get_width() + 14, 20), 2, border_radius=8)
    screen.blit(tag, (x + 17, y - 9))
    for i, l in enumerate(lines):
        screen.blit(font.render(l, True, (70, 44, 52)), (x + 12, y + 12 + i * lh))


def bar(screen, small, label, val, x, y, color):
    screen.blit(small.render(label, True, (236, 232, 224)), (x, y))
    pygame.draw.rect(screen, (10, 10, 18), (x + 62, y + 2, 104, 14), border_radius=5)
    pygame.draw.rect(screen, color, (x + 64, y + 4, int(100 * clamp(val, 0, 1)), 10), border_radius=4)


# ============================================================================
# MAIN
# ============================================================================
def build_system_prompt(cat, world):
    P = cat.pers
    where = cat.plat.name if cat.plat else "mid-air"
    hungry = "very hungry" if cat.hunger > 0.7 else "a bit peckish" if cat.hunger > 0.4 else "full"
    tired = "sleepy" if cat.energy < 0.3 else "awake"
    mood = "happy" if cat.joy > 0.6 else "okay" if cat.joy > 0.3 else "bored"
    return (
        f"You are {P['name']}, a pet cat living in a cozy little room: a window with rolling green hills outside, "
        f"two bookshelves, a table with a hot coffee and a loaf of bread, a soft bed and a pink curtain you love to climb. "
        f"You are chatting with your human.\n"
        f"Personality: {P['trait']}\n"
        "Rules: stay in character as a cat, never say you are an AI. Reply in 1-3 SHORT sentences (max 35 words). "
        "You may use a cat action in *asterisks* sparingly. Plain text only.\n"
        "Optionally end with ONE action tag to physically do something: "
        "[ACTION: play] [ACTION: sleep] [ACTION: jump] [ACTION: climb] [ACTION: eat] [ACTION: groom].\n"
        f"Right now: you are on {where}; you feel {hungry}, {tired}, {mood}. "
        f"There {'is' if world.ball else 'is no'} a ball; there {'is' if world.treat else 'is no'} a treat on the floor."
    )


def run_test(host, model):
    print(f"Checking Ollama at {host} ...")
    info = check_brain(host, model)
    print(info)
    if not info["ok"]: return
    print("Asking the model to say hi...")
    llm_thread(host, info["model"], "You are a cat. Reply in one short sentence.", [{"role": "user", "content": "hi!"}])
    last = None
    while not Q.empty():
        last = Q.get()
    print("->", last)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="llama3.2")
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--cat", type=int, default=1, choices=range(1, 7), help="1-6 (Cat-1 .. Cat-6 of the pack)")
    ap.add_argument("--scale", type=int, default=6, help="screen pixels per art pixel (6 = 1152x648)")
    ap.add_argument("--assets", help="folder that contains the extracted packs (default: next to this script)")
    ap.add_argument("--cats-dir", help="the 'Pet Cats Pack' folder")
    ap.add_argument("--cozy-dir", help="the folder with bookshelf_1.png etc.")
    ap.add_argument("--hills-dir", help="the folder with 'Hills Layer 01.png' etc.")
    ap.add_argument("--voice", default="auto", choices=["auto", "edge", "animalese", "system", "off"],
                    help="how the cat talks: edge=natural voices, animalese=cute offline chirps, system=pyttsx3")
    ap.add_argument("--test", action="store_true", help="test the Ollama connection and exit")
    a = ap.parse_args()
    host = a.host.replace("localhost", "127.0.0.1").rstrip("/")
    if a.test:
        run_test(host, a.model); return
    S, model = a.scale, a.model

    pygame.mixer.pre_init(22050, -16, 1, 512)
    pygame.init()
    screen = pygame.display.set_mode((W * S, H * S))
    pygame.display.set_caption("Cozy Cat")
    A = Assets(a)
    if not A.cats_root:
        pygame.quit()
        sys.exit("Couldn't find the 'Pet Cats Pack' art.\nExtract Pet_Cats_Pack.zip next to this script "
                 "(so you have 'Pet Cats Pack/Cat-1/Cat-1-Idle.png'), or pass --cats-dir \"path\\to\\Pet Cats Pack\".")
    print("cats :", A.cats_root)
    print("props:", A.cozy_dir or "NOT FOUND (using simple furniture) - extract cozy.zip next to the script")
    print("hills:", A.hills_dir or "NOT FOUND (using a painted view) - extract Free_Pixel_Art_Hill.rar next to the script")

    wsurf = pygame.Surface((W, H))
    fam = "trebuchetms,verdana,segoeui,arial,helvetica"
    font = pygame.font.SysFont(fam, 17, bold=True)
    small = pygame.font.SysFont(fam, 13, bold=True)
    clock = pygame.time.Clock()

    bg = build_room(A)
    view, fx = WindowView(A), RoomFX()
    world, cat = World(), Cat(a.cat, A)
    history, mode, speak_on = [], "TEXT", False
    voice = Voice(a.voice)
    typing, buf, sysmsg, sysuntil = False, "", "", 0
    brain = dict(ok=False, model=model, msg="connecting...")
    grab_hist = deque(maxlen=6)
    threading.Thread(target=brain_thread, args=(host, model), daemon=True).start()
    world.say(f"*{cat.pers['name']} stretches* Press Enter to talk to me!", 5)

    def notify(msg, secs=6):
        nonlocal sysmsg, sysuntil
        sysmsg, sysuntil = msg, time.time() + secs

    def send(text):
        text = text.strip()
        if not text: return
        cat.wake(True)
        history.append({"role": "user", "content": text}); del history[:-12]
        world.thinking = True
        world.hold_until = time.time() + 600
        cat.moving = False
        threading.Thread(target=llm_thread, args=(host, brain["model"] if brain["ok"] else model,
                                                  build_system_prompt(cat, world), list(history)), daemon=True).start()
        notify("You: " + text, 6)

    running = True
    while running:
        dt = min(clock.tick(60) / 1000.0, 0.05)
        now = time.time()
        mx, my = pygame.mouse.get_pos()
        wx, wy = mx // S, my // S

        try:
            while True:
                m = Q.get_nowait()
                if m[0] == "partial":
                    if m[1]: world.bubble = (m[1], now + 120)
                elif m[0] == "reply":
                    world.thinking = False
                    world.hold_until = now + max(4, len(m[1]) * 0.07)
                    world.say(m[1])
                    history.append({"role": "assistant", "content": m[1]})
                    cat.joy = min(1, cat.joy + 0.05)
                    voice.enabled = speak_on
                    voice.say(m[1], VOICES[cat.idx])
                    if m[2]: cat.do(m[2], world)
                elif m[0] == "fail":
                    world.thinking = False; world.hold_until = 0
                    world.say("*tilts head* ...my brain isn't connected.", 4); notify(m[1], 10)
                elif m[0] == "sys": notify(m[1], 8)
                elif m[0] == "brain":
                    brain = m[1]
                    if brain["ok"]: model = brain["model"]
                    notify(brain["msg"], 8)
                elif m[0] == "heard": notify("You said: " + m[1], 5); send(m[1])
        except queue.Empty:
            pass

        for e in pygame.event.get():
            if e.type == pygame.QUIT: running = False
            elif e.type == pygame.KEYDOWN:
                if typing:
                    if e.key == pygame.K_RETURN: send(buf); buf, typing = "", False
                    elif e.key == pygame.K_ESCAPE: buf, typing = "", False
                    elif e.key == pygame.K_BACKSPACE: buf = buf[:-1]
                    elif e.unicode and e.unicode.isprintable() and len(buf) < 200: buf += e.unicode
                else:
                    k = e.key
                    if k == pygame.K_ESCAPE: running = False
                    elif k == pygame.K_RETURN:
                        if mode == "TEXT": typing = True
                        else: threading.Thread(target=listen_thread, daemon=True).start()
                    elif k == pygame.K_TAB:
                        mode = "VOICE" if mode == "TEXT" else "TEXT"; speak_on = (mode == "VOICE")
                        notify(f"{mode} mode" + (" - press Enter or M and speak; the cat talks back" if mode == "VOICE" else ""), 5)
                    elif k == pygame.K_m: threading.Thread(target=listen_thread, daemon=True).start()
                    elif k == pygame.K_s: speak_on = not speak_on; notify("Cat voice " + ("ON" if speak_on else "OFF"), 3)
                    elif k == pygame.K_r:
                        brain = dict(ok=False, model=model, msg="connecting..."); notify("Reconnecting to Ollama...", 4)
                        threading.Thread(target=brain_thread, args=(host, a.model), daemon=True).start()
                    elif k == pygame.K_v:
                        voice.cycle(); speak_on = True; voice.enabled = True
                        voice.say(f"Hi, I am {cat.pers['name']}! {random.choice(cat.pers['lines'])}", VOICES[cat.idx])
                        notify(f"Voice style: {voice.engine} ({voice.label()}) - press V again to switch", 5)
                    elif k == pygame.K_f: world.feed(); cat.do("eat", world); notify("Treat time!", 3)
                    elif k == pygame.K_b: world.spawn_ball()
                    elif pygame.K_1 <= k <= pygame.K_6:
                        cat.set_cat(k - pygame.K_0); history.clear()
                        world.say(f"Hi, I'm {cat.pers['name']}!", 3)
            elif e.type == pygame.MOUSEBUTTONDOWN:
                if e.button == 1:
                    b = world.ball
                    if b and (wx - b.x) ** 2 + (wy - (b.y - 3)) ** 2 < 36: b.grab = True; grab_hist.clear()
                    elif cat.x - 12 <= wx <= cat.x + 12 and cat.y - 17 <= wy <= cat.y + 2:
                        cat.pet(world); voice.enabled = speak_on; voice.purr()
                elif e.button == 3: world.spawn_ball(wx, wy)
            elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                b = world.ball
                if b and b.grab:
                    b.grab = False
                    if len(grab_hist) >= 2:
                        t0, x0, y0 = grab_hist[0]; t1, x1, y1 = grab_hist[-1]
                        d = max(t1 - t0, 0.03)
                        b.vx, b.vy = clamp((x1 - x0) / d, -170, 170), clamp((y1 - y0) / d, -170, 170)

        keys = pygame.key.get_pressed()
        world.laser = (wx, wy) if (keys[pygame.K_SPACE] and not typing) else None
        if world.ball and world.ball.grab:
            world.ball.x, world.ball.y, world.ball.vx, world.ball.vy = wx, wy + 3, 0, 0
            grab_hist.append((now, wx, wy))

        cat.talking = world.thinking or voice.busy or (world.bubble is not None and now < world.hold_until)
        cat.update(dt, world)
        if world.ball: world.ball.update(dt)
        if world.bubble and now > world.bubble[1]: world.bubble = None
        for p in world.particles:
            p["x"] += p["vx"] * dt; p["y"] += p["vy"] * dt; p["life"] -= dt
        world.particles = [p for p in world.particles if p["life"] > 0]

        wsurf.blit(bg, (0, 0))
        view.draw(wsurf, now)
        fx.back(wsurf, now)
        draw_objects(wsurf, world, A)
        draw_cat(wsurf, cat, A)
        fx.front(wsurf)
        pygame.transform.scale(wsurf, (W * S, H * S), screen)

        # ---- HUD
        panel(screen, (10, 10, 236, 100))
        screen.blit(font.render(f"{cat.pers['name']}", True, (255, 226, 170)), (22, 17))
        screen.blit(small.render(f"{mode}{' + voice' if speak_on else ''}", True, (190, 210, 235)), (150, 20))
        bar(screen, small, "Full", 1 - cat.hunger, 22, 42, (244, 164, 76))
        bar(screen, small, "Energy", cat.energy, 22, 62, (110, 190, 244))
        bar(screen, small, "Joy", cat.joy, 22, 82, (244, 104, 148))
        panel(screen, (10, 116, 236, 46))
        pygame.draw.circle(screen, (90, 220, 120) if brain["ok"] else (240, 90, 90), (26, 129), 5)
        screen.blit(small.render(("Brain: " + brain["model"]) if brain["ok"] else "Brain offline - press R", True, (240, 232, 224)), (38, 122))
        pygame.draw.circle(screen, (110, 190, 244) if speak_on else (120, 110, 120), (26, 150), 5)
        screen.blit(small.render(f"Voice: {voice.label()} " + ("ON" if speak_on else "off (S)"), True, (240, 232, 224)), (38, 143))

        if world.bubble:
            draw_bubble(screen, font, small, cat.pers["name"], cat.pers["color"], world.bubble[0],
                        int(cat.x * S), int((cat.y - 30) * S))
        elif world.thinking:
            draw_bubble(screen, font, small, cat.pers["name"], cat.pers["color"], "." * (1 + int(now * 3) % 3),
                        int(cat.x * S), int((cat.y - 30) * S))

        bh = 38
        panel(screen, (10, H * S - bh - 10, W * S - 20, bh))
        if typing:
            txt = "You > " + buf + ("|" if int(now * 2) % 2 == 0 else " ")
            screen.blit(font.render(txt[-90:], True, (255, 255, 255)), (24, H * S - bh + 2))
        elif now < sysuntil:
            screen.blit(font.render(sysmsg[:100], True, (255, 226, 170)), (24, H * S - bh + 2))
        else:
            screen.blit(small.render("Enter talk | Tab text/voice | F treat | B ball | Space laser | click pet/throw | 1-6 cat | R reconnect | V voice | Esc quit",
                                     True, (190, 180, 190)), (24, H * S - bh + 5))
        pygame.display.flip()
    pygame.quit()


if __name__ == "__main__":
    main()
