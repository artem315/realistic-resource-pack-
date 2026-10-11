"""Natural blocks: stone family, soils, sand, ores, nether / end stone."""
import functools

import numpy as np

from pbrlib import (RES, Mat, bevel, blend_normals, blur, clamp01, fill_cells, grains, hex_rgb, height_mix, lerp, load,
                    mix, new_mat, noise, normal_from_height, normalize_v, rect_cells, rng, scaled, smoothstep,
                    voronoi, warp)
import pbrlib

R = {}


def recipe(fn):
    R[fn.__name__] = fn
    return fn


def cached(fn):
    c = functools.lru_cache(maxsize=None)(fn)

    @functools.wraps(fn)
    def w(*a, **k):
        return c(*a, **k).copy()
    return w


# --------------------------------------------------------------------------- #
# Base materials (re-used by many recipes)
# --------------------------------------------------------------------------- #
@cached
def m_stone():
    m = load("Rock020", zoom=2.0, relief=0.22)
    m.match_color(hex_rgb("7d7d7d"), contrast=1.15, saturation=0.25)
    return m.set_spec(smooth=0.22, smooth_var=0.6, f0=0.04, porosity=0.35)


@cached
def m_deepslate(top=False):
    m = load("Rock022", zoom=1.6, offset=(0.3, 0.1) if top else (0, 0), rot=1 if top else 0, relief=0.3)
    m.match_color(hex_rgb("4d4d51"), contrast=1.1, saturation=0.2)
    return m.set_spec(smooth=0.3, smooth_var=0.6, f0=0.045, porosity=0.2)


@cached
def m_dirt():
    m = load("Ground048", zoom=1.5, relief=0.25)
    m.match_color(hex_rgb("7a5639"), contrast=1.05, saturation=0.95)
    return m.set_spec(smooth=0.08, smooth_var=0.5, f0=0.03, porosity=0.85)


@cached
def m_sand():
    m = load("Ground093C", zoom=1.4, relief=0.15)
    m.match_color(hex_rgb("dbcfa3"), contrast=1.25, saturation=1.0)
    return m.set_spec(smooth=0.18, smooth_var=0.5, f0=0.04, porosity=0.6)


@cached
def m_netherrack():
    m = load("Rock029", zoom=1.8, relief=0.4)
    m.match_color(hex_rgb("6a2b2b"), contrast=1.35, saturation=1.1)
    return m.set_spec(smooth=0.12, smooth_var=0.6, f0=0.04, porosity=0.5)


@cached
def m_end_stone():
    m = load("Ground054", zoom=1.6, relief=0.35)
    m.match_color(hex_rgb("dbdea0"), contrast=1.1, saturation=0.9)
    return m.set_spec(smooth=0.15, smooth_var=0.5, f0=0.04, porosity=0.4)


def polished(m: Mat, seed, border=True, smooth=0.62):
    """Polished stone slab: flattened relief, glossy, small bevelled border."""
    m = m.copy()
    m.height = 1 - 0.03 * (1 - m.height)
    m.normal = normalize_v(lerp(m.normal, np.array([0, 0, 1.0], np.float32), 0.85))
    m.ao = lerp(m.ao, np.ones_like(m.ao), 0.8)
    m.adjust(contrast=0.9)
    if border:
        cid, u, v, edge, _, _ = rect_cells(1, 1)
        b = bevel(edge, scaled(5), 0.6)
        m.add_height((b - 1) * 0.12, 1.0)
        m.albedo = m.albedo * (0.85 + 0.15 * b[..., None])
    m.set_spec(smooth=smooth, smooth_var=0.3, porosity=0.05)
    return m


# --------------------------------------------------------------------------- #
# Stone family
# --------------------------------------------------------------------------- #
@recipe
def stone():
    return {"stone": m_stone()}


@cached
def m_cobble():
    m = load("Rocks007", zoom=1.4, relief=0.75)
    m.match_color(hex_rgb("8a8a88"), contrast=1.25, saturation=0.25)
    # darken the crevices between stones
    m.albedo *= (0.72 + 0.28 * smoothstep(0.25, 0.7, m.height))[..., None]
    return m.set_spec(smooth=0.2, smooth_var=0.6, f0=0.04, porosity=0.45)


@recipe
def cobblestone():
    return {"cobblestone": m_cobble()}


