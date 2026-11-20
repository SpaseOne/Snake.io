import pygame
import random
import math
import array

# ==================== ИНИЦИАЛИЗАЦИЯ ====================
pygame.display.init()
pygame.font.init()
try:
    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
    AUDIO_OK = True
except Exception as e:
    print("mixer init failed:", e)
    AUDIO_OK = False

info = pygame.display.Info()
WIDTH, HEIGHT = info.current_w, info.current_h
if WIDTH <= 0 or HEIGHT <= 0:
    WIDTH, HEIGHT = 1280, 720

try:
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.NOFRAME)
except Exception:
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
screen.fill((20, 60, 30))
pygame.display.flip()
clock = pygame.time.Clock()
pygame.event.pump()

SR = 44100
sound_enabled = False
muted = False
eat_sound = crash_sound = gold_sound = poison_sound = None
monster_hit_sound = laser_sound = boss_hit_sound = shield_sound = None
bg_music = None

menu_font = pygame.font.SysFont("sans", max(28, int(min(WIDTH, HEIGHT) * 0.06)), bold=True)
btn_font = pygame.font.SysFont("sans", max(22, int(min(WIDTH, HEIGHT) * 0.045)), bold=True)
small_font = pygame.font.SysFont("sans", max(14, int(min(WIDTH, HEIGHT) * 0.03)), bold=True)
tiny_font = pygame.font.SysFont("sans", max(12, int(min(WIDTH, HEIGHT) * 0.025)))
font = menu_font

title_font = pygame.font.SysFont("sans", max(48, int(min(WIDTH, HEIGHT) * 0.11)), bold=True)
author_font = pygame.font.SysFont("sans", max(18, int(min(WIDTH, HEIGHT) * 0.038)), bold=True, italic=True)

