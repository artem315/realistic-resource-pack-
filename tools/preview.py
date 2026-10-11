"""Render a quick lit preview of generated labPBR textures (for checking the output).

Each texture is shown as a 2x2 tiled patch (so seams are visible), lit from the
upper left with Lambert diffuse + GGX-ish specular using the _n and _s maps.

    python tools/preview.py out.png stone cobblestone oak_planks ...
    python tools/preview.py out.png --all
"""
import argparse
import os

import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLOCK = os.path.join(ROOT, "assets", "minecraft", "textures", "block")


def shade(name, size=192, light=(-0.55, -0.55, 0.63), tiles=2, tint=None):
    alb = Image.open(os.path.join(BLOCK, name + ".png")).convert("RGBA")
    nrm_p = os.path.join(BLOCK, name + "_n.png")
    spc_p = os.path.join(BLOCK, name + "_s.png")
    a = np.asarray(alb, np.float32) / 255
    h, w = a.shape[:2]
    if h > w:  # animated strip: first frame
        a = a[:w]
    n = np.asarray(Image.open(nrm_p).convert("RGBA"), np.float32)[:a.shape[0]] / 255 if os.path.exists(nrm_p) else None
    s = np.asarray(Image.open(spc_p).convert("RGBA"), np.float32)[:a.shape[0]] / 255 if os.path.exists(spc_p) else None
    tile = lambda x: np.tile(x, (tiles, tiles, 1))
    a, = [tile(a)]
    col = a[..., :3] ** 2.2
    if tint is not None:
        col = col * (np.asarray(tint, np.float32) ** 2.2)
    if n is not None:
        n = tile(n)
        nx, ny = n[..., 0] * 2 - 1, n[..., 1] * 2 - 1
        nz = np.sqrt(np.clip(1 - nx * nx - ny * ny, 0, 1))
        N = np.stack([nx, ny, nz], -1)
        ao = n[..., 2]
    else:
        N = np.zeros(a.shape[:2] + (3,))
        N[..., 2] = 1
        ao = np.ones(a.shape[:2])
    L = np.array(light, np.float32)
    L /= np.linalg.norm(L)
    V = np.array([0, 0, 1.0])
    H = (L + V) / np.linalg.norm(L + V)
    ndl = np.clip((N * L).sum(-1), 0, 1)
    out = col * (0.18 * ao[..., None] + 1.0 * ndl[..., None])
    if s is not None:
        s = tile(s)
        smooth = s[..., 0]
        g = s[..., 1] * 255
        metal = g >= 229.5
        f0 = np.where(metal, 0.9, g / 255)
        rough = (1 - smooth) ** 2
        a2 = np.maximum(rough * rough, 1e-3)
        ndh = np.clip((N * H).sum(-1), 0, 1)
        D = a2 / (np.pi * (ndh * ndh * (a2 - 1) + 1) ** 2)
        spec = np.minimum(D * f0 * 0.25, 4)[..., None] * ndl[..., None]
        spec = np.where(metal[..., None], spec * col * 3, spec)
        diffuse_scale = np.where(metal, 0.25, 1.0)[..., None]
        out = out * diffuse_scale + spec
        em = s[..., 3]
        em = np.where(em > 0.999, 0, em)
        out += col * em[..., None] * 1.5
    out = np.clip(out, 0, 1) ** (1 / 2.2)
    if a.shape[-1] == 4:
        bg = np.full_like(out, 0.25)
        bg[((np.indices(out.shape[:2]).sum(0) // 16) % 2) == 0] = 0.32
        out = np.where(a[..., 3:4] > 0.1, out, bg)
    im = Image.fromarray((out * 255).astype(np.uint8))
    return im.resize((size, size), Image.LANCZOS)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out")
    p.add_argument("names", nargs="*")
    p.add_argument("--all", action="store_true")
    p.add_argument("--cols", type=int, default=6)
    p.add_argument("--size", type=int, default=192)
    p.add_argument("--albedo", action="store_true", help="show raw albedo next to the shaded tile")
    args = p.parse_args()
    names = args.names
    if args.all:
        names = sorted(f[:-4] for f in os.listdir(BLOCK)
                       if f.endswith(".png") and not f.endswith(("_n.png", "_s.png")))
    sz = args.size
    cols = args.cols
    rows = (len(names) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * sz, rows * (sz + 14)), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    for i, nm in enumerate(names):
        x, y = (i % cols) * sz, (i // cols) * (sz + 14)
        sheet.paste(shade(nm, sz), (x, y))
        d.text((x + 3, y + sz + 1), nm, fill=(230, 230, 230))
    sheet.save(args.out)
    print(args.out, len(names))


if __name__ == "__main__":
    main()