def mossify(m: Mat, seed, amount=0.5, low_bias=1.0):
    moss = load("Moss002", zoom=3.0, relief=0.2)
    moss.match_color(hex_rgb("5b6b2e"), contrast=1.2, saturation=1.0)
    moss.set_spec(smooth=0.05, f0=0.03, sss=0.35, porosity=0.9)
    moss.height = m.height * 0.3 + moss.height * 0.7 + 0.05
    n = noise(("moss", seed), 4, 4)
    cav = 1 - m.height
    t = clamp01((n - (1 - amount)) * 2.5 + (cav - 0.45) * low_bias * 2.0)
    return height_mix(m, moss, t, sharp=6)


@recipe
def mossy_cobblestone():
    return {"mossy_cobblestone": mossify(m_cobble(), "mc", 0.4)}


@recipe
def smooth_stone():
    base = load("Rock020", zoom=3.0, offset=(0.4, 0.2), relief=0.05)
    base.match_color(hex_rgb("9e9e9e"), contrast=0.7, saturation=0.15)
    p = polished(base, "ss", border=True, smooth=0.45)
    side = p.copy()
    # slab side: a horizontal groove in the middle, like vanilla
    yy = (np.mgrid[0:RES, 0:RES][0] + 0.5) / RES
    d = np.abs(yy - 0.5) * RES
    groove = 1 - bevel(d, scaled(4))
    side.add_height(-groove * 0.15, 1.0)
    side.albedo *= (1 - 0.25 * groove)[..., None]
    return {"smooth_stone": p, "smooth_stone_slab_side": side}


def bricks_from(stone_mat: Mat, mortar: Mat, seed, rows, cols, offsets=None, mortar_px=4.0, bevel_px=7.0,
                jitter=0.06, depth=0.35, widths=None, rot_choices=(0,)):
    cid, u, v, edge, _, _ = rect_cells(rows, cols, offsets=offsets, widths=widths)
    bricks = fill_cells(cid, [stone_mat], seed, jitter_color=jitter, rot_choices=rot_choices)
    mw = scaled(mortar_px) / 2
    inside = clamp01((edge - mw) / max(scaled(1.2), 0.5))
    b = bevel(np.maximum(edge - mw, 0), scaled(bevel_px), 0.7)
    # chipped edges: noisy bevel
    chip = noise(("chip", seed), 12, 3)
    b = clamp01(b * (0.75 + 0.5 * chip))
    bricks.add_height((b - 1) * depth, 1.0)
    bricks.height -= 0.0
    mortar = mortar.copy()
    mortar.height = mortar.height * 0.25 + (1 - depth - 0.25)
    out = mix(mortar, bricks, inside)
    out.ao *= (0.6 + 0.4 * inside)
    return out


@cached
def m_mortar_grey():
    m = load("Concrete048", zoom=3.0, relief=0.2)
    m.match_color(hex_rgb("6e6e6a"), contrast=1.2, saturation=0.2)
    return m.set_spec(smooth=0.1, f0=0.04, porosity=0.8)


@cached
def m_stone_bricks():
    s = load("Rock020", zoom=2.5, relief=0.12, offset=(0.2, 0.6))
    s.match_color(hex_rgb("7c7b7b"), contrast=1.1, saturation=0.2)
    s.set_spec(smooth=0.25, smooth_var=0.5, f0=0.04, porosity=0.3)
    return bricks_from(s, m_mortar_grey(), "sb", rows=2, cols=1, offsets=[0, 0.5], mortar_px=5, bevel_px=8)


@recipe
def stone_bricks():
    return {"stone_bricks": m_stone_bricks()}


def crack(m: Mat, seed, count=3, width_px=2.5, depth=0.35):
    """Draw random-walk cracks."""
    r = rng(("crack", seed))
    size = RES
    canvas = np.zeros((size, size), np.float32)
    for c in range(count):
        x, y = r.random() * size, r.random() * size
        ang = r.random() * 2 * np.pi
        length = int(size * (0.4 + r.random() * 0.5))
        w = scaled(width_px) * (0.6 + r.random() * 0.8)
        for i in range(length):
            ang += (r.random() - 0.5) * 0.5
            x = (x + np.cos(ang)) % size
            y = (y + np.sin(ang)) % size
            ww = w * (1 - i / length) + 0.6
            iy, ix = int(y), int(x)
            rad = int(np.ceil(ww)) + 1
            for oy in range(-rad, rad + 1):
                for ox in range(-rad, rad + 1):
                    d = np.hypot(ox, oy)
                    if d <= ww:
                        canvas[(iy + oy) % size, (ix + ox) % size] = max(canvas[(iy + oy) % size, (ix + ox) % size],
                                                                       1 - d / (ww + 1e-3))
    canvas = blur(canvas, scaled(0.6))
    out = m.copy()
    out.add_height(-canvas * depth, 1.0)
    out.albedo *= (1 - 0.6 * clamp01(canvas * 1.5))[..., None]
    out.ao *= 1 - 0.5 * clamp01(canvas * 2)
    return out