def draw_loading(progress, text="Загрузка..."):
    screen.fill((20, 45, 30))
    pygame.draw.rect(screen, (40, 90, 55), (0, 0, WIDTH, HEIGHT), 8)
    title = menu_font.render("ЗМЕЙКА", True, (140, 220, 130))
    screen.blit(title, (WIDTH // 2 - title.get_width() // 2, HEIGHT // 2 - 80))
    t = small_font.render(text, True, (200, 220, 200))
    screen.blit(t, (WIDTH // 2 - t.get_width() // 2, HEIGHT // 2 - 10))
    bar_w = int(WIDTH * 0.5); bar_h = 14
    bx = WIDTH // 2 - bar_w // 2; by = HEIGHT // 2 + 30
    pygame.draw.rect(screen, (30, 60, 40), (bx, by, bar_w, bar_h), border_radius=7)
    pygame.draw.rect(screen, (100, 220, 120), (bx, by, int(bar_w * progress), bar_h), border_radius=7)
    pygame.draw.rect(screen, (200, 240, 200), (bx, by, bar_w, bar_h), 2, border_radius=7)
    pygame.display.flip()
    pygame.event.pump()

# ==================== СИНТЕЗ ====================
def make_stereo_sound(samples):
    buf = array.array("h")
    for s in samples:
        v = max(-1.0, min(1.0, s))
        iv = int(v * 32767)
        buf.append(iv); buf.append(iv)
    return pygame.mixer.Sound(buffer=buf.tobytes())

def adsr(i, n, a=0.01, d=0.05, s=0.7, r=0.12):
    t = i / SR; total = n / SR
    if t < a: return t / a
    if t < a + d: return 1.0 - (1.0 - s) * ((t - a) / d)
    if t < total - r: return s
    return s * ((total - t) / r) if r > 0 else 0.0

def synth_tone(freq, dur, vol=0.3, wave="sine", vibrato=0.0, detune=0.0):
    n = int(SR * dur)
    out = [0.0] * n
    phase = 0.0; phase2 = 0.0
    for i in range(n):
        t = i / SR
        f = freq
        if vibrato > 0:
            f *= 1.0 + vibrato * math.sin(2 * math.pi * 5.5 * t)
        phase += 2 * math.pi * f / SR
        if wave == "sine":   v = math.sin(phase)
        elif wave == "square": v = 1.0 if math.sin(phase) > 0 else -1.0
        elif wave == "saw":  v = 2.0 * ((phase / (2 * math.pi)) % 1.0) - 1.0
        elif wave == "triangle":
            p = (phase / (2 * math.pi)) % 1.0
            v = 4 * abs(p - 0.5) - 1
        else: v = math.sin(phase)
        if detune > 0:
            phase2 += 2 * math.pi * f * (1 + detune) / SR
            v = 0.6 * v + 0.4 * math.sin(phase2)
        out[i] = v * adsr(i, n) * vol
    return out

def seq(notes, durs, vol=0.3, wave="sine", vib=0.0, detune=0.0):
    out = []
    for f, d in zip(notes, durs):
        out.extend(synth_tone(f, d, vol, wave, vib, detune))
    return out

def build_song(melody, mdur, bass, bdur, vol_mel=0.09, vol_bass=0.07,
               wave_mel="triangle", wave_bass="sine", drums=None, drum_vol=0.1):
    mel = seq(melody, (mdur,) * len(melody), vol=vol_mel, wave=wave_mel, vib=0.012, detune=0.004)
    bas = seq(bass, (bdur,) * len(bass), vol=vol_bass, wave=wave_bass)
    n = max(len(mel), len(bas))
    out = [0.0] * n
    for i, s in enumerate(mel): out[i] += s
    for i, s in enumerate(bas): out[i] += s
    if drums:
        step = int(SR * drums["interval"])
        for k in range(0, n, step):
            for j in range(min(int(SR * 0.05), n - k)):
                env = adsr(j, int(SR * 0.05), a=0.001, d=0.01, s=0.5, r=0.02)
                out[k + j] += math.sin(2 * math.pi * 65 * j / SR) * env * drum_vol
    return out

SONGS = []
SONG_NAMES = ["Летняя", "Минорная", "Энергичная", "Восточная", "Грустная"]
_song_cache = {}
_song_lengths = {}

def build_all_audio():
    global sound_enabled, eat_sound, crash_sound, gold_sound, poison_sound
    global monster_hit_sound, laser_sound, boss_hit_sound, shield_sound
    if not AUDIO_OK: return
    try:
        draw_loading(0.0, "Синтез звуков...")
        eat_sound = make_stereo_sound(seq((523, 659, 784, 1047), (0.05, 0.05, 0.06, 0.12), vol=0.22, wave="triangle", vib=0.02, detune=0.003))
        draw_loading(0.08, "Синтез звуков...")
        crash_sound = make_stereo_sound(seq((220, 165, 110, 82, 55), (0.08, 0.1, 0.12, 0.14, 0.3), vol=0.3, wave="saw", vib=0.06, detune=0.01))
        draw_loading(0.14, "Синтез звуков...")
        gold_sound = make_stereo_sound(seq((880, 1047, 1319, 1568, 2093), (0.05, 0.05, 0.06, 0.08, 0.18), vol=0.25, wave="triangle", vib=0.04, detune=0.005))
        poison_sound = make_stereo_sound(seq((300, 220, 150, 100), (0.08, 0.1, 0.12, 0.25), vol=0.28, wave="saw", vib=0.08, detune=0.02))
        draw_loading(0.22, "Синтез звуков...")
        monster_hit_sound = make_stereo_sound(seq((180, 120, 90, 60), (0.06, 0.08, 0.12, 0.25), vol=0.3, wave="saw", vib=0.1, detune=0.03))
        laser_sound = make_stereo_sound(seq((1500, 1200, 900, 600, 400), (0.03, 0.04, 0.05, 0.06, 0.15), vol=0.18, wave="saw", vib=0.15, detune=0.02))
        boss_hit_sound = make_stereo_sound(seq((400, 300, 200, 100, 60), (0.08, 0.1, 0.14, 0.2, 0.35), vol=0.32, wave="saw", vib=0.08, detune=0.02))
        shield_sound = make_stereo_sound(seq((600, 900, 1200, 1500), (0.06, 0.06, 0.08, 0.15), vol=0.25, wave="triangle", vib=0.05, detune=0.01))

        SONG1 = build_song(
            melody=(262, 330, 392, 523, 392, 330, 294, 349, 440, 523, 440, 349,
                    262, 330, 392, 523, 659, 523, 392, 330, 294, 349, 440, 587,
                    523, 440, 392, 330, 294, 262, 294, 330),
            mdur=0.20,
            bass=(131, 131, 165, 165, 131, 131, 196, 196, 131, 131, 165, 165,
                  131, 131, 196, 196) * 2, bdur=0.40,
            wave_mel="triangle", wave_bass="sine")
        SONG2 = build_song(
            melody=(220, 262, 330, 440, 330, 262, 196, 233, 294, 392, 294, 233,
                    220, 262, 330, 440, 523, 440, 330, 262, 196, 233, 294, 392,
                    349, 294, 262, 220, 196, 175, 196, 220),
            mdur=0.24,
            bass=(110, 110, 131, 131, 110, 110, 147, 147, 110, 110, 131, 131,
                  110, 110, 147, 147) * 2, bdur=0.48,
            wave_mel="sine", wave_bass="triangle")
        SONG3 = build_song(
            melody=(392, 440, 523, 587, 659, 587, 523, 440, 392, 349, 392, 440,
                    523, 587, 698, 784, 698, 587, 523, 440, 392, 349, 294, 349,
                    392, 440, 523, 587, 659, 698, 784, 880),
            mdur=0.14,
            bass=(196, 196, 261, 261, 196, 196, 261, 261, 196, 196, 261, 261,
                  196, 196, 261, 261) * 2, bdur=0.28,
            wave_mel="square", wave_bass="sine",
            drums={"interval": 0.28}, drum_vol=0.12)
        SONG4 = build_song(
            melody=(330, 349, 415, 440, 494, 523, 587, 659, 587, 523, 494, 440,
                    415, 349, 330, 294, 330, 349, 415, 440, 523, 587, 659, 698,
                    659, 587, 523, 494, 440, 415, 349, 330),
            mdur=0.26,
            bass=(165, 165, 175, 175, 208, 208, 220, 220, 165, 165, 175, 175,
                  208, 208, 220, 220) * 2, bdur=0.52,
            wave_mel="sine", wave_bass="saw")
        SONG5 = build_song(
            melody=(587, 523, 440, 392, 349, 392, 440, 523, 587, 523, 440, 392,
                    349, 294, 262, 349, 392, 440, 494, 440, 392, 349, 294, 262,
                    233, 262, 294, 349, 392, 440, 494, 523),
            mdur=0.30,
            bass=(147, 147, 175, 175, 147, 147, 131, 131, 147, 147, 175, 175,
                  147, 147, 131, 131) * 2, bdur=0.60,
            wave_mel="saw", wave_bass="triangle")

        song_samples = [SONG1, SONG2, SONG3, SONG4, SONG5]
        for k, samples in enumerate(song_samples):
            draw_loading(0.30 + (k / 5) * 0.65, f"Песня {k+1}/5 — {SONG_NAMES[k]}")
            _song_cache[k] = make_stereo_sound(samples)
            _song_lengths[k] = len(samples) // 2
            SONGS.append(samples)
        draw_loading(1.0, "Готово!")
        sound_enabled = True
    except Exception as e:
        print("audio build error:", e)
        import traceback; traceback.print_exc()
        sound_enabled = False

build_all_audio()

# ==================== ЦВЕТА ====================
GRASS_LIGHT = (46, 115, 58); GRASS_DARK = (33, 88, 43)
WALL_COLOR = (95, 100, 108); WALL_DARK = (55, 59, 66); WALL_LIGHT = (140, 146, 156)
STONE_BLOCK = (110, 105, 100); STONE_EDGE = (80, 76, 72); STONE_HIGHLIGHT = (150, 145, 138)
SNAKE_MAIN = (58, 130, 45); SNAKE_DARK = (30, 78, 22); SNAKE_LIGHT = (110, 180, 70)
SNAKE_BELLY = (200, 220, 140); EYE_WHITE = (245, 240, 200); EYE_PUPIL = (15, 15, 15)
APPLE_RED = (210, 30, 30); APPLE_DARK = (140, 15, 15); APPLE_HIGHLIGHT = (255, 160, 160)
GOLD = (255, 200, 40); GOLD_DARK = (180, 130, 10); GOLD_LIGHT = (255, 245, 160)
POISON = (140, 60, 180); POISON_DARK = (80, 30, 110); POISON_LIGHT = (200, 140, 240)
SHADOW = (22, 60, 28)
MONSTER_BODY = (70, 40, 90); MONSTER_EDGE = (40, 20, 55); MONSTER_EYE = (255, 60, 60)
MONSTER_LEG = (30, 15, 40)
LASER_RED = (255, 40, 40); LASER_WARN = (255, 220, 80)
SHIELD_C = (100, 200, 255); SHIELD_DARK = (40, 120, 180)
BOSS_BODY = (200, 40, 40); BOSS_DARK = (120, 15, 15); BOSS_EYE = (255, 240, 60)
BOSS_SPIKE = (255, 200, 150)
EVENT_COL = (255, 220, 100)

SPEED_EASY = 5.5
SEGMENT_DIST = 5
BASE_RADIUS = max(10, int(min(WIDTH, HEIGHT) * 0.032))
WALL_THICKNESS = max(16, int(min(WIDTH, HEIGHT) * 0.045))
TOP_OFFSET = int(WALL_THICKNESS * 2.4)

# ==================== ФОН ИГРЫ ====================
bg_surface = pygame.Surface((WIDTH, HEIGHT))
for y in range(TOP_OFFSET - WALL_THICKNESS, HEIGHT):
    t = (y - TOP_OFFSET) / max(1, HEIGHT - TOP_OFFSET)
    pygame.draw.line(bg_surface, (
        int(GRASS_LIGHT[0] * (1 - t) + GRASS_DARK[0] * t),
        int(GRASS_LIGHT[1] * (1 - t) + GRASS_DARK[1] * t),
        int(GRASS_LIGHT[2] * (1 - t) + GRASS_DARK[2] * t)), (0, y), (WIDTH, y))
for _ in range(3000):
    gx = random.randint(WALL_THICKNESS, WIDTH - WALL_THICKNESS)
    gy = random.randint(TOP_OFFSET, HEIGHT - WALL_THICKNESS)
    col = random.choice([(40, 105, 52), (33, 88, 43), (55, 135, 65)])
    pygame.draw.line(bg_surface, col, (gx, gy), (gx + random.randint(-2, 2), gy - random.randint(4, 12)), 1)
pygame.draw.rect(bg_surface, (25, 28, 33), (0, 0, WIDTH, TOP_OFFSET - WALL_THICKNESS))
walls = (
    pygame.Rect(0, TOP_OFFSET - WALL_THICKNESS, WIDTH, WALL_THICKNESS),
    pygame.Rect(0, HEIGHT - WALL_THICKNESS, WIDTH, WALL_THICKNESS),
    pygame.Rect(0, TOP_OFFSET - WALL_THICKNESS, WALL_THICKNESS, HEIGHT),
    pygame.Rect(WIDTH - WALL_THICKNESS, TOP_OFFSET - WALL_THICKNESS, WALL_THICKNESS, HEIGHT),
)
pygame.draw.rect(bg_surface, SHADOW, (WALL_THICKNESS, TOP_OFFSET, WIDTH - WALL_THICKNESS * 2, 14))
pygame.draw.rect(bg_surface, SHADOW, (WALL_THICKNESS, TOP_OFFSET, 14, HEIGHT - TOP_OFFSET - WALL_THICKNESS))
for w in walls:
    pygame.draw.rect(bg_surface, WALL_COLOR, w)
    pygame.draw.rect(bg_surface, WALL_DARK, w, 3)
bs = WALL_THICKNESS
for x in range(0, WIDTH, bs):
    for y in (TOP_OFFSET - WALL_THICKNESS, HEIGHT - WALL_THICKNESS):
        off = (x // bs) % 2
        pygame.draw.rect(bg_surface, WALL_DARK, (x + 1, y + 1 + off, bs - 2, bs - 2), 2)
        pygame.draw.line(bg_surface, WALL_LIGHT, (x + 3, y + 3 + off), (x + bs - 5, y + 3 + off), 2)
for y in range(TOP_OFFSET - WALL_THICKNESS, HEIGHT, bs):
    for x in (0, WIDTH - WALL_THICKNESS):
        pygame.draw.rect(bg_surface, WALL_DARK, (x + 1, y + 1, bs - 2, bs - 2), 2)
        pygame.draw.line(bg_surface, WALL_LIGHT, (x + 3, y + 3), (x + 3, y + bs - 5), 2)

# ==================== ХЕЛПЕРЫ ====================
def in_field(x, y):
    return (WALL_THICKNESS + BASE_RADIUS < x < WIDTH - WALL_THICKNESS - BASE_RADIUS and
            TOP_OFFSET + BASE_RADIUS < y < HEIGHT - WALL_THICKNESS - BASE_RADIUS)

def collides_obstacle(x, y, obstacles):
    pad = BASE_RADIUS * 2
    for o in obstacles:
        if (x > o.left - pad and x < o.right + pad and
            y > o.top - pad and y < o.bottom + pad):
            return o
    return None

def find_free_spot(obstacles, head, margin_mult=3):
    margin = WALL_THICKNESS + BASE_RADIUS * margin_mult
    x = random.randint(margin, WIDTH - margin)
    y = random.randint(TOP_OFFSET + BASE_RADIUS * margin_mult, HEIGHT - margin)
    if collides_obstacle(x, y, obstacles):
        return None
    if math.hypot(x - head[0], y - head[1]) < BASE_RADIUS * 4:
        return None
    return (float(x), float(y))

def spawn_apple(snake_head, obstacles):
    for _ in range(40):
        spot = find_free_spot(obstacles, snake_head)
        if spot: return spot
    return (float(WIDTH // 2), float(HEIGHT // 2))

def make_obstacles(level):
    obs = []
    if level < 1: return obs
    count = min(6, level)
    margin = WALL_THICKNESS + BASE_RADIUS * 6
    for _ in range(count * 5):
        bw = random.choice([60, 80, 100]); bh = random.choice([20, 30, 40])
        bx = random.randint(margin, WIDTH - margin - bw)
        by = random.randint(TOP_OFFSET + BASE_RADIUS * 4, HEIGHT - margin - bh)
        r = pygame.Rect(bx, by, bw, bh)
        if any(r.colliderect(o.inflate(50, 50)) for o in obs): continue
        if r.collidepoint(WIDTH // 2, (HEIGHT + TOP_OFFSET) // 2): continue
        obs.append(r)
        if len(obs) >= count: break
    return obs

def draw_obstacle(surf, r):
    pygame.draw.rect(surf, SHADOW, (r.x + 4, r.y + 6, r.w, r.h), border_radius=6)
    pygame.draw.rect(surf, STONE_BLOCK, r, border_radius=6)
    pygame.draw.rect(surf, STONE_EDGE, r, 3, border_radius=6)
    for i in range(r.y + 8, r.y + r.h - 4, 12):
        pygame.draw.line(surf, STONE_EDGE, (r.x + 4, i), (r.x + r.w - 4, i), 1)
        pygame.draw.line(surf, STONE_HIGHLIGHT, (r.x + 4, i + 1), (r.x + r.w - 4, i + 1), 1)

def add_particles(store, x, y, color, count=10, speed=3.0, life=30):
    count = min(count, 15)
    for _ in range(count):
        a = random.uniform(0, 2 * math.pi)
        s = random.uniform(0.5, speed)
        store.append([x, y, math.cos(a) * s, math.sin(a) * s, life, color])

def update_particles(store):
    for p in store:
        p[0] += p[2]; p[1] += p[3]; p[2] *= 0.94; p[3] = p[3] * 0.94 + 0.08; p[4] -= 1
    store[:] = [p for p in store if p[4] > 0]

def draw_particles(surf, store):
    for x, y, vx, vy, life, color in store:
        r = max(1, int(life / 6))
        pygame.draw.circle(surf, color, (int(x), int(y)), r)

# ==================== ОТРИСОВКА ОБЪЕКТОВ ====================
def draw_apple(surf, x, y, r, pulse, kind):
    rr = int(r * (1 + 0.06 * math.sin(pulse * 0.15)))
    if kind == "gold": body, dark, hi = GOLD, GOLD_DARK, GOLD_LIGHT
    elif kind == "poison": body, dark, hi = POISON, POISON_DARK, POISON_LIGHT
    elif kind == "shield": body, dark, hi = SHIELD_C, SHIELD_DARK, (200, 240, 255)
    else: body, dark, hi = APPLE_RED, APPLE_DARK, APPLE_HIGHLIGHT
    pygame.draw.circle(surf, SHADOW, (int(x) + 5, int(y) + 7), rr)
    pygame.draw.circle(surf, dark, (int(x), int(y)), rr)
    pygame.draw.circle(surf, body, (int(x) - 1, int(y) - 1), rr - 2)
    hx = int(x - rr * 0.35); hy = int(y - rr * 0.4)
    pygame.draw.circle(surf, hi, (hx, hy), max(2, rr // 3))
    pygame.draw.circle(surf, (255, 255, 255), (hx - 1, hy - 1), max(1, rr // 6))
    if kind == "gold":
        for a in range(0, 360, 90):
            ang = math.radians(a + pulse * 3)
            pygame.draw.line(surf, GOLD_LIGHT,
                (x + math.cos(ang) * (rr + 4), y + math.sin(ang) * (rr + 4)),
                (x + math.cos(ang) * (rr + 10), y + math.sin(ang) * (rr + 10)), 2)
    if kind == "shield":
        for a in range(0, 360, 90):
            ang = math.radians(a + pulse * 4)
            pygame.draw.line(surf, (220, 245, 255),
                (x + math.cos(ang) * (rr + 3), y + math.sin(ang) * (rr + 3)),
                (x + math.cos(ang) * (rr + 8), y + math.sin(ang) * (rr + 8)), 1)
    if kind == "poison":
        for k in range(3):
            ang = math.radians(k * 120 + pulse * 2)
            px = x + math.cos(ang) * rr * 0.7
            py = y + math.sin(ang) * rr * 0.7 + (pulse * 0.5 % 10)
            pygame.draw.circle(surf, POISON_DARK, (int(px), int(py)), 2)

def draw_snake(surf, pts, dir_x, dir_y, apple_pos, game_over, frame, has_shield=False):
    n = len(pts)
    if n < 2: return
    for i in range(n - 1, -1, -1):
        px, py = pts[i]
        taper = 1.0 if i < n * 0.7 else max(0.25, (n - i) / (n * 0.3))
        pygame.draw.circle(surf, SHADOW, (int(px) + 6, int(py) + 9), max(2, int(BASE_RADIUS * taper)))
    for i in range(n - 1, 0, -1):
        px, py = pts[i]
        taper = 1.0 if i < n * 0.7 else max(0.25, (n - i) / (n * 0.3))
        r = max(3, int(BASE_RADIUS * taper))
        wobble = math.sin(frame * 0.15 + i * 0.5) * 1.5
        px += math.cos(math.atan2(dir_y, dir_x) + math.pi / 2) * wobble
        py += math.sin(math.atan2(dir_y, dir_x) + math.pi / 2) * wobble
        base = SNAKE_MAIN if (i // 5) % 2 == 0 else SNAKE_DARK
        pygame.draw.circle(surf, base, (int(px), int(py)), r)
        if r >= 5:
            pygame.draw.circle(surf, SNAKE_DARK, (int(px), int(py)), r, 1)
            pygame.draw.ellipse(surf, SNAKE_BELLY, (int(px) - r // 2, int(py) + r // 4, r, r // 2))
            pygame.draw.circle(surf, SNAKE_LIGHT, (int(px) - r // 3, int(py) - r // 3), max(1, r // 4))
    hx, hy = pts[0]
    angle = math.atan2(dir_y, dir_x); hr = BASE_RADIUS + 2
    pygame.draw.circle(surf, SHADOW, (int(hx) + 6, int(hy) + 9), hr + 2)
    head_pts = []
    for a_off in range(0, 360, 20):
        a = math.radians(a_off)
        rx, ry = hr * 1.25, hr * 1.0
        head_pts.append((hx + math.cos(a) * rx * math.cos(angle) - math.sin(a) * ry * math.sin(angle),
                         hy + math.cos(a) * rx * math.sin(angle) + math.sin(a) * ry * math.cos(angle)))
    pygame.draw.polygon(surf, SNAKE_MAIN, head_pts)
    pygame.draw.polygon(surf, SNAKE_DARK, head_pts, 2)
    belly_pts = []
    for a_off in range(150, 390, 20):
        a = math.radians(a_off)
        belly_pts.append((hx + math.cos(a) * hr * 0.9 * math.cos(angle) - math.sin(a) * hr * 0.5 * math.sin(angle),
                          hy + math.cos(a) * hr * 0.9 * math.sin(angle) + math.sin(a) * hr * 0.5 * math.cos(angle)))
    if len(belly_pts) > 2: pygame.draw.polygon(surf, SNAKE_BELLY, belly_pts)
    for side in (-1, 1):
        ex = hx + math.cos(angle) * hr * 0.5 + math.cos(angle + math.pi / 2) * side * hr * 0.65
        ey = hy + math.sin(angle) * hr * 0.5 + math.sin(angle + math.pi / 2) * side * hr * 0.65
        pygame.draw.circle(surf, EYE_WHITE, (int(ex), int(ey)), max(3, hr // 3))
        if not game_over:
            dx_ = apple_pos[0] - ex; dy_ = apple_pos[1] - ey
            d = math.hypot(dx_, dy_) or 1
            px_, py_ = ex + dx_ / d * hr * 0.15, ey + dy_ / d * hr * 0.15
        else:
            px_, py_ = ex, ey
        pygame.draw.circle(surf, EYE_PUPIL, (int(px_), int(py_)), max(1, hr // 5))
        pygame.draw.circle(surf, (255, 255, 255), (int(px_) - 1, int(py_) - 1), max(1, hr // 12))
    if has_shield:
        sr = hr + 8 + int(math.sin(frame * 0.2) * 2)
        surf2 = pygame.Surface((sr * 2, sr * 2), pygame.SRCALPHA)
        pygame.draw.circle(surf2, (*SHIELD_C, 90), (sr, sr), sr)
        pygame.draw.circle(surf2, (*SHIELD_C, 200), (sr, sr), sr, 3)
        surf.blit(surf2, (int(hx - sr), int(hy - sr)))

def draw_monster(surf, x, y, frame):
    r = BASE_RADIUS * 0.9
    pygame.draw.ellipse(surf, SHADOW, (x - r, y + r * 0.4, r * 2, r * 0.6))
    for k in range(8):
        base_ang = k * (math.pi / 4) + math.sin(frame * 0.2 + k) * 0.15
        lx1 = x + math.cos(base_ang) * r * 0.6; ly1 = y + math.sin(base_ang) * r * 0.6
        lx2 = x + math.cos(base_ang) * r * 1.6; ly2 = y + math.sin(base_ang) * r * 1.6 + math.sin(frame * 0.3 + k * 2) * 2
        pygame.draw.line(surf, MONSTER_LEG, (lx1, ly1), (lx2, ly2), 3)
    pygame.draw.circle(surf, MONSTER_BODY, (int(x), int(y)), int(r))
    pygame.draw.circle(surf, MONSTER_EDGE, (int(x), int(y)), int(r), 2)
    for dx, dy, er in [(-r*0.35, -r*0.2, r*0.18), (r*0.35, -r*0.2, r*0.18), (0, r*0.3, r*0.12)]:
        pygame.draw.circle(surf, MONSTER_EYE, (int(x + dx), int(y + dy)), max(2, int(er)))

def draw_boss(surf, x, y, r, hp, max_hp, frame, angry):
    pygame.draw.ellipse(surf, SHADOW, (x - r, y + r * 0.6, r * 2, r * 0.7))
    for k in range(8):
        ang = k * (math.pi / 4) + frame * 0.03
        sp_x = x + math.cos(ang) * r * 0.9; sp_y = y + math.sin(ang) * r * 0.9
        tip_x = x + math.cos(ang) * r * 1.5; tip_y = y + math.sin(ang) * r * 1.5
        pygame.draw.polygon(surf, BOSS_SPIKE, [
            (sp_x + math.cos(ang + 1.5) * 6, sp_y + math.sin(ang + 1.5) * 6),
            (tip_x, tip_y),
            (sp_x + math.cos(ang - 1.5) * 6, sp_y + math.sin(ang - 1.5) * 6)])
    body_col = BOSS_BODY if not angry else (255, 80, 80)
    pygame.draw.circle(surf, BOSS_DARK, (int(x), int(y)), int(r + 3))
    pygame.draw.circle(surf, body_col, (int(x), int(y)), int(r))
    pygame.draw.circle(surf, BOSS_DARK, (int(x), int(y)), int(r), 3)
    eye_r = r * 0.22
    for side in (-1, 1):
        ex = x + side * r * 0.4; ey = y - r * 0.15
        pygame.draw.circle(surf, (250, 250, 250), (int(ex), int(ey)), int(eye_r))
        pygame.draw.circle(surf, BOSS_EYE, (int(ex), int(ey)), int(eye_r * 0.7))
        pygame.draw.circle(surf, (0, 0, 0), (int(ex), int(ey)), int(eye_r * 0.3))
    mouth_y = y + r * 0.35
    pygame.draw.ellipse(surf, (40, 0, 0), (int(x - r * 0.5), int(mouth_y - r * 0.15), int(r), int(r * 0.35)))
    bar_w = r * 2.2; bar_h = 8
    bx = x - bar_w / 2; by = y - r - 20
    pygame.draw.rect(surf, (40, 40, 40), (bx, by, bar_w, bar_h))
    pygame.draw.rect(surf, (220, 40, 40), (bx, by, bar_w * (hp / max_hp), bar_h))
    pygame.draw.rect(surf, (255, 255, 255), (bx, by, bar_w, bar_h), 1)

# ==================== РЕЖИМЫ ====================
DIFFICULTY = {
    "easy":   {"name": "Лёгкая",  "speed": SPEED_EASY, "speed_per_score": 0.12,
               "monsters": 0, "monster_speed": 0.0, "lasers": False, "laser_count": 0, "laser_interval": 15000,
               "events": False, "blackout": False, "boss_score": 15},
    "medium": {"name": "Средняя", "speed": SPEED_EASY + 1.0, "speed_per_score": 0.15,
               "monsters": 1, "monster_speed": 0.9, "lasers": False, "laser_count": 0, "laser_interval": 15000,
               "events": True, "blackout": False, "boss_score": 15},
    "hard":   {"name": "Сложная", "speed": SPEED_EASY + 2.0, "speed_per_score": 0.18,
               "monsters": 3, "monster_speed": 1.3, "lasers": True, "laser_count": 1, "laser_interval": 15000,
               "events": True, "blackout": False, "boss_score": 15},
    "impossible": {"name": "Невозможная", "speed": SPEED_EASY + 3.0, "speed_per_score": 0.22,
               "monsters": 4, "monster_speed": 1.6, "lasers": True, "laser_count": 5, "laser_interval": 8000,
               "events": True, "blackout": True, "boss_score": 10},
}
DIFF_ORDER = ["easy", "medium", "hard", "impossible"]
DIFF_COLORS = {"easy": (100, 200, 120), "medium": (240, 190, 80),
               "hard": (240, 100, 100), "impossible": (200, 60, 200)}

def spawn_monster(snake_head, obstacles, existing):
    margin = WALL_THICKNESS + BASE_RADIUS * 3
    for _ in range(60):
        x = random.randint(margin, WIDTH - margin)
        y = random.randint(TOP_OFFSET + BASE_RADIUS * 4, HEIGHT - margin)
        if collides_obstacle(x, y, obstacles): continue
        if math.hypot(x - snake_head[0], y - snake_head[1]) < BASE_RADIUS * 15: continue
        if any(math.hypot(x - m[0], y - m[1]) < BASE_RADIUS * 8 for m in existing): continue
        return [float(x), float(y), random.uniform(0, 2 * math.pi)]
    return [float(WIDTH * 0.25), float(HEIGHT * 0.25), 0.0]

def spawn_laser():
    horizontal = random.choice([True, False])
    thickness = BASE_RADIUS * 2
    if horizontal:
        y = random.randint(TOP_OFFSET + BASE_RADIUS * 3, HEIGHT - WALL_THICKNESS - BASE_RADIUS * 3)
        rect = pygame.Rect(WALL_THICKNESS, y, WIDTH - WALL_THICKNESS * 2, thickness)
    else:
        x = random.randint(WALL_THICKNESS + BASE_RADIUS * 3, WIDTH - WALL_THICKNESS - BASE_RADIUS * 3)
        rect = pygame.Rect(x, TOP_OFFSET, thickness, HEIGHT - WALL_THICKNESS - TOP_OFFSET)
    now = pygame.time.get_ticks()
    return {"rect": rect, "warn_end": now + 3000, "fire_end": now + 3000 + 1200, "fired": False}

def spawn_boss():
    return {"x": float(WIDTH // 2), "y": float(TOP_OFFSET + BASE_RADIUS * 8),
            "r": BASE_RADIUS * 2.5, "hp": 10, "max_hp": 10, "phase": 0,
            "shoot_timer": 0, "bullets": [], "dir": 0, "speed": 1.0, "angry": False}

EVENT_TYPES = [
    ("speed", "Ускорение!", 5000, 0),
    ("slow", "Замедление", 4000, 0),
    ("apples", "Яблокопад", 5000, 4),
    ("dark", "Туман", 4000, 0),
    ("gold_rush", "Золотая лихорадка", 4000, 3),
]
def pick_event():
    return random.choice(EVENT_TYPES)

def reset_game(diff_key="easy"):
    cfg = DIFFICULTY[diff_key]
    sx, sy = WIDTH // 2, (HEIGHT + TOP_OFFSET) // 2
    pts = [(float(sx - i * SEGMENT_DIST), float(sy)) for i in range(45)]
    obs = make_obstacles(1)
    ax, ay = spawn_apple(pts[0], obs)
    gx, gy = spawn_apple(pts[0], obs)
    sx2, sy2 = spawn_apple(pts[0], obs)
    monsters = []
    for _ in range(cfg["monsters"]):
        monsters.append(spawn_monster(pts[0], obs, monsters))
    now = pygame.time.get_ticks()
    return {
        "points": pts, "dx": 1.0, "dy": 0.0, "tx": 1.0, "ty": 0.0,
        "apple": [ax, ay, "normal"], "gold": [gx, gy, "gold", 0],
        "shield_pickup": [sx2, sy2, "shield"], "poison": None,
        "score": 0, "game_over": False, "obstacles": obs, "level": 1,
        "slow_until": 0, "speed": cfg["speed"],
        "particles": [], "trail": [], "frame": 0, "shake": 0, "grow_pending": 0,
        "monsters": monsters, "lasers": [], "next_laser_time": now + cfg["laser_interval"],
        "difficulty": diff_key, "has_shield": False,
        "boss": None, "boss_spawn_score": cfg["boss_score"],
        "next_event_time": now + 12000, "active_event": None, "event_end": 0,
        "extra_apples": [], "pending_apples": [],
        "blackout_until": 0, "next_blackout_time": now + 20000,
    }

# ==================== МЕНЮ ====================
MENU_BG = pygame.Surface((WIDTH, HEIGHT))
for y in range(HEIGHT):
    t = y / max(1, HEIGHT - 1)
    r = int(15 * (1 - t) + 20 * t)
    g = int(25 * (1 - t) + 70 * t)
    b = int(50 * (1 - t) + 35 * t)
    pygame.draw.line(MENU_BG, (r, g, b), (0, y), (WIDTH, y))

menu_stars = []
for _ in range(120):
    sx = random.randint(0, WIDTH)
    sy = random.randint(0, int(HEIGHT * 0.6))
    br = random.randint(1, 3)
    col = random.choice([(255, 255, 255), (200, 220, 255), (255, 240, 200)])
    menu_stars.append([sx, sy, br, col, random.uniform(0.5, 2.5), random.uniform(0, 6.28)])

MOON_X = int(WIDTH * 0.82); MOON_Y = int(HEIGHT * 0.12); MOON_R = int(min(WIDTH, HEIGHT) * 0.05)
pygame.draw.circle(MENU_BG, (240, 240, 200), (MOON_X, MOON_Y), MOON_R)
pygame.draw.circle(MENU_BG, (220, 220, 170), (MOON_X - MOON_R//3, MOON_Y - MOON_R//4), max(2, MOON_R//4))
pygame.draw.circle(MENU_BG, (220, 220, 170), (MOON_X + MOON_R//4, MOON_Y + MOON_R//3), max(2, MOON_R//5))
pygame.draw.circle(MENU_BG, (220, 220, 170), (MOON_X + MOON_R//3, MOON_Y - MOON_R//3), max(1, MOON_R//6))
moon_glow = pygame.Surface((MOON_R*6, MOON_R*6), pygame.SRCALPHA)
for gr in range(MOON_R*3, MOON_R, -3):
    a = max(0, 60 - (gr - MOON_R) * 3)
    pygame.draw.circle(moon_glow, (255, 255, 220, a), (MOON_R*3, MOON_R*3), gr)
MENU_BG.blit(moon_glow, (MOON_X - MOON_R*3, MOON_Y - MOON_R*3), special_flags=pygame.BLEND_RGBA_ADD)

for hill_layer in range(3):
    pts = [(0, HEIGHT)]
    base_y = int(HEIGHT * 0.75 + hill_layer * HEIGHT * 0.06)
    amp = int(HEIGHT * 0.08)
    for x in range(0, WIDTH + 20, 20):
        y = base_y + int(math.sin(x * 0.005 + hill_layer * 2) * amp) + int(math.sin(x * 0.013 + hill_layer) * amp * 0.4)
        pts.append((x, y))
    pts.append((WIDTH, HEIGHT))
    col = (int(20 + hill_layer * 10), int(45 + hill_layer * 15), int(35 + hill_layer * 8))
    pygame.draw.polygon(MENU_BG, col, pts)

grass_pts = [(0, HEIGHT)]
for x in range(0, WIDTH + 10, 10):
    y = HEIGHT - int(HEIGHT * 0.04) + int(math.sin(x * 0.02) * 5)
    grass_pts.append((x, y))
grass_pts.append((WIDTH, HEIGHT))
pygame.draw.polygon(MENU_BG, (35, 100, 45), grass_pts)

_vignette = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
for i in range(15):
    a = 6 + i * 4
    pygame.draw.rect(_vignette, (0, 0, 0, a), (0, 0, WIDTH, HEIGHT), 80 - i * 5, border_radius=40)
MENU_BG.blit(_vignette, (0, 0))

fireflies = []
for _ in range(30):
    fireflies.append({
        "x": random.uniform(0, WIDTH),
        "y": random.uniform(0, HEIGHT),
        "vx": random.uniform(-0.5, 0.5),
        "vy": random.uniform(-0.5, 0.5),
        "phase": random.uniform(0, 6.28),
        "size": random.randint(2, 4),
    })

menu_decor_apples = []
for _ in range(5):
    menu_decor_apples.append({
        "x": random.randint(int(WIDTH * 0.05), int(WIDTH * 0.95)),
        "y": random.randint(int(HEIGHT * 0.15), int(HEIGHT * 0.75)),
        "kind": random.choice(["normal", "gold", "shield"]),
        "phase": random.uniform(0, 6.28),
        "speed": random.uniform(0.01, 0.03),
    })

menu_snake_pts = []
menu_snake_phase = 0.0

def update_menu_snake():
    global menu_snake_phase, menu_snake_pts
    menu_snake_phase += 0.035
    cx = WIDTH * 0.5 + math.sin(menu_snake_phase * 0.7) * WIDTH * 0.3
    cy = HEIGHT * 0.82 + math.sin(menu_snake_phase * 1.3) * HEIGHT * 0.04
    menu_snake_pts.insert(0, (cx, cy))
    if len(menu_snake_pts) > 45:
        menu_snake_pts.pop()

def draw_menu_bg(frame):
    screen.blit(MENU_BG, (0, 0))
    for sx, sy, br, col, speed, phase in menu_stars:
        twinkle = 0.6 + 0.4 * math.sin(frame * 0.05 * speed + phase)
        r = max(1, int(br * twinkle))
        pygame.draw.circle(screen, col, (sx, sy), r)
    for ff in fireflies:
        ff["x"] += ff["vx"]; ff["y"] += ff["vy"]
        if ff["x"] < 0 or ff["x"] > WIDTH: ff["vx"] *= -1
        if ff["y"] < 0 or ff["y"] > HEIGHT: ff["vy"] *= -1
        glow = 0.5 + 0.5 * math.sin(frame * 0.1 + ff["phase"])
        col = (int(200 * glow + 55), int(255 * glow), int(150 * glow + 50))
        pygame.draw.circle(screen, col, (int(ff["x"]), int(ff["y"])), ff["size"])
        s = pygame.Surface((ff["size"] * 6, ff["size"] * 6), pygame.SRCALPHA)
        pygame.draw.circle(s, (*col, 40), (ff["size"] * 3, ff["size"] * 3), ff["size"] * 3)
        screen.blit(s, (ff["x"] - ff["size"] * 3, ff["y"] - ff["size"] * 3))
    for ap in menu_decor_apples:
        ap["phase"] += ap["speed"]
        ax = ap["x"] + math.sin(ap["phase"]) * 20
        ay = ap["y"] + math.cos(ap["phase"] * 0.7) * 15
        draw_apple(screen, ax, ay, BASE_RADIUS * 0.85, frame + ap["phase"] * 30, ap["kind"])
    if len(menu_snake_pts) > 2:
        for i in range(len(menu_snake_pts) - 1, 0, -1):
            px, py = menu_snake_pts[i]
            taper = 1.0 if i < len(menu_snake_pts) * 0.7 else max(0.3, (len(menu_snake_pts) - i) / (len(menu_snake_pts) * 0.3))
            r = max(3, int(BASE_RADIUS * 0.75 * taper))
            base = SNAKE_MAIN if (i // 4) % 2 == 0 else SNAKE_DARK
            pygame.draw.circle(screen, base, (int(px), int(py)), r)
            if r >= 5:
                pygame.draw.circle(screen, SNAKE_LIGHT, (int(px) - r // 3, int(py) - r // 3), max(1, r // 4))
        hx, hy = menu_snake_pts[0]
        pygame.draw.circle(screen, SNAKE_MAIN, (int(hx), int(hy)), int(BASE_RADIUS * 0.95))
        pygame.draw.circle(screen, SNAKE_DARK, (int(hx), int(hy)), int(BASE_RADIUS * 0.95), 2)
        pygame.draw.circle(screen, EYE_WHITE, (int(hx + 4), int(hy - 3)), 3)
        pygame.draw.circle(screen, EYE_PUPIL, (int(hx + 5), int(hy - 3)), 1)

def get_menu_buttons():
    bw = int(WIDTH * 0.55); bh = int(HEIGHT * 0.1); gap = int(HEIGHT * 0.025)
    total = len(DIFF_ORDER) * bh + (len(DIFF_ORDER) - 1) * gap
    start_y = (HEIGHT - total) // 2 + int(HEIGHT * 0.08)
    return [(key, pygame.Rect((WIDTH - bw) // 2, start_y + i * (bh + gap), bw, bh))
            for i, key in enumerate(DIFF_ORDER)]

def get_help_button():
    size = int(min(WIDTH, HEIGHT) * 0.08)
    return pygame.Rect(WIDTH - size - 20, HEIGHT - size - 20, size, size)

def draw_help_button(hover, frame):
    r = get_help_button()
    if hover:
        col = (120, 220, 255)
        glow = int(4 + math.sin(frame * 0.15) * 2)
        pygame.draw.circle(screen, (60, 140, 200), r.center, r.w // 2 + glow)
    else:
        col = (70, 130, 180)
    pygame.draw.circle(screen, col, r.center, r.w // 2)
    pygame.draw.circle(screen, (200, 240, 255), r.center, r.w // 2, 3)
    q = menu_font.render("?", True, (255, 255, 255))
    screen.blit(q, (r.centerx - q.get_width() // 2, r.centery - q.get_height() // 2))

def draw_gradient_button(rect, col_top, col_bottom, border_col, border_w=3, hover=False, frame=0):
    shadow_surf = pygame.Surface((rect.w + 8, rect.h + 8), pygame.SRCALPHA)
    pygame.draw.rect(shadow_surf, (0, 0, 0, 100), (0, 0, rect.w + 8, rect.h + 8), border_radius=16)
    screen.blit(shadow_surf, (rect.x - 4 + (3 if hover else 2), rect.y - 4 + (5 if hover else 4)))
    btn = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    for y in range(rect.h):
        t = y / max(1, rect.h - 1)
        c = (int(col_top[0] * (1 - t) + col_bottom[0] * t),
             int(col_top[1] * (1 - t) + col_bottom[1] * t),
             int(col_top[2] * (1 - t) + col_bottom[2] * t))
        pygame.draw.rect(btn, c, (0, y, rect.w, 1))
    highlight = pygame.Surface((rect.w - 20, rect.h // 3), pygame.SRCALPHA)
    highlight.fill((255, 255, 255, 40))
    btn.blit(highlight, (10, 4))
    mask = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255), (0, 0, rect.w, rect.h), border_radius=16)
    btn.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    screen.blit(btn, (rect.x, rect.y))
    if border_w > 0:
        pygame.draw.rect(screen, border_col, rect, border_w, border_radius=16)

def draw_title(frame):
    title_text = "ЗМЕЙКА"
    shadow = title_font.render(title_text, True, (10, 20, 10))
    title = title_font.render(title_text, True, (240, 250, 200))
    grad_surf = pygame.Surface((title.get_width(), title.get_height()), pygame.SRCALPHA)
    for y in range(title.get_height()):
        t = y / max(1, title.get_height() - 1)
        c = (int(140 * (1 - t) + 240 * t),
             int(220 * (1 - t) + 250 * t),
             int(100 * (1 - t) + 200 * t))
        pygame.draw.line(grad_surf, c, (0, y), (title.get_width(), y))
    mask_title = pygame.Surface((title.get_width(), title.get_height()), pygame.SRCALPHA)
    mask_title.blit(title, (0, 0))
    grad_surf.blit(mask_title, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    scale = 1.0 + math.sin(frame * 0.06) * 0.03
    tw = int(title.get_width() * scale)
    th = int(title.get_height() * scale)
    scaled = pygame.transform.smoothscale(grad_surf, (tw, th))
    cx = WIDTH // 2
    title_y = int(HEIGHT * 0.07)
    for glow_off in range(8, 0, -2):
        glow_surf = pygame.transform.smoothscale(grad_surf, (tw + glow_off * 2, th + glow_off * 2))
        glow_alpha = int(20 * (1 - glow_off / 10))
        glow_surf.set_alpha(glow_alpha)
        screen.blit(glow_surf, (cx - glow_surf.get_width() // 2, title_y - glow_off))
    screen.blit(pygame.transform.smoothscale(shadow, (tw, th)), (cx - tw // 2 + 4, title_y + 5))
    screen.blit(scaled, (cx - tw // 2, title_y))
    shine_x = int((math.sin(frame * 0.02) * 0.5 + 0.5) * tw)
    shine = pygame.Surface((40, th), pygame.SRCALPHA)
    for i in range(40):
        a = int(80 * (1 - abs(i - 20) / 20))
        pygame.draw.line(shine, (255, 255, 255, a), (i, 0), (i, th))
    scaled_with_shine = scaled.copy()
    scaled_with_shine.blit(shine, (shine_x - 20, 0), special_flags=pygame.BLEND_RGBA_ADD)
    screen.blit(scaled_with_shine, (cx - tw // 2, title_y))
    return title_y + th

def draw_menu(selected, frame):
    draw_menu_bg(frame)
    title_bottom = draw_title(frame)

    author_txt = author_font.render("by SpaseNik", True, (220, 240, 220))
    author_glow = author_font.render("by SpaseNik", True, (140, 220, 150))
    author_shadow = author_font.render("by SpaseNik", True, (20, 40, 20))
    ax = WIDTH // 2 - author_txt.get_width() // 2
    ay = title_bottom + 8
    glow_alpha = int(110 + 70 * math.sin(frame * 0.08))
    author_glow.set_alpha(glow_alpha)
    screen.blit(author_glow, (ax - 1, ay - 1))
    screen.blit(author_glow, (ax + 1, ay + 1))
    screen.blit(author_shadow, (ax + 2, ay + 2))
    screen.blit(author_txt, (ax, ay))
    for side in (-1, 1):
        lx1 = ax + (author_txt.get_width() + 12) if side > 0 else ax - 12
        lx2 = lx1 + side * 50
        ly = ay + author_txt.get_height() // 2
        pygame.draw.line(screen, (120, 200, 140), (lx1, ly), (lx2, ly), 2)
        pygame.draw.circle(screen, (160, 230, 180), (lx2, ly), 2)

    sub = small_font.render("ВЫБЕРИ СЛОЖНОСТЬ", True, (180, 220, 180))
    sub_rect = sub.get_rect(center=(WIDTH // 2, ay + author_txt.get_height() + 14))
    sub_rect.y += int(math.sin(frame * 0.05) * 2)
    sub_shadow = small_font.render("ВЫБЕРИ СЛОЖНОСТЬ", True, (20, 40, 20))
    screen.blit(sub_shadow, (sub_rect.x + 2, sub_rect.y + 2))
    screen.blit(sub, sub_rect)
    line_y = sub_rect.centery
    for side in (-1, 1):
        line_x1 = sub_rect.centerx + side * (sub_rect.width // 2 + 20)
        line_x2 = sub_rect.centerx + side * (sub_rect.width // 2 + 70)
        pygame.draw.line(screen, (100, 180, 120), (line_x1, line_y), (line_x2, line_y), 2)
        pygame.draw.circle(screen, (140, 220, 160), (line_x2, line_y), 3)

    descs = {
        "easy": "Спокойно. Яблоки и препятствия.",
        "medium": "Быстрее + монстр + события.",
        "hard": "Хаос! Монстры, лазеры, босс.",
        "impossible": "5 лазеров + затемнение!",
    }
    for key, r in get_menu_buttons():
        col = DIFF_COLORS[key]
        hover = r.collidepoint(pygame.mouse.get_pos())
        if hover or key == selected:
            top = tuple(min(255, c + 40) for c in col)
            draw_gradient_button(r, top, col, (255, 255, 255), 3, hover=True, frame=frame)
            txt_col = (25, 25, 25); desc_col = (40, 40, 40)
        else:
            draw_gradient_button(r, (75, 80, 90), (45, 50, 60), col, 3, hover=False, frame=frame)
            txt_col = col; desc_col = (170, 175, 185)
        t1 = btn_font.render(DIFFICULTY[key]["name"], True, txt_col)
        screen.blit(t1, (r.x + 24, r.y + r.h // 2 - t1.get_height() // 2 - 8))
        t2 = tiny_font.render(descs[key], True, desc_col)
        screen.blit(t2, (r.x + 24, r.y + r.h - t2.get_height() - 8))
        ic_x = r.right - 50; ic_y = r.centery
        if key == "easy":
            pygame.draw.circle(screen, (200, 255, 200), (ic_x, ic_y), 16)
            pygame.draw.circle(screen, (40, 160, 60), (ic_x, ic_y), 16, 3)
            pygame.draw.circle(screen, (60, 200, 90), (ic_x, ic_y), 8)
        elif key == "medium":
            for k in range(8):
                a = k * math.pi / 4 + frame * 0.02
                pygame.draw.line(screen, (255, 220, 120), (ic_x, ic_y),
                                 (ic_x + math.cos(a) * 14, ic_y + math.sin(a) * 14), 2)
            pygame.draw.circle(screen, (255, 220, 120), (ic_x, ic_y), 8)
            pygame.draw.circle(screen, (255, 240, 180), (ic_x, ic_y), 4)
        elif key == "hard":
            for k in range(10):
                a = k * math.pi / 5 + frame * 0.05
                x1 = ic_x + math.cos(a) * 6; y1 = ic_y + math.sin(a) * 6
                x2 = ic_x + math.cos(a) * 18; y2 = ic_y + math.sin(a) * 18
                pygame.draw.line(screen, (255, 120, 120), (x1, y1), (x2, y2), 2)
            pygame.draw.circle(screen, (255, 120, 120), (ic_x, ic_y), 10)
            pygame.draw.circle(screen, (255, 200, 200), (ic_x, ic_y), 5)
        else:
            for k in range(12):
                a = k * math.pi / 6 + frame * 0.08
                x1 = ic_x + math.cos(a) * 4; y1 = ic_y + math.sin(a) * 4
                x2 = ic_x + math.cos(a) * 20; y2 = ic_y + math.sin(a) * 20
                pygame.draw.line(screen, (220, 100, 240), (x1, y1), (x2, y2), 2)
            pygame.draw.circle(screen, (220, 100, 240), (ic_x, ic_y), 12)
            pygame.draw.circle(screen, (255, 220, 255), (ic_x, ic_y), 6)
            pygame.draw.circle(screen, (150, 40, 180), (ic_x, ic_y), 3)

    draw_help_button(get_help_button().collidepoint(pygame.mouse.get_pos()), frame)

    hint = tiny_font.render("Нажми на кнопку · ESC — выход · ? — как играть", True, (150, 170, 150))
    screen.blit(hint, (WIDTH // 2 - hint.get_width() // 2, HEIGHT - int(HEIGHT * 0.04)))
    ver = tiny_font.render("v11", True, (100, 120, 100))
    screen.blit(ver, (10, HEIGHT - ver.get_height() - 6))

# ==================== ЭКРАН "КАК ИГРАТЬ" ====================
def draw_howto(frame):
    draw_menu_bg(frame)
    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 200))
    screen.blit(overlay, (0, 0))
    title = menu_font.render("КАК ИГРАТЬ", True, (140, 220, 130))
    screen.blit(title, (WIDTH // 2 - title.get_width() // 2, int(HEIGHT * 0.06)))
    panel_w = int(WIDTH * 0.8); panel_h = int(HEIGHT * 0.7)
    px = (WIDTH - panel_w) // 2; py = int(HEIGHT * 0.15)
    panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
    panel.fill((20, 30, 40, 220))
    pygame.draw.rect(panel, (100, 180, 120), (0, 0, panel_w, panel_h), 3, border_radius=16)
    for corner in [(0, 0, 1, 1), (panel_w, 0, -1, 1), (0, panel_h, 1, -1), (panel_w, panel_h, -1, -1)]:
        cx_, cy_, dx_, dy_ = corner
        pygame.draw.line(panel, (140, 220, 150), (cx_, cy_ + dy_ * 20), (cx_ + dx_ * 30, cy_ + dy_ * 20), 3)
    screen.blit(panel, (px, py))
    line_y = py + 20
    pad = 30
    def draw_section(header, lines, color=(140, 220, 150)):
        nonlocal line_y
        h = small_font.render(header, True, color)
        screen.blit(h, (px + pad, line_y))
        line_y += h.get_height() + 6
        for line in lines:
            t = tiny_font.render(line, True, (220, 230, 220))
            screen.blit(t, (px + pad + 10, line_y))
            line_y += t.get_height() + 2
        line_y += 8
    draw_section("УПРАВЛЕНИЕ", [
        "• Свайп по экрану (или мышь) — поворот змеи",
        "• ESC — выход в меню",
        "• Нажми на 🔊 в правом верхнем углу — вкл/выкл музыку",
    ])
    draw_section("ЯБЛОКИ", [
        "🍎 Красное — +1 очко, длина +10",
        "✨ Золотое — +3 очка, длина +15, замедление на 2.5 сек",
        "🛡 Голубое (щит) — поглощает одно столкновение",
        "☠ Фиолетовое (яд, после 5 очков) — −1 очко, длина −8",
    ], color=(255, 200, 100))
    draw_section("ОПАСНОСТИ", [
        "👾 Монстр-паук — преследует змею. Касание = смерть",
        "⚡ Лазер — 3 сек мигает (предупреждение), потом 1.2 сек жжёт",
        "👹 БОСС (с 15 очков) — стреляет пулями, убивается 10 ударами головой",
        "🌑 Затемнение (невозможная) — 2 сек полной темноты",
    ], color=(255, 130, 130))
    draw_section("СОБЫТИЯ (средняя+)", [
        "⚡ Ускорение · 🐌 Замедление · 🍎 Яблокопад · 🌫 Туман · ✨ Золотая лихорадка",
    ], color=(255, 220, 100))
    bw = int(WIDTH * 0.3); bh = int(HEIGHT * 0.08)
    btn_r = pygame.Rect((WIDTH - bw) // 2, py + panel_h - bh - 20, bw, bh)
    hover = btn_r.collidepoint(pygame.mouse.get_pos())
    col = (100, 220, 120) if hover else (60, 160, 80)
    pygame.draw.rect(screen, col, btn_r, border_radius=12)
    pygame.draw.rect(screen, (200, 255, 200), btn_r, 3, border_radius=12)
    txt = small_font.render("Понятно!", True, (20, 40, 20) if hover else (240, 255, 240))
    screen.blit(txt, (btn_r.centerx - txt.get_width() // 2, btn_r.centery - txt.get_height() // 2))
    return btn_r

# ==================== МУЗЫКА ====================
song_idx = 0
song_repeats = 0
song_target_repeats = random.randint(2, 3)
current_song_start = 0
music_started = False

def play_song(idx):
    global bg_music, song_repeats, song_target_repeats, current_song_start, music_started, song_idx
    if not sound_enabled or idx not in _song_cache:
        return
    try:
        song_idx = idx
        bg_music = _song_cache[idx]
        bg_music.set_volume(0 if muted else 0.45)
        bg_music.play(loops=0)
        song_repeats = 0
        song_target_repeats = random.randint(2, 3)
        current_song_start = pygame.time.get_ticks()
        music_started = True
    except Exception as e:
        print("play_song err:", e)

def update_music():
    global song_idx, song_repeats, current_song_start
    if not sound_enabled or not bg_music or not SONGS or not music_started:
        return
    if song_idx not in _song_lengths:
        return
    song_len_ms = int(_song_lengths[song_idx] / SR * 1000)
    elapsed = pygame.time.get_ticks() - current_song_start
    if elapsed >= song_len_ms + 50:
        song_repeats += 1
        if song_repeats >= song_target_repeats:
            next_idx = (song_idx + 1) % len(SONGS)
            play_song(next_idx)
        else:
            bg_music.play(loops=0)
            current_song_start = pygame.time.get_ticks()

# ==================== ИГРОВОЙ ЦИКЛ ====================
state = None
game_mode = "menu"
selected_diff = "easy"
touch_start = None
running = True
menu_frame = 0

# ↓↓↓ КЭШИРОВАННЫЕ ПОВЕРХНОСТИ (ФИКС ЛАГОВ ТУМАНА И ЗАТЕМНЕНИЯ) ↓↓↓
blackout_surface = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
blackout_surface.fill((0, 0, 0, 255))

fog_surface = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
fog_surface.fill((10, 10, 20, 100))
# ↑↑↑ КОНЕЦ ФИКСА ↑↑↑

while running:
    clock.tick(60)
    menu_frame += 1
    if state: state["frame"] += 1; frame = state["frame"]
    else: frame = menu_frame

    if sound_enabled and SONGS and not music_started:
        play_song(0)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos
            if sound_enabled and mx > WIDTH - 60 and my < TOP_OFFSET - WALL_THICKNESS and game_mode == "play":
                muted = not muted
                if bg_music: bg_music.set_volume(0 if muted else 0.45)
                continue
            if game_mode == "menu":
                if get_help_button().collidepoint(mx, my):
                    game_mode = "howto"
                    continue
                for key, r in get_menu_buttons():
                    if r.collidepoint(mx, my):
                        selected_diff = key
                        state = reset_game(key)
                        game_mode = "play"
                        break
            elif game_mode == "howto":
                bw = int(WIDTH * 0.3); bh = int(HEIGHT * 0.08)
                panel_w = int(WIDTH * 0.8); panel_h = int(HEIGHT * 0.7)
                py = int(HEIGHT * 0.15)
                btn_r = pygame.Rect((WIDTH - bw) // 2, py + panel_h - bh - 20, bw, bh)
                if btn_r.collidepoint(mx, my):
                    game_mode = "menu"
                continue
            elif game_mode == "play":
                if state["game_over"]:
                    state = reset_game(state["difficulty"])
                else:
                    touch_start = event.pos
        elif event.type == pygame.MOUSEBUTTONUP and touch_start and state and not state["game_over"] and game_mode == "play":
            sx, sy = touch_start
            ex, ey = event.pos
            dx_ = ex - sx; dy_ = ey - sy
            if math.hypot(dx_, dy_) > 20:
                if abs(dx_) > abs(dy_):
                    nx, ny = (1.0, 0.0) if dx_ > 0 else (-1.0, 0.0)
                else:
                    nx, ny = (0.0, 1.0) if dy_ > 0 else (0.0, -1.0)
                if not (round(nx) == -round(state["dx"]) and round(ny) == -round(state["dy"])):
                    state["tx"], state["ty"] = nx, ny
            touch_start = None
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if game_mode in ("play", "howto"):
                    game_mode = "menu"
                elif game_mode == "menu":
                    running = False

    update_music()

    if game_mode == "play" and state and not state["game_over"]:
        cfg = DIFFICULTY[state["difficulty"]]
        now_ms = pygame.time.get_ticks()

        dx, dy = state["dx"], state["dy"]
        dx += (state["tx"] - dx) * 0.16
        dy += (state["ty"] - dy) * 0.16
        L = math.hypot(dx, dy)
        if L > 0: dx /= L; dy /= L
        state["dx"], state["dy"] = dx, dy

        target_speed = cfg["speed"] + state["score"] * cfg["speed_per_score"]
        if now_ms < state["slow_until"]: target_speed *= 0.6
        if state["active_event"] == "speed": target_speed *= 1.5
        if state["active_event"] == "slow": target_speed *= 0.6
        if now_ms < state["blackout_until"]: target_speed *= 0.85
        state["speed"] += (target_speed - state["speed"]) * 0.05
        spd = state["speed"]

        hx, hy = state["points"][0]
        hx += dx * spd; hy += dy * spd

        if not in_field(hx, hy):
            if state["has_shield"]:
                state["has_shield"] = False; state["shake"] = 15
                add_particles(state["particles"], hx, hy, SHIELD_C, 20, 5, 40)
                if sound_enabled and not muted and shield_sound: shield_sound.play()
                if hx < WALL_THICKNESS + BASE_RADIUS: hx = WALL_THICKNESS + BASE_RADIUS + 2
                if hx > WIDTH - WALL_THICKNESS - BASE_RADIUS: hx = WIDTH - WALL_THICKNESS - BASE_RADIUS - 2
                if hy < TOP_OFFSET + BASE_RADIUS: hy = TOP_OFFSET + BASE_RADIUS + 2
                if hy > HEIGHT - WALL_THICKNESS - BASE_RADIUS: hy = HEIGHT - WALL_THICKNESS - BASE_RADIUS - 2
                state["tx"], state["ty"] = -dx, -dy
            else:
                state["game_over"] = True; state["shake"] = 20
                add_particles(state["particles"], hx, hy, (255, 100, 100), 20, 4, 40)
                if sound_enabled and not muted and crash_sound: crash_sound.play()

        if not state["game_over"] and collides_obstacle(hx, hy, state["obstacles"]):
            if state["has_shield"]:
                state["has_shield"] = False; state["shake"] = 15
                add_particles(state["particles"], hx, hy, SHIELD_C, 20, 5, 40)
                if sound_enabled and not muted and shield_sound: shield_sound.play()
                state["tx"], state["ty"] = -dx, -dy
            else:
                state["game_over"] = True; state["shake"] = 20
                add_particles(state["particles"], hx, hy, (255, 100, 100), 20, 4, 40)
                if sound_enabled and not muted and crash_sound: crash_sound.play()

        new_pts = [(hx, hy)]
        px, py = hx, hy
        for cx, cy in state["points"][1:]:
            ang = math.atan2(cy - py, cx - px)
            nx = px + math.cos(ang) * SEGMENT_DIST
            ny = py + math.sin(ang) * SEGMENT_DIST
            new_pts.append((nx, ny)); px, py = nx, ny
        state["points"] = new_pts

        if frame % 3 == 0: state["trail"].append([hx, hy, 40])
        for t in state["trail"]: t[2] -= 1
        state["trail"][:] = [t for t in state["trail"] if t[2] > 0]

        if not state["game_over"]:
            for px2, py2 in state["points"][26:]:
                if math.hypot(hx - px2, hy - py2) < BASE_RADIUS * 1.05:
                    if state["has_shield"]:
                        state["has_shield"] = False; state["shake"] = 15
                        add_particles(state["particles"], hx, hy, SHIELD_C, 20, 5, 40)
                        if sound_enabled and not muted and shield_sound: shield_sound.play()
                    else:
                        state["game_over"] = True; state["shake"] = 20
                        add_particles(state["particles"], hx, hy, (255, 100, 100), 20, 4, 40)
                        if sound_enabled and not muted and crash_sound: crash_sound.play()
                    break

        ax, ay, ak = state["apple"]
        if math.hypot(hx - ax, hy - ay) < BASE_RADIUS * 1.8:
            state["score"] += 1; state["grow_pending"] += 10
            add_particles(state["particles"], ax, ay, APPLE_RED, 12, 3.5, 30)
            if sound_enabled and not muted and eat_sound: eat_sound.play()
            ax, ay = spawn_apple(state["points"][0], state["obstacles"])
            state["apple"] = [ax, ay, "normal"]
            if state["score"] >= 5 and state["poison"] is None:
                px3, py3 = spawn_apple(state["points"][0], state["obstacles"])
                state["poison"] = [px3, py3, "poison"]
            new_level = 1 + state["score"] // 10
            if new_level != state["level"]:
                state["level"] = new_level
                state["obstacles"] = make_obstacles(new_level)

        gx, gy, _, gt = state["gold"]
        if math.hypot(hx - gx, hy - gy) < BASE_RADIUS * 1.8:
            state["score"] += 3; state["grow_pending"] += 15
            state["slow_until"] = now_ms + 2500
            add_particles(state["particles"], gx, gy, GOLD, 15, 4.5, 40)
            if sound_enabled and not muted and gold_sound: gold_sound.play()
            gx, gy = spawn_apple(state["points"][0], state["obstacles"])
            state["gold"] = [gx, gy, "gold", 0]

        sx_, sy_, sk = state["shield_pickup"]
        if math.hypot(hx - sx_, hy - sy_) < BASE_RADIUS * 1.8:
            state["has_shield"] = True
            add_particles(state["particles"], sx_, sy_, SHIELD_C, 15, 4.5, 40)
            if sound_enabled and not muted and shield_sound: shield_sound.play()
            sx_, sy_ = spawn_apple(state["points"][0], state["obstacles"])
            state["shield_pickup"] = [sx_, sy_, "shield"]

        if state["poison"] is not None:
            px3, py3, _ = state["poison"]
            if math.hypot(hx - px3, hy - py3) < BASE_RADIUS * 1.8:
                add_particles(state["particles"], px3, py3, POISON, 15, 4, 35)
                if sound_enabled and not muted and poison_sound: poison_sound.play()
                if state["has_shield"]:
                    state["has_shield"] = False
                    add_particles(state["particles"], hx, hy, SHIELD_C, 15, 4.5, 35)
                else:
                    state["score"] = max(0, state["score"] - 1)
                    state["grow_pending"] -= 8
                    excess = min(8, max(0, len(state["points"]) - 15))
                    if excess > 0: state["points"] = state["points"][:len(state["points"]) - excess]
                state["poison"] = None; state["shake"] = 10

        if state["grow_pending"] > 0:
            tail = state["points"][-1]
            add = min(state["grow_pending"], 3)
            for _ in range(add): state["points"].append(tail)
            state["grow_pending"] -= add

        for m in state["monsters"]:
            mx_, my_, mdir = m
            ang = math.atan2(hy - my_, hx - mx_)
            ms = cfg["monster_speed"]
            if state["active_event"] == "speed": ms *= 1.3
            if state["active_event"] == "slow": ms *= 0.6
            mx_ += math.cos(ang) * ms; my_ += math.sin(ang) * ms
            if mx_ < WALL_THICKNESS + BASE_RADIUS: mx_ = WALL_THICKNESS + BASE_RADIUS
            if mx_ > WIDTH - WALL_THICKNESS - BASE_RADIUS: mx_ = WIDTH - WALL_THICKNESS - BASE_RADIUS
            if my_ < TOP_OFFSET + BASE_RADIUS: my_ = TOP_OFFSET + BASE_RADIUS
            if my_ > HEIGHT - WALL_THICKNESS - BASE_RADIUS: my_ = HEIGHT - WALL_THICKNESS - BASE_RADIUS
            m[0], m[1] = mx_, my_
            for px2, py2 in state["points"][::3]:
                if math.hypot(mx_ - px2, my_ - py2) < BASE_RADIUS * 1.3:
                    if state["has_shield"]:
                        state["has_shield"] = False; state["shake"] = 15
                        add_particles(state["particles"], mx_, my_, SHIELD_C, 20, 5, 40)
                        if sound_enabled and not muted and shield_sound: shield_sound.play()
                        m[0] = WIDTH * 0.1 if mx_ < WIDTH / 2 else WIDTH * 0.9
                        m[1] = HEIGHT * 0.2 if my_ < HEIGHT / 2 else HEIGHT * 0.8
                    else:
                        state["game_over"] = True; state["shake"] = 20
                        add_particles(state["particles"], mx_, my_, MONSTER_EYE, 20, 4, 40)
                        if sound_enabled and not muted and monster_hit_sound: monster_hit_sound.play()
                    break
            if state["game_over"]: break

        if cfg["lasers"] and not state["game_over"]:
            if now_ms >= state["next_laser_time"]:
                for _ in range(cfg["laser_count"]):
                    state["lasers"].append(spawn_laser())
                state["next_laser_time"] = now_ms + cfg["laser_interval"]
                if sound_enabled and not muted and laser_sound: laser_sound.play()
            alive_lasers = []
            for lz in state["lasers"]:
                if not lz["fired"] and now_ms >= lz["warn_end"]:
                    lz["fired"] = True
                if lz["fired"] and now_ms < lz["fire_end"]:
                    r = lz["rect"].inflate(int(BASE_RADIUS * 1.8), int(BASE_RADIUS * 1.8))
                    if r.collidepoint(hx, hy):
                        if state["has_shield"]:
                            state["has_shield"] = False; state["shake"] = 15
                            add_particles(state["particles"], hx, hy, SHIELD_C, 20, 5, 40)
                            if sound_enabled and not muted and shield_sound: shield_sound.play()
                        else:
                            state["game_over"] = True; state["shake"] = 20
                            add_particles(state["particles"], hx, hy, LASER_RED, 20, 5, 40)
                            if sound_enabled and not muted and crash_sound: crash_sound.play()
                if now_ms < lz["fire_end"]:
                    alive_lasers.append(lz)
            state["lasers"] = alive_lasers

        if state["boss"] is None and state["score"] >= state["boss_spawn_score"]:
            state["boss"] = spawn_boss()
            if sound_enabled and not muted and boss_hit_sound: boss_hit_sound.play()
            state["shake"] = 20

        if state["boss"] is not None and not state["game_over"]:
            b = state["boss"]
            b["phase"] += 0.03
            target_x = WIDTH / 2 + math.cos(b["phase"]) * WIDTH * 0.25
            target_y = TOP_OFFSET + BASE_RADIUS * 10 + math.sin(b["phase"] * 0.7) * HEIGHT * 0.08
            b["x"] += (target_x - b["x"]) * 0.01
            b["y"] += (target_y - b["y"]) * 0.01
            b["angry"] = b["hp"] < b["max_hp"] * 0.4
            b["shoot_timer"] -= 1
            if b["shoot_timer"] <= 0:
                shoot_interval = 80 if not b["angry"] else 45
                b["shoot_timer"] = shoot_interval
                ang = math.atan2(hy - b["y"], hx - b["x"])
                speed_b = 2.5 if not b["angry"] else 3.5
                b["bullets"].append([b["x"], b["y"], math.cos(ang) * speed_b, math.sin(ang) * speed_b, 300])
                if b["angry"]:
                    for off in (-0.3, 0.3):
                        b["bullets"].append([b["x"], b["y"], math.cos(ang + off) * speed_b, math.sin(ang + off) * speed_b, 300])
            for bullet in b["bullets"]:
                bullet[0] += bullet[2]; bullet[1] += bullet[3]; bullet[4] -= 1
            b["bullets"][:] = [bl for bl in b["bullets"] if bl[4] > 0 and
                                WALL_THICKNESS < bl[0] < WIDTH - WALL_THICKNESS and
                                TOP_OFFSET < bl[1] < HEIGHT - WALL_THICKNESS]
            for bullet in b["bullets"][:]:
                for px2, py2 in state["points"][::2]:
                    if math.hypot(bullet[0] - px2, bullet[1] - py2) < BASE_RADIUS * 1.3:
                        b["bullets"].remove(bullet)
                        if state["has_shield"]:
                            state["has_shield"] = False; state["shake"] = 15
                            add_particles(state["particles"], px2, py2, SHIELD_C, 15, 4, 35)
                            if sound_enabled and not muted and shield_sound: shield_sound.play()
                        else:
                            state["game_over"] = True; state["shake"] = 20
                            add_particles(state["particles"], px2, py2, (255, 60, 60), 20, 4, 40)
                            if sound_enabled and not muted and crash_sound: crash_sound.play()
                        break
                if state["game_over"]: break
            if not state["game_over"] and math.hypot(hx - b["x"], hy - b["y"]) < BASE_RADIUS + b["r"]:
                b["hp"] -= 1
                state["shake"] = 10
                add_particles(state["particles"], b["x"], b["y"], BOSS_SPIKE, 15, 4, 30)
                if sound_enabled and not muted and boss_hit_sound: boss_hit_sound.play()
                state["tx"], state["ty"] = -dx, -dy
                vx = hx - b["x"]; vy = hy - b["y"]
                dl = math.hypot(vx, vy) or 1
                hx = b["x"] + vx / dl * (BASE_RADIUS + b["r"] + 2)
                hy = b["y"] + vy / dl * (BASE_RADIUS + b["r"] + 2)
                state["points"][0] = (hx, hy)
                if b["hp"] <= 0:
                    state["score"] += 10
                    state["grow_pending"] += 30
                    add_particles(state["particles"], b["x"], b["y"], (255, 220, 100), 30, 7, 60)
                    state["shake"] = 30
                    if sound_enabled and not muted and gold_sound: gold_sound.play()
                    state["boss"] = None
                    state["boss_spawn_score"] += 15

        for pending in state["pending_apples"][:]:
            spot = find_free_spot(state["obstacles"], state["points"][0])
            if spot:
                ex_, ey_ = spot
                is_gold = pending.get("gold", False)
                state["extra_apples"].append([ex_, ey_, 800, is_gold] if is_gold else [ex_, ey_, 800])
                state["pending_apples"].remove(pending)
            else:
                pending["tries"] = pending.get("tries", 0) + 1
                if pending["tries"] > 30:
                    state["pending_apples"].remove(pending)

        if cfg["events"] and not state["game_over"]:
            if state["active_event"] is None and now_ms >= state["next_event_time"]:
                ev_name, ev_label, ev_dur, apple_count = pick_event()
                state["active_event"] = ev_name
                state["event_end"] = now_ms + ev_dur
                state["next_event_time"] = now_ms + ev_dur + random.randint(12000, 20000)
                state["shake"] = 8
                add_particles(state["particles"], WIDTH / 2, HEIGHT / 2, EVENT_COL, 15, 6, 40)
                if ev_name == "apples":
                    for _ in range(apple_count):
                        state["pending_apples"].append({"gold": False, "tries": 0})
                elif ev_name == "gold_rush":
                    for _ in range(apple_count):
                        state["pending_apples"].append({"gold": True, "tries": 0})
            if state["active_event"] is not None and now_ms >= state["event_end"]:
                state["active_event"] = None
                state["extra_apples"].clear()
            for ap in state["extra_apples"][:]:
                ax2, ay2 = ap[0], ap[1]
                is_gold = len(ap) > 3 and ap[3]
                if math.hypot(hx - ax2, hy - ay2) < BASE_RADIUS * 1.8:
                    state["score"] += 3 if is_gold else 1
                    state["grow_pending"] += 15 if is_gold else 8
                    add_particles(state["particles"], ax2, ay2, GOLD if is_gold else APPLE_RED, 12, 4, 30)
                    if sound_enabled and not muted and (gold_sound if is_gold else eat_sound):
                        (gold_sound if is_gold else eat_sound).play()
                    state["extra_apples"].remove(ap)

        if cfg["blackout"] and not state["game_over"]:
            if now_ms >= state["next_blackout_time"]:
                state["blackout_until"] = now_ms + 2000
                state["next_blackout_time"] = now_ms + 2000 + random.randint(18000, 28000)

        update_particles(state["particles"])

    # ==================== РЕНДЕР ====================
    if game_mode == "menu":
        update_menu_snake()
        draw_menu(selected_diff, menu_frame)
    elif game_mode == "howto":
        draw_howto(menu_frame)
    elif state:
        offset_x = offset_y = 0
        if state["shake"] > 0:
            offset_x = random.randint(-state["shake"], state["shake"])
            offset_y = random.randint(-state["shake"], state["shake"])
            state["shake"] -= 1

        screen.blit(bg_surface, (offset_x, offset_y))

        # ФИКС: туман теперь из кэша, а не создаётся каждый кадр
        if state["active_event"] == "dark":
            screen.blit(fog_surface, (offset_x, offset_y))

        for x, y, life in state["trail"]:
            r = max(1, int(life / 8))
            s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            pygame.draw.circle(s, (25, 70, 30, 120), (r, r), r)
            screen.blit(s, (int(x - r) + offset_x, int(y - r) + offset_y))

        for o in state["obstacles"]:
            draw_obstacle(screen, o.move(offset_x, offset_y))

        now_ms = pygame.time.get_ticks()
        for lz in state["lasers"]:
            r = lz["rect"].move(offset_x, offset_y)
            if not lz["fired"]:
                blink = (now_ms // 120) % 2 == 0
                col = LASER_WARN if blink else (200, 170, 60)
                pygame.draw.rect(screen, col, r, 2)
                if blink:
                    pygame.draw.rect(screen, (255, 240, 130), r, 1)
            else:
                pygame.draw.rect(screen, LASER_RED, r)
                if r.w < r.h:
                    pygame.draw.line(screen, (255, 255, 255), (r.centerx, r.y), (r.centerx, r.bottom), 3)
                else:
                    pygame.draw.line(screen, (255, 255, 255), (r.x, r.centery), (r.right, r.centery), 3)

        for ap in state["extra_apples"]:
            ax2, ay2 = ap[0], ap[1]
            is_gold = len(ap) > 3 and ap[3]
            draw_apple(screen, ax2 + offset_x, ay2 + offset_y, BASE_RADIUS * 0.9, frame,
                       "gold" if is_gold else "normal")

        draw_apple(screen, state["apple"][0] + offset_x, state["apple"][1] + offset_y,
                   BASE_RADIUS * 1.05, frame, "normal")
        draw_apple(screen, state["gold"][0] + offset_x, state["gold"][1] + offset_y,
                   BASE_RADIUS * 0.95, frame, "gold")
        draw_apple(screen, state["shield_pickup"][0] + offset_x, state["shield_pickup"][1] + offset_y,
                   BASE_RADIUS * 0.9, frame, "shield")
        if state["poison"] is not None:
            draw_apple(screen, state["poison"][0] + offset_x, state["poison"][1] + offset_y,
                       BASE_RADIUS * 0.9, frame, "poison")

        if state["boss"] is not None:
            b = state["boss"]
            draw_boss(screen, b["x"] + offset_x, b["y"] + offset_y, b["r"],
                      b["hp"], b["max_hp"], frame, b["angry"])
            for bullet in b["bullets"]:
                pygame.draw.circle(screen, (255, 100, 100),
                                   (int(bullet[0] + offset_x), int(bullet[1] + offset_y)), 5)
                pygame.draw.circle(screen, (255, 220, 220),
                                   (int(bullet[0] + offset_x), int(bullet[1] + offset_y)), 2)

        draw_snake(screen, state["points"], state["dx"], state["dy"],
                   (state["apple"][0], state["apple"][1]), state["game_over"], frame,
                   has_shield=state["has_shield"])

        for m in state["monsters"]:
            draw_monster(screen, m[0] + offset_x, m[1] + offset_y, frame)

        draw_particles(screen, state["particles"])

        if not state["game_over"]:
            tongue_timer = frame % 140
            if tongue_timer < 28:
                hx, hy = state["points"][0]
                ang = math.atan2(state["dy"], state["dx"])
                flick = math.sin(tongue_timer * 0.35)
                t_len = BASE_RADIUS * (1.4 + flick * 0.5)
                tx1 = hx + math.cos(ang) * (BASE_RADIUS + t_len)
                ty1 = hy + math.sin(ang) * (BASE_RADIUS + t_len)
                pygame.draw.line(screen, (225, 40, 60), (hx + offset_x, hy + offset_y),
                                 (tx1 + offset_x, ty1 + offset_y), 3)

        if now_ms < state["blackout_until"]:
            screen.blit(blackout_surface, (0, 0))
            dark_txt = font.render("🌑 ТЕМНОТА", True, (200, 100, 200))
            screen.blit(dark_txt, (WIDTH // 2 - dark_txt.get_width() // 2, HEIGHT // 2))

        score_txt = font.render(f"Счёт: {state['score']}", True, (240, 240, 220))
        screen.blit(score_txt, (WALL_THICKNESS + 10, 8))
        diff_name = DIFFICULTY[state["difficulty"]]["name"]
        lvl_txt = small_font.render(f"{diff_name} · Ур.{state['level']}", True, (200, 220, 180))
        screen.blit(lvl_txt, (WALL_THICKNESS + 10 + score_txt.get_width() + 20, 12))

        spd_indicator = ""
        spd_color = (200, 200, 200)
        if now_ms < state["slow_until"]:
            spd_indicator = "🐌"; spd_color = (100, 180, 255)
        elif state["active_event"] == "speed":
            spd_indicator = "⚡"; spd_color = (255, 220, 100)
        elif state["active_event"] == "slow":
            spd_indicator = "🐌"; spd_color = (100, 180, 255)
        if spd_indicator:
            ind = small_font.render(spd_indicator, True, spd_color)
            screen.blit(ind, (WALL_THICKNESS + 10 + score_txt.get_width() + lvl_txt.get_width() + 40, 12))

        if state["boss"] is not None:
            b = state["boss"]
            bar_w = WIDTH * 0.4; bar_h = 14
            bx = WIDTH / 2 - bar_w / 2; by = TOP_OFFSET - WALL_THICKNESS - 22
            pygame.draw.rect(screen, (40, 40, 40), (bx, by, bar_w, bar_h))
            pygame.draw.rect(screen, (220, 40, 40), (bx, by, bar_w * (b["hp"] / b["max_hp"]), bar_h))
            pygame.draw.rect(screen, (255, 255, 255), (bx, by, bar_w, bar_h), 1)
            boss_txt = tiny_font.render("БОСС", True, (255, 200, 200))
            screen.blit(boss_txt, (bx - boss_txt.get_width() - 8, by))

        if state["active_event"]:
            ev_label = {
                "speed": "⚡ УСКОРЕНИЕ", "slow": "🐌 ЗАМЕДЛЕНИЕ",
                "apples": "🍎 ЯБЛОКОПАД", "dark": "🌫 ТУМАН",
                "gold_rush": "✨ ЗОЛОТАЯ ЛИХОРАДКА",
            }.get(state["active_event"], "")
            ev_txt = font.render(ev_label, True, EVENT_COL)
            screen.blit(ev_txt, (WIDTH // 2 - ev_txt.get_width() // 2, TOP_OFFSET + 10))

        esc_txt = tiny_font.render("ESC — меню", True, (150, 150, 150))
        screen.blit(esc_txt, (WIDTH - esc_txt.get_width() - 10, TOP_OFFSET - WALL_THICKNESS - 16))
        muted_txt = small_font.render("🔇" if muted else "🔊", True, (200, 200, 200))
        screen.blit(muted_txt, (WIDTH - 40, 8))
        if sound_enabled and SONGS:
            song_txt = tiny_font.render(f"♪ {SONG_NAMES[song_idx] if song_idx < len(SONG_NAMES) else '?'}", True, (180, 200, 220))
            screen.blit(song_txt, (WIDTH - 180, 12))

        if state["game_over"]:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 160))
            screen.blit(overlay, (0, 0))
            go = font.render("Игра окончена", True, (255, 80, 80))
            sc = font.render(f"Счёт: {state['score']}", True, (255, 255, 255))
            hint = small_font.render("Нажми — заново · ESC — меню", True, (200, 200, 200))
            screen.blit(go, (WIDTH // 2 - go.get_width() // 2, HEIGHT // 2 - 70))
            screen.blit(sc, (WIDTH // 2 - sc.get_width() // 2, HEIGHT // 2))
            screen.blit(hint, (WIDTH // 2 - hint.get_width() // 2, HEIGHT // 2 + 60))

    pygame.display.flip()

pygame.quit()