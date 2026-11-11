#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEO-TRAFFIC // Simulator Lampu Lalu Lintas Cyberpunk  (pygame + web/pygbag)
==========================================================================
Cara menjalankan di komputer (desktop):
    pip install pygame
    python main.py

Cara menjalankan / build untuk WEB (lihat juga README.md):
    pip install pygbag
    pygbag neo-traffic            -> tes di http://localhost:8000
    pygbag --build neo-traffic    -> hasil siap upload ada di neo-traffic/build/web

Fitur:
  - Persimpangan 4 arah (lalu lintas lajur kiri, seperti di Indonesia)
  - Lampu lalu lintas neon dengan glow + hitung mundur
  - Mobil dengan fisika sederhana (mengerem, menjaga jarak, lampu rem)
  - Mode AUTO / MANUAL / ALERT (darurat)
  - Hujan neon, scanline CRT, efek glitch, kota cyberpunk
  - Panel HUD: telemetri, tombol kontrol, dan log sistem

Kontrol keyboard:
  A      = mode AUTO
  M      = mode MANUAL
  E      = mode ALERT / EMERGENCY (semua merah berkedip)
  N      = ganti fase lampu berikutnya
  SPASI  = pause / lanjut
  R      = hujan on/off
  + / -  = tambah / kurangi kepadatan lalu lintas
  L      = mode LITE (matikan efek berat jika terasa lag)
  ESC    = keluar (hanya versi desktop)