@recipe
def cracked_stone_bricks():
    return {"cracked_stone_bricks": crack(m_stone_bricks(), "csb", 4)}


@recipe
def mossy_stone_bricks():
    return {"mossy_stone_bricks": mossify(m_stone_bricks(), "msb", 0.45, low_bias=1.4)}


@recipe
def chiseled_stone_bricks():
    s = m_stone_bricks()
    yy, xx = (np.mgrid[0:RES, 0:RES] + 0.5) / RES
    # concentric carved ring in the centre, like the vanilla pattern
    d = np.maximum(np.abs(xx - 0.5), np.abs(yy - 0.5))
    ring = smoothstep(0.03, 0.0, np.abs(d - 0.28) - 0.03) * (d < 0.45)
    inner = smoothstep(0.17, 0.15, np.hypot(xx - 0.5, yy - 0.5))
    carve = clamp01(ring + (smoothstep(0.02, 0.0, np.abs(np.hypot(xx - 0.5, yy - 0.5) - 0.13) - 0.015)))
    s.add_height(-carve * 0.18 + inner * 0.0, 1.0)
    s.albedo *= (1 - 0.3 * carve)[..., None]
    return {"chiseled_stone_bricks": s}


def stone_variant(asset, color, seed, zoom=2.0, contrast=1.1, sat=0.6, relief=0.25, smooth=0.25, rot=0,
                  offset=(0, 0)):
    m = load(asset, zoom=zoom, relief=relief, rot=rot, offset=offset)
    m.match_color(hex_rgb(color), contrast=contrast, saturation=sat)
    return m.set_spec(smooth=smooth, smooth_var=0.6, f0=0.045, porosity=0.25)


def igneous(base: Mat, seed, n, palette, weights, amount=0.75, grain_relief=0.04):
    """Overlay a crystal-grain mosaic on a photo stone (granite, diorite, andesite)."""
    rgb, cid, f1, f2, pick = grains(seed, n, palette, weights)
    m = base.copy()
    lum = (m.albedo.mean(-1, keepdims=True) / (m.albedo.mean() + 1e-6))
    m.albedo = clamp01(lerp(m.albedo, rgb * (0.75 + 0.25 * lum), amount))
    edge = smoothstep(0.004, 0.0, f2 - f1)
    r = rng(("ign-h", seed))
    hv = r.random(cid.max() + 1).astype(np.float32)[cid]
    m.add_height((hv - 0.5) * grain_relief - edge * grain_relief, 0.8)
    m.albedo *= (1 - 0.12 * edge)[..., None]
    # mica / quartz grains are glossier
    m.smooth = clamp01(m.smooth + (hv > 0.7) * 0.15)
    return m


@recipe
def granite_family():
    base = stone_variant("Rock050", "9c6b5c", "gr", zoom=1.6, contrast=1.0, sat=1.0, relief=0.22)
    g = igneous(base, "granite", 1800, ["c08470", "a8665a", "d9b7a8", "8c5446", "2b2421", "e6d6cc"],
                [4, 3, 2, 2, 1.3, 1], amount=0.7)
    return {"granite": g, "polished_granite": polished(g, "pg", smooth=0.72)}


@recipe
def diorite_family():
    base = stone_variant("Rock026", "bdbdbd", "di", zoom=1.8, contrast=1.0, sat=0.1)
    d = igneous(base, "diorite", 1600, ["ebebe8", "d2d2cd", "bfbfba", "2d2d2d", "5a5a57"],
                [4, 3, 2, 1.1, 1.0], amount=0.7)
    return {"diorite": d, "polished_diorite": polished(d, "pd", smooth=0.72)}


@recipe
def andesite_family():
    base = stone_variant("Rock050", "848484", "an", zoom=1.8, contrast=1.15, sat=0.15)
    a = igneous(base, "andesite", 3000, ["8e8e8c", "7b7b79", "a3a3a0", "5e5e5c", "bdbdba"],
                [4, 4, 2, 1.5, 0.6], amount=0.45, grain_relief=0.03)
    return {"andesite": a, "polished_andesite": polished(a, "pa", smooth=0.64)}


