import pygame
import random
import time
import sys
from pygame.locals import *
import math
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
import json
import os

# Initialize Pygame (robust audio init with fallbacks)
# Try to configure mixer before pygame.init so the audio device matches our buffers
SOUND_ENABLED = True
try:
    pygame.mixer.pre_init(22050, -16, 1, 512)  # mono 16-bit at 22.05kHz keeps buffers small and simple
except Exception as e:
    print(f"[Audio] pre_init warning: {e}")

pygame.init()
pygame.font.init()

try:
    pygame.mixer.init()  # use pre_init params
except Exception as e:
    print(f"[Audio] mixer.init failed (pass 1): {e}")
    SOUND_ENABLED = False
    # Try a fallback configuration
    try:
        pygame.mixer.quit()
        pygame.mixer.pre_init(44100, -16, 1, 512)
        pygame.mixer.init()
        SOUND_ENABLED = True
    except Exception as e2:
        print(f"[Audio] mixer.init failed (pass 2): {e2}")

print(f"[Audio] device settings: {pygame.mixer.get_init()} | enabled={SOUND_ENABLED}")
try:
    # Ensure we have enough channels for SFX + BGM
    pygame.mixer.set_num_channels(max(16, pygame.mixer.get_num_channels()))
except Exception:
    pass

# Target volume for all SFX to keep loudness consistent across different tones
SFX_TARGET_VOLUME = 0.5
# Fine-tuned per-sound volumes (success/error slightly lower, miss/combo slightly higher)
SFX_VOL_SUCCESS = 0.45
SFX_VOL_ERROR = 0.36
SFX_VOL_MISS = 0.56
SFX_VOL_COMBO = 0.58

# UI sound volumes
UI_VOL_NAV = 0.42
UI_VOL_KEY_TAP = 0.28
UI_VOL_KEY_BACKSPACE = 0.30
UI_VOL_KEY_ENTER = 0.34
UI_VOL_COUNTDOWN = 0.30

# Event sound volumes
SFX_VOL_START = 0.42
SFX_VOL_GAMEOVER = 0.46

# Background music controls
BGM_ENABLED = True
BGM_VOLUME = 0.22  # keep bgm subtle so SFX remain clear
BGM_LENGTH = 32.0  # seconds per loop (longer loop reduces repetition)
BGM_SOUND = None
BGM_CHANNEL = None

# Pixel-style font settings
# Build candidate list at runtime, preferring local pixel fonts under fonts/ and assets/fonts/
def _pixel_font_candidates():
    here = os.path.dirname(__file__)
    cwd = os.getcwd()
    names = [
        'PressStart2P-Regular.ttf',
        'PixelOperator.ttf',
        '04B_03__.TTF',
        'VT323-Regular.ttf',
    ]
    folders = [
        os.path.join(here, 'fonts'),
        os.path.join(here, 'assets', 'fonts'),
        os.path.join(cwd, 'fonts'),
        os.path.join(cwd, 'assets', 'fonts'),
    ]
    candidates = []
    for folder in folders:
        for name in names:
            candidates.append(os.path.join(folder, name))
    return candidates

_SELECTED_FONT_PATH = None

def _load_pixel_font(size):
    global _SELECTED_FONT_PATH
    candidates = _pixel_font_candidates()
    # On first load, log probe results for visibility
    if _SELECTED_FONT_PATH is None:
        try:
            probe = {p: os.path.isfile(p) for p in candidates}
            print("[Font] Probe candidates:")
            for k, v in probe.items():
                print(f"  - {k} -> {'FOUND' if v else 'missing'}")
        except Exception:
            pass
    for p in candidates:
        try:
            if os.path.isfile(p):
                f = pygame.font.Font(p, size)
                if _SELECTED_FONT_PATH is None:
                    _SELECTED_FONT_PATH = p
                print(f"[Font] Using pixel font: {p} @ {size}px")
                return f
            # If candidate is a directory (e.g., mistakenly copied as a folder), search inside for .ttf/.otf
            if os.path.isdir(p):
                try:
                    for name in os.listdir(p):
                        if name.lower().endswith(('.ttf', '.otf')):
                            fp = os.path.join(p, name)
                            f = pygame.font.Font(fp, size)
                            if _SELECTED_FONT_PATH is None:
                                _SELECTED_FONT_PATH = fp
                            print(f"[Font] Using pixel font (from dir): {fp} @ {size}px")
                            return f
                except Exception as se:
                    print(f"[Font] Scan dir failed {p}: {se}")
        except Exception as e:
            print(f"[Font] Failed loading {p}: {e}")
    if _SELECTED_FONT_PATH is None:
        print("[Font] No pixel font found. Falling back to default.")
    return pygame.font.Font(None, size)

# Suggested integer-multiple sizes to preserve pixel look (e.g., 16/24/32/48/64)
# Global font scale: quickly shrink/enlarge all pixel fonts; lower to restore original proportions
FONT_SCALE = 0.6  # 将所有字号统一按 60% 缩放，避免任何边界溢出

def px(size):
    try:
        s = int(round(size * FONT_SCALE))
        return max(8, s)
    except Exception:
        return size

font = _load_pixel_font(px(32))
small_font = _load_pixel_font(px(24))
large_font = _load_pixel_font(px(48))
instruction_font = _load_pixel_font(px(20))
title_font = _load_pixel_font(px(64))

# Pixel-style color palette
PIXEL_COLORS = {
    'bg_primary': (32, 34, 37),      # dark gray background
    'bg_secondary': (54, 57, 63),    # secondary background
    'text_primary': (220, 221, 222), # primary text
    'text_secondary': (150, 152, 157), # secondary text (lighter gray)
    'text_accent': (114, 137, 218),  # accent text (blue)
    'success': (67, 181, 129),       # success green
    'error': (240, 71, 71),          # error red
    'warning': (250, 166, 26),       # warning orange
    'combo': (255, 231, 146),        # combo gold
    'frame': (79, 84, 92),           # frame color
    'button': (88, 101, 242),        # button color
    'button_hover': (71, 84, 200),   # button hover
    'accent': (114, 137, 218),       # accent color (same as text_accent)
}

# Text wrapping helper
def wrap_text(text, font_obj, max_width):
    """Wrap text to fit max_width in pixels. Returns a list of lines."""
    words = text.split(' ')
    lines = []
    current = ''
    for w in words:
        test = (current + ' ' + w).strip()
        if font_obj.size(test)[0] <= max_width:
            current = test
        else:
            # if single word is too long, hard-break by characters
            if current:
                lines.append(current)
                current = ''
            while font_obj.size(w)[0] > max_width and len(w) > 1:
                # find max fit prefix
                lo, hi = 1, len(w)
                while lo < hi:
                    mid = (lo + hi) // 2
                    if font_obj.size(w[:mid])[0] <= max_width:
                        lo = mid + 1
                    else:
                        hi = mid
                fit = w[:lo-1]
                lines.append(fit)
                w = w[lo-1:]
            current = w
    if current:
        lines.append(current)
    return lines

# Pixel-style drawing helper functions
def draw_pixel_border(surface, rect, color, width=2):
    """Draw a pixel-style border."""
    # Outer border
    pygame.draw.rect(surface, color, rect, width)
    # Inner border highlight
    inner_rect = pygame.Rect(rect.x + width, rect.y + width, 
                           rect.width - width*2, rect.height - width*2)
    highlight_color = tuple(min(255, c + 30) for c in color)
    pygame.draw.line(surface, highlight_color, 
                    (inner_rect.x, inner_rect.y), 
                    (inner_rect.right-1, inner_rect.y), width)
    pygame.draw.line(surface, highlight_color, 
                    (inner_rect.x, inner_rect.y), 
                    (inner_rect.x, inner_rect.bottom-1), width)

def draw_pixel_button(surface, rect, text, font_obj, bg_color, text_color, border_color):
    """Draw a pixel-style button."""
    # Button background
    pygame.draw.rect(surface, bg_color, rect)
    # Button border
    draw_pixel_border(surface, rect, border_color, 2)
    # Button text
    text_surface = font_obj.render(text, False, text_color)
    text_x = rect.x + (rect.width - text_surface.get_width()) // 2
    text_y = rect.y + (rect.height - text_surface.get_height()) // 2
    surface.blit(text_surface, (text_x, text_y))

def draw_pixel_text_with_shadow(surface, text, font_obj, x, y, text_color, shadow_color):
    """Draw pixel-style text with a shadow."""
    # Draw shadow
    shadow_surface = font_obj.render(text, False, shadow_color)
    surface.blit(shadow_surface, (x + 2, y + 2))
    # Draw main text
    text_surface = font_obj.render(text, False, text_color)
    surface.blit(text_surface, (x, y))

def draw_pixel_grid(surface, cell_size, color):
    """Draw a pixel-style background grid."""
    width, height = surface.get_size()
    
    # Draw vertical lines
    for x in range(0, width, cell_size):
        pygame.draw.line(surface, color, (x, 0), (x, height), 1)
    
    # Draw horizontal lines
    for y in range(0, height, cell_size):
        pygame.draw.line(surface, color, (0, y), (width, y), 1)

# Sound generation functions
def generate_sound(frequency, duration, volume=0.5, sample_rate=22050):
    """Generate a simple tone sound using numpy when available."""
    if not NUMPY_AVAILABLE:
        return None
    try:
        frames = int(duration * sample_rate)
        t = np.linspace(0, duration, frames, endpoint=False)
        wave = volume * np.sin(2 * np.pi * frequency * t)
        # Match current mixer channels
        mi = pygame.mixer.get_init() or (sample_rate, -16, 1)
        channels = mi[2]
        if channels == 2:
            arr = np.vstack([wave, wave]).T
        else:
            arr = wave.reshape(-1, 1)
        arr = (arr * 32767).astype(np.int16)
        arr = np.ascontiguousarray(arr)
        return pygame.sndarray.make_sound(arr)
    except Exception as e:
        print(f"Error generating sound: {e}")
        return None

def _tone_bytes(frequency, duration, volume=0.5, sample_rate=22050, channels=1, waveform="sine"):
    """Create raw PCM bytes for a tone. Uses numpy if available, else pure Python math.
    Returns bytes suitable for pygame.mixer.Sound(buffer=...).
    """
    frames = int(duration * sample_rate)
    if frames <= 0:
        return b""

    if NUMPY_AVAILABLE:
        t = np.linspace(0, duration, frames, endpoint=False)
        if waveform == "square":
            wave = np.sign(np.sin(2 * np.pi * frequency * t)) * volume
        else:
            wave = np.sin(2 * np.pi * frequency * t) * volume
        wave_i16 = (wave * 32767).astype(np.int16)
        if channels == 2:
            wave_i16 = np.repeat(wave_i16[:, None], 2, axis=1).ravel()
        else:
            # mono
            pass
        return wave_i16.tobytes()
    else:
        import math
        from array import array
        buf = array('h')
        two_pi_f = 2.0 * math.pi * float(frequency)
        for i in range(frames):
            t = i / float(sample_rate)
            if waveform == "square":
                s = volume if math.sin(two_pi_f * t) >= 0 else -volume
            else:
                s = volume * math.sin(two_pi_f * t)
            sample = int(max(-1.0, min(1.0, s)) * 32767)
            if channels == 2:
                buf.append(sample)
                buf.append(sample)
            else:
                buf.append(sample)
        return buf.tobytes()

def create_simple_beep_sound(frequency, duration, volume=0.4):
    """Create a simple beep as a pygame Sound without requiring numpy."""
    try:
        mi = pygame.mixer.get_init() or (22050, -16, 1)
        sample_rate, _, channels = mi
        pcm = _tone_bytes(frequency, duration, volume=volume, sample_rate=sample_rate, channels=channels, waveform="square")
        if not pcm:
            return None
        snd = pygame.mixer.Sound(buffer=pcm)
        snd.set_volume(min(1.0, max(0.0, volume)))
        return snd
    except Exception as e:
        print(f"Error creating simple beep: {e}")
        return None

def create_success_sound():
    """Create a pleasant success sound distinct from combo: a short chiming tone
    with a subtle harmonic and a gentle fade-out. Works with and without numpy.
    """
    try:
        mi = pygame.mixer.get_init() or (22050, -16, 1)
        sample_rate, _, channels = mi
        duration = 0.18
        f1 = 784.0   # G5
        f2 = 1568.0  # 2nd harmonic (subtle)
        frames = int(duration * sample_rate)
        if frames <= 0:
            return None

        if NUMPY_AVAILABLE:
            t = np.linspace(0.0, duration, frames, endpoint=False)
            # Simple linear envelope: 10ms attack, 60ms release
            attack = int(0.010 * sample_rate)
            release = int(0.060 * sample_rate)
            env = np.ones(frames, dtype=np.float32)
            if attack > 0:
                env[:attack] = np.linspace(0.0, 1.0, attack, endpoint=False)
            if release > 0:
                env[-release:] = np.linspace(1.0, 0.0, release, endpoint=False)
            wave = (0.85 * np.sin(2 * np.pi * f1 * t) + 0.25 * np.sin(2 * np.pi * f2 * t)) * env
            wave_i16 = (wave * 32767).astype(np.int16)
            if channels == 2:
                pcm = np.repeat(wave_i16[:, None], 2, axis=1).ravel().tobytes()
            else:
                pcm = wave_i16.tobytes()
        else:
            import math
            from array import array
            buf = array('h')
            attack = int(0.010 * sample_rate)
            release = int(0.060 * sample_rate)
            two_pi_f1 = 2.0 * math.pi * f1
            two_pi_f2 = 2.0 * math.pi * f2
            for i in range(frames):
                t = i / float(sample_rate)
                # Envelope
                if i < attack:
                    env = i / float(max(1, attack))
                elif i >= frames - release:
                    env = (frames - i) / float(max(1, release))
                else:
                    env = 1.0
                s = (0.85 * math.sin(two_pi_f1 * t) + 0.25 * math.sin(two_pi_f2 * t)) * env
                sample = int(max(-1.0, min(1.0, s)) * 32767)
                if channels == 2:
                    buf.append(sample)
                    buf.append(sample)
                else:
                    buf.append(sample)
            pcm = buf.tobytes()

        snd = pygame.mixer.Sound(buffer=pcm)
        # Volume will be normalized later; set a reasonable default
        snd.set_volume(SFX_VOL_SUCCESS)
        return snd
    except Exception as e:
        print(f"Error generating success sound: {e}")
        return None