Semua juga bisa diklik/disentuh lewat tombol di panel kanan.
"""

import asyncio
import math
import os
import random
import sys
import time
from collections import deque

import pygame

# ============================== KONFIGURASI ==============================
SW, SH = 840, 700            # ukuran area simulasi
PW = 300                     # lebar panel HUD
W, H = SW + PW, SH           # ukuran jendela
CX, CY = SW // 2, SH // 2    # pusat persimpangan
HW = 52                      # setengah lebar jalan
M = HW + 72                  # margin blok gedung dari pusat
FPS = 60
WEB = sys.platform == "emscripten"   # True saat berjalan di browser (pygbag)
FONT_FILE = "font.ttf"               # opsional: taruh font .ttf di folder yang sama

BG = (4, 5, 13)
CYAN = (0, 240, 255)
MAGENTA = (255, 43, 214)
YELLOW = (252, 238, 10)
GREEN = (57, 255, 20)
RED = (255, 23, 68)
PURPLE = (157, 77, 255)
ORANGE = (255, 138, 0)
TERM = (0, 255, 156)
WHITE = (255, 255, 255)

LCOL = {"R": RED, "Y": YELLOW, "G": GREEN}
LNAME = {"R": "RED", "Y": "YELLOW", "G": "GREEN"}

# (nama fase, durasi detik, status NS, status EW)
PHASES = [
    ("NS GREEN",   8.0, "G", "R"),
    ("NS YELLOW",  2.5, "Y", "R"),
    ("CLEARANCE",  1.5, "R", "R"),
    ("EW GREEN",   8.0, "R", "G"),
    ("EW YELLOW",  2.5, "R", "Y"),
    ("CLEARANCE",  1.5, "R", "R"),
]

# Arah mobil: N = datang dari utara (jalan ke bawah), S = dari selatan (ke atas),
#             W = dari barat (ke kanan), E = dari timur (ke kiri)
DIRV = {"N": (0, 1), "S": (0, -1), "W": (1, 0), "E": (-1, 0)}
STOP = {
    "N": CY - HW - 28,
    "S": SH - (CY + HW + 28),
    "W": CX - HW - 28,
    "E": SW - (CX + HW + 28),
}
AXIS_LEN = {"N": SH, "S": SH, "W": SW, "E": SW}
HEADS = {  # x, y, orientasi
    "N": (CX + HW + 24, CY - HW - 52, "v"),
    "S": (CX - HW - 24, CY + HW + 52, "v"),
    "W": (CX - HW - 52, CY - HW - 24, "h"),
    "E": (CX + HW + 52, CY + HW + 24, "h"),
}
CAR_COLORS = [CYAN, MAGENTA, YELLOW, (124, 255, 0), ORANGE, PURPLE, (255, 77, 109)]


# ============================== UTILITAS ==============================
def mix(a, b, t):
    """Campur warna a -> b dengan proporsi t (0 = a, 1 = b)."""
    return (int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


def dim(c, t):
    """Redupkan warna ke arah background (0 = terang penuh, 1 = hilang)."""
    return mix(c, BG, t)


def R(x1, y1, x2, y2):
    """Rect dari dua sudut (x1,y1)-(x2,y2) -> (x, y, w, h)."""
    return (int(x1), int(y1), int(x2 - x1), int(y2 - y1))


def car_xy(d, s):
    """Posisi (x, y) mobil dari koordinat 1D 's' sepanjang jalurnya."""
    if d == "N":
        return CX + 26, s
    if d == "S":
        return CX - 26, SH - s
    if d == "W":
        return s, CY - 26
    return SW - s, CY + 26


# ============================== APLIKASI ==============================
class App:
    def __init__(self, screen):
        self.screen = screen

        # cache font, teks, dan sprite glow
        self.fonts = {}
        self.tcache = {}
        self.glows = {}

        # state simulasi
        self.cars = []
        self.idx = 0
        self.phase_t = 0.0
        self.mode = "AUTO"
        self.paused = False
        self.rain = True
        self.spawn_rate = 0.35
        self.passed = 0
        self.waiting = 0
        self.pass_times = deque()
        self.logs = deque(maxlen=8)
        self.mouse = (-1, -1)
        self.glitch = 0.0
        self.bars = []
        self.blink = 0.0
        self.fps = 60.0
        self.running = True
        self.drops = [[random.uniform(0, SW), random.uniform(0, SH),
                       random.uniform(9, 16), random.uniform(8, 16)]
                      for _ in range(90 if WEB else 150)]
        self.lite = False      # mode ringan: tanpa lapisan cahaya & scanline
        self.lowfps = 0.0      # penghitung durasi FPS rendah (untuk auto-LITE di web)

        self.static = pygame.Surface((W, H))
        self.build_static()
        self.light_layer = pygame.Surface((SW, SH), pygame.SRCALPHA)
        self.scan = pygame.Surface((W, H), pygame.SRCALPHA)
        for y in range(0, H, 3):
            pygame.draw.line(self.scan, (0, 0, 0, 55), (0, y), (W, y))
        self.build_buttons()

        self.log("SYSTEM ONLINE // NEO-X 01")
        self.log("PHASE > " + PHASES[0][0])

    # ------------------------------------------------------------------
    # HELPER GAMBAR
    # ------------------------------------------------------------------
    def font(self, size, bold=True):
        key = (size, bold)
        f = self.fonts.get(key)
        if f is None:
            if os.path.exists(FONT_FILE):
                f = pygame.font.Font(FONT_FILE, size)
            elif not WEB:
                f = pygame.font.SysFont("consolas,couriernew,dejavusansmono,monospace", size, bold)
            else:  # di browser tidak ada font sistem -> pakai font bawaan pygame
                f = pygame.font.Font(None, int(size * 1.1))
                f.set_bold(bold)
            self.fonts[key] = f
        return f

    def text(self, s, pos, col, size=10, bold=True, anchor="midleft", surf=None):
        key = (s, size, bold, col)
        img = self.tcache.get(key)
        if img is None:
            if len(self.tcache) > 800:
                self.tcache.clear()
            img = self.font(size, bold).render(s, True, col)
            self.tcache[key] = img
        r = img.get_rect()
        setattr(r, anchor, (int(pos[0]), int(pos[1])))
        (surf or self.screen).blit(img, r)

    def glow(self, col, r, k=1.0):
        key = (col, r, k)
        g = self.glows.get(key)
        if g is None:
            g = pygame.Surface((2 * r, 2 * r))
            g.fill((0, 0, 0))
            for i in range(r, 0, -1):
                t = (1 - i / r) ** 2 * k
                c = (int(col[0] * t), int(col[1] * t), int(col[2] * t))
                pygame.draw.circle(g, c, (r, r), i)
            self.glows[key] = g
        return g

    def add_glow(self, x, y, col, r, k=1.0):
        self.screen.blit(self.glow(col, r, k), (int(x - r), int(y - r)),
                         special_flags=pygame.BLEND_RGB_ADD)

    @staticmethod
    def neon_line(s, p1, p2, col, w=1):
        pygame.draw.line(s, dim(col, 0.9), p1, p2, w + 6)
        pygame.draw.line(s, dim(col, 0.7), p1, p2, w + 3)
        pygame.draw.line(s, col, p1, p2, w)

    @staticmethod
    def neon_rect(s, x1, y1, x2, y2, col, fill=(7, 9, 20)):
        pygame.draw.rect(s, dim(col, 0.8), R(x1 - 2, y1 - 2, x2 + 2, y2 + 2), 4)
        pygame.draw.rect(s, fill, R(x1, y1, x2, y2))
        pygame.draw.rect(s, dim(col, 0.15), R(x1, y1, x2, y2), 1)

    @staticmethod
    def dashed(s, col, p1, p2, dash=14, gap=12, w=2):
        x1, y1 = p1
        x2, y2 = p2
        if x1 == x2:
            y = min(y1, y2)
            while y < max(y1, y2):
                pygame.draw.line(s, col, (x1, y), (x1, min(y + dash, max(y1, y2))), w)
                y += dash + gap
        else:
            x = min(x1, x2)
            while x < max(x1, x2):
                pygame.draw.line(s, col, (x, y1), (min(x + dash, max(x1, x2)), y1), w)
                x += dash + gap

    # ------------------------------------------------------------------
    # LOG & KONTROL
    # ------------------------------------------------------------------
    def log(self, msg):
        self.logs.append(time.strftime("%H:%M:%S ") + msg)

    def set_mode(self, m):
        if self.mode != m:
            self.mode = m
            self.log("MODE > " + m + (" (OVERRIDE)" if m == "EMERGENCY" else ""))

    def next_phase(self):
        self.idx = (self.idx + 1) % len(PHASES)
        self.phase_t = 0.0
        self.log("PHASE > " + PHASES[self.idx][0])

    def toggle_pause(self):
        self.paused = not self.paused
        self.log("SIMULATION " + ("PAUSED" if self.paused else "RESUMED"))

    def toggle_rain(self):
        self.rain = not self.rain
        self.log("RAIN " + ("ON" if self.rain else "OFF"))

    def change_flow(self, delta):
        self.spawn_rate = max(0.1, min(1.2, round(self.spawn_rate + delta, 2)))
        self.log("FLOW > %d%%" % int(self.spawn_rate * 100))

    def handle_event(self, e):
        if e.type == pygame.QUIT:
            self.running = False
        elif e.type == pygame.MOUSEMOTION:
            self.mouse = e.pos
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            for (_, x1, y1, x2, y2, action, _, _) in self.buttons:
                if x1 <= mx <= x2 and y1 <= my <= y2:
                    action()
                    break
        elif e.type == pygame.KEYDOWN:
            k = e.key
            if k == pygame.K_a:
                self.set_mode("AUTO")
            elif k == pygame.K_m:
                self.set_mode("MANUAL")
            elif k == pygame.K_e:
                self.set_mode("EMERGENCY")
            elif k == pygame.K_n:
                self.next_phase()
            elif k == pygame.K_SPACE:
                self.toggle_pause()
            elif k == pygame.K_r:
                self.toggle_rain()
            elif k in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                self.change_flow(0.1)
            elif k in (pygame.K_MINUS, pygame.K_KP_MINUS):
                self.change_flow(-0.1)
            elif k == pygame.K_l:
                self.lite = not self.lite
                self.log("QUALITY > " + ("LITE" if self.lite else "FULL"))
            elif k == pygame.K_ESCAPE and not WEB:
                self.running = False

    # ------------------------------------------------------------------
    # LOGIKA LAMPU
    # ------------------------------------------------------------------
    def light_state(self, d):
        if self.mode == "EMERGENCY":
            return "R"
        ph = PHASES[self.idx]
        return ph[2] if d in "NS" else ph[3]

    def group_state(self, gi):
        if self.mode == "EMERGENCY":
            return "R"
        return PHASES[self.idx][gi]

    def countdown(self, gi):
        """Sisa detik sampai lampu grup berganti (atau sampai hijau jika merah)."""
        if self.mode == "EMERGENCY":
            return "!!"
        if self.mode != "AUTO":
            return "--"
        rem = PHASES[self.idx][1] - self.phase_t
        if PHASES[self.idx][gi] in "GY":
            return "%02d" % max(0, math.ceil(rem))
        t = rem
        for j in range(1, len(PHASES) + 1):
            ni = (self.idx + j) % len(PHASES)
            if PHASES[ni][gi] == "G":
                return "%02d" % max(0, math.ceil(t))
            t += PHASES[ni][1]
        return "--"

    # ------------------------------------------------------------------
    # UPDATE SIMULASI
    # ------------------------------------------------------------------
    def update(self, dt):
        k = dt * 60

        # glitch acak
        if self.glitch > 0:
            self.glitch -= dt
        elif random.random() < 0.004:
            self.glitch = 0.12
            self.bars = [(random.randint(0, SH - 12), random.randint(3, 10),
                          random.randint(-14, 14), random.choice([CYAN, MAGENTA]))
                         for _ in range(random.randint(1, 3))]

        # fase lampu
        if self.mode == "AUTO":
            self.phase_t += dt
            if self.phase_t >= PHASES[self.idx][1]:
                self.phase_t -= PHASES[self.idx][1]
                self.idx = (self.idx + 1) % len(PHASES)
                self.log("PHASE > " + PHASES[self.idx][0])

        # spawn mobil
        for d in "NSWE":
            if random.random() < self.spawn_rate * dt:
                if not any(c["d"] == d and c["s"] < 90 for c in self.cars):
                    self.cars.append({
                        "d": d, "s": -40.0, "speed": 0.0,
                        "vmax": random.uniform(2.0, 2.8),
                        "L": random.choice([34, 36, 40, 50]),
                        "Wd": random.choice([20, 20, 22, 24]),
                        "col": random.choice(CAR_COLORS),
                        "brake": False,
                    })

        # gerak mobil per jalur
        waiting = 0
        for d in "NSWE":
            lane = sorted((c for c in self.cars if c["d"] == d), key=lambda c: -c["s"])
            ahead = None
            st = self.light_state(d)
            stop = STOP[d]
            for c in lane:
                L = c["L"]
                lim_ahead = None
                if ahead is not None:
                    lim_ahead = ahead["s"] - (ahead["L"] + L) / 2 - 10
                limit = lim_ahead if lim_ahead is not None else float("inf")

                front = c["s"] + L / 2
                if front <= stop + 2:  # belum melewati garis stop
                    must_stop = st == "R" or (st == "Y" and stop - front > 26)
                    if must_stop:
                        lim = stop - L / 2
                        committed = c["s"] > lim + 1 and c["speed"] > 0.6
                        if not committed:
                            limit = min(limit, lim)

                gap = limit - c["s"]
                if limit == float("inf"):
                    target = c["vmax"]
                else:
                    target = min(c["vmax"], max(0.0, gap) * 0.12)
                old = c["speed"]
                c["speed"] += max(-0.22, min(0.05, target - c["speed"])) * k
                if c["speed"] < 0.02 and target < 0.1:
                    c["speed"] = 0.0
                c["brake"] = c["speed"] < old - 0.005 or c["speed"] < 0.05
                c["s"] += c["speed"] * k

                # pengaman agar tidak menabrak mobil depan
                if lim_ahead is not None and c["s"] > lim_ahead:
                    c["s"] = lim_ahead
                    c["speed"] = min(c["speed"], ahead["speed"])

                if c["speed"] < 0.3 and front <= stop + 2:
                    waiting += 1
                ahead = c
        self.waiting = waiting

        # hapus mobil yang sudah keluar layar
        alive = []
        now = time.time()
        for c in self.cars:
            if c["s"] - c["L"] / 2 > AXIS_LEN[c["d"]] + 40:
                self.passed += 1
                self.pass_times.append(now)
            else:
                alive.append(c)
        self.cars = alive
        while self.pass_times and now - self.pass_times[0] > 60:
            self.pass_times.popleft()

        # hujan
        if self.rain:
            for dr in self.drops:
                dr[1] += dr[2] * k
                dr[0] -= 1.0 * k
                if dr[1] > SH or dr[0] < 0:
                    dr[0] = random.uniform(0, SW + 60)
                    dr[1] = random.uniform(-40, 0)

    # ------------------------------------------------------------------
    # LOOP UTAMA
    # ------------------------------------------------------------------
    async def run(self):
        clock = pygame.time.Clock()
        while self.running:
            dt = min(0.05, clock.tick(FPS) / 1000.0)
            if dt <= 0:
                dt = 1.0 / FPS
            self.fps = self.fps * 0.92 + (1.0 / dt) * 0.08
            self.blink += dt
            for e in pygame.event.get():
                self.handle_event(e)
            if not self.paused:
                self.update(dt)
            self.render()
            pygame.display.flip()

            # di browser: kalau FPS rendah > 3 detik, otomatis pindah ke mode LITE
            if WEB and not self.lite:
                self.lowfps = self.lowfps + dt if self.fps < 30 else 0.0
                if self.lowfps > 3.0:
                    self.lite = True
                    self.log("LAG DETECTED > LITE MODE")

            await asyncio.sleep(0)   # wajib untuk pygbag: beri napas ke browser

    # ------------------------------------------------------------------
    # GAMBAR STATIS (digambar sekali ke self.static)
    # ------------------------------------------------------------------
    def build_static(self):
        s = self.static
        s.fill(BG)

        # grid latar
        gc = (8, 11, 28)
        for x in range(0, SW, 40):
            pygame.draw.line(s, gc, (x, 0), (x, SH))
        for y in range(0, SH, 40):
            pygame.draw.line(s, gc, (0, y), (SW, y))

        rnd = random.Random(7)

        # trotoar
        sidewalk = (10, 13, 31)
        pygame.draw.rect(s, sidewalk, R(CX - M, 0, CX + M, SH))
        pygame.draw.rect(s, sidewalk, R(0, CY - M, SW, CY + M))

        # ---- blok gedung ----
        blocks = [(0, 0, CX - M, CY - M), (CX + M, 0, SW, CY - M),
                  (0, CY + M, CX - M, SH), (CX + M, CY + M, SW, SH)]
        names = ["NEXUS", "VOID-9", "KAIJU", "ZEN//7", "OMNI", "HYPER", "SYNTH", "N30N",
                 "GRID", "ARC-X", "PULSE", "CHROME"]
        neon_cols = [CYAN, MAGENTA, PURPLE, ORANGE, (0, 255, 163)]

        for (bx1, by1, bx2, by2) in blocks:
            cols, rows = 2, 2
            cw = (bx2 - bx1) / cols
            rh = (by2 - by1) / rows
            for ci in range(cols):
                for ri in range(rows):
                    x1 = max(4, bx1 + ci * cw + 8)
                    y1 = max(4, by1 + ri * rh + 8)
                    x2 = min(SW - 4, bx1 + (ci + 1) * cw - 8)
                    y2 = min(SH - 4, by1 + (ri + 1) * rh - 8)
                    col = rnd.choice(neon_cols)
                    self.neon_rect(s, x1, y1, x2, y2, col)
                    # jendela
                    wc = rnd.choice([CYAN, YELLOW, MAGENTA, WHITE])
                    wx = x1 + 10
                    while wx < x2 - 12:
                        wy = y1 + 30
                        while wy < y2 - 12:
                            if rnd.random() < 0.35:
                                f = dim(wc, rnd.choice([0.35, 0.5, 0.65]))
                            else:
                                f = (10, 13, 30)
                            pygame.draw.rect(s, f, (int(wx), int(wy), 6, 8))
                            wy += 15
                        wx += 14
                    # papan neon
                    if rnd.random() < 0.8:
                        nm = rnd.choice(names)
                        mx = (x1 + x2) / 2
                        self.text(nm, (mx + 1, y1 + 15), dim(col, 0.75), 13, True, "center", s)
                        self.text(nm, (mx, y1 + 14), col, 13, True, "center", s)

        # ---- jalan ----
        road = (6, 7, 15)
        pygame.draw.rect(s, road, R(CX - HW, 0, CX + HW, SH))
        pygame.draw.rect(s, road, R(0, CY - HW, SW, CY + HW))

        # tepi jalan neon
        for x in (CX - HW, CX + HW):
            self.neon_line(s, (x, 0), (x, CY - HW), CYAN)
            self.neon_line(s, (x, CY + HW), (x, SH), CYAN)
        for y in (CY - HW, CY + HW):
            self.neon_line(s, (0, y), (CX - HW, y), MAGENTA)
            self.neon_line(s, (CX + HW, y), (SW, y), MAGENTA)

        # kotak persimpangan
        pygame.draw.rect(s, (7, 10, 24), R(CX - HW, CY - HW, CX + HW, CY + HW))
        for i in range(-HW, HW + 1, 13):
            pygame.draw.line(s, (13, 19, 48), (CX + i, CY - HW), (CX + i, CY + HW))
            pygame.draw.line(s, (13, 19, 48), (CX - HW, CY + i), (CX + HW, CY + i))
        pygame.draw.circle(s, dim(CYAN, 0.6), (CX, CY), 16, 2)
        pygame.draw.circle(s, dim(MAGENTA, 0.5), (CX, CY), 8, 1)

        # siku persimpangan
        for sx in (-1, 1):
            for sy in (-1, 1):
                px, py = CX + sx * HW, CY + sy * HW
                self.neon_line(s, (px, py), (px - sx * 18, py), YELLOW, 2)
                self.neon_line(s, (px, py), (px, py - sy * 18), YELLOW, 2)

        # garis tengah putus-putus
        dc = dim(YELLOW, 0.45)
        self.dashed(s, dc, (CX, 0), (CX, CY - HW - 30))
        self.dashed(s, dc, (CX, CY + HW + 30), (CX, SH))
        self.dashed(s, dc, (0, CY), (CX - HW - 30, CY))
        self.dashed(s, dc, (CX + HW + 30, CY), (SW, CY))

        # zebra cross
        zc = mix((143, 216, 255), BG, 0.55)
        for x in range(CX - HW + 6, CX + HW - 6, 14):
            pygame.draw.rect(s, zc, R(x, CY - HW - 24, x + 8, CY - HW - 8))
            pygame.draw.rect(s, zc, R(x, CY + HW + 8, x + 8, CY + HW + 24))
        for y in range(CY - HW + 6, CY + HW - 6, 14):
            pygame.draw.rect(s, zc, R(CX - HW - 24, y, CX - HW - 8, y + 8))
            pygame.draw.rect(s, zc, R(CX + HW + 8, y, CX + HW + 24, y + 8))

        # watermark peta
        self.text("SECTOR 07 // NEO-JAKARTA // 2077", (16, SH - 14), dim(CYAN, 0.45),
                  12, True, "midleft", s)

        # ---- panel HUD (statis) ----
        pygame.draw.rect(s, (6, 8, 18), R(SW, 0, W, H))
        self.neon_line(s, (SW, 0), (SW, H), CYAN, 2)
        self.text("NEO-TRAFFIC", (SW + 21, 27), dim(MAGENTA, 0.3), 28, True, "midleft", s)
        self.text("NEO-TRAFFIC", (SW + 20, 26), CYAN, 28, True, "midleft", s)
        self.text("INTERSECTION CTRL // v2.077", (SW + 20, 52), MAGENTA, 12, True, "midleft", s)
        self.neon_line(s, (SW + 20, 68), (W - 20, 68), MAGENTA)
        for label, y in (("// STATUS", 82), ("// TELEMETRY", 222),
                         ("// CONTROL", 350), ("// SYSLOG", 498)):
            self.text(label, (SW + 20, y), MAGENTA, 12, True, "midleft", s)
            pygame.draw.line(s, dim(MAGENTA, 0.6), (SW + 20 + len(label) * 8 + 10, y),
                             (W - 20, y))

    # ------------------------------------------------------------------
    # TOMBOL
    # ------------------------------------------------------------------
    def build_buttons(self):
        x0 = SW + 20
        bw, gap, h = 80, 10, 32
        rows = [370, 410, 450]
        self.buttons = []

        def add(label, row, c, span, action, active, colr):
            x1 = x0 + c * (bw + gap)
            x2 = x1 + bw * span + gap * (span - 1)
            y1 = rows[row]
            self.buttons.append((label, x1, y1, x2, y1 + h, action, active, colr))

        add("AUTO", 0, 0, 1, lambda: self.set_mode("AUTO"), lambda: self.mode == "AUTO", CYAN)
        add("MANUAL", 0, 1, 1, lambda: self.set_mode("MANUAL"), lambda: self.mode == "MANUAL", PURPLE)
        add("ALERT", 0, 2, 1, lambda: self.set_mode("EMERGENCY"), lambda: self.mode == "EMERGENCY", RED)
        add("NEXT PHASE >>", 1, 0, 2, self.next_phase, lambda: False, YELLOW)
        add("PAUSE", 1, 2, 1, self.toggle_pause, lambda: self.paused, ORANGE)
        add("RAIN", 2, 0, 1, self.toggle_rain, lambda: self.rain, MAGENTA)
        add("FLOW -", 2, 1, 1, lambda: self.change_flow(-0.1), lambda: False, GREEN)
        add("FLOW +", 2, 2, 1, lambda: self.change_flow(0.1), lambda: False, GREEN)

    # ------------------------------------------------------------------
    # GAMBAR DINAMIS
    # ------------------------------------------------------------------
    def render(self):
        scr = self.screen
        scr.blit(self.static, (0, 0))

        # lapisan cahaya transparan (cahaya garis stop, lampu depan mobil)
        if not self.lite:
            ll = self.light_layer
            ll.fill((0, 0, 0, 0))
            self.draw_light_layer(ll)
            scr.blit(ll, (0, 0))

        self.draw_stoplines()
        for c in self.cars:
            self.draw_car(c)
        self.draw_heads()
        if self.rain:
            self.draw_rain()
        self.draw_glitch()
        self.draw_overlays()
        self.draw_hud()
        if not self.lite:
            scr.blit(self.scan, (0, 0))

    def stop_segments(self):
        return {
            "N": ((CX, CY - HW - 28), (CX + HW, CY - HW - 28)),
            "S": ((CX - HW, CY + HW + 28), (CX, CY + HW + 28)),
            "W": ((CX - HW - 28, CY - HW), (CX - HW - 28, CY)),
            "E": ((CX + HW + 28, CY), (CX + HW + 28, CY + HW)),
        }

    def stop_color(self, d):
        col = LCOL[self.light_state(d)]
        if self.mode == "EMERGENCY" and int(self.blink * 2) % 2 == 1:
            col = dim(RED, 0.7)
        return col

    def draw_light_layer(self, ll):
        # cahaya garis stop
        for d, (p1, p2) in self.stop_segments().items():
            col = self.stop_color(d)
            pygame.draw.line(ll, col + (45,), p1, p2, 18)
            pygame.draw.line(ll, col + (80,), p1, p2, 9)
        # lampu depan & underglow mobil
        for c in self.cars:
            d = c["d"]
            x, y = car_xy(d, c["s"])
            fx, fy = DIRV[d]
            rx, ry = -fy, fx
            h, w = c["L"] / 2, c["Wd"] / 2

            def P(a, b):
                return (x + fx * a + rx * b, y + fy * a + ry * b)

            pygame.draw.polygon(ll, (174, 246, 255, 38),
                                [P(h, w - 4), P(h + 44, w + 10), P(h + 44, -w - 10), P(h, -(w - 4))])
            pygame.draw.polygon(ll, (174, 246, 255, 30),
                                [P(h, w - 6), P(h + 24, w), P(h + 24, -w), P(h, -(w - 6))])
            col = c["col"]
            pygame.draw.polygon(ll, col + (55,),
                                [P(h + 5, w + 5), P(-h - 5, w + 5), P(-h - 5, -w - 5), P(h + 5, -w - 5)])

    def draw_stoplines(self):
        for d, (p1, p2) in self.stop_segments().items():
            pygame.draw.line(self.screen, self.stop_color(d), p1, p2, 3)

    def draw_car(self, c):
        scr = self.screen
        d = c["d"]
        x, y = car_xy(d, c["s"])
        fx, fy = DIRV[d]
        rx, ry = -fy, fx
        L, Wd, col = c["L"], c["Wd"], c["col"]
        h, w = L / 2, Wd / 2

        def P(a, b):
            return (x + fx * a + rx * b, y + fy * a + ry * b)

        # glow neon di bawah mobil
        if not self.lite:
            self.add_glow(x, y, col, int(L * 0.8), 0.35)

        # badan
        body = [P(h, w), P(-h, w), P(-h, -w), P(h, -w)]
        pygame.draw.polygon(scr, dim(col, 0.82), body)
        pygame.draw.polygon(scr, col, body, 2)
        # kaca depan
        pygame.draw.polygon(scr, (10, 26, 42),
                            [P(h - 8, w - 3), P(h - 17, w - 3), P(h - 17, -w + 3), P(h - 8, -w + 3)])
        # garis atap
        pygame.draw.line(scr, dim(col, 0.4), P(h - 21, 0), P(-h + 6, 0), 1)
        # lampu depan & belakang
        for sgn in (1, -1):
            hx, hy = P(h - 1, sgn * (w - 4))
            pygame.draw.circle(scr, (234, 255, 255), (int(hx), int(hy)), 3)
            tx, ty = P(-h + 1, sgn * (w - 4))
            if c["brake"]:
                self.add_glow(tx, ty, RED, 12, 0.9)
                pygame.draw.circle(scr, RED, (int(tx), int(ty)), 3)
            else:
                pygame.draw.circle(scr, dim(RED, 0.4), (int(tx), int(ty)), 3)

    def draw_heads(self):
        scr = self.screen
        blink_on = int(self.blink * 2) % 2 == 0
        text_pos = {"N": (34, 0), "S": (-34, 0), "W": (0, -30), "E": (0, 30)}
        for d, (x, y, ori) in HEADS.items():
            gi = 2 if d in "NS" else 3
            st = self.light_state(d)
            if ori == "v":
                box = R(x - 15, y - 40, x + 15, y + 40)
                pts = [(x, y - 24), (x, y), (x, y + 24)]
            else:
                box = R(x - 40, y - 15, x + 40, y + 15)
                pts = [(x - 24, y), (x, y), (x + 24, y)]
            pygame.draw.rect(scr, (8, 10, 24), box)
            pygame.draw.rect(scr, dim(CYAN, 0.4), box, 2)
            r = 9
            for (px, py), s in zip(pts, "RYG"):
                if self.mode == "EMERGENCY":
                    on = s == "R" and blink_on
                else:
                    on = st == s
                col = LCOL[s]
                if on:
                    self.add_glow(px, py, col, 34, 0.9)
                    pygame.draw.circle(scr, col, (px, py), r)
                    pygame.draw.circle(scr, mix(col, WHITE, 0.6), (px, py), r, 2)
                    pygame.draw.circle(scr, mix(col, WHITE, 0.85), (px - 2, py - 3), 2)
                else:
                    pygame.draw.circle(scr, dim(col, 0.86), (px, py), r)
                    pygame.draw.circle(scr, dim(col, 0.6), (px, py), r, 1)
            ox, oy = text_pos[d]
            tcol = LCOL[st] if self.mode != "EMERGENCY" else RED
            self.text(self.countdown(gi), (x + ox, y + oy), tcol, 20, True, "center")

    def draw_rain(self):
        rc = mix((74, 168, 255), BG, 0.55)
        for x, y, sp, ln in self.drops:
            pygame.draw.line(self.screen, rc, (x, y), (x + 2.5, y - ln))

    def draw_glitch(self):
        if self.glitch <= 0:
            return
        scr = self.screen
        for (y, hh, dx, col) in self.bars:
            y = max(0, min(y, SH - hh))
            strip = scr.subsurface((0, y, SW, hh)).copy()
            scr.blit(strip, (dx, y))
            pygame.draw.line(scr, dim(col, 0.4), (0, y), (SW, y), 1)

    def draw_overlays(self):
        scr = self.screen
        blink_on = int(self.blink * 2) % 2 == 0
        if self.mode == "EMERGENCY" and blink_on:
            pygame.draw.rect(scr, RED, R(4, 4, SW - 4, SH - 4), 4)
            self.text("!! EMERGENCY OVERRIDE !!", (CX + 2, 42), dim(RED, 0.6), 28, True, "center")
            self.text("!! EMERGENCY OVERRIDE !!", (CX, 40), RED, 28, True, "center")
        if self.paused:
            self.text("|| PAUSED", (CX + 2, CY + 2), dim(MAGENTA, 0.4), 40, True, "center")
            self.text("|| PAUSED", (CX, CY), CYAN, 40, True, "center")

    # ------------------------------------------------------------------
    # HUD
    # ------------------------------------------------------------------
    def draw_hud(self):
        scr = self.screen
        px = SW + 20
        pw = PW - 40
        blink_on = int(self.blink * 2) % 2 == 0

        # jam
        self.text(time.strftime("%H:%M:%S"), (W - 20, 82), CYAN, 14, True, "midright")

        # kotak fase
        sts = [self.group_state(2), self.group_state(3)]
        if self.mode == "EMERGENCY":
            pname, pcol = "EMERGENCY LOCK", RED
        else:
            pname = PHASES[self.idx][0]
            pcol = GREEN if "G" in sts else (YELLOW if "Y" in sts else RED)
        pygame.draw.rect(scr, (9, 12, 28), R(px, 98, px + pw, 160))
        pygame.draw.rect(scr, dim(pcol, 0.3), R(px, 98, px + pw, 160), 2)
        self.text(pname, (px + pw / 2, 118), pcol, 22, True, "center")
        bx1, bx2 = px + 12, px + pw - 12
        pygame.draw.rect(scr, dim(pcol, 0.5), R(bx1, 138, bx2, 148), 1)
        if self.mode == "AUTO":
            ratio = min(1.0, self.phase_t / PHASES[self.idx][1])
            label = "AUTO CYCLE"
        elif self.mode == "MANUAL":
            ratio = 1.0
            label = "MANUAL HOLD"
        else:
            ratio = 1.0 if blink_on else 0.0
            label = "OVERRIDE"
        if ratio > 0:
            pygame.draw.rect(scr, pcol, R(bx1 + 2, 140, bx1 + 2 + (bx2 - bx1 - 4) * ratio, 147))
        self.text(label, (px + pw / 2, 155), dim(pcol, 0.3), 11, False, "center")

        # status NS / EW
        for i, (name, gi) in enumerate((("NORTH-SOUTH", 2), ("EAST-WEST", 3))):
            y = 182 + i * 24
            st = self.group_state(gi)
            col = LCOL[st]
            if self.mode == "EMERGENCY" and not blink_on:
                col = dim(RED, 0.7)
            pygame.draw.circle(scr, dim(col, 0.6), (px + 9, y), 7)
            pygame.draw.circle(scr, col, (px + 9, y), 7, 2)
            self.text(name, (px + 28, y), (159, 180, 255), 14, True, "midleft")
            self.text("%s  %s" % (LNAME[st], self.countdown(gi)), (px + pw, y), col, 14, True, "midright")

        # telemetri
        stats = [
            ("VEHICLES PASSED", "%d" % self.passed, CYAN),
            ("WAITING AT LIGHT", "%d" % self.waiting, ORANGE if self.waiting > 6 else GREEN),
            ("ACTIVE VEHICLES", "%d" % len(self.cars), CYAN),
            ("FLOW / MIN", "%d" % len(self.pass_times), MAGENTA),
            ("TRAFFIC DENSITY", "%d%%" % int(self.spawn_rate * 100), YELLOW),
            ("FPS / FX", "%d %s" % (self.fps, "LITE" if self.lite else "FULL"), dim(TERM, 0.2)),
        ]
        for i, (lab, val, col) in enumerate(stats):
            y = 242 + i * 18
            self.text(lab, (px, y), (127, 140, 196), 13, False, "midleft")
            self.text(val, (px + pw, y), col, 14, True, "midright")

        # tombol
        mx, my = self.mouse
        for (label, x1, y1, x2, y2, action, active, colr) in self.buttons:
            hover = x1 <= mx <= x2 and y1 <= my <= y2
            on = active()
            if on or hover:
                pygame.draw.rect(scr, dim(colr, 0.75), R(x1, y1, x2, y2))
            else:
                pygame.draw.rect(scr, (8, 10, 24), R(x1, y1, x2, y2))
            pygame.draw.rect(scr, colr if (on or hover) else dim(colr, 0.45),
                             R(x1, y1, x2, y2), 2 if on else 1)
            self.text(label, ((x1 + x2) / 2, (y1 + y2) / 2),
                      colr if (on or hover) else dim(colr, 0.2), 13, True, "center")

        # syslog
        n = len(self.logs)
        for i, line in enumerate(self.logs):
            age = n - 1 - i
            col = dim(TERM, min(0.8, age * 0.1))
            self.text("> " + line, (px, 518 + i * 20), col, 12, False, "midleft")
        if blink_on:
            self.text("> _", (px, 518 + n * 20), TERM, 12, False, "midleft")


async def main():
    pygame.init()
    pygame.display.set_caption("NEO-TRAFFIC // Cyberpunk Traffic Light Simulator")
    screen = pygame.display.set_mode((W, H))
    app = App(screen)
    await app.run()
    pygame.quit()


# pygbag: panggilan ini harus di baris paling akhir, jangan ada kode lagi setelahnya
asyncio.run(main())