@recipe
def calcite():
    c = stone_variant("Rock026", "dfe0dc", "ca", zoom=2.5, contrast=0.8, sat=0.1, offset=(0.5, 0.5), smooth=0.35)
    return {"calcite": c}


@recipe
def tuff():
    t = stone_variant("Rock062", "6c6d66", "tu", zoom=2.0, contrast=1.1, sat=0.35, relief=0.3)
    t.set_spec(porosity=0.6)
    return {"tuff": t}


@recipe
def deepslate_family():
    side = m_deepslate()
    top = m_deepslate(top=True)
    cobbled = load("Rocks007", zoom=1.7, offset=(0.4, 0.3), relief=0.75)
    cobbled.match_color(hex_rgb("57575c"), contrast=1.3, saturation=0.15)
    cobbled.albedo *= (0.7 + 0.3 * smoothstep(0.25, 0.7, cobbled.height))[..., None]
    cobbled.set_spec(smooth=0.25, smooth_var=0.6, f0=0.045, porosity=0.3)
    pol = polished(load("Rock022", zoom=3, offset=(0.6, 0.6), relief=0.1), "pds", smooth=0.68)
    pol.match_color(hex_rgb("48484b"), contrast=1.0, saturation=0.1)
    brick_src = load("Rock022", zoom=3, offset=(0.1, 0.7), relief=0.12)
    brick_src.match_color(hex_rgb("47474b"), contrast=1.15, saturation=0.15)
    brick_src.set_spec(smooth=0.32, smooth_var=0.5, f0=0.045, porosity=0.2)
    mortar = m_mortar_grey()
    mortar.match_color(hex_rgb("2b2b2e"), contrast=1.0, saturation=0.1)
    dbricks = bricks_from(brick_src, mortar, "dsb", rows=4, cols=2, offsets=[0, 0.5, 0, 0.5], mortar_px=4,
                          bevel_px=5)
    dtiles = bricks_from(brick_src, mortar, "dst", rows=4, cols=4, offsets=[0, 0, 0, 0], mortar_px=4, bevel_px=4,
                         jitter=0.08, rot_choices=(0, 1, 2, 3))
    return {
        "deepslate": side,
        "deepslate_top": top,
        "cobbled_deepslate": cobbled,
        "polished_deepslate": pol,
        "deepslate_bricks": dbricks,
        "cracked_deepslate_bricks": crack(dbricks, "cdsb", 4),
        "deepslate_tiles": dtiles,
        "cracked_deepslate_tiles": crack(dtiles, "cdst", 4),
    }


@recipe
def bedrock():
    m = load("Rock031", zoom=1.5, relief=0.8)
    m.match_color(hex_rgb("575757"), contrast=1.7, saturation=0.1)
    m.albedo *= (0.35 + 0.65 * smoothstep(0.2, 0.8, m.height))[..., None]
    return {"bedrock": m.set_spec(smooth=0.2, smooth_var=0.6, f0=0.04)}


@recipe
def obsidian():
    m = load("Marble016", zoom=1.5, relief=0.08)
    m.match_color(hex_rgb("15111f"), contrast=1.6, saturation=1.3)
    # conchoidal fractures
    cid, f1, f2 = voronoi("obs", 14)
    edges = smoothstep(0.012, 0.0, f2 - f1)
    m.add_height(-edges * 0.1 + (f1 * 0.4), 0.6)
    m.albedo = lerp(m.albedo, hex_rgb("3b2a55")[None, None, :] * np.ones_like(m.albedo), edges * 0.5)
    return {"obsidian": m.set_spec(smooth=0.88, smooth_var=0.2, f0=0.045)}


@recipe
def crying_obsidian():
    m = obsidian()["obsidian"]
    n = noise("cry", 6, 4)
    glow = smoothstep(0.74, 0.86, n) * smoothstep(0.4, 0.6, noise("cry2", 2, 2))
    m.albedo = lerp(m.albedo, hex_rgb("8c2fd9")[None, None, :] * np.ones_like(m.albedo), glow)
    m.emit = glow * 0.85
    return {"crying_obsidian": m}


# --------------------------------------------------------------------------- #
# Soils
# --------------------------------------------------------------------------- #
@recipe
def dirt():
    return {"dirt": m_dirt()}


@recipe
def coarse_dirt():
    m = load("Ground085", zoom=1.3, relief=0.45)
    m.match_color(hex_rgb("77553b"), contrast=1.15, saturation=0.9)
    return {"coarse_dirt": m.set_spec(smooth=0.1, smooth_var=0.6, f0=0.04, porosity=0.7)}


