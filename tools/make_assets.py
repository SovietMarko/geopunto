"""Genera el icono (planeta), la pantalla de carga y los marcadores del mapa."""
import math
import os
from PIL import Image, ImageDraw, ImageFilter

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
S = 4  # supersampling


def planet(size):
    W = size * S
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    cx = cy = W / 2
    R = W * 0.27
    # anillo trasero
    ring = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring)
    for k, col in ((0.0, (255, 196, 77, 255)), (0.06, (255, 160, 60, 255))):
        rx, ry = R * (1.75 - k), R * (0.50 - k * 0.3)
        rd.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], outline=col, width=int(W * 0.035))
    ring = ring.rotate(-22, resample=Image.BICUBIC, center=(cx, cy))
    back = ring.copy()
    # recorta la mitad frontal del anillo (se dibuja despues de la esfera)
    mask_front = Image.new("L", (W, W), 0)
    ImageDraw.Draw(mask_front).rectangle([0, cy, W, W], fill=255)
    mask_front = mask_front.rotate(-22, resample=Image.BICUBIC, center=(cx, cy))
    img.alpha_composite(back)
    # esfera con degradado radial
    sphere = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    px = sphere.load()
    lx, ly = cx - R * 0.45, cy - R * 0.45
    for y in range(int(cy - R), int(cy + R) + 1):
        for x in range(int(cx - R), int(cx + R) + 1):
            d = math.hypot(x - cx, y - cy)
            if d <= R:
                t = min(1.0, math.hypot(x - lx, y - ly) / (R * 1.6))
                r = int(70 + (10 - 70) * t)
                g = int(170 + (60 - 170) * t)
                b = int(235 + (130 - 235) * t)
                px[x, y] = (r, g, b, 255)
    # continentes simples
    cont = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    cd = ImageDraw.Draw(cont)
    green = (76, 175, 80, 235)
    for ox, oy, rx, ry in ((-0.35, -0.25, 0.30, 0.22), (-0.15, -0.05, 0.18, 0.30),
                           (0.30, 0.10, 0.25, 0.18), (0.40, -0.35, 0.15, 0.10),
                           (0.05, 0.45, 0.22, 0.12)):
        cd.ellipse([cx + (ox - rx) * R, cy + (oy - ry) * R, cx + (ox + rx) * R, cy + (oy + ry) * R], fill=green)
    cmask = Image.new("L", (W, W), 0)
    ImageDraw.Draw(cmask).ellipse([cx - R, cy - R, cx + R, cy + R], fill=255)
    cont.putalpha(Image.composite(cont.split()[3], Image.new("L", (W, W), 0), cmask))
    sphere.alpha_composite(cont)
    # brillo
    glow = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([lx - R * 0.35, ly - R * 0.25, lx + R * 0.25, ly + R * 0.2],
                                 fill=(255, 255, 255, 90))
    glow = glow.filter(ImageFilter.GaussianBlur(W * 0.02))
    sphere.alpha_composite(Image.composite(glow, Image.new("RGBA", (W, W)), cmask))
    img.alpha_composite(sphere)
    # anillo frontal
    front = Image.composite(ring, Image.new("RGBA", (W, W)), mask_front)
    img.alpha_composite(front)
    return img.resize((size, size), Image.LANCZOS)


def icon(size=512):
    W = size * S
    bg = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(bg)
    d.rounded_rectangle([0, 0, W - 1, W - 1], radius=W * 0.22, fill=(16, 42, 67, 255))
    for i, (x, y) in enumerate(((0.15, 0.2), (0.82, 0.15), (0.88, 0.7), (0.2, 0.85), (0.6, 0.9), (0.1, 0.55))):
        r = W * (0.008 if i % 2 else 0.012)
        d.ellipse([x * W - r, y * W - r, x * W + r, y * W + r], fill=(255, 255, 255, 200))
    bg = bg.resize((size, size), Image.LANCZOS)
    p = planet(int(size * 1.0))
    off = (size - p.size[0]) // 2
    bg.alpha_composite(p, (off, off))
    return bg


def presplash():
    img = Image.new("RGBA", (1024, 1024), (16, 42, 67, 255))
    p = planet(700)
    img.alpha_composite(p, (162, 162))
    return img.convert("RGB")


def marker_gps(size=36):
    W = size * S
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([0, 0, W - 1, W - 1], fill=(33, 150, 243, 70))
    m = W * 0.28
    d.ellipse([m, m, W - m, W - m], fill=(33, 150, 243, 255), outline=(255, 255, 255, 255), width=int(W * 0.07))
    return img.resize((size, size), Image.LANCZOS)


def marker_point(w=32, h=46):
    Ws, Hs = w * S, h * S
    img = Image.new("RGBA", (Ws, Hs), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = Ws / 2 - 2
    d.polygon([(Ws * 0.18, r * 1.3), (Ws / 2, Hs - 1), (Ws * 0.82, r * 1.3)], fill=(229, 57, 53, 255))
    d.ellipse([2, 2, Ws - 2, 2 * r + 2], fill=(229, 57, 53, 255))
    d.ellipse([Ws * 0.32, r * 0.64, Ws * 0.68, r * 1.36 + 2], fill=(255, 255, 255, 255))
    return img.resize((w, h), Image.LANCZOS)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    icon().save(os.path.join(OUT, "icon.png"))
    presplash().save(os.path.join(OUT, "presplash.png"))
    marker_gps().save(os.path.join(OUT, "marker_gps.png"))
    marker_point().save(os.path.join(OUT, "marker_point.png"))
    print("ok")
