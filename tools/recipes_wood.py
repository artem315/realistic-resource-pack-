"""Wood: planks, logs, log tops (growth rings), stripped logs for every overworld species."""
import numpy as np

from pbrlib import (RES, bevel, blur, clamp01, fill_cells, hex_rgb, lerp, load, mix, new_mat, noise,
                    normal_from_height, rect_cells, rng, scaled, smoothstep, warp)

R = {}

# species: bark source, bark colour, plank source (grain must end up horizontal), plank rot,
#          plank colour, stripped colour, ring dark colour
SPECIES = {
    "oak":      ("Bark014", "6b5536", "Wood058", 1, "a2834f", "b4935b", "7d5c33"),
    "spruce":   ("Bark001", "3d2913", "Wood060", 0, "735532", "7a5c38", "4f3820"),
    "birch":    ("Bark004", "d8d6cf", "Wood050", 0, "c4b27c", "c9b680", "a38e5c"),
    "jungle":   ("Bark013", "57441c", "Wood052", 0, "a07351", "ae8657", "7c5536"),
    "acacia":   ("Bark002", "686259", "Wood092", 1, "a95a32", "b05d3c", "803e22"),
    "dark_oak": ("Bark012", "3c2e1a", "Wood051", 0, "432b16", "60492f", "2d1d0e"),
    "mangrove": ("Bark002", "54412b", "Wood066", 0, "763631", "7b3734", "5a2724"),
    "cherry":   ("Bark004", "3a2330", "Wood096", 1, "e2b3ad", "d99a98", "b8817c"),
    "pale_oak": ("Bark004", "5d5552", "Wood096", 1, "e4dbd7", "f1ebe8", "c7bcb6"),
}

PLANK_ROWS = dict(rows=4, cols=1,
                  offsets=[0.0, 0.47, 0.21, 0.73],
                  widths=[[1.0], [1.0], [1.0], [1.0]])


def plank_source(sp, zoom=2.0, offset=(0, 0)):
    _, _, src, rot, pcol, _, _ = SPECIES[sp]
    w = load(src, zoom=zoom, rot=rot, offset=offset, relief=0.12)
    w.match_color(hex_rgb(pcol), contrast=1.6, saturation=1.0)
    return w.set_spec(smooth=0.38, smooth_var=0.4, f0=0.04, porosity=0.55)


def planks(sp):
    srcs = [plank_source(sp, 1.5, (0, 0)), plank_source(sp, 1.7, (0.37, 0.61))]
    cid, u, v, edge, cw, rh = rect_cells(**PLANK_ROWS)
    m = fill_cells(cid, srcs, ("planks", sp), jitter_color=0.07)
    gap = scaled(1.6)
    inside = clamp01((edge - gap) / max(scaled(1.0), 0.5))
    b = bevel(np.maximum(edge - gap, 0), scaled(3.5), 0.8)
    r = rng(("plank-h", sp))
    tilt = r.random(cid.max() + 1).astype(np.float32)
    warp_h = (tilt[cid] - 0.5) * 0.06 + (v / rh - 0.5) * (tilt[(cid + 7) % (cid.max() + 1)] - 0.5) * 0.04
    m.add_height((b - 1) * 0.25 + warp_h, 1.0)
    gap_col = np.asarray(hex_rgb(SPECIES[sp][6]), np.float32) * 0.35
    m.albedo = lerp(np.ones_like(m.albedo) * gap_col, m.albedo, inside)
    m.height = lerp(np.full_like(m.height, 0.55), m.height, inside)
    m.ao *= 0.45 + 0.55 * inside
    # nails near the board ends
    yy, xx = np.mgrid[0:RES, 0:RES].astype(np.float32) + 0.5
    nails = np.zeros((RES, RES), np.float32)
    rows = PLANK_ROWS["rows"]
    for row in range(rows):
        ws = np.asarray(PLANK_ROWS["widths"][row], np.float32)
        edges = np.concatenate([[0], np.cumsum(ws / ws.sum())])
        off = PLANK_ROWS["offsets"][row]
        for e in edges[:-1]:
            for side in (+1, -1):
                x = ((e + off) * RES + side * scaled(7)) % RES
                for fy in (0.3, 0.7):
                    y = (row + fy) * RES / rows
                    dx = np.abs(xx - x)
                    dx = np.minimum(dx, RES - dx)
                    d = np.hypot(dx, yy - y)
                    nails = np.maximum(nails, smoothstep(scaled(1.6), scaled(0.9), d))
    nail = new_mat()
    nail.albedo[:] = hex_rgb("3d3a36")
    nail.height = m.height + 0.01
    nail.set_spec(smooth=0.45, metal=230, porosity=0.0)
    m = mix(m, nail, nails)
    return m