@recipe
def rooted_dirt():
    m = m_dirt()
    # thin roots
    n = noise("roots", 3, 3, aniso=(1, 4))
    roots = smoothstep(0.02, 0.0, np.abs(n - 0.5) - 0.006)
    m.add_height(roots * 0.12, 1.0)
    m.albedo = lerp(m.albedo, hex_rgb("9b7653")[None, None, :] * np.ones_like(m.albedo), roots * 0.8)
    return {"rooted_dirt": m}


@recipe
def mud():
    m = load("Ground048", zoom=2.0, offset=(0.5, 0.5), relief=0.15)
    m.match_color(hex_rgb("3c3836"), contrast=0.9, saturation=0.5)
    return {"mud": m.set_spec(smooth=0.55, smooth_var=0.4, f0=0.03, porosity=0.2)}


@recipe
def clay():
    m = load("Rock041", zoom=1.6, relief=0.08)
    m.match_color(hex_rgb("a0a6b3"), contrast=0.9, saturation=0.8)
    return {"clay": m.set_spec(smooth=0.38, smooth_var=0.5, f0=0.04, porosity=0.4)}


@recipe
def gravel():
    m = load("Gravel022", zoom=1.6, relief=0.6)
    m.match_color(hex_rgb("847f7e"), contrast=1.25, saturation=0.45)
    return {"gravel": m.set_spec(smooth=0.25, smooth_var=0.6, f0=0.04, porosity=0.3)}


@recipe
def sand():
    return {"sand": m_sand()}


@recipe
def red_sand():
    m = load("Ground093C", zoom=1.4, offset=(0.5, 0.5), relief=0.15)
    m.match_color(hex_rgb("be6621"), contrast=1.25, saturation=1.0)
    return {"red_sand": m.set_spec(smooth=0.18, smooth_var=0.5, f0=0.04, porosity=0.6)}


def sandstone_set(prefix, color, seed):
    side = load("Ground097", zoom=1.6, relief=0.35)
    side.match_color(hex_rgb(color), contrast=1.15, saturation=0.9)
    side.set_spec(smooth=0.15, smooth_var=0.5, f0=0.04, porosity=0.5)
    top = load("Ground093C", zoom=1.8, offset=(0.3, 0.6), relief=0.12)
    top.match_color(hex_rgb(color), contrast=1.0, saturation=0.9)
    top.set_spec(smooth=0.2, smooth_var=0.5, f0=0.04, porosity=0.4)
    bottom = load("Ground088", zoom=1.6, relief=0.3)
    bottom.match_color(hex_rgb(color), contrast=1.2, saturation=0.9)
    bottom.set_spec(smooth=0.12, smooth_var=0.5, f0=0.04, porosity=0.6)
    cut = top.copy()
    cid, u, v, edge, _, _ = rect_cells(2, 1, offsets=[0, 0])
    b = bevel(edge, scaled(6), 0.6)
    cut.add_height((b - 1) * 0.25, 1.0)
    cut.albedo *= (0.8 + 0.2 * b[..., None])
    return {
        f"{prefix}": side,
        f"{prefix}_top": top,
        f"{prefix}_bottom": bottom,
        f"cut_{prefix}": cut,
    }


@recipe
def sandstone():
    return sandstone_set("sandstone", "d8cb9b", "ss")


@recipe
def red_sandstone():
    return sandstone_set("red_sandstone", "b5621f", "rss")


@recipe
def snow():
    m = load("Snow006", zoom=1.5, relief=0.12)
    m.match_color(hex_rgb("f3f8fa"), contrast=1.3, saturation=0.4)
    m.set_spec(smooth=0.45, smooth_var=0.5, f0=0.02, sss=0.6)
    # sparkles
    sp = smoothstep(0.92, 0.97, noise("sparkle", 90, 1))
    m.smooth = clamp01(m.smooth + sp * 0.5)
    return {"snow": m, "powder_snow": m.copy()}


@recipe
def ice_family():
    ice = load("Ice003", zoom=1.4, relief=0.05)
    ice.match_color(hex_rgb("91b4f0"), contrast=1.1, saturation=1.0)
    ice.set_spec(smooth=0.93, smooth_var=0.15, f0=0.02, sss=0.3)
    ice.alpha = np.full(ice.height.shape, 0.72, np.float32)
    packed = load("Ice004", zoom=1.4, relief=0.05)
    packed.match_color(hex_rgb("8db4ec"), contrast=0.7, saturation=0.9)
    packed.set_spec(smooth=0.8, smooth_var=0.2, f0=0.02, sss=0.2)
    blue = load("Ice003", zoom=1.8, offset=(0.5, 0.2), relief=0.05)
    blue.match_color(hex_rgb("74a8fd"), contrast=1.2, saturation=1.2)
    blue.set_spec(smooth=0.9, smooth_var=0.15, f0=0.02, sss=0.25)
    return {"ice": ice, "packed_ice": packed, "blue_ice": blue}