def create_combo_sound():
    """Create combo sound effect - two short pleasant tones.
    Uses numpy if available; else builds bytes manually.
    """
    try:
        mi = pygame.mixer.get_init() or (22050, -16, 1)
        sample_rate, _, channels = mi
        if NUMPY_AVAILABLE:
            # Build two short sine beeps with a small gap
            part1 = _tone_bytes(523, 0.10, volume=0.25, sample_rate=sample_rate, channels=channels, waveform="sine")
            gap = _tone_bytes(523, 0.05, volume=0.0, sample_rate=sample_rate, channels=channels, waveform="sine")
            part2 = _tone_bytes(659, 0.10, volume=0.25, sample_rate=sample_rate, channels=channels, waveform="sine")
            pcm = part1 + gap + part2
        else:
            # Pure-Python fallback: use sine to reduce harshness
            part1 = _tone_bytes(523, 0.10, volume=0.25, sample_rate=sample_rate, channels=channels, waveform="sine")
            gap = _tone_bytes(523, 0.05, volume=0.0, sample_rate=sample_rate, channels=channels, waveform="sine")
            part2 = _tone_bytes(659, 0.10, volume=0.25, sample_rate=sample_rate, channels=channels, waveform="sine")
            pcm = part1 + gap + part2
        snd = pygame.mixer.Sound(buffer=pcm)
        snd.set_volume(0.6)
        return snd
    except Exception as e:
        print(f"Error generating combo sound: {e}")
        return None

def create_miss_sound():
    """Create miss sound effect - two descending disappointed tones."""
    try:
        mi = pygame.mixer.get_init() or (22050, -16, 1)
        sample_rate, _, channels = mi
        part1 = _tone_bytes(349, 0.15, volume=0.30, sample_rate=sample_rate, channels=channels, waveform="sine")
        gap = _tone_bytes(349, 0.05, volume=0.0, sample_rate=sample_rate, channels=channels, waveform="sine")
        part2 = _tone_bytes(294, 0.20, volume=0.25, sample_rate=sample_rate, channels=channels, waveform="sine")
        pcm = part1 + gap + part2
        snd = pygame.mixer.Sound(buffer=pcm)
        snd.set_volume(0.6)
        return snd
    except Exception as e:
        print(f"Error generating miss sound: {e}")
        return None

def create_ui_sounds():
    """Create UI sounds: page navigation and keyboard typing clicks.
    Uses short sine blips to stay subtle and non-intrusive.
    """
    if not SOUND_ENABLED:
        return None, None, None, None
    try:
        mi = pygame.mixer.get_init() or (22050, -16, 1)
        sample_rate, _, channels = mi

        # Navigation sound: short mid tone with tiny decay-like effect via two segments
        nav_p1 = _tone_bytes(660, 0.05, volume=0.22, sample_rate=sample_rate, channels=channels, waveform="sine")
        nav_p2 = _tone_bytes(660, 0.03, volume=0.14, sample_rate=sample_rate, channels=channels, waveform="sine")
        nav_pcm = nav_p1 + nav_p2
        nav = pygame.mixer.Sound(buffer=nav_pcm)
        nav.set_volume(UI_VOL_NAV)

        # Key tap: very short high tone
        tap_pcm = _tone_bytes(1500, 0.03, volume=0.20, sample_rate=sample_rate, channels=channels, waveform="sine")
        tap = pygame.mixer.Sound(buffer=tap_pcm)
        tap.set_volume(UI_VOL_KEY_TAP)

        # Backspace: slightly lower short tone
        back_pcm = _tone_bytes(600, 0.04, volume=0.22, sample_rate=sample_rate, channels=channels, waveform="sine")
        back = pygame.mixer.Sound(buffer=back_pcm)
        back.set_volume(UI_VOL_KEY_BACKSPACE)

        # Enter: small upward two-tone
        ent_p1 = _tone_bytes(880, 0.05, volume=0.20, sample_rate=sample_rate, channels=channels, waveform="sine")
        ent_gap = _tone_bytes(880, 0.02, volume=0.0, sample_rate=sample_rate, channels=channels, waveform="sine")
        ent_p2 = _tone_bytes(1175, 0.06, volume=0.20, sample_rate=sample_rate, channels=channels, waveform="sine")
        ent_pcm = ent_p1 + ent_gap + ent_p2
        enter = pygame.mixer.Sound(buffer=ent_pcm)
        enter.set_volume(UI_VOL_KEY_ENTER)

        return nav, tap, enter, back
    except Exception as e:
        print(f"[Audio] UI sound generation failed: {e}")
        return None, None, None, None

def create_event_sounds():
    """Create game start and game over sounds (three-syllable sequences)."""
    if not SOUND_ENABLED:
        return None, None
    try:
        mi = pygame.mixer.get_init() or (22050, -16, 1)
        sample_rate, _, channels = mi

        # Game Start: rising triad (C5, E5, G5)
        s1 = _tone_bytes(523.25, 0.12, volume=0.22, sample_rate=sample_rate, channels=channels, waveform="sine")
        gap = _tone_bytes(440.00, 0.03, volume=0.0, sample_rate=sample_rate, channels=channels, waveform="sine")
        s2 = _tone_bytes(659.25, 0.12, volume=0.22, sample_rate=sample_rate, channels=channels, waveform="sine")
        s3 = _tone_bytes(783.99, 0.16, volume=0.22, sample_rate=sample_rate, channels=channels, waveform="sine")
        start_pcm = s1 + gap + s2 + gap + s3
        start_snd = pygame.mixer.Sound(buffer=start_pcm)
        start_snd.set_volume(SFX_VOL_START)

        # Game Over: descending minor-ish (E5, C5, A4) and longer
        g1 = _tone_bytes(659.25, 0.30, volume=0.22, sample_rate=sample_rate, channels=channels, waveform="sine")
        ggap = _tone_bytes(440.00, 0.06, volume=0.0, sample_rate=sample_rate, channels=channels, waveform="sine")
        g2 = _tone_bytes(523.25, 0.30, volume=0.22, sample_rate=sample_rate, channels=channels, waveform="sine")
        g3 = _tone_bytes(440.00, 0.32, volume=0.22, sample_rate=sample_rate, channels=channels, waveform="sine")
        gameover_pcm = g1 + ggap + g2 + ggap + g3
        gameover_snd = pygame.mixer.Sound(buffer=gameover_pcm)
        gameover_snd.set_volume(SFX_VOL_GAMEOVER)

        return start_snd, gameover_snd
    except Exception as e:
        print(f"[Audio] Event sound generation failed: {e}")
        return None, None

def create_countdown_beep():
    """Create a short subtle beep for countdown numbers 3-2-1."""
    if not SOUND_ENABLED:
        return None
    try:
        mi = pygame.mixer.get_init() or (22050, -16, 1)
        sample_rate, _, channels = mi
        # A soft mid-high sine blip
        pcm = _tone_bytes(800.0, 0.09, volume=0.22, sample_rate=sample_rate, channels=channels, waveform="sine")
        snd = pygame.mixer.Sound(buffer=pcm)
        snd.set_volume(UI_VOL_COUNTDOWN)
        return snd
    except Exception as e:
        print(f"[Audio] Countdown beep generation failed: {e}")
        return None

def create_game_sounds():
    """Create game sound effects with robust fallbacks."""
    if not SOUND_ENABLED:
        print("[Audio] disabled – running without sound effects")
        return None, None, None, None

    # Prefer smoother sine tones via numpy when available
    if NUMPY_AVAILABLE:
        try:
            success_sound = create_success_sound()
            error_sound = generate_sound(196, 0.25, 0.35)   # G3 slightly lower than 220Hz to differentiate
            miss_sound = create_miss_sound()
            combo_sound = create_combo_sound()
            if success_sound and error_sound and miss_sound and combo_sound:
                # Normalize volumes with fine-tuned per-sound targets
                success_sound.set_volume(SFX_VOL_SUCCESS)
                error_sound.set_volume(SFX_VOL_ERROR)
                miss_sound.set_volume(SFX_VOL_MISS)
                combo_sound.set_volume(SFX_VOL_COMBO)
                return success_sound, error_sound, miss_sound, combo_sound
            else:
                print("[Audio] numpy path incomplete, falling back to pure-Python beeps")
        except Exception as e:
            print(f"[Audio] numpy sound path failed: {e}")

    # Pure-Python fallback tones (square/sine)
    success_sound = create_success_sound()
    error_sound = create_simple_beep_sound(196, 0.25, 0.45)
    miss_sound = create_miss_sound()
    combo_sound = create_combo_sound()

    # Normalize volumes if sounds exist (apply per-sound targets)
    try:
        if success_sound is not None:
            success_sound.set_volume(SFX_VOL_SUCCESS)
        if error_sound is not None:
            error_sound.set_volume(SFX_VOL_ERROR)
        if miss_sound is not None:
            miss_sound.set_volume(SFX_VOL_MISS)
        if combo_sound is not None:
            combo_sound.set_volume(SFX_VOL_COMBO)
    except Exception:
        pass
    return success_sound, error_sound, miss_sound, combo_sound