def bark(sp, seed=0):
    src, col = SPECIES[sp][0], SPECIES[sp][1]
    m = load(src, zoom=1.4 if sp != "spruce" else 1.2, offset=(0.13 * seed, 0.29 * seed), relief=0.7)
    soft = sp in ("birch",)
    m.match_color(hex_rgb(col), contrast=1.3 if not soft else 0.45,
                  saturation=0.9 if sp != "birch" else 0.2)
    m.albedo *= ((0.6 if not soft else 0.88) + (0.4 if not soft else 0.12) * smoothstep(0.2, 0.8, m.height))[..., None]
    if soft:
        m.height = 1 - (1 - m.height) * 0.35
        m.albedo = lerp(blur(m.albedo, scaled(4)), m.albedo, 0.25)
        m.albedo = clamp01((m.albedo - m.albedo.mean()) * 0.6 + hex_rgb("dcdad3"))
    m.set_spec(smooth=0.12, smooth_var=0.5, f0=0.035, porosity=0.75)
    if sp in ("birch", "cherry"):
        # horizontal lenticels / birch marks
        n = noise(("lent", sp), 5, 3, aniso=(0.12, 1.0))
        marks = smoothstep(0.7, 0.8, n) * smoothstep(0.3, 0.55, noise(("lent2", sp), 3, 2))
        dark = hex_rgb("2a2622") if sp == "birch" else hex_rgb("1f1216")
        m.albedo = lerp(m.albedo, np.ones_like(m.albedo) * dark, marks * 0.9)
        m.add_height(-marks * 0.15, 1.0)
    if sp == "birch":
        m.albedo = clamp01(m.albedo * 1.05)
    return m


def superellipse(xx, yy, p=4.0):
    return (np.abs(xx) ** p + np.abs(yy) ** p) ** (1 / p)


def rings(sp, with_bark=True):
    _, bark_col, _, _, pcol, scol, dcol = SPECIES[sp]
    light = hex_rgb(scol)
    dark = hex_rgb(dcol)
    yy, xx = (np.mgrid[0:RES, 0:RES].astype(np.float32) + 0.5) / RES - 0.5
    r = rng(("rings", sp))
    cx, cy = (r.random(2) - 0.5) * 0.06
    wn = (noise(("ringwarp", sp), 2, 2) - 0.5) * 0.035
    d = superellipse(xx - cx, yy - cy) + wn
    count = 13 + r.integers(0, 5)
    t = d * count * 2 + (noise(("ringn", sp), 4, 2) - 0.5) * 0.25
    phase = t - np.floor(t)
    late = smoothstep(0.6, 0.88, phase) * (1 - smoothstep(0.9, 1.0, phase))
    grain = noise(("ringgrain", sp), 40, 3, aniso=(1, 1))
    col = lerp(np.ones((RES, RES, 3), np.float32) * light, np.ones((RES, RES, 3), np.float32) * dark, late * 0.75)
    col = col * (0.9 + 0.2 * grain[..., None])
    # heartwood is a little darker
    heart = smoothstep(0.25, 0.05, d)
    col = col * (1 - 0.12 * heart[..., None])
    m = new_mat()
    m.albedo = clamp01(col)
    h = 0.92 + late * 0.03 + grain * 0.02
    # radial drying cracks
    ang = np.arctan2(yy - cy, xx - cx)
    cracks = np.zeros_like(d)
    for k in range(r.integers(1, 3)):
        a0 = r.random() * 2 * np.pi
        da = np.angle(np.exp(1j * (ang - a0)))
        reach = 0.12 + r.random() * 0.2
        width = 0.005 * clamp01(1 - d / reach)
        cracks = np.maximum(cracks, smoothstep(width + 0.003, width, np.abs(da) * d) * (d < reach) * (d > 0.02))
    h -= cracks * 0.3
    m.albedo *= (1 - 0.6 * cracks)[..., None]
    pith = smoothstep(0.02, 0.008, np.hypot(xx - cx, yy - cy))
    m.albedo = lerp(m.albedo, np.ones_like(m.albedo) * dark * 0.6, pith)
    m.height = h
    m.normal = normal_from_height(h, 1.0)
    m.set_spec(smooth=0.3, f0=0.04, porosity=0.6)
    if with_bark:
        b = bark(sp, seed=3)
        edge = 0.468 + (noise(("barkedge", sp), 8, 2) - 0.5) * 0.015
        band = smoothstep(edge - 0.005, edge + 0.005, d)
        cambium = smoothstep(0.012, 0.0, np.abs(d - edge + 0.008))
        m.albedo = lerp(m.albedo, np.ones_like(m.albedo) * dark * 0.7, cambium * 0.7)
        b.height = b.height * 0.5 + 0.5
        m = mix(m, b, band)
    else:
        edge = 0.48
        cambium = smoothstep(0.015, 0.0, np.abs(d - edge))
        m.albedo = lerp(m.albedo, np.ones_like(m.albedo) * dark * 0.8, cambium * 0.5)
    return m


def stripped(sp):
    _, _, src, rot, _, scol, _ = SPECIES[sp]
    m = load(src, zoom=1.3, rot=(rot + 1) % 4, offset=(0.2, 0.4), relief=0.15)
    m.match_color(hex_rgb(scol), contrast=1.3, saturation=1.05)
    # shallow draw-knife facets running along the log
    n = noise(("facet", sp), 3, 2, aniso=(1.0, 0.12))
    m.add_height((n - 0.5) * 0.08, 0.6)
    return m.set_spec(smooth=0.3, smooth_var=0.4, f0=0.04, porosity=0.6)


def species_recipe(sp):
    def fn():
        return {
            f"{sp}_planks": planks(sp),
            f"{sp}_log": bark(sp),
            f"{sp}_log_top": rings(sp, True),
            f"stripped_{sp}_log": stripped(sp),
            f"stripped_{sp}_log_top": rings(sp, False),
        }
    fn.__name__ = f"wood_{sp}"
    return fn


for _sp in SPECIES:
    R[f"wood_{_sp}"] = species_recipe(_sp)