# --------------------------------------------------------------------------- #
# Ores
# --------------------------------------------------------------------------- #
ORES = {
    #           colour A, colour B, smooth, f0, metal, emit, raised, crystal cells
    "coal":     ("1c1c1e", "3a3a3e", 0.55, 0.05, 0, 0.0, 0.10, 28),
    "iron":     ("d8af93", "a8705a", 0.30, 0.05, 0, 0.0, 0.10, 18),
    "copper":   ("c86b45", "5aa58a", 0.45, 0.0, 234, 0.0, 0.10, 18),
    "gold":     ("fcee4b", "d49b1a", 0.70, 0.0, 231, 0.0, 0.10, 18),
    "redstone": ("ff1a0a", "8f0000", 0.55, 0.06, 0, 0.35, 0.12, 22),
    "emerald":  ("17dd62", "087a34", 0.88, 0.06, 0, 0.0, 0.16, 10),
    "lapis":    ("2b5bd6", "102e8f", 0.55, 0.05, 0, 0.0, 0.10, 22),
    "diamond":  ("9cf6ef", "2fc7c0", 0.95, 0.17, 0, 0.0, 0.18, 12),
}


def ore_on(base: Mat, kind, seed, density=1.0):
    ca, cb, smooth, f0, metal, emit, raise_, cells = ORES[kind]
    size = RES
    # clustered deposits
    cluster = noise(("ore-cl", seed), 3.0, 3)
    vcid, f1, f2 = voronoi(("ore-v", seed), cells * 3)
    r = rng(("ore", seed))
    pick = r.random(vcid.max() + 1)
    chosen = pick[vcid] < 0.55 * density
    blob = smoothstep(0.55, 0.35, f1 * np.sqrt(cells * 3) * (1.0 + 0.6 * noise(("orewarp", seed), 10, 3)))
    mask = clamp01(blob * chosen * smoothstep(0.35, 0.6, cluster) * 1.6)
    mask = smoothstep(0.25, 0.6, mask)
    # crystal facets
    fcid, ff1, ff2 = voronoi(("ore-f", seed), int(cells * 22))
    rr = rng(("ore-fn", seed))
    tilt = rr.normal(0, 0.45, (fcid.max() + 1, 2)).astype(np.float32)
    fn = np.stack([tilt[fcid][..., 0], tilt[fcid][..., 1], np.ones_like(ff1)], -1)
    fn = normalize_v(fn)
    shade = rr.random(fcid.max() + 1).astype(np.float32)[fcid]
    edge = smoothstep(0.006, 0.0, ff2 - ff1)
    col = lerp(np.ones((size, size, 3), np.float32) * hex_rgb(cb), np.ones((size, size, 3), np.float32) * hex_rgb(ca),
               clamp01(shade * 0.8 + 0.2))
    col = col * (1 - 0.35 * edge[..., None])
    ore = base.copy()
    ore.albedo = col
    ore.normal = blend_normals(fn, base.normal)
    ore.height = base.height * 0.3 + 0.7 + raise_ * mask
    ore.smooth = np.full_like(mask, smooth) * (1 - 0.5 * edge)
    ore.f0 = np.full_like(mask, f0 if f0 else 0.04)
    ore.metal = np.full(mask.shape, metal, np.int32)
    ore.porosity = np.zeros_like(mask)
    ore.emit = np.full_like(mask, emit) * (0.6 + 0.4 * shade)
    ore.ao = np.ones_like(mask)
    out = mix(base, ore, mask)
    # dark rim around the deposits
    rim = clamp01(blur(mask, scaled(2.5)) - mask)
    out.albedo *= (1 - 0.5 * rim)[..., None]
    out.ao *= 1 - 0.4 * rim
    return out


