#!/usr/bin/env python3
"""Generates the PACE app icon (PNG set, .ico, .icns). Needs: pip install pillow
Design: dark rounded tile, cyan power-symbol ring, white power bar and an amber
square-wave pulse (= power cycling). Small sizes drop the wave for legibility."""
import math, os, sys
from PIL import Image, ImageDraw, ImageFilter

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
S = 1024  # master canvas

def lerp(a, b, t): return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

def master(with_wave=True):
    # background: vertical navy gradient inside a rounded square
    bg = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        gd.line([(0, y), (S, y)], fill=lerp((22, 34, 58), (9, 14, 28), y / S) + (255,))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([40, 40, S - 40, S - 40], radius=210, fill=255)
    bg.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(bg)
    cx, cy = S // 2, S // 2 - (85 if with_wave else 0)
    R, W = (255 if with_wave else 290), 66
    cyan = (45, 212, 235, 255)

    # glow layer
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gdr = ImageDraw.Draw(glow)
    box = [cx - R, cy - R, cx + R, cy + R]
    gdr.arc(box, start=-60, end=240, fill=(45, 212, 235, 150), width=W + 30)
    glow = glow.filter(ImageFilter.GaussianBlur(28))
    bg = Image.alpha_composite(bg, glow)
    d = ImageDraw.Draw(bg)

    # power ring: gap at the top (-60..240 measured so the gap is centred on 270 deg)
    d.arc(box, start=-60, end=240, fill=cyan, width=W)
    for ang in (-60, 240):  # round caps
        a = math.radians(ang)
        px, py = cx + (R - W / 2) * math.cos(a), cy + (R - W / 2) * math.sin(a)
        d.ellipse([px - W / 2, py - W / 2, px + W / 2, py + W / 2], fill=cyan)

    # power bar
    top, bot = cy - R - 40, cy - 30
    d.rounded_rectangle([cx - W // 2, top, cx + W // 2, bot], radius=W // 2, fill=(255, 255, 255, 255))

    if with_wave:
        amber = (255, 176, 32, 255)
        y_lo, y_hi = 850, 765
        x0, x1 = 215, S - 215
        path = [(x0, y_lo), (x0 + 100, y_lo), (x0 + 100, y_hi), (x0 + 250, y_hi), (x0 + 250, y_lo),
                (x0 + 400, y_lo), (x0 + 400, y_hi), (x1, y_hi)]
        d.line(path, fill=amber, width=38, joint="curve")
        for (px, py) in (path[0], path[-1]):
            d.ellipse([px - 19, py - 19, px + 19, py + 19], fill=amber)
    return bg

def save_sizes():
    os.makedirs(OUT, exist_ok=True)
    big, small = master(True), master(False)
    sizes = [16, 24, 32, 48, 64, 128, 256, 512, 1024]
    imgs = {}
    for s in sizes:
        src = big if s >= 64 else small
        imgs[s] = src.resize((s, s), Image.LANCZOS)
        imgs[s].save(os.path.join(OUT, f"pace_{s}.png"))
    imgs[512].save(os.path.join(OUT, "pace.png"))
    # Windows .ico (multi-size)
    imgs[256].save(os.path.join(OUT, "pace.ico"),
                   sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
                   append_images=[imgs[s] for s in (16, 24, 32, 48, 64, 128)])
    # macOS .icns
    imgs[1024].save(os.path.join(OUT, "pace.icns"))
    print("icons written to", os.path.abspath(OUT))

if __name__ == "__main__":
    save_sizes()