def create_background_music():
    """Create a longer electronic-style looping BGM (bass + arp + drums) with variation.
    Loop length ~BGM_LENGTH seconds to reduce repetitiveness. No external files needed.
    """
    if not SOUND_ENABLED or not BGM_ENABLED:
        return None
    try:
        mi = pygame.mixer.get_init() or (22050, -16, 1)
        sample_rate, _, channels = mi
        duration = float(BGM_LENGTH)
        frames = int(duration * sample_rate)
        if frames <= 0:
            return None

        import math
        from array import array

        # Musical grid and progression
        bpm = 120.0            # tempo
        beat_len = 60.0 / bpm  # seconds per quarter
        step_len = beat_len / 2.0  # 8th notes grid
        steps = int(duration / step_len)
        measure_beats = 4
        measure_len = beat_len * measure_beats  # length of a 4/4 measure

        # Chord progression (A minor-ish): Am | F | C | G (loop)
        # Arp notes per chord (triad, middle octave)
        CHORDS = [
            [440.00, 523.25, 659.25],  # Am: A4, C5, E5
            [349.23, 440.00, 523.25],  # F:  F4, A4, C5
            [261.63, 329.63, 392.00],  # C:  C4, E4, G4
            [392.00, 493.88, 587.33],  # G:  G4, B4, D5
        ]
        # Bass roots (lower octave)
        BASS = [110.00, 87.31, 65.41, 98.00]  # A2, F2, C2, G2

        # Envelopes and voice levels
        attack_s = 0.010
        release_s = 0.060
        kick_len = 0.11
        snare_len = 0.045
        hat_len = 0.020
        arp_level = 0.13
        bass_level = 0.10
        kick_level = 0.20
        snare_level = 0.16
        hat_level = 0.08

        def env_linear(i, total, a_samples, r_samples):
            # 0..1 envelope with attack then release
            if i < a_samples:
                return i / float(max(1, a_samples))
            if i >= total - r_samples:
                return (total - i) / float(max(1, r_samples))
            return 1.0

        buf = array('h')
        # Precompute constants
        two_pi = 2.0 * math.pi
        step_samples = int(step_len * sample_rate)
        a_samp = int(attack_s * sample_rate)
        r_samp = int(release_s * sample_rate)
        kick_samples = int(kick_len * sample_rate)
        snare_samples = int(snare_len * sample_rate)
        hat_samples = int(hat_len * sample_rate)

        # Simple PRNG for noise (hats/snare); LCG parameters
        noise_state = 1234567
        def next_noise():
            nonlocal noise_state
            noise_state = (1103515245 * noise_state + 12345) & 0x7fffffff
            return (noise_state / 1073741824.0) - 1.0  # roughly [-1, 1]

        for n in range(frames):
            t = n / float(sample_rate)
            # Measure info
            measure_idx = int((t // measure_len))
            t_in_measure = t - measure_idx * measure_len
            # Which chord of the progression (4-chord loop)
            chord_idx = measure_idx % 4
            chord = CHORDS[chord_idx]
            bass_freq = BASS[chord_idx]

            # Step index and position within step
            step_idx = int(t / step_len)
            within_step = n - step_idx * step_samples
            if step_idx >= steps:
                step_idx = steps - 1
                within_step = step_samples - 1

            # Arpeggio pattern varies by measure parity
            # Even measures: 0-1-2-1; odd measures: 0-2-1-2
            pat_even = [0, 1, 2, 1]
            pat_odd = [0, 2, 1, 2]
            pat = pat_even if (measure_idx % 2 == 0) else pat_odd
            pat_note = pat[step_idx % len(pat)]
            arp_freq = chord[pat_note]

            # Mild LFO for arp level to add movement (0.08 Hz)
            lfo = 0.5 + 0.5 * math.sin(two_pi * 0.08 * t)

            # Arp voice (with per-step envelope)
            env = env_linear(within_step, step_samples, a_samp, r_samp)
            arp = arp_level * lfo * math.sin(two_pi * arp_freq * t) * env

            # Bass voice (odd harmonics for warmth)
            bass = bass_level * (math.sin(two_pi * bass_freq * t) + 0.33 * math.sin(3 * two_pi * bass_freq * t))

            # Kick: on beats 1 and 3 (every measure), short decaying low thump
            # Beats inside measure happen at multiples of beat_len
            kick = 0.0
            for beat in (0, 2):
                rel = t_in_measure - beat * beat_len
                if 0.0 <= rel < kick_len:
                    k_env = 1.0 - (rel / kick_len)
                    kick += kick_level * math.sin(two_pi * 60.0 * t) * (k_env ** 2)

            # Snare: on beats 2 and 4 (noise burst)
            snare = 0.0
            for beat in (1, 3):
                rel = t_in_measure - beat * beat_len
                if 0.0 <= rel < snare_len:
                    s_env = 1.0 - (rel / snare_len)
                    # White noise burst (slight band-pass by mixing with 200Hz sine)
                    noise = next_noise()
                    snare += snare_level * (0.6 * noise + 0.4 * math.sin(two_pi * 200.0 * t)) * (s_env ** 1.5)

            # Hi-hat: on every 8th-note (grid), very short noise tick
            hat = 0.0
            grid_pos = t % step_len
            if grid_pos < hat_len:
                h_env = 1.0 - (grid_pos / hat_len)
                noise = next_noise()
                # Simple high-pass feel: subtract a tiny smoothed component
                hat += hat_level * (noise - 0.1 * math.sin(two_pi * 80.0 * t)) * (h_env ** 2)

            s = arp + bass + kick + snare + hat
            # Soft clip
            if s > 1.0:
                s = 1.0
            elif s < -1.0:
                s = -1.0
            sample = int(s * 32767)
            if channels == 2:
                buf.append(sample)
                buf.append(sample)
            else:
                buf.append(sample)

        pcm = buf.tobytes()
        snd = pygame.mixer.Sound(buffer=pcm)
        # We'll control bgm loudness via channel volume, not baked-in
        return snd
    except Exception as e:
        print(f"[Audio] background music generation failed: {e}")
        return None

# Initialize sound effects
try:
    sounds = create_game_sounds()
    if sounds and any(s is not None for s in sounds):
        SUCCESS_SOUND, ERROR_SOUND, MISS_SOUND, COMBO_SOUND = sounds
        print("✅ Sound effects ready:", {
            'success': SUCCESS_SOUND is not None,
            'error': ERROR_SOUND is not None,
            'miss': MISS_SOUND is not None,
            'combo': COMBO_SOUND is not None,
        })
    else:
        SUCCESS_SOUND, ERROR_SOUND, MISS_SOUND, COMBO_SOUND = None, None, None, None
        print("⚠️ Playing without audio effects")
except Exception as e:
    SUCCESS_SOUND, ERROR_SOUND, MISS_SOUND, COMBO_SOUND = None, None, None, None
    print(f"⚠️ Sound initialization failed: {e}")

# Initialize UI sounds (navigation and typing)
try:
    UI_NAV_SOUND, UI_KEY_TAP_SOUND, UI_KEY_ENTER_SOUND, UI_KEY_BACKSPACE_SOUND = create_ui_sounds()
    print("✅ UI sounds ready:", {
        'nav': UI_NAV_SOUND is not None,
        'tap': UI_KEY_TAP_SOUND is not None,
        'enter': UI_KEY_ENTER_SOUND is not None,
        'backspace': UI_KEY_BACKSPACE_SOUND is not None,
    })
except Exception as e:
    UI_NAV_SOUND, UI_KEY_TAP_SOUND, UI_KEY_ENTER_SOUND, UI_KEY_BACKSPACE_SOUND = None, None, None, None
    print(f"⚠️ UI sound initialization failed: {e}")

# Initialize event sounds (start and game over)
try:
    START_SOUND, GAMEOVER_SOUND = create_event_sounds()
    print("✅ Event sounds ready:", {
        'start': START_SOUND is not None,
        'gameover': GAMEOVER_SOUND is not None,
    })
except Exception as e:
    START_SOUND, GAMEOVER_SOUND = None, None
    print(f"⚠️ Event sound initialization failed: {e}")

# Initialize countdown beep sound
try:
    COUNTDOWN_BEEP_SOUND = create_countdown_beep()
    print("✅ Countdown beep ready:", COUNTDOWN_BEEP_SOUND is not None)
except Exception as e:
    COUNTDOWN_BEEP_SOUND = None
    print(f"⚠️ Countdown beep initialization failed: {e}")

# Start background music (looping)
if SOUND_ENABLED and BGM_ENABLED:
    try:
        BGM_SOUND = create_background_music()
        if BGM_SOUND is not None:
            BGM_CHANNEL = BGM_SOUND.play(loops=-1)
            if BGM_CHANNEL is not None:
                BGM_CHANNEL.set_volume(BGM_VOLUME)
            print("🎵 BGM started")
        else:
            print("⚠️ BGM not available")
    except Exception as e:
        print(f"⚠️ Failed to start BGM: {e}")

# Game constants
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
SCREEN = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Test Your Brain Age!")

# UI layout constants
UI_MARGIN_X = 20
TOP_BAR_HEIGHT = 40  # reserved height for score/progress
FRAME_MARGIN = 20
# Play area (game frame) rectangle: blocks will only appear inside this rect
PLAY_AREA = pygame.Rect(
    FRAME_MARGIN,
    TOP_BAR_HEIGHT + 20,
    SCREEN_WIDTH - 2 * FRAME_MARGIN,
    SCREEN_HEIGHT - (TOP_BAR_HEIGHT + 20) - FRAME_MARGIN,
)

# Frame and spawn margins
FRAME_BORDER_WIDTH = 4  # must match the width used when drawing the black game frame
BLOCK_SPAWN_MARGIN = 12  # extra inner margin so blocks don't press against the black frame

# Pixel-style block color definitions
COLORS = {
    'red': {'rgb': (255, 85, 85), 'key': 'r', 'name': 'RED'},      # pixel red
    'blue': {'rgb': (85, 170, 255), 'key': 'b', 'name': 'BLUE'},   # pixel blue
    'yellow': {'rgb': (255, 221, 85), 'key': 'y', 'name': 'YELLOW'}, # pixel yellow
    'green': {'rgb': (85, 255, 85), 'key': 'g', 'name': 'GREEN'}   # pixel green
}
COLOR_LIST = list(COLORS.keys())

# Block size (wider than letter display)
BLOCK_WIDTH = int(SCREEN_WIDTH * 0.12)  # increased width from 7% to 12%
BLOCK_HEIGHT = int(SCREEN_HEIGHT * 0.07)

# Game parameters
TOTAL_BLOCKS = 10  # total number of blocks
BLOCK_DURATION = 0.8  # block display duration (seconds)
BLOCK_INTERVAL = 3.0  # time between blocks (seconds)
CORRECT_BLOCKS = 6  # number of correct blocks (text matches color)
DISTURB_BLOCKS = 4  # number of distractor blocks (text doesn't match color)

# Rankings data (only valid during a single run)
rankings = []


class Block:
    def __init__(self, is_disturb=False):
        # random block color
        self.color = random.choice(COLOR_LIST)
        # create a distractor based on parameter (text does not match the block color)
        if is_disturb:
            # distractor: pick a text color different from the block color
            self.text_color = random.choice([c for c in COLOR_LIST if c != self.color])
        else:
            # normal item: text matches the color
            self.text_color = self.color

        # random position inside play area with inner margin (avoid pressing the black frame)
        min_x = PLAY_AREA.left + BLOCK_SPAWN_MARGIN
        max_x = PLAY_AREA.right - BLOCK_WIDTH - BLOCK_SPAWN_MARGIN
        min_y = PLAY_AREA.top + BLOCK_SPAWN_MARGIN
        max_y = PLAY_AREA.bottom - BLOCK_HEIGHT - BLOCK_SPAWN_MARGIN
        # Fallback clamp if margins are too aggressive for a very small play area
        if max_x < min_x:
            min_x = PLAY_AREA.left + FRAME_BORDER_WIDTH + 1
            max_x = PLAY_AREA.right - BLOCK_WIDTH - FRAME_BORDER_WIDTH - 1
        if max_y < min_y:
            min_y = PLAY_AREA.top + FRAME_BORDER_WIDTH + 1
            max_y = PLAY_AREA.bottom - BLOCK_HEIGHT - FRAME_BORDER_WIDTH - 1
        self.x = random.randint(min_x, max_x)
        self.y = random.randint(min_y, max_y)

        # block attributes
        self.rgb = COLORS[self.color]['rgb']
        self.display_text = COLORS[self.text_color]['name']
        self.correct_key = COLORS[self.color]['key']  # correct key for the block color
        self.is_clicked = False  # whether the block has been clicked
        
        # Animation properties
        self.is_animating = False
        self.animation_start_time = 0
        self.animation_duration = 0.3  # seconds
        self.scale = 1.0
        self.alpha = 255
    
    def start_disappear_animation(self):
        """Start the disappearing animation"""
        self.is_animating = True
        self.animation_start_time = time.time()
    
    def update_animation(self):
        """Update animation state"""
        if not self.is_animating:
            return False
            
        elapsed = time.time() - self.animation_start_time
        progress = elapsed / self.animation_duration
        
        if progress >= 1.0:
            # Animation finished
            self.is_animating = False
            return True  # Animation complete
        
        # Scale and fade out effect
        self.scale = 1.0 + (progress * 0.5)  # Grow slightly
        self.alpha = max(0, int(255 * (1.0 - progress)))  # Fade out
        
        return False  # Animation still running
    
    def draw(self, screen):
        """Draw the block with pixel art style and animation effects"""
        if self.alpha <= 0:
            return
            
        # Calculate animated size and position
        animated_width = int(BLOCK_WIDTH * self.scale)
        animated_height = int(BLOCK_HEIGHT * self.scale)
        
        # Center the scaled block
        offset_x = (animated_width - BLOCK_WIDTH) // 2
        offset_y = (animated_height - BLOCK_HEIGHT) // 2
        
        animated_x = self.x - offset_x
        animated_y = self.y - offset_y
        
        # Create a surface with per-pixel alpha
        block_surface = pygame.Surface((animated_width, animated_height), pygame.SRCALPHA)
        
    # Pixel-style block background
        block_color = tuple(int(c * self.alpha / 255) for c in self.rgb)
        pygame.draw.rect(block_surface, (*block_color, self.alpha), 
                        (0, 0, animated_width, animated_height))
        
    # Pixel-style border effect
        border_color = tuple(max(0, c - 40) for c in block_color)
        pygame.draw.rect(block_surface, (*border_color, self.alpha), 
                        (0, 0, animated_width, animated_height), 3)
        
    # Highlight effect
        highlight_color = tuple(min(255, c + 60) for c in block_color)
        pygame.draw.rect(block_surface, (*highlight_color, self.alpha), 
                        (3, 3, animated_width - 6, animated_height - 6), 2)
        
    # Pixel-style text (use contrasting color)
        text_color = (20, 20, 20) if sum(self.rgb) > 400 else (240, 240, 240)
        text_surface = small_font.render(self.display_text, False, text_color)
        text_surface.set_alpha(self.alpha)
        
        # Scale text if needed
        if self.scale != 1.0:
            text_width = int(text_surface.get_width() * self.scale)
            text_height = int(text_surface.get_height() * self.scale)
            if text_width > 0 and text_height > 0:
                text_surface = pygame.transform.scale(text_surface, (text_width, text_height))
        
        # Center text on block
        text_x = (animated_width - text_surface.get_width()) // 2
        text_y = (animated_height - text_surface.get_height()) // 2
        
        block_surface.blit(text_surface, (text_x, text_y))
        screen.blit(block_surface, (animated_x, animated_y))


class Game:
    def __init__(self):
        self.username = ""
        self.score = 0
        self.streak = 0  # current consecutive correct count (streak)
        # combo display and stats
        self.max_combo = 0
        self.combo_visible_until = 0.0  # timestamp until which combo bubble is visible
        self.combo_last_streak = 0      # last streak value shown in the combo bubble
        self.reaction_times = []  # list of valid reaction times (seconds)
        self.current_block = None  # currently displayed block
        self.block_start_time = 0  # timestamp when current block appeared
        self.next_state_time = 0  # timestamp for switching between visible/interval states
        self.block_visible = False  # whether a block is currently visible
        self.block_count = 0  # number of blocks shown so far
        self.game_state = "input_name"  # states: input_name/instructions/playing/results/rankings
        # click feedback (e.g., +1, +2, -1)
        self.feedback_text = None
        self.feedback_color = (0, 0, 0)
        self.feedback_time = 0.0
        self.feedback_duration = 1.2  # seconds (increased from 0.6 to 1.2)
        # reaction time display
        self.reaction_time_text = None
        self.reaction_time_display_time = 0.0
        self.reaction_time_duration = 1.5  # seconds to display reaction time
        self.last_reaction_time_id = 0  # used to prevent duplicate display
        # Predefined block sequence: 6 correct + 4 distractors, randomized
        self.block_sequence = self.generate_block_sequence()
        # Animation state
        self.animating_blocks = []  # List of blocks currently animating
        # Instructions screen animation state
        self.instructions_enter_time = 0.0
        self.instructions_anim_duration = 0.6  # seconds
        # Typing SFX throttle
        self.last_key_sound_time = 0.0
        # Countdown state
        self.countdown_start = 0.0
        self.countdown_current = 3  # counts 3,2,1 then GO
        self.countdown_active = False

    # Perfect particle effect container
        self.perfect_particles = []  # list of dicts: {x,y,vx,vy,life,age,color}
        self._last_play_dt_time = 0.0

        # GIF capture state (F12 toggles recording)
        self._cap_active = False
        self._cap_dir = os.path.join(os.path.dirname(__file__), 'assets', 'gifs')
        self._cap_tmp = None
        self._cap_last = 0.0
        self._cap_interval = 1.0 / 12.0  # 12 FPS
        self._cap_frames = 0
        self._cap_max_frames = 180  # ~15s at 12 FPS
        self._cap_target = ''
        try:
            os.makedirs(self._cap_dir, exist_ok=True)
        except Exception:
            pass

        # Auto GIF capture (demo) state
        self.autogif = False
        self.autogif_phase = None
        self.autogif_t0 = 0.0
        self.autogif_flags = {}

        # Persistence paths and settings
        self.data_dir = os.path.join(os.path.expanduser('~'), '.reaction_mini')
        self.data_file = os.path.join(self.data_dir, 'data.json')
        self.settings = {
            'bgm_enabled': BGM_ENABLED,
            'bgm_volume': BGM_VOLUME,
            'sfx_volume': 1.0
        }
        self.load_persistence()
        # Apply audio settings (volume/toggles)
        try:
            self.apply_audio_settings()
        except Exception:
            pass

        # Title screen animation state (opening screen)
        self.title_anim_start = time.time()
        self.last_frame_time = time.time()
        # Decorative particles for the opening screen (upper half)
        self.title_particles = []
        try:
            for _ in range(28):
                self.title_particles.append({
                    'x': random.uniform(0, SCREEN_WIDTH),
                    'y': random.uniform(0, SCREEN_HEIGHT * 0.55),
                    'dx': random.uniform(-12.0, 12.0),
                    'dy': random.uniform(8.0, 22.0),
                    'phase': random.uniform(0.0, math.pi * 2.0),
                    'size': random.choice([1, 1, 2])
                })
        except Exception:
            pass

    def generate_block_sequence(self):
        """Generate block sequence: 6 correct blocks + 4 distractor blocks in random order."""
        sequence = []
        # Add 6 correct blocks
        for _ in range(CORRECT_BLOCKS):
            sequence.append(False)  # False means a valid block (text matches color)
        # Add 4 distractor blocks
        for _ in range(DISTURB_BLOCKS):
            sequence.append(True)   # True means a distractor (text doesn't match color)
        # Shuffle order randomly
        random.shuffle(sequence)
        return sequence

    def load_persistence(self):
        """Load rankings and settings from disk if available."""
        try:
            if not os.path.isdir(self.data_dir):
                os.makedirs(self.data_dir, exist_ok=True)
            if os.path.isfile(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if 'rankings' in data and isinstance(data['rankings'], list):
                        global rankings
                        rankings = data['rankings']
                    if 'settings' in data and isinstance(data['settings'], dict):
                        for k, v in data['settings'].items():
                            if k in self.settings:
                                self.settings[k] = v
                                # apply bgm setting immediately
                                if k == 'bgm_enabled':
                                    pass
                                if k == 'bgm_volume':
                                    try:
                                        if BGM_CHANNEL:
                                            BGM_CHANNEL.set_volume(v)
                                    except Exception:
                                        pass
        except Exception as e:
            print(f"[Persistence] load failed: {e}")

    def save_persistence(self):
        """Save rankings and settings to disk."""
        try:
            data = {
                'rankings': rankings,
                'settings': self.settings
            }
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Persistence] save failed: {e}")

    def apply_audio_settings(self):
        """Apply SFX/BGM volumes and bgm enabled flag to current mixer objects."""
        if not SOUND_ENABLED:
            return
        # SFX volume
        try:
            vol = float(self.settings.get('sfx_volume', 1.0))
        except Exception:
            vol = 1.0
        for name in [
            'SUCCESS_SOUND','ERROR_SOUND','MISS_SOUND','COMBO_SOUND',
            'UI_NAV_SOUND','UI_KEY_TAP_SOUND','UI_KEY_ENTER_SOUND','UI_KEY_BACKSPACE_SOUND',
            'START_SOUND','GAMEOVER_SOUND','COUNTDOWN_BEEP_SOUND'
        ]:
            try:
                if name in globals() and globals()[name] is not None:
                    globals()[name].set_volume(max(0.0, min(1.0, vol)))
            except Exception:
                pass
        # BGM volume and enable
        try:
            bgm_on = bool(self.settings.get('bgm_enabled', True))
            bgm_vol = float(self.settings.get('bgm_volume', BGM_VOLUME if 'BGM_VOLUME' in globals() else 0.4))
            if 'BGM_CHANNEL' in globals() and globals()['BGM_CHANNEL'] is not None:
                ch = globals()['BGM_CHANNEL']
                ch.set_volume(bgm_vol if bgm_on else 0.0)
        except Exception:
            pass

    def spawn_perfect_particles(self, cx, cy, color):
        """Spawn small pixel particles at (cx,cy) with given RGB color tuple."""
        try:
            count = 16
            for _ in range(count):
                angle = random.uniform(0, 2*math.pi)
                speed = random.uniform(120.0, 260.0)
                vx = math.cos(angle) * speed
                vy = math.sin(angle) * speed - random.uniform(30.0, 80.0)
                life = random.uniform(0.55, 0.9)
                self.perfect_particles.append({
                    'x': float(cx),
                    'y': float(cy),
                    'vx': vx,
                    'vy': vy,
                    'life': life,
                    'age': 0.0,
                    'color': color,
                    'size': random.choice([2,2,3])
                })
        except Exception:
            pass

    def _cap_pick_filename(self):
        """Pick target GIF filename based on current state."""
        state = self.game_state
        if state == 'input_name':
            name = 'title_intro.gif'
        elif state == 'instructions':
            name = 'instructions_countdown.gif'
        elif state == 'playing':
            name = 'gameplay_combo_perfect.gif'
        elif state in ('results', 'rankings'):
            name = 'results_rankings.gif'
        elif state == 'settings':
            name = 'settings.gif'
        else:
            name = 'gameplay_combo_perfect.gif'
        return os.path.join(self._cap_dir, name)

    def _toggle_capture(self):
        """Toggle frame capture; on stop try to build GIF with imageio if available."""
        try:
            if not self._cap_active:
                # start recording
                ts = int(time.time())
                self._cap_tmp = os.path.join(self._cap_dir, f"_tmp_{ts}")
                os.makedirs(self._cap_tmp, exist_ok=True)
                self._cap_active = True
                self._cap_last = 0.0
                self._cap_frames = 0
                self._cap_target = self._cap_pick_filename()
                # lightweight on-screen hint if available
                self.feedback_text = "REC..."
                self.feedback_color = (255, 200, 0)
                self.feedback_time = time.time()
            else:
                # stop and finalize
                self._cap_active = False
                self._finalize_capture()
        except Exception:
            self._cap_active = False

    def _maybe_capture_frame(self):
        """Capture current SCREEN to PNG if recording and within FPS budget."""
        if not self._cap_active or not self._cap_tmp:
            return
        now = time.time()
        if (now - self._cap_last) < self._cap_interval:
            return
        try:
            fn = os.path.join(self._cap_tmp, f"frame_{self._cap_frames:04d}.png")
            pygame.image.save(SCREEN, fn)
            self._cap_frames += 1
            self._cap_last = now
            if self._cap_frames >= self._cap_max_frames:
                # auto stop
                self._toggle_capture()
        except Exception:
            self._cap_active = False

    def _finalize_capture(self):
        """Assemble PNG frames into a GIF if imageio is available; otherwise keep PNGs."""
        try:
            if not self._cap_tmp:
                return
            files = []
            for fname in sorted(os.listdir(self._cap_tmp)):
                if fname.lower().endswith('.png'):
                    files.append(os.path.join(self._cap_tmp, fname))
            if not files:
                return
            try:
                import imageio.v2 as imageio
                imgs = [imageio.imread(p) for p in files]
                imageio.mimsave(self._cap_target, imgs, duration=self._cap_interval)
                # cleanup
                for p in files:
                    try: os.remove(p)
                    except Exception: pass
                try: os.rmdir(self._cap_tmp)
                except Exception: pass
                self.feedback_text = f"GIF saved: {os.path.basename(self._cap_target)}"
                self.feedback_color = (0, 160, 0)
                self.feedback_time = time.time()
            except Exception:
                self.feedback_text = "Saved PNG frames (install imageio for GIF)"
                self.feedback_color = (255, 200, 0)
                self.feedback_time = time.time()
        finally:
            self._cap_tmp = None
    
    def _start_autogif(self):
        """Start automated GIF recording across all key screens."""
        try:
            # Stop any ongoing capture first
            if self._cap_active:
                self._toggle_capture()
        except Exception:
            pass
        self.autogif = True
        self.autogif_phase = 'title'
        self.autogif_t0 = time.time()
        self.autogif_flags = {}
        # Ensure we begin from the title/name screen
        self.username = ''
        self.game_state = 'input_name'
        self.countdown_active = False
        self.block_visible = False
        self.current_block = None
        self.block_count = 0
        self.reaction_times = []
        self.score = 0
        self.streak = 0
        self.max_combo = 0
        # Ensure block sequence starts with two valid blocks for combo demo
        try:
            if len(self.block_sequence) >= 2:
                self.block_sequence[0] = False
                self.block_sequence[1] = False
        except Exception:
            pass

    def _tick_autogif(self, loop_name: str):
        """Advance the automated GIF recording sequence. Call this every frame from loops."""
        if not getattr(self, 'autogif', False):
            return
        now = time.time()
        t = now - (self.autogif_t0 or now)

        # Helper: safe key post
        def post_key(key_code):
            try:
                pygame.event.post(pygame.event.Event(KEYDOWN, key=key_code))
            except Exception:
                pass

        # Helper: safe mouse click post
        def post_click(x=20, y=20):
            try:
                pygame.event.post(pygame.event.Event(MOUSEBUTTONDOWN, pos=(x, y), button=1))
            except Exception:
                pass

        # PHASE: Title / Name input -> record title_intro.gif then go to instructions
        if self.autogif_phase == 'title':
            if t >= 0.1 and not self._cap_active:
                try: self._toggle_capture()
                except Exception: pass
            if t >= 2.7 and self._cap_active:
                try: self._toggle_capture()
                except Exception: pass
            if t >= 3.0:
                # Fill a demo username and go to instructions
                self.username = 'DEMO'
                self.instructions_enter_time = 0.0
                self.game_state = 'instructions'
                self.autogif_phase = 'instructions'
                self.autogif_t0 = now
                self.autogif_flags = {}
                return

        # PHASE: Instructions + Countdown -> record instructions_countdown.gif
        if self.autogif_phase == 'instructions':
            if t >= 0.0 and not self._cap_active:
                try: self._toggle_capture()
                except Exception: pass
            if t >= 0.2 and not self.countdown_active:
                # Trigger countdown via any key (SPACE)
                post_key(pygame.K_SPACE)
            # Stop after GO shows for a moment
            if t >= 4.2 and self._cap_active:
                try: self._toggle_capture()
                except Exception: pass
            # Transition proceeds automatically to playing
            if self.game_state == 'playing':
                self.autogif_phase = 'playing'
                self.autogif_t0 = now
                self.autogif_flags = {}
                return

        # PHASE: Playing -> ensure two quick correct hits (Perfect + Combo)
        if self.autogif_phase == 'playing':
            if t >= 0.05 and not self._cap_active:
                try: self._toggle_capture()
                except Exception: pass
            # Ensure first block is visible quickly
            if t >= 0.08 and not self.block_visible and self.current_block is None:
                try:
                    # guarantee first two are valid blocks
                    if len(self.block_sequence) >= 2:
                        self.block_sequence[0] = False
                        self.block_sequence[1] = False
                except Exception:
                    pass
                try:
                    self.next_block()
                except Exception:
                    pass
            # Hit first block fast (aim for Perfect <0.28s)
            if t >= 0.18 and self.block_visible and self.current_block and not self.current_block.is_clicked:
                try:
                    keyname = getattr(self.current_block, 'correct_key', 'r')
                    keycode = pygame.key.key_code(keyname) if hasattr(pygame.key, 'key_code') else getattr(pygame, f'K_{keyname}', pygame.K_r)
                    post_key(keycode)
                except Exception:
                    post_key(pygame.K_r)
            # Spawn second block during interval
            if t >= 0.45 and (not self.block_visible) and self.current_block is None and self.block_count == 1:
                try:
                    self.next_block()
                except Exception:
                    pass
            # Hit second block to build combo
            if t >= 0.55 and self.block_visible and self.block_count == 2 and self.current_block and not self.current_block.is_clicked:
                try:
                    keyname = getattr(self.current_block, 'correct_key', 'g')
                    keycode = pygame.key.key_code(keyname) if hasattr(pygame.key, 'key_code') else getattr(pygame, f'K_{keyname}', pygame.K_g)
                    post_key(keycode)
                except Exception:
                    post_key(pygame.K_g)
            # Stop gameplay capture after combo text appears for a bit
            if t >= 1.6 and self._cap_active:
                try: self._toggle_capture()
                except Exception: pass
            # Force fast finish to results
            if t >= 1.7:
                self.current_block = None
                self.block_visible = False
                self.block_count = TOTAL_BLOCKS
                self.next_state_time = now
            if self.game_state == 'results':
                self.autogif_phase = 'results_rankings'
                self.autogif_t0 = now
                self.autogif_flags = {}
                return

        # PHASE: Results -> Rankings combined GIF
        if self.autogif_phase == 'results_rankings':
            if t >= 0.1 and not self._cap_active:
                try: self._toggle_capture()
                except Exception: pass
            if t >= 1.2 and not self.autogif_flags.get('clicked_to_rank', False):
                post_click(20, 20)  # click away from REC button
                self.autogif_flags['clicked_to_rank'] = True
            if t >= 2.0 and self._cap_active:
                try: self._toggle_capture()
                except Exception: pass
            if self.game_state == 'rankings':
                self.autogif_phase = 'rankings_settings'
                self.autogif_t0 = now
                self.autogif_flags = {}
                return

        # PHASE: Rankings -> open settings
        if self.autogif_phase == 'rankings_settings':
            if t >= 0.5 and not self.autogif_flags.get('open_settings', False):
                post_key(pygame.K_s)
                self.autogif_flags['open_settings'] = True
            if self.game_state == 'settings':
                self.autogif_phase = 'settings'
                self.autogif_t0 = now
                self.autogif_flags = {}
                return

        # PHASE: Settings -> small adjustments and save settings.gif
        if self.autogif_phase == 'settings':
            if t >= 0.2 and not self._cap_active:
                try: self._toggle_capture()
                except Exception: pass
            if t >= 0.6 and not self.autogif_flags.get('move_down', False):
                post_key(pygame.K_DOWN)
                self.autogif_flags['move_down'] = True
            if t >= 0.8 and not self.autogif_flags.get('right1', False):
                post_key(pygame.K_RIGHT)
                self.autogif_flags['right1'] = True
            if t >= 1.0 and not self.autogif_flags.get('right2', False):
                post_key(pygame.K_RIGHT)
                self.autogif_flags['right2'] = True
            if t >= 1.2 and not self.autogif_flags.get('up_to_bgm', False):
                post_key(pygame.K_UP)
                self.autogif_flags['up_to_bgm'] = True
            if t >= 1.4 and not self.autogif_flags.get('toggle_bgm', False):
                post_key(pygame.K_RETURN)
                self.autogif_flags['toggle_bgm'] = True
            if t >= 2.1 and self._cap_active:
                try: self._toggle_capture()
                except Exception: pass
            if t >= 2.3:
                # Done
                self.autogif = False
                self.autogif_phase = None
                self.autogif_flags = {}
                return
    
    def _draw_rec_button(self):
        """Draw a small REC/STOP button at the bottom-right corner (outside the frame) and return its rect for hit testing."""
        try:
            btn_w, btn_h = 86, 28
            margin = 8
            x = SCREEN_WIDTH - btn_w - margin
            # Place at window bottom-right so it's outside the play frame in all screens
            y = SCREEN_HEIGHT - btn_h - margin
            rect = pygame.Rect(x, y, btn_w, btn_h)
            # Background
            pygame.draw.rect(SCREEN, PIXEL_COLORS['bg_secondary'], rect)
            # Border indicates state
            border_col = PIXEL_COLORS['warning'] if self._cap_active else PIXEL_COLORS['frame']
            draw_pixel_border(SCREEN, rect, border_col, 2)
            # Label text
            label = "STOP" if self._cap_active else "REC"
            txt_col = PIXEL_COLORS['error'] if self._cap_active else PIXEL_COLORS['text_primary']
            draw_pixel_text_with_shadow(
                SCREEN, label, small_font,
                rect.x + (rect.width - small_font.size(label)[0]) // 2,
                rect.y + (rect.height - small_font.get_linesize()) // 2 + 2,
                txt_col, PIXEL_COLORS['bg_primary']
            )
            # Red dot indicator on the left
            dot = pygame.Rect(rect.x + 8, rect.y + (rect.height - 10)//2, 10, 10)
            if self._cap_active:
                pygame.draw.rect(SCREEN, PIXEL_COLORS['error'], dot)
            else:
                pygame.draw.rect(SCREEN, PIXEL_COLORS['frame'], dot, 1)
            return rect
        except Exception:
            return None
    
    def calculate_brain_age(self):
        """Calculate brain age"""
        if not self.reaction_times:
            # No valid clicks; default to 80 years
            return 80, "Your brain age is 80 years old! Your reactions are rather slow and you make more mistakes, but no worries! Play a few more times to train your brain—maybe you can even achieve \"reverse aging\"!"
        
        avg_reaction_time = sum(self.reaction_times) / len(self.reaction_times)
        score = self.score
        
        # Age 20: score ≥16 and <0.4s. If score qualifies, slightly slower (0.4-0.45s) still counts
        if score >= 16 and avg_reaction_time < 0.4:
            return 20, "Congratulations! Your brain age is only 20 years old! Your reaction speed is comparable to professional esports players, with almost no mistakes in consecutive judgments—your brain is in the prime period of a young person!"
        elif score >= 16 and 0.4 <= avg_reaction_time <= 0.45:
            return 20, "Congratulations! Your brain age is only 20 years old! Your reaction speed is comparable to professional esports players, with almost no mistakes in consecutive judgments—your brain is in the prime period of a young person!"
        
        # Age 35: 10-15 points or 0.4-0.55s (either condition qualifies)
        elif (10 <= score <= 15) or (0.4 <= avg_reaction_time <= 0.55):
            return 35, "Nice work! Your brain age is 35 years old! You have stable reactions and solid judgment; though you might be a little slow occasionally, your overall performance is far better than your peers!"
        
        # Age 55: 3-9 points and 0.55-0.7s (both conditions; small deviation allowed)
        elif (1 <= score <= 11) and (0.5 <= avg_reaction_time <= 0.75):
            return 55, "Your brain age is 55 years old! Your reactions are slightly slower but you make fewer mistakes—you have a \"steady-type\" brain. Just like a mature decision-maker, you don't chase speed but prioritize accuracy!"
        
        # Age 65: -5 to 2 points and 0.7-0.85s. If time qualifies, slightly lower scores (-6 to -5) still count
        elif (-5 <= score <= 2) and (0.7 <= avg_reaction_time <= 0.85):
            return 65, "Your brain age is 65 years old! Your reactions are relatively slow and you may make misjudgments from time to time. Could it be that you're not focused enough? Stay more focused next time, and you might even shave a few years off your brain age!"
        elif (-6 <= score <= -5) and (0.7 <= avg_reaction_time <= 0.85):
            return 65, "Your brain age is 65 years old! Your reactions are relatively slow and you may make misjudgments from time to time. Could it be that you're not focused enough? Stay more focused next time, and you might even shave a few years off your brain age!"
        
        # Age 80: ≤-6 points or ≥0.85s (either condition qualifies)
        else:
            return 80, "Your brain age is 80 years old! Your reactions are rather slow and you make more mistakes, but no worries! Play a few more times to train your brain—maybe you can even achieve \"reverse aging\"!"

    def get_username(self):
        """Username input screen"""
        input_text = ""
        # enable SDL text input (handles IME and produces TEXTINPUT events)
        try:
            pygame.key.start_text_input()
        except Exception:
            pass
        cursor_visible = True
        cursor_timer = time.time()
        # ensure frame time baseline
        self.last_frame_time = time.time()
        while self.game_state == "input_name":
            # Pixel-style background
            SCREEN.fill(PIXEL_COLORS['bg_primary'])
            
            # Draw grid background
            grid_size = 20
            for x in range(0, SCREEN_WIDTH, grid_size):
                pygame.draw.line(SCREEN, PIXEL_COLORS['bg_secondary'], 
                               (x, 0), (x, SCREEN_HEIGHT), 1)
            for y in range(0, SCREEN_HEIGHT, grid_size):
                pygame.draw.line(SCREEN, PIXEL_COLORS['bg_secondary'], 
                               (0, y), (SCREEN_WIDTH, y), 1)

            # Time and delta for animations
            now = time.time()
            dt = max(0.0, min(0.05, now - self.last_frame_time))
            self.last_frame_time = now

            # Opening screen decorative particles (twinkling pixels)
            try:
                star_overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
                for p in self.title_particles:
                    p['x'] += p['dx'] * dt
                    p['y'] += p['dy'] * dt
                    # wrap around edges
                    if p['y'] > SCREEN_HEIGHT * 0.6:
                        p['y'] = -2
                        p['x'] = random.uniform(0, SCREEN_WIDTH)
                    if p['x'] < -2:
                        p['x'] = SCREEN_WIDTH + 2
                    elif p['x'] > SCREEN_WIDTH + 2:
                        p['x'] = -2
                    # twinkle alpha
                    a = 90 + int(80 * (0.5 + 0.5 * math.sin(2.0 * now + p['phase'])))
                    a = max(0, min(170, a))
                    col = (*PIXEL_COLORS['text_accent'], a)
                    size = p['size']
                    pygame.draw.rect(star_overlay, col, (int(p['x']), int(p['y']), size, size))
                SCREEN.blit(star_overlay, (0, 0))
            except Exception:
                pass
            
            # Pixel-style title
            title_text = "TEST YOUR BRAIN AGE!"
            # Title bobbing + pulsing glow
            try:
                tw = title_font.size(title_text)[0]
                th = title_font.get_linesize()
                bob = int(3 * math.sin(now * 2.0))
                tx = SCREEN_WIDTH // 2 - tw // 2
                ty = 100 + bob

                # Pulsing glow behind the title
                glow_alpha = max(0, min(120, int(60 + 50 * math.sin(2.0 * math.pi * 0.7 * now))))
                glow_overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
                glow_rect = pygame.Rect(tx - 16, ty - 10, tw + 32, th + 20)
                pygame.draw.rect(glow_overlay, (*PIXEL_COLORS['accent'], int(glow_alpha * 0.9)), glow_rect, 4)
                pygame.draw.rect(glow_overlay, (*PIXEL_COLORS['accent'], int(glow_alpha * 0.5)), glow_rect.inflate(10, 8), 6)
                SCREEN.blit(glow_overlay, (0, 0))

                # Draw title text with shadow
                draw_pixel_text_with_shadow(SCREEN, title_text, title_font, tx, ty, 
                                            PIXEL_COLORS['text_accent'], PIXEL_COLORS['bg_secondary'])

                # Animated underline segments
                underline_y = ty + th + 6
                seg_w = max(6, tw // 28)
                gap = 2
                nseg = max(8, min(60, (tw // (seg_w + gap))))
                # recompute width coverage
                total_w = nseg * seg_w + (nseg - 1) * gap
                ux = SCREEN_WIDTH // 2 - total_w // 2
                active = int((now * 10.0) % nseg)
                for i in range(nseg):
                    # brightness falloff from active index
                    d = abs(i - active)
                    boost = max(0, 40 - d * 16)
                    col = tuple(min(255, c + boost) for c in PIXEL_COLORS['accent'])
                    rect = pygame.Rect(ux + i * (seg_w + gap), underline_y, seg_w, 3)
                    pygame.draw.rect(SCREEN, col, rect)
            except Exception:
                # fallback title without effects
                draw_pixel_text_with_shadow(SCREEN, title_text, title_font, 
                                            SCREEN_WIDTH//2 - title_font.size(title_text)[0]//2, 
                                            100, PIXEL_COLORS['text_accent'], PIXEL_COLORS['bg_secondary'])
            
            # Input prompt
            prompt_text = "ENTER YOUR NAME:"
            draw_pixel_text_with_shadow(SCREEN, prompt_text, font,
                                      SCREEN_WIDTH//2 - font.size(prompt_text)[0]//2,
                                      220, PIXEL_COLORS['text_primary'], PIXEL_COLORS['bg_secondary'])
            
            # Input box
            input_box = pygame.Rect(SCREEN_WIDTH//2 - 150, 280, 300, 40)
            pygame.draw.rect(SCREEN, PIXEL_COLORS['bg_secondary'], input_box)
            draw_pixel_border(SCREEN, input_box, PIXEL_COLORS['frame'], 2)
            # Accent corner decorations with subtle pulse
            try:
                pulse = 0.5 + 0.5 * math.sin(now * 2.2)
                a = int(60 + 80 * pulse)
                deco = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
                c = (*PIXEL_COLORS['accent'], a)
                s = 6
                pygame.draw.rect(deco, c, (input_box.left - 2, input_box.top - 2, s, s))
                pygame.draw.rect(deco, c, (input_box.right - s + 2, input_box.top - 2, s, s))
                pygame.draw.rect(deco, c, (input_box.left - 2, input_box.bottom - s + 2, s, s))
                pygame.draw.rect(deco, c, (input_box.right - s + 2, input_box.bottom - s + 2, s, s))
                SCREEN.blit(deco, (0, 0))
            except Exception:
                pass
            
            # Input text
            if cursor_visible:
                display_text = input_text + "|"
            else:
                display_text = input_text
            name_surface = font.render(display_text, False, PIXEL_COLORS['text_primary'])
            SCREEN.blit(name_surface, (input_box.x + 10, input_box.y + 10))
            
            # Confirm hint
            hint_text = "PRESS ENTER TO CONFIRM"
            draw_pixel_text_with_shadow(SCREEN, hint_text, small_font,
                                      SCREEN_WIDTH//2 - small_font.size(hint_text)[0]//2,
                                      350, PIXEL_COLORS['warning'], PIXEL_COLORS['bg_secondary'])

            # REC/STOP button (top-right). Note: R hotkey disabled on name screen to avoid interfering with typing
            rec_rect = self._draw_rec_button()

            
            for event in pygame.event.get():
                if event.type == QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == MOUSEBUTTONDOWN:
                    if rec_rect and rec_rect.collidepoint(event.pos):
                        try:
                            self._toggle_capture()
                        except Exception:
                            pass
                        continue
                if event.type == KEYDOWN:
                    if event.key == pygame.K_F9:
                        self._start_autogif()
                        continue
                    # Only F12 toggles on the name screen; R is used for typing
                    if event.key == pygame.K_F12:
                        try:
                            self._toggle_capture()
                        except Exception:
                            pass
                        continue
                    if event.key == K_RETURN and input_text.strip() != "":
                        # key enter sound
                        try:
                            if 'UI_KEY_ENTER_SOUND' in globals() and UI_KEY_ENTER_SOUND:
                                UI_KEY_ENTER_SOUND.play()
                        except Exception:
                            pass
                        self.username = input_text.strip()
                        # stop text input before leaving this screen
                        try:
                            pygame.key.stop_text_input()
                        except Exception:
                            pass
                        # navigation sound
                        try:
                            if 'UI_NAV_SOUND' in globals() and UI_NAV_SOUND:
                                UI_NAV_SOUND.play()
                        except Exception:
                            pass
                        # Prepare to enter instructions screen
                        self.instructions_enter_time = 0.0  # ensure animation restarts cleanly
                        self.game_state = "instructions"  # enter instructions screen
                    elif event.key == K_BACKSPACE:
                        input_text = input_text[:-1]
                        try:
                            if 'UI_KEY_BACKSPACE_SOUND' in globals() and UI_KEY_BACKSPACE_SOUND:
                                UI_KEY_BACKSPACE_SOUND.play()
                        except Exception:
                            pass
                    # NOTE: Character input is now handled exclusively by TEXTINPUT to avoid duplicates.
                if event.type == TEXTINPUT:
                    # This event is preferred for text input as it handles IME and avoids duplicate characters.
                    input_text += event.text
                    # play key tap with small cooldown
                    try:
                        now_t = time.time()
                        if now_t - self.last_key_sound_time >= 0.04:
                            if 'UI_KEY_TAP_SOUND' in globals() and UI_KEY_TAP_SOUND:
                                UI_KEY_TAP_SOUND.play()
                            self.last_key_sound_time = now_t
                    except Exception:
                        pass

            # handle cursor blink
            if time.time() - cursor_timer > 0.5:
                cursor_visible = not cursor_visible
                cursor_timer = time.time()
            
            # autogif driver
            try:
                self._tick_autogif('input_name')
            except Exception:
                pass
            pygame.display.update()
            # capture after draw
            try:
                self._maybe_capture_frame()
            except Exception:
                pass

    def show_instructions(self):
        """Show game instructions"""
        while self.game_state == "instructions":
            # Pixel-style background
            SCREEN.fill(PIXEL_COLORS['bg_primary'])
            
            # Draw decorative grid
            grid_size = 40
            for x in range(0, SCREEN_WIDTH, grid_size):
                pygame.draw.line(SCREEN, PIXEL_COLORS['bg_secondary'], 
                               (x, 0), (x, SCREEN_HEIGHT), 1)
            for y in range(0, SCREEN_HEIGHT, grid_size):
                pygame.draw.line(SCREEN, PIXEL_COLORS['bg_secondary'], 
                               (0, y), (SCREEN_WIDTH, y), 1)
            
            # Pixel-style title
            title_text = "INSTRUCTIONS"
            draw_pixel_text_with_shadow(SCREEN, title_text, large_font,
                                      SCREEN_WIDTH//2 - large_font.size(title_text)[0]//2,
                                      30, PIXEL_COLORS['text_accent'], PIXEL_COLORS['bg_secondary'])
            lines = [
                "Click on blocks where the color matches the text on them.",
                "The faster, the better!"
            ]
            
            # Centered, tighter instruction panel to reduce whitespace
            text_area = pygame.Rect(60, 150, SCREEN_WIDTH - 120, 240)
            pygame.draw.rect(SCREEN, PIXEL_COLORS['bg_secondary'], text_area)
            # Use accent-colored border
            draw_pixel_border(SCREEN, text_area, PIXEL_COLORS['accent'], 2)

            try:
                # Animation params (fade-in + slide-down + scale) with accent glow
                now = time.time()
                if getattr(self, "instructions_enter_time", 0.0) == 0.0:
                    self.instructions_enter_time = now
                elapsed = now - self.instructions_enter_time
                dur = getattr(self, "instructions_anim_duration", 0.6)
                p = 0.0 if dur <= 0 else max(0.0, min(1.0, elapsed / dur))
                ease = 1.0 - (1.0 - p) ** 3  # ease-out cubic
                slide_offset = int((1.0 - ease) * 14)
                text_alpha = int(255 * ease)
                scale = 0.92 + 0.08 * ease

                import math
                glow_alpha = max(0, min(120, int(60 + 50 * math.sin(2 * math.pi * 0.8 * now))))
                overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
                glow_rect = text_area.inflate(18, 14)
                pygame.draw.rect(overlay, (*PIXEL_COLORS['accent'], int(glow_alpha * 0.8)), glow_rect, 6)
                pygame.draw.rect(overlay, (*PIXEL_COLORS['accent'], int(glow_alpha * 0.45)), glow_rect.inflate(8, 6), 8)
                SCREEN.blit(overlay, (0, 0))

                headline_font = _load_pixel_font(px(48))
                text_margin = 30
                text_width = text_area.width - text_margin * 2
                wrapped_lines = []
                for ln in lines:
                    wrapped_lines.extend(wrap_text(ln, headline_font, text_width))

                line_spacing = 10
                rendered_lines = []
                for sub in wrapped_lines:
                    base_surf = headline_font.render(sub, False, PIXEL_COLORS['text_primary'])
                    base_shadow = headline_font.render(sub, False, PIXEL_COLORS['accent'])
                    w, h = base_surf.get_width(), base_surf.get_height()
                    sw = max(1, int(w * scale))
                    sh = max(1, int(h * scale))
                    if sw <= 0 or sh <= 0:
                        continue
                    # Use nearest-neighbor scaling to preserve crisp pixel edges
                    surf = pygame.transform.scale(base_surf, (sw, sh))
                    shadow = pygame.transform.scale(base_shadow, (sw, sh))
                    surf.set_alpha(text_alpha)
                    shadow.set_alpha(text_alpha)
                    rendered_lines.append((sub, surf, shadow, sw, sh))

                total_height = sum(h for (_, _, _, _, h) in rendered_lines) + (len(rendered_lines) - 1) * line_spacing
                y = text_area.y + (text_area.height - total_height) // 2 + slide_offset

                for (_, surf, shadow, sw, sh) in rendered_lines:
                    x = text_area.x + (text_area.width - sw) // 2
                    SCREEN.blit(shadow, (x + 2, y + 2))
                    SCREEN.blit(surf, (x, y))
                    y += sh + line_spacing
            except Exception as e:
                # Fallback to static rendering on error to avoid crash
                try:
                    import traceback
                    print(f"[Instructions] render error: {e}")
                    traceback.print_exc()
                except Exception:
                    pass
                fallback_font = _load_pixel_font(px(44))
                text_margin = 30
                text_width = text_area.width - text_margin * 2
                wrapped = []
                for ln in lines:
                    wrapped.extend(wrap_text(ln, fallback_font, text_width))
                line_spacing = 10
                total_height = len(wrapped) * fallback_font.get_linesize() + (len(wrapped) - 1) * line_spacing
                y = text_area.y + (text_area.height - total_height) // 2
                for sub in wrapped:
                    surf = fallback_font.render(sub, False, PIXEL_COLORS['text_primary'])
                    x = text_area.x + (text_area.width - surf.get_width()) // 2
                    SCREEN.blit(surf, (x, y))
                    y += fallback_font.get_linesize() + line_spacing
            
            # Start hint (or show countdown/GO)
            if self.countdown_active:
                # during countdown, show big number or GO
                if self.countdown_current > 0:
                    cd_text = str(self.countdown_current)
                else:
                    cd_text = "GO!"
                cd_font = _load_pixel_font(px(84))
                draw_pixel_text_with_shadow(SCREEN, cd_text, cd_font,
                                            SCREEN_WIDTH//2 - cd_font.size(cd_text)[0]//2,
                                            SCREEN_HEIGHT - 140, PIXEL_COLORS['accent'], PIXEL_COLORS['bg_secondary'])
            else:
                start_text = "PRESS ANY KEY TO START"
                draw_pixel_text_with_shadow(SCREEN, start_text, font,
                                          SCREEN_WIDTH//2 - font.size(start_text)[0]//2,
                                          SCREEN_HEIGHT - 80, PIXEL_COLORS['success'], PIXEL_COLORS['bg_secondary'])
            
            # REC/STOP button (top-right)
            rec_rect = self._draw_rec_button()
            
            for event in pygame.event.get():
                if event.type == QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == KEYDOWN:
                    if event.key == pygame.K_F9:
                        self._start_autogif()
                        continue
                    if event.key == pygame.K_F12 or event.key == pygame.K_r:
                        try:
                            self._toggle_capture()
                        except Exception:
                            pass
                        # do not trigger countdown on F12/R
                        continue
                    # start countdown on first key press (except F12/R)
                    if not self.countdown_active:
                        self.countdown_active = True
                        self.countdown_start = time.time()
                        self.countdown_current = 3
                        # play initial '3' beep immediately so it's audible
                        try:
                            if 'COUNTDOWN_BEEP_SOUND' in globals() and COUNTDOWN_BEEP_SOUND:
                                COUNTDOWN_BEEP_SOUND.play()
                            elif 'UI_NAV_SOUND' in globals() and UI_NAV_SOUND:
                                UI_NAV_SOUND.play()
                        except Exception:
                            pass
                    else:
                        # if already active, ignore further keys
                        pass
                elif event.type == MOUSEBUTTONDOWN:
                    if rec_rect and rec_rect.collidepoint(event.pos):
                        try:
                            self._toggle_capture()
                        except Exception:
                            pass
                        continue
                    # start countdown on mouse click (except when clicking the REC button)
                    if not self.countdown_active:
                        self.countdown_active = True
                        self.countdown_start = time.time()
                        self.countdown_current = 3
                        # play initial '3' beep immediately so it's audible
                        try:
                            if 'COUNTDOWN_BEEP_SOUND' in globals() and COUNTDOWN_BEEP_SOUND:
                                COUNTDOWN_BEEP_SOUND.play()
                            elif 'UI_NAV_SOUND' in globals() and UI_NAV_SOUND:
                                UI_NAV_SOUND.play()
                        except Exception:
                            pass
                    else:
                        # if already active, ignore further keys
                        pass
                # handle countdown progression outside event loop
            # countdown handling
            if self.countdown_active:
                now = time.time()
                elapsed = now - self.countdown_start
                # each number lasts about 1 second; 'GO' triggers after 3 seconds
                new_idx = 3 - int(elapsed)
                if new_idx < 0:
                    # GO moment
                    # play start sound (or nav fallback)
                    try:
                        if 'START_SOUND' in globals() and START_SOUND:
                            START_SOUND.play()
                        elif 'UI_NAV_SOUND' in globals() and UI_NAV_SOUND:
                            UI_NAV_SOUND.play()
                    except Exception:
                        pass
                    # begin playing after short moment so player sees GO
                    self.next_state_time = now + 0.6
                    self.block_visible = False
                    self.current_block = None
                    self.countdown_active = False
                    self.instructions_enter_time = 0.0
                    self.game_state = "playing"
                else:
                    # update display number for animation (we use countdown_current for rendering)
                    if new_idx != self.countdown_current:
                        self.countdown_current = new_idx
                        # play countdown beep on 3,2,1
                        if self.countdown_current > 0:
                            try:
                                if 'COUNTDOWN_BEEP_SOUND' in globals() and COUNTDOWN_BEEP_SOUND:
                                    COUNTDOWN_BEEP_SOUND.play()
                                elif 'UI_NAV_SOUND' in globals() and UI_NAV_SOUND:
                                    UI_NAV_SOUND.play()
                            except Exception:
                                pass
            
            # autogif driver
            try:
                self._tick_autogif('instructions')
            except Exception:
                pass
            pygame.display.update()
            # capture after draw
            try:
                self._maybe_capture_frame()
            except Exception:
                pass

    def next_block(self):
        """Generate the next block"""
        # schedule next block: when called, create and show a block immediately
        self.block_count += 1
        if self.block_count > TOTAL_BLOCKS:
            self.current_block = None
            self.block_visible = False
            
            # Add to rankings (only if player not already in rankings)
            player_exists = any(rank["name"] == self.username for rank in rankings)
            if not player_exists:
                rankings.append({
                    "name": self.username,
                    "score": self.score,                                                                                                                                                                                                                                                                                                                                                                                                                                                
                    "avg_rt": sum(self.reaction_times)/len(self.reaction_times) if self.reaction_times else None
                })
                # Sort by score descending; tie-breaker is lower average reaction time
                rankings.sort(key=lambda x: (-x["score"], x["avg_rt"] if x["avg_rt"] is not None else float('inf')))
            
            # Game over sound on moving to results (fallback to nav)
            try:
                if 'GAMEOVER_SOUND' in globals() and GAMEOVER_SOUND:
                    GAMEOVER_SOUND.play()
                elif 'UI_NAV_SOUND' in globals() and UI_NAV_SOUND:
                    UI_NAV_SOUND.play()
            except Exception:
                pass
            self.game_state = "results"  # all blocks shown, go to results screen
            return
    # Use predefined sequence to create the block
        is_disturb = self.block_sequence[self.block_count - 1]
        self.current_block = Block(is_disturb=is_disturb)
        self.block_start_time = time.time()  # when this block appeared
        self.block_visible = True
        # set next transition to after BLOCK_DURATION (then interval will start)
        self.next_state_time = self.block_start_time + BLOCK_DURATION

    def handle_playing(self):
        """Handle game logic while playing"""
        current_time = time.time()
        # dt for animations/particles
        try:
            last_t = self._last_play_dt_time if self._last_play_dt_time else current_time
            dt = max(0.0, min(0.05, current_time - last_t))
            self._last_play_dt_time = current_time
        except Exception:
            dt = 0.016

        # Update animations for disappearing blocks
        self.animating_blocks = [block for block in self.animating_blocks 
                               if not block.update_animation()]

        # if currently a block is visible and it's time to end its visible period
        if self.block_visible and current_time >= self.next_state_time:
            # block visible period ended -> enter interval period
            self.block_visible = False
            # if it wasn't clicked during visible time, reset streak (no score)
            if self.current_block and not self.current_block.is_clicked:
                # Only reset streak if a valid (matching) block was missed; ignoring distractors doesn't break streak
                if self.current_block.color == self.current_block.text_color:
                    self.streak = 0
                    # Show "MISS!" and play miss sound for correct blocks that weren't clicked
                    self.reaction_time_text = "MISS!"
                    self.reaction_time_display_time = current_time
                    self.last_reaction_time_id += 1  # 防止重复显示
                    # Play miss sound
                    if MISS_SOUND:
                        try:
                            MISS_SOUND.play()
                        except Exception as e:
                            print(f"Error playing miss sound: {e}")
                    # Start disappear animation for the missed block so MISS! can be positioned correctly
                    self.current_block.start_disappear_animation()
                    self.animating_blocks.append(self.current_block)
            # hide the block
            self.current_block = None
            # schedule next action
            if self.block_count == TOTAL_BLOCKS:
                # if that was the last block, wait 1 second then show results
                self.next_state_time = current_time + 1.0
            else:
                # otherwise, wait for the normal interval
                self.next_state_time = current_time + BLOCK_INTERVAL
            return

        # if currently in interval (no block visible) and it's time to spawn next
        if (not self.block_visible) and self.current_block is None and current_time >= self.next_state_time:
            if self.block_count < TOTAL_BLOCKS:
                self.next_block()
            else:
                # all blocks have been processed, and the final interval is over
                # Add to rankings (only if player not already in rankings)
                player_exists = any(rank["name"] == self.username for rank in rankings)
                if not player_exists:
                    rankings.append({
                        "name": self.username,
                        "score": self.score,
                        "avg_rt": sum(self.reaction_times)/len(self.reaction_times) if self.reaction_times else None
                    })
                    # Sort by score descending; tie-breaker is lower average reaction time
                    rankings.sort(key=lambda x: (-x["score"], x["avg_rt"] if x["avg_rt"] is not None else float('inf')))
                
                try:
                    if 'GAMEOVER_SOUND' in globals() and GAMEOVER_SOUND:
                        GAMEOVER_SOUND.play()
                    elif 'UI_NAV_SOUND' in globals() and UI_NAV_SOUND:
                        UI_NAV_SOUND.play()
                except Exception:
                    pass
                self.game_state = "results"
            return
        
    # draw UI
    # Pixel-style background
        SCREEN.fill(PIXEL_COLORS['bg_primary'])
        
    # Draw background grid
        draw_pixel_grid(SCREEN, 20, PIXEL_COLORS['bg_secondary'])
        
    # Pixel-style score display
        score_bg = pygame.Rect(UI_MARGIN_X - 5, 5, 180, 40)
        pygame.draw.rect(SCREEN, PIXEL_COLORS['bg_secondary'], score_bg)
        draw_pixel_border(SCREEN, score_bg, PIXEL_COLORS['frame'], 2)
        draw_pixel_text_with_shadow(SCREEN, f"SCORE: {self.score}", font, UI_MARGIN_X + 5, 18, 
                                  PIXEL_COLORS['text_primary'], PIXEL_COLORS['bg_secondary'])
        
    # Pixel-style progress display
        progress_text = f"PROGRESS: {self.block_count}/{TOTAL_BLOCKS}"
        progress_width = font.size(progress_text)[0] + 20
        progress_bg = pygame.Rect(SCREEN_WIDTH - UI_MARGIN_X - progress_width + 5, 5, progress_width, 40)
        pygame.draw.rect(SCREEN, PIXEL_COLORS['bg_secondary'], progress_bg)
        draw_pixel_border(SCREEN, progress_bg, PIXEL_COLORS['frame'], 2)
        draw_pixel_text_with_shadow(SCREEN, progress_text, font, 
                                  SCREEN_WIDTH - UI_MARGIN_X - progress_width + 15, 18,
                                  PIXEL_COLORS['text_primary'], PIXEL_COLORS['bg_secondary'])

    # During combos, briefly show "COMBO! +2" in the center; no combo shown on a single hit
        if self.combo_last_streak >= 2 and current_time < self.combo_visible_until:
            combo_text = "COMBO! +2"
            cx = SCREEN_WIDTH // 2 - large_font.size(combo_text)[0] // 2
            cy = SCREEN_HEIGHT // 2 - large_font.get_linesize() // 2
            draw_pixel_text_with_shadow(
                SCREEN, combo_text, large_font,
                cx, cy,
                PIXEL_COLORS['accent'], PIXEL_COLORS['bg_secondary']
            )

    # Pixel-style feedback text (draw above play area)
        if self.feedback_text and (current_time - self.feedback_time) < self.feedback_duration:
            # 根据反馈类型选择颜色
            if "+" in self.feedback_text:
                feedback_color = PIXEL_COLORS['success']
            elif "-" in self.feedback_text:
                feedback_color = PIXEL_COLORS['error']
            else:
                feedback_color = PIXEL_COLORS['text_primary']
            
            # 绘制反馈背景（位置在游戏框上方）
            feedback_width = font.size(self.feedback_text)[0] + 20
            feedback_y = PLAY_AREA.top - 50  # 50px above the play area
            feedback_bg = pygame.Rect(SCREEN_WIDTH//2 - feedback_width//2, feedback_y, feedback_width, 35)
            pygame.draw.rect(SCREEN, PIXEL_COLORS['bg_secondary'], feedback_bg)
            draw_pixel_border(SCREEN, feedback_bg, feedback_color, 2)
            
            draw_pixel_text_with_shadow(SCREEN, self.feedback_text, font, 
                                      SCREEN_WIDTH//2 - font.size(self.feedback_text)[0]//2, feedback_y + 8,
                                      feedback_color, PIXEL_COLORS['bg_secondary'])

        # Show reaction time (near the block position)
        if self.reaction_time_text and (current_time - self.reaction_time_display_time) < self.reaction_time_duration:
            # Find the most recent clicked block position; if a block is disappearing, show there
            display_x, display_y = SCREEN_WIDTH//2, SCREEN_HEIGHT//2  # default position
            
            if self.animating_blocks:
                # Use the last animating block's position
                last_block = self.animating_blocks[-1]
                display_x = last_block.x + BLOCK_WIDTH//2
                display_y = last_block.y - 30  # 30px above the block
                
                # Ensure the reaction time stays within the play area and doesn't jump to center
                display_x = max(PLAY_AREA.left + 50, min(PLAY_AREA.right - 50, display_x))
                display_y = max(PLAY_AREA.top + 20, min(PLAY_AREA.bottom - 20, display_y))
            else:
                # If there is no animating block, don't show reaction time (avoid center display)
                self.reaction_time_text = None
                return
            
            # Draw reaction time text (no border)
            rt_width = small_font.size(self.reaction_time_text)[0]
            draw_pixel_text_with_shadow(SCREEN, self.reaction_time_text, small_font,
                                      display_x - rt_width//2, display_y,
                                      PIXEL_COLORS['text_accent'], PIXEL_COLORS['bg_primary'])

        # draw black game frame (play area)
        pygame.draw.rect(SCREEN, (0, 0, 0), PLAY_AREA, width=4)
        
        # draw current block (only when visible)
        if self.block_visible and self.current_block:
            self.current_block.draw(SCREEN)
        
        # draw animating (disappearing) blocks
        for block in self.animating_blocks:
            block.draw(SCREEN)

        # update and draw perfect particles
        if self.perfect_particles:
            alive = []
            for p in self.perfect_particles:
                p['age'] += dt
                if p['age'] <= p['life']:
                    p['x'] += p['vx'] * dt
                    p['y'] += p['vy'] * dt
                    # gravity-like drift
                    p['vy'] += 40.0 * dt
                    alive.append(p)
                    # fade by age
                    alpha = max(0, min(255, int(255 * (1.0 - p['age']/p['life']))))
                    col = (*p['color'], alpha)
                    s = 2 if p.get('size', 2) <= 2 else 3
                    surf = pygame.Surface((s, s), pygame.SRCALPHA)
                    surf.fill(col)
                    SCREEN.blit(surf, (int(p['x']), int(p['y'])))
            self.perfect_particles = alive
        
        # event handling
        # Draw REC/STOP button
        rec_rect = self._draw_rec_button()
        for event in pygame.event.get():
            if event.type == QUIT:
                pygame.quit()
                sys.exit()
            if event.type == KEYDOWN and (event.key == pygame.K_F12 or event.key == pygame.K_r):
                try:
                    self._toggle_capture()
                except Exception:
                    pass
                continue
            if event.type == KEYDOWN and event.key == pygame.K_F9:
                self._start_autogif()
                continue
            if event.type == MOUSEBUTTONDOWN:
                if rec_rect and rec_rect.collidepoint(event.pos):
                    try:
                        self._toggle_capture()
                    except Exception:
                        pass
                    continue
            if event.type == KEYDOWN and self.block_visible and not self.current_block.is_clicked:
                self.current_block.is_clicked = True
                reaction_time = current_time - self.block_start_time
                self.reaction_times.append(reaction_time)  # record reaction time
                
                # Set reaction time display with unique ID
                self.last_reaction_time_id += 1
                self.reaction_time_text = f"{reaction_time:.3f}s"
                self.reaction_time_display_time = current_time

                # determine pressed key correctness
                pressed_key = pygame.key.name(event.key).lower()
                is_correct_key = (pressed_key == self.current_block.correct_key)
                is_valid_block = (self.current_block.color == self.current_block.text_color)

                # scoring and effects
                if is_valid_block and is_correct_key:
                    # correct block and correct key: add points with cap at +2
                    self.streak += 1
                    add_points = 1 if self.streak <= 1 else 2
                    self.score += add_points
                    self.feedback_color = (0, 160, 0)
                    self.feedback_time = current_time

                    # Grade thresholds: Perfect / Good / Slow
                    grade = 'Good'
                    if reaction_time < 0.28:
                        grade = 'Perfect'
                        # extra bonus for Perfect
                        self.score += 1
                    elif reaction_time < 0.45:
                        grade = 'Good'
                    elif reaction_time < 0.6:
                        grade = 'Slow'
                    else:
                        grade = 'Slow'

                    # 根据实际得分设置反馈文本：基础(1或2) + Perfect 额外+1
                    gained_points = add_points + (1 if grade == 'Perfect' else 0)
                    if grade == 'Perfect':
                        self.feedback_text = f"+{gained_points} PERFECT!"
                    else:
                        self.feedback_text = f"+{gained_points}"

                    # Play grade-appropriate sound
                    try:
                        if grade == 'Perfect' and 'SUCCESS_SOUND' in globals() and SUCCESS_SOUND:
                            ch = SUCCESS_SOUND.play()
                            # 同时轻声播放 combo 音色以增强手感
                            if 'COMBO_SOUND' in globals() and COMBO_SOUND:
                                ch2 = COMBO_SOUND.play()
                                try:
                                    if ch2:
                                        ch2.set_volume(0.6 * float(self.settings.get('sfx_volume', 1.0)))
                                except Exception:
                                    pass
                        elif grade == 'Good' and 'COMBO_SOUND' in globals() and COMBO_SOUND:
                            COMBO_SOUND.play()
                        elif 'UI_KEY_TAP_SOUND' in globals() and UI_KEY_TAP_SOUND:
                            UI_KEY_TAP_SOUND.play()
                    except Exception:
                        pass
                    # Perfect particle effect
                    if grade == 'Perfect':
                        try:
                            cx = self.current_block.x + BLOCK_WIDTH//2
                            cy = self.current_block.y + BLOCK_HEIGHT//2
                            self.spawn_perfect_particles(cx, cy, PIXEL_COLORS['accent'])
                        except Exception:
                            pass

                    # Update combo indicator and max combo
                    self.max_combo = max(self.max_combo, self.streak)
                    if self.streak >= 2:
                        self.combo_last_streak = self.streak
                        self.combo_visible_until = current_time + 1.5
                else:
                    # wrong (distractor or wrong key): deduct 1 point and reset streak
                    self.score -= 1
                    self.streak = 0
                    self.feedback_text = "-1"
                    self.feedback_color = (180, 0, 0)
                    self.feedback_time = current_time
                    # Play error sound
                    if ERROR_SOUND:
                        ERROR_SOUND.play()

                # Start disappear animation and move to animating blocks
                self.current_block.start_disappear_animation()
                self.animating_blocks.append(self.current_block)
                
                # after a valid key press, hide block and enter interval
                self.current_block = None
                self.block_visible = False
                if self.block_count == TOTAL_BLOCKS:
                    self.next_state_time = current_time + 1.0
                else:
                    self.next_state_time = current_time + BLOCK_INTERVAL
                # save progress to persistence occasionally (after each click)
                try:
                    self.save_persistence()
                except Exception:
                    pass
            if event.type == MOUSEBUTTONDOWN and self.block_visible and not self.current_block.is_clicked:
                mx, my = event.pos
                bx, by = self.current_block.x, self.current_block.y
                if bx <= mx <= bx + BLOCK_WIDTH and by <= my <= by + BLOCK_HEIGHT:
                    # treat as a click on the block
                    self.current_block.is_clicked = True
                    reaction_time = current_time - self.block_start_time
                    self.reaction_times.append(reaction_time)
                    
                    # Set reaction time display with unique ID
                    self.last_reaction_time_id += 1
                    self.reaction_time_text = f"{reaction_time:.3f}s"
                    self.reaction_time_display_time = current_time

                    # clicked: determine correctness
                    # mouse click doesn't tell which key, so correctness is whether text matches color
                    is_valid_block = (self.current_block.color == self.current_block.text_color)
                    if is_valid_block:
                        # Correct click on a valid block
                        self.streak += 1
                        add_points = 1 if self.streak <= 1 else 2
                        self.score += add_points
                        self.feedback_color = (0, 160, 0)
                        self.feedback_time = current_time

                        # Grade by reaction time (align with keyboard path)
                        grade = 'Good'
                        if reaction_time < 0.28:
                            grade = 'Perfect'
                            self.score += 1  # extra bonus for Perfect
                        elif reaction_time < 0.45:
                            grade = 'Good'
                        elif reaction_time < 0.6:
                            grade = 'Slow'
                        else:
                            grade = 'Slow'

                        # 根据实际得分设置反馈文本（鼠标路径）
                        gained_points = add_points + (1 if grade == 'Perfect' else 0)
                        if grade == 'Perfect':
                            self.feedback_text = f"+{gained_points} PERFECT!"
                        else:
                            self.feedback_text = f"+{gained_points}"

                        # Play grade-appropriate sound (mirror keyboard behavior)
                        try:
                            if grade == 'Perfect' and 'SUCCESS_SOUND' in globals() and SUCCESS_SOUND:
                                ch = SUCCESS_SOUND.play()
                                if 'COMBO_SOUND' in globals() and COMBO_SOUND:
                                    ch2 = COMBO_SOUND.play()
                                    try:
                                        if ch2:
                                            ch2.set_volume(0.6 * float(self.settings.get('sfx_volume', 1.0)))
                                    except Exception:
                                        pass
                            elif grade == 'Good' and 'COMBO_SOUND' in globals() and COMBO_SOUND:
                                COMBO_SOUND.play()
                            elif 'UI_KEY_TAP_SOUND' in globals() and UI_KEY_TAP_SOUND:
                                UI_KEY_TAP_SOUND.play()
                        except Exception:
                            pass
                        # Perfect particle effect (mouse path)
                        if grade == 'Perfect':
                            try:
                                cx = self.current_block.x + BLOCK_WIDTH//2
                                cy = self.current_block.y + BLOCK_HEIGHT//2
                                self.spawn_perfect_particles(cx, cy, PIXEL_COLORS['accent'])
                            except Exception:
                                pass

                        # Update combo indicator and max combo (mouse path)
                        self.max_combo = max(self.max_combo, self.streak)
                        if self.streak >= 2:
                            self.combo_last_streak = self.streak
                            self.combo_visible_until = current_time + 1.5
                    else:
                        self.score -= 1
                        self.streak = 0
                        self.feedback_text = "-1"
                        self.feedback_color = (180, 0, 0)
                        self.feedback_time = current_time
                        # Play error sound
                        if ERROR_SOUND:
                            ERROR_SOUND.play()

                    # Start disappear animation and move to animating blocks
                    self.current_block.start_disappear_animation()
                    self.animating_blocks.append(self.current_block)

                    # hide block and enter interval
                    self.current_block = None
                    self.block_visible = False
                    if self.block_count == TOTAL_BLOCKS:
                        self.next_state_time = current_time + 1.0
                    else:
                        self.next_state_time = current_time + BLOCK_INTERVAL
        
        # autogif driver
        try:
            self._tick_autogif('playing')
        except Exception:
            pass
        pygame.display.update()
        # capture after draw
        try:
            self._maybe_capture_frame()
        except Exception:
            pass

    def show_results(self):
        """Show game results and statistics"""
        while self.game_state == "results":
            # Pixel-style background
            SCREEN.fill(PIXEL_COLORS['bg_primary'])
            draw_pixel_grid(SCREEN, 25, PIXEL_COLORS['bg_secondary'])
            
            # Pixel-style title
            draw_pixel_text_with_shadow(SCREEN, "GAME OVER", large_font,
                                      SCREEN_WIDTH//2 - large_font.size("GAME OVER")[0]//2,
                                      60, PIXEL_COLORS['error'], PIXEL_COLORS['bg_primary'])
            
            # Results panel
            panel_rect = pygame.Rect(50, 130, SCREEN_WIDTH - 100, 300)
            pygame.draw.rect(SCREEN, PIXEL_COLORS['bg_secondary'], panel_rect)
            draw_pixel_border(SCREEN, panel_rect, PIXEL_COLORS['frame'], 3)
            
            # Player info
            draw_pixel_text_with_shadow(SCREEN, f"PLAYER: {self.username}", font,
                                      SCREEN_WIDTH//2 - font.size(f"PLAYER: {self.username}")[0]//2,
                                      160, PIXEL_COLORS['text_primary'], PIXEL_COLORS['bg_secondary'])
            
            # Score display
            score_color = PIXEL_COLORS['success'] if self.score >= 0 else PIXEL_COLORS['error']
            draw_pixel_text_with_shadow(SCREEN, f"TOTAL SCORE: {self.score}", font,
                                      SCREEN_WIDTH//2 - font.size(f"TOTAL SCORE: {self.score}")[0]//2,
                                      200, score_color, PIXEL_COLORS['bg_secondary'])

            # Max combo display
            max_combo_text = f"MAX COMBO: x{self.max_combo}"
            draw_pixel_text_with_shadow(SCREEN, max_combo_text, font,
                                      SCREEN_WIDTH//2 - font.size(max_combo_text)[0]//2,
                                      230, PIXEL_COLORS['text_primary'], PIXEL_COLORS['bg_secondary'])
            
            # reaction time statistics (only if there are valid clicks)
            rt_texts = []
            if self.reaction_times:
                avg_rt = sum(self.reaction_times) / len(self.reaction_times)
                min_rt = min(self.reaction_times)
                max_rt = max(self.reaction_times)
                rt_texts = [
                    f"Average reaction time: {avg_rt:.3f}s",
                    f"Fastest reaction time: {min_rt:.3f}s",
                    f"Slowest reaction time: {max_rt:.3f}s"
                ]
            else:
                rt_texts = ["NO VALID CLICKS RECORDED"]
            
            # Reaction time stats display
            y_offset = 250
            for i, rt_line in enumerate(rt_texts):
                draw_pixel_text_with_shadow(SCREEN, rt_line, small_font,
                                          SCREEN_WIDTH//2 - small_font.size(rt_line)[0]//2,
                                          y_offset + i*30, PIXEL_COLORS['text_secondary'], PIXEL_COLORS['bg_secondary'])
            
            # Brain age result
            brain_age, brain_age_text = self.calculate_brain_age()
            
            # Brain age panel
            brain_panel_rect = pygame.Rect(50, 380, SCREEN_WIDTH - 100, 120)
            pygame.draw.rect(SCREEN, PIXEL_COLORS['bg_secondary'], brain_panel_rect)
            draw_pixel_border(SCREEN, brain_panel_rect, PIXEL_COLORS['warning'], 3)
            
            # Brain age title
            brain_title = f"BRAIN AGE: {brain_age} YEARS OLD"
            draw_pixel_text_with_shadow(SCREEN, brain_title, font,
                                      SCREEN_WIDTH//2 - font.size(brain_title)[0]//2,
                                      395, PIXEL_COLORS['warning'], PIXEL_COLORS['bg_secondary'])
            
            # Brain age description (auto wrap)
            brain_text_lines = wrap_text(brain_age_text, small_font, SCREEN_WIDTH - 120)
            brain_y = 425
            for line in brain_text_lines[:3]:  # show at most 3 lines
                draw_pixel_text_with_shadow(SCREEN, line, small_font,
                                          SCREEN_WIDTH//2 - small_font.size(line)[0]//2,
                                          brain_y, PIXEL_COLORS['text_primary'], PIXEL_COLORS['bg_secondary'])
                brain_y += 20
            
            # Continue hint (moved lower)
            hint_text = "PRESS ANY KEY TO VIEW RANKINGS"
            draw_pixel_text_with_shadow(SCREEN, hint_text, font,
                                      SCREEN_WIDTH//2 - font.size(hint_text)[0]//2,
                                      520, PIXEL_COLORS['success'], PIXEL_COLORS['bg_primary'])
            
            # REC/STOP button (top-right)
            rec_rect = self._draw_rec_button()

            for event in pygame.event.get():
                if event.type == QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == KEYDOWN:
                    if event.key == pygame.K_F9:
                        self._start_autogif()
                        continue
                    if event.key == pygame.K_F12 or event.key == pygame.K_r:
                        try:
                            self._toggle_capture()
                        except Exception:
                            pass
                        continue
                if event.type == MOUSEBUTTONDOWN:
                    if rec_rect and rec_rect.collidepoint(event.pos):
                        try:
                            self._toggle_capture()
                        except Exception:
                            pass
                        continue
                    try:
                        if 'UI_NAV_SOUND' in globals() and UI_NAV_SOUND:
                            UI_NAV_SOUND.play()
                    except Exception:
                        pass
                    self.game_state = "rankings"
            
            # autogif driver
            try:
                self._tick_autogif('results')
            except Exception:
                pass
            pygame.display.update()
            # capture after draw
            try:
                self._maybe_capture_frame()
            except Exception:
                pass

    def show_rankings(self):
        """Show rankings"""
        while self.game_state == "rankings":
            # Pixel-style background
            SCREEN.fill(PIXEL_COLORS['bg_primary'])
            draw_pixel_grid(SCREEN, 30, PIXEL_COLORS['bg_secondary'])
            
            # Pixel-style title
            draw_pixel_text_with_shadow(SCREEN, "RANKINGS", large_font,
                                      SCREEN_WIDTH//2 - large_font.size("RANKINGS")[0]//2,
                                      30, PIXEL_COLORS['text_primary'], PIXEL_COLORS['bg_primary'])
            
            # Rankings panel
            panel_rect = pygame.Rect(30, 80, SCREEN_WIDTH - 60, 380)
            pygame.draw.rect(SCREEN, PIXEL_COLORS['bg_secondary'], panel_rect)
            draw_pixel_border(SCREEN, panel_rect, PIXEL_COLORS['frame'], 3)
            
            # Show top 10
            for i in range(min(10, len(rankings))):
                rank = i + 1
                user = rankings[i]
                # Highlight current player
                color = PIXEL_COLORS['error'] if user["name"] == self.username else PIXEL_COLORS['text_primary']
                rank_text = f"{rank}. {user['name']} - SCORE: {user['score']}"
                
                # Rank background
                if user["name"] == self.username:
                    rank_bg = pygame.Rect(50, 100 + i*35, SCREEN_WIDTH - 100, 30)
                    pygame.draw.rect(SCREEN, PIXEL_COLORS['accent'], rank_bg)
                    draw_pixel_border(SCREEN, rank_bg, PIXEL_COLORS['error'], 2)
                
                draw_pixel_text_with_shadow(SCREEN, rank_text, font,
                                          SCREEN_WIDTH//2 - font.size(rank_text)[0]//2,
                                          105 + i*35, color, PIXEL_COLORS['bg_secondary'])
            
            # Hints (with settings entry)
            hint_text = "ESC: QUIT | ANY KEY: RESTART | S: SETTINGS"
            draw_pixel_text_with_shadow(SCREEN, hint_text, small_font,
                                      SCREEN_WIDTH//2 - small_font.size(hint_text)[0]//2,
                                      480, PIXEL_COLORS['text_secondary'], PIXEL_COLORS['bg_primary'])
            
            # REC/STOP button (top-right)
            rec_rect = self._draw_rec_button()
            
            for event in pygame.event.get():
                if event.type == QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == MOUSEBUTTONDOWN:
                    if rec_rect and rec_rect.collidepoint(event.pos):
                        try:
                            self._toggle_capture()
                        except Exception:
                            pass
                        continue
                if event.type == KEYDOWN:
                    if event.key == pygame.K_F9:
                        self._start_autogif()
                        continue
                    if event.key == pygame.K_F12 or event.key == pygame.K_r:
                        try:
                            self._toggle_capture()
                        except Exception:
                            pass
                        continue
                    if event.key == K_ESCAPE:
                        try:
                            if 'UI_NAV_SOUND' in globals() and UI_NAV_SOUND:
                                UI_NAV_SOUND.play()
                        except Exception:
                            pass
                        pygame.quit()
                        sys.exit()
                    elif event.key == pygame.K_s:
                        # Enter settings page
                        try:
                            if 'UI_NAV_SOUND' in globals() and UI_NAV_SOUND:
                                UI_NAV_SOUND.play()
                        except Exception:
                            pass
                        self.game_state = "settings"
                    else:
                        try:
                            if 'UI_NAV_SOUND' in globals() and UI_NAV_SOUND:
                                UI_NAV_SOUND.play()
                        except Exception:
                            pass
                        # restart the game
                        self.__init__()
                        self.game_state = "input_name"
            
            # autogif driver
            try:
                self._tick_autogif('rankings')
            except Exception:
                pass
            pygame.display.update()
            # capture after draw
            try:
                self._maybe_capture_frame()
            except Exception:
                pass

    def show_settings(self):
        """Settings screen: adjust BGM on/off, BGM volume, SFX volume."""
        selected = 0
        items = ["BGM: ", "BGM VOLUME: ", "SFX VOLUME: ", "BACK"]
        adjusting = False
        while self.game_state == "settings":
            SCREEN.fill(PIXEL_COLORS['bg_primary'])
            draw_pixel_grid(SCREEN, 30, PIXEL_COLORS['bg_secondary'])

            # Title
            draw_pixel_text_with_shadow(SCREEN, "SETTINGS", large_font,
                                        SCREEN_WIDTH//2 - large_font.size("SETTINGS")[0]//2,
                                        30, PIXEL_COLORS['text_accent'], PIXEL_COLORS['bg_primary'])

            panel = pygame.Rect(80, 90, SCREEN_WIDTH - 160, 360)
            pygame.draw.rect(SCREEN, PIXEL_COLORS['bg_secondary'], panel)
            draw_pixel_border(SCREEN, panel, PIXEL_COLORS['frame'], 3)

            # Render items
            opts = {
                'bgm': "ON" if self.settings.get('bgm_enabled', True) else "OFF",
                'bgm_vol': f"{float(self.settings.get('bgm_volume', 0.4)):.1f}",
                'sfx_vol': f"{float(self.settings.get('sfx_volume', 1.0)):.1f}",
            }
            labels = [
                f"BGM: {opts['bgm']}",
                f"BGM VOLUME: {opts['bgm_vol']}",
                f"SFX VOLUME: {opts['sfx_vol']}",
                "BACK"
            ]
            start_y = 140
            gap = 46
            for i, text in enumerate(labels):
                col = PIXEL_COLORS['text_primary'] if i != selected else PIXEL_COLORS['success']
                draw_pixel_text_with_shadow(
                    SCREEN, text, font,
                    SCREEN_WIDTH//2 - font.size(text)[0]//2,
                    start_y + i*gap,
                    col, PIXEL_COLORS['bg_secondary']
                )

            hint = "UP/DOWN: SELECT  LEFT/RIGHT: ADJUST  ENTER: TOGGLE  ESC: BACK"
            draw_pixel_text_with_shadow(
                SCREEN, hint, small_font,
                SCREEN_WIDTH//2 - small_font.size(hint)[0]//2,
                480, PIXEL_COLORS['text_secondary'], PIXEL_COLORS['bg_primary']
            )

            # REC/STOP button (top-right)
            rec_rect = self._draw_rec_button()

            for event in pygame.event.get():
                if event.type == QUIT:
                    pygame.quit(); sys.exit()
                if event.type == MOUSEBUTTONDOWN:
                    if rec_rect and rec_rect.collidepoint(event.pos):
                        try:
                            self._toggle_capture()
                        except Exception:
                            pass
                        continue
                if event.type == KEYDOWN:
                    if event.key == pygame.K_F9:
                        self._start_autogif()
                        continue
                    if event.key == pygame.K_F12 or event.key == pygame.K_r:
                        try:
                            self._toggle_capture()
                        except Exception:
                            pass
                        continue
                    if event.key == K_ESCAPE:
                        try:
                            if 'UI_NAV_SOUND' in globals() and UI_NAV_SOUND: UI_NAV_SOUND.play()
                        except Exception: pass
                        # save and go back
                        try:
                            self.save_persistence()
                        except Exception: pass
                        self.game_state = "rankings"
                    elif event.key in (K_UP, K_w):
                        selected = (selected - 1) % 4
                        try:
                            if 'UI_NAV_SOUND' in globals() and UI_NAV_SOUND: UI_NAV_SOUND.play()
                        except Exception: pass
                    elif event.key in (K_DOWN, K_s):
                        selected = (selected + 1) % 4
                        try:
                            if 'UI_NAV_SOUND' in globals() and UI_NAV_SOUND: UI_NAV_SOUND.play()
                        except Exception: pass
                    elif event.key in (K_LEFT, K_a, K_RIGHT, K_d):
                        # adjust volumes with left/right when on volume rows
                        delta = -0.1 if event.key in (K_LEFT, K_a) else 0.1
                        if selected == 1:  # bgm volume
                            v = float(self.settings.get('bgm_volume', 0.4))
                            v = max(0.0, min(1.0, round(v + delta, 2)))
                            self.settings['bgm_volume'] = v
                            try:
                                self.apply_audio_settings()
                                if 'UI_KEY_TAP_SOUND' in globals() and UI_KEY_TAP_SOUND: UI_KEY_TAP_SOUND.play()
                            except Exception: pass
                        elif selected == 2:  # sfx volume
                            v = float(self.settings.get('sfx_volume', 1.0))
                            v = max(0.0, min(1.0, round(v + delta, 2)))
                            self.settings['sfx_volume'] = v
                            try:
                                self.apply_audio_settings()
                                if 'UI_KEY_TAP_SOUND' in globals() and UI_KEY_TAP_SOUND: UI_KEY_TAP_SOUND.play()
                            except Exception: pass
                    elif event.key in (K_RETURN, K_SPACE):
                        if selected == 0:
                            self.settings['bgm_enabled'] = not bool(self.settings.get('bgm_enabled', True))
                            try:
                                self.apply_audio_settings()
                                if 'UI_KEY_ENTER_SOUND' in globals() and UI_KEY_ENTER_SOUND: UI_KEY_ENTER_SOUND.play()
                            except Exception: pass
                        elif selected == 3:
                            try:
                                if 'UI_NAV_SOUND' in globals() and UI_NAV_SOUND: UI_NAV_SOUND.play()
                            except Exception: pass
                            try:
                                self.save_persistence()
                            except Exception: pass
                            self.game_state = "rankings"

            # autogif driver
            try:
                self._tick_autogif('settings')
            except Exception:
                pass
            pygame.display.update()
            # capture after draw
            try:
                self._maybe_capture_frame()
            except Exception:
                pass

    def run(self):
        """Run the main game loop"""
        while True:
            if self.game_state == "input_name":
                self.get_username()
            elif self.game_state == "instructions":
                self.show_instructions()
            elif self.game_state == "playing":
                self.handle_playing()
            elif self.game_state == "results":
                self.show_results()
            elif self.game_state == "rankings":
                self.show_rankings()
            elif self.game_state == "settings":
                self.show_settings()


if __name__ == "__main__":
    game = Game()
    game.run()