@recipe
def ores():
    out = {}
    st = m_stone()
    ds = m_deepslate()
    for k in ORES:
        out[f"{k}_ore"] = ore_on(st, k, k)
        out[f"deepslate_{k}_ore"] = ore_on(ds, k, "d" + k)
    nr = m_netherrack()
    out["nether_gold_ore"] = ore_on(nr, "gold", "ngold", density=1.3)
    q = ore_on(nr, "diamond", "nquartz", density=1.2)
    # recolour the diamond crystals to milky quartz
    q2 = ore_on(nr, "diamond", "nquartz", density=1.2)
    mask = (q2.f0 > 0.1).astype(np.float32)
    lum = q2.albedo.mean(-1, keepdims=True)
    q2.albedo = lerp(q2.albedo, np.clip(lum * 1.1 + 0.25, 0, 1) * np.array([1, 0.97, 0.94], np.float32), mask)
    q2.smooth = lerp(q2.smooth, np.full_like(mask, 0.75), mask)
    out["nether_quartz_ore"] = q2
    return out


# --------------------------------------------------------------------------- #
# Nether / End
# --------------------------------------------------------------------------- #
@recipe
def netherrack():
    return {"netherrack": m_netherrack()}


@recipe
def nether_bricks():
    src = load("Rock029", zoom=3, offset=(0.5, 0.2), relief=0.15)
    src.match_color(hex_rgb("2e1619"), contrast=1.2, saturation=1.0)
    src.set_spec(smooth=0.3, smooth_var=0.5, f0=0.04, porosity=0.2)
    mortar = m_mortar_grey()
    mortar.match_color(hex_rgb("150a0b"), contrast=1.0, saturation=0.5)
    nb = bricks_from(src, mortar, "nb", rows=4, cols=2, offsets=[0, 0.5, 0, 0.5], mortar_px=4, bevel_px=5)
    red = src.copy()
    red.match_color(hex_rgb("470709"), contrast=1.2, saturation=1.1)
    rnb = bricks_from(red, mortar, "rnb", rows=4, cols=2, offsets=[0, 0.5, 0, 0.5], mortar_px=4, bevel_px=5)
    return {"nether_bricks": nb, "red_nether_bricks": rnb, "cracked_nether_bricks": crack(nb, "cnb", 4)}


@recipe
def soul_sand_soil():
    ss = load("Ground085", zoom=1.5, offset=(0.3, 0.3), relief=0.5)
    ss.match_color(hex_rgb("51402f"), contrast=1.2, saturation=0.6)
    # faces in the sand
    cid, f1, f2 = voronoi("faces", 5)
    eye = smoothstep(0.05, 0.03, f1)
    ss.add_height(-eye * 0.3, 1.0)
    ss.albedo *= (1 - 0.6 * eye)[..., None]
    ss.set_spec(smooth=0.1, smooth_var=0.5, f0=0.04, porosity=0.6)
    soil = load("Ground048", zoom=1.8, offset=(0.5, 0.1), relief=0.3)
    soil.match_color(hex_rgb("4c3a2e"), contrast=1.1, saturation=0.6)
    soil.set_spec(smooth=0.08, smooth_var=0.5, f0=0.04, porosity=0.8)
    return {"soul_sand": ss, "soul_soil": soil}


@recipe
def blackstone_family():
    side = load("Rock035", zoom=1.6, relief=0.4)
    side.match_color(hex_rgb("2a2328"), contrast=1.4, saturation=0.4)
    side.set_spec(smooth=0.3, smooth_var=0.6, f0=0.045, porosity=0.2)
    top = load("Rock035", zoom=1.6, offset=(0.5, 0.5), rot=1, relief=0.3)
    top.match_color(hex_rgb("2b2428"), contrast=1.3, saturation=0.4)
    top.set_spec(smooth=0.3, smooth_var=0.6, f0=0.045, porosity=0.2)
    pol = polished(load("Marble016", zoom=2, relief=0.05), "pbs", smooth=0.75)
    pol.match_color(hex_rgb("36303a"), contrast=0.8, saturation=0.5)
    bsrc = load("Marble016", zoom=3, offset=(0.4, 0.4), relief=0.08)
    bsrc.match_color(hex_rgb("302a30"), contrast=0.9, saturation=0.4)
    bsrc.set_spec(smooth=0.6, smooth_var=0.3, f0=0.045)
    mortar = m_mortar_grey()
    mortar.match_color(hex_rgb("161214"), contrast=1.0, saturation=0.2)
    pbb = bricks_from(bsrc, mortar, "pbb", rows=4, cols=2, offsets=[0, 0.5, 0, 0.5], mortar_px=4, bevel_px=5)
    return {
        "blackstone": side, "blackstone_top": top, "polished_blackstone": pol,
        "polished_blackstone_bricks": pbb,
        "cracked_polished_blackstone_bricks": crack(pbb, "cpbb", 4),
    }


@recipe
def basalt_family():
    side = load("Rock022", zoom=1.4, rot=1, offset=(0.2, 0.2), relief=0.45)
    side.match_color(hex_rgb("4b4a4e"), contrast=1.3, saturation=0.15)
    side.set_spec(smooth=0.25, smooth_var=0.6, f0=0.045, porosity=0.2)
    top = load("Rock031", zoom=1.6, relief=0.4)
    top.match_color(hex_rgb("515155"), contrast=1.2, saturation=0.1)
    # columnar joints on top
    cid, f1, f2 = voronoi("basalt", 7)
    e = smoothstep(0.02, 0.0, f2 - f1)
    top.add_height(-e * 0.4, 1.0)
    top.albedo *= (1 - 0.5 * e)[..., None]
    top.set_spec(smooth=0.25, smooth_var=0.6, f0=0.045)
    pol_side = polished(side, "pbas", border=False, smooth=0.55)
    pol_top = polished(top, "pbat", border=True, smooth=0.55)
    sm = polished(load("Rock031", zoom=2.5, offset=(0.3, 0.6), relief=0.1), "sbas", border=False, smooth=0.5)
    sm.match_color(hex_rgb("48484e"), contrast=0.9, saturation=0.1)
    return {"basalt_side": side, "basalt_top": top, "polished_basalt_side": pol_side,
            "polished_basalt_top": pol_top, "smooth_basalt": sm}


@recipe
def end_stone():
    es = m_end_stone()
    src = load("Ground054", zoom=3, offset=(0.4, 0.2), relief=0.12)
    src.match_color(hex_rgb("dfe3a6"), contrast=1.0, saturation=0.9)
    src.set_spec(smooth=0.25, smooth_var=0.5, f0=0.04, porosity=0.3)
    mortar = m_mortar_grey()
    mortar.match_color(hex_rgb("a7a676"), contrast=1.0, saturation=0.6)
    esb = bricks_from(src, mortar, "esb", rows=4, cols=2, offsets=[0, 0.5, 0, 0.5], mortar_px=4, bevel_px=6)
    return {"end_stone": es, "end_stone_bricks": esb}


@recipe
def glowstone():
    rock = load("Rock029", zoom=2.2, offset=(0.3, 0.5), relief=0.5)
    rock.match_color(hex_rgb("5a3c1e"), contrast=1.3, saturation=0.9)
    rock.set_spec(smooth=0.2, smooth_var=0.5, f0=0.04, porosity=0.2)
    cid, f1, f2 = voronoi("glow", 220)
    r = rng("glowc")
    shade = r.random(cid.max() + 1).astype(np.float32)[cid]
    edge = smoothstep(0.006, 0.0, f2 - f1)
    cluster = smoothstep(0.35, 0.6, noise("glowcl", 4, 3))
    lit = clamp01(cluster * (0.4 + 0.8 * shade))
    crystal = rock.copy()
    crystal.albedo = lerp(np.ones((RES, RES, 3), np.float32) * hex_rgb("d9902e"),
                          np.ones((RES, RES, 3), np.float32) * hex_rgb("fff0b0"), shade[..., None]) \
        * (1 - 0.4 * edge[..., None])
    facet = 1 - f1 / (f1.max() + 1e-6)
    crystal.height = 0.75 + 0.25 * facet * (0.6 + 0.4 * shade)
    crystal.normal = normal_from_height(crystal.height, 0.8)
    crystal.set_spec(smooth=0.85, f0=0.05, porosity=0.0, sss=0.4)
    crystal.emit = clamp01(0.3 + 0.7 * shade) * (1 - edge)
    out = mix(rock, crystal, lit)
    out.emit = out.emit * lit
    return {"glowstone": out}


@recipe
def magma():
    frames = []
    crust = load("Lava001", zoom=1.3, relief=0.5)
    glow_map = clamp01((crust.albedo[..., 0] - crust.albedo[..., 2]) * 2.2)
    for i in range(3):
        f = crust.copy()
        ph = noise(("magma", i), 3, 2)
        g = clamp01(glow_map * (0.75 + 0.5 * ph))
        f.albedo = lerp(f.albedo * 0.6, np.ones_like(f.albedo) * hex_rgb("ff7a1a"), g)
        f.emit = g
        f.set_spec(smooth=0.35, smooth_var=0.4, f0=0.05, porosity=0.0)
        frames.append(f)
    return {"magma": ("anim", frames, 8)}
