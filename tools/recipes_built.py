"""Crafted blocks: bricks, glass, bookshelf, crafting table, furnace, quartz, metal & gem blocks, hay."""
import numpy as np

from pbrlib import (RES, bevel, blur, clamp01, fill_cells, hex_rgb, lerp, load, mix, new_mat, noise,
                    normal_from_height, rect_cells, rng, scaled, smoothstep, voronoi)
from recipes_natural import bricks_from, m_mortar_grey, m_stone, polished
from recipes_wood import plank_source, planks

R = {}


def recipe(fn):
    R[fn.__name__] = fn
    return fn


def col(c):
    return np.ones((RES, RES, 3), np.float32) * hex_rgb(c)


def grid():
    yy, xx = (np.mgrid[0:RES, 0:RES].astype(np.float32) + 0.5) / RES
    return xx, yy


def box_edge(x0, y0, x1, y1):
    """Signed-ish distance (in pixels) to the border of a rectangle, positive inside."""
    xx, yy = grid()
    d = np.minimum(np.minimum(xx - x0, x1 - xx), np.minimum(yy - y0, y1 - yy))
    return d * RES


# --------------------------------------------------------------------------- #
@recipe
def bricks():
    clay = load("Ground111", zoom=3.0, relief=0.12)
    clay.match_color(hex_rgb("975545"), contrast=1.2, saturation=1.0)
    clay.set_spec(smooth=0.22, smooth_var=0.5, f0=0.04, porosity=0.55)
    clay2 = load("Ground111", zoom=3.0, offset=(0.5, 0.3), relief=0.12)
    clay2.match_color(hex_rgb("83463a"), contrast=1.2, saturation=1.0)
    clay2.set_spec(smooth=0.22, smooth_var=0.5, f0=0.04, porosity=0.55)
    mortar = load("Concrete048", zoom=3.0, offset=(0.2, 0.2), relief=0.25)
    mortar.match_color(hex_rgb("a8a297"), contrast=1.1, saturation=0.4)
    mortar.set_spec(smooth=0.1, f0=0.04, porosity=0.8)
    cid, u, v, edge, _, _ = rect_cells(4, 2, offsets=[0, 0.5, 0, 0.5])
    b = fill_cells(cid, [clay, clay2], "bricks", jitter_color=0.12)
    mw = scaled(5) / 2
    inside = clamp01((edge - mw) / max(scaled(1.2), 0.5))
    bv = bevel(np.maximum(edge - mw, 0), scaled(4), 0.7) * (0.8 + 0.4 * noise("brchip", 14, 3))
    b.add_height((clamp01(bv) - 1) * 0.3, 1.0)
    mortar.height = mortar.height * 0.2 + 0.45
    out = mix(mortar, b, inside)
    out.ao *= 0.6 + 0.4 * inside
    return {"bricks": out}


@recipe
def glass():
    m = new_mat(color=(0.85, 0.9, 0.92))
    e = box_edge(0, 0, 1, 1)
    frame = (e < scaled(5)).astype(np.float32)
    fr = load("Metal032", zoom=3, relief=0.05)
    fr.match_color(hex_rgb("c9cdd0"), contrast=0.8, saturation=0.2)
    fr.set_spec(smooth=0.55, metal=232)  # aluminium
    b = bevel(np.maximum(e, 0), scaled(2.5), 0.8)
    fr.add_height((b - 1) * 0.2, 1.0)
    xx, yy = grid()
    # a few faint diagonal reflections (glass is a cut-out texture, so keep them thin)
    s1 = smoothstep(0.012, 0.0, np.abs((xx + yy) - 0.55)) * ((xx > 0.15) & (xx < 0.4))
    s2 = smoothstep(0.008, 0.0, np.abs((xx + yy) - 0.62)) * ((xx > 0.2) & (xx < 0.35))
    s3 = smoothstep(0.01, 0.0, np.abs((xx + yy) - 1.35)) * ((xx > 0.6) & (xx < 0.82))
    streak = clamp01(s1 + s2 + s3)
    m.albedo = lerp(m.albedo, col("ffffff"), streak)
    m.set_spec(smooth=0.97, f0=0.04)
    out = mix(m, fr, frame)
    out.alpha = clamp01(frame + streak * 0.6)
    out.alpha = (out.alpha > 0.3).astype(np.float32)
    pane = out.copy()
    return {"glass": ("opts", {"flat_pom": True}, out), "glass_pane_top": ("opts", {"flat_pom": True}, fr)}


# --------------------------------------------------------------------------- #
BOOK_COLORS = ["5e1a14", "7a2a1a", "2c3a1c", "1f2b44", "3b2414", "6b4a26", "1c1a18", "8a6a3a", "4a1d2f",
               "234038", "702d22", "a08a5c"]


@recipe
def bookshelf():
    wood = planks("oak")
    out = wood.copy()
    xx, yy = grid()
    r = rng("books")
    leather = load("Fabric030", zoom=3, relief=0.1)
    leather.set_spec(smooth=0.35, f0=0.04)
    shelves = [(0.075, 0.46), (0.54, 0.925)]
    book_mask = np.zeros((RES, RES), np.float32)
    book = new_mat()
    book.normal = leather.normal.copy()
    book.height = np.zeros((RES, RES), np.float32)
    for (y0, y1) in shelves:
        x = 0.0
        while x < 1.0:
            w = r.uniform(0.04, 0.085)
            hgt = r.uniform(0.72, 0.97) * (y1 - y0)
            c = hex_rgb(BOOK_COLORS[r.integers(len(BOOK_COLORS))]) * r.uniform(0.75, 1.15)
            gap = r.uniform(0.002, 0.008)
            sel = (xx >= x + gap) & (xx < min(x + w, 1.0)) & (yy > y1 - hgt) & (yy < y1)
            if r.random() < 0.08:  # empty slot
                x += w
                continue
            local = clamp01((xx - x - gap) / max(w - gap, 1e-3))
            round_ = np.sin(local * np.pi) ** 0.5
            lum = leather.albedo.mean(-1)
            bc = c[None, None, :] * (0.75 + 0.5 * lum[..., None]) * (0.75 + 0.25 * round_[..., None])
            # gilded bands near top and bottom of the spine
            top = y1 - hgt
            band = (np.abs(yy - (top + 0.035)) < 0.008) | (np.abs(yy - (y1 - 0.035)) < 0.008)
            if r.random() < 0.6:
                band |= np.abs(yy - (top + hgt * 0.45)) < 0.012
            band = band & sel
            book.albedo[sel] = bc[sel]
            book.height[sel] = (0.86 + 0.08 * round_ + r.uniform(-0.04, 0.04))[sel]
            book.smooth[sel] = 0.35
            book.metal[sel] = 0
            book.albedo[band] = hex_rgb("c9a14a")
            book.metal[band] = 231
            book.smooth[band] = 0.6
            book_mask[sel] = 1
            x += w
    # shelf cavity: dark, deep
    cav = np.zeros((RES, RES), np.float32)
    for (y0, y1) in shelves:
        cav = np.maximum(cav, ((yy > y0) & (yy < y1)).astype(np.float32))
    hole = new_mat(color=hex_rgb("150f0a"))
    hole.height = np.full((RES, RES), 0.3, np.float32)
    hole.ao[:] = 0.3
    hole.set_spec(smooth=0.1, porosity=0.0)
    book.normal = normal_from_height(book.height, 1.0) * 0.5 + leather.normal * 0.5
    book.normal /= np.linalg.norm(book.normal, axis=-1, keepdims=True)
    book.ao = np.ones((RES, RES), np.float32)
    inner = mix(hole, book, book_mask)
    # shadow under the shelf above
    for (y0, y1) in shelves:
        sh = clamp01(1 - (yy - y0) / 0.12) * ((yy > y0) & (yy < y1))
        inner.ao *= 1 - 0.5 * sh
        inner.albedo *= (1 - 0.45 * sh)[..., None]
    out = mix(out, inner, cav)
    return {"bookshelf": out}


def tool_shapes():
    """Hammer and saw silhouettes for the crafting table front.  Returns (metal, wood) masks."""
    xx, yy = grid()
    metal = np.zeros((RES, RES), np.float32)
    handle = np.zeros((RES, RES), np.float32)
    # hammer (left)
    handle += ((np.abs(xx - 0.3) < 0.022) & (yy > 0.3) & (yy < 0.78))
    metal += ((np.abs(yy - 0.3) < 0.04) & (xx > 0.2) & (xx < 0.4))
    # saw (right)
    blade = (xx > 0.55) & (xx < 0.8) & (yy > 0.32) & (yy < 0.7 - (xx - 0.55) * 0.5)
    teeth = (np.abs(yy - (0.7 - (xx - 0.55) * 0.5)) < 0.012) & ((np.floor(xx * 60) % 2) == 0) & (xx > 0.55) & (xx < 0.8)
    metal += blade | teeth
    handle += (xx > 0.5) & (xx < 0.58) & (yy > 0.28) & (yy < 0.42)
    return clamp01(metal), clamp01(handle) * (1 - clamp01(metal))


@recipe
def crafting_table():
    base = planks("oak")
    dark = plank_source("oak", 1.6, (0.3, 0.3))
    dark.match_color(hex_rgb("6b4a2a"), contrast=1.3, saturation=1.0)
    xx, yy = grid()
    # top: frame + 3x3 grid groove
    top = plank_source("oak", 1.4, (0.1, 0.5))
    top.match_color(hex_rgb("a8875a"), contrast=1.4)
    e = box_edge(0, 0, 1, 1)
    frame = (e < scaled(18)).astype(np.float32)
    top = mix(top, dark, frame)
    b = bevel(np.abs(e - scaled(18)), scaled(3))
    top.add_height((b - 1) * 0.2, 1.0)
    gl = np.zeros_like(xx)
    for t in (0.07 + 0.86 / 3, 0.07 + 2 * 0.86 / 3):
        gl = np.maximum(gl, smoothstep(scaled(2.5) / RES, 0, np.abs(xx - t)) * (1 - frame))
        gl = np.maximum(gl, smoothstep(scaled(2.5) / RES, 0, np.abs(yy - t)) * (1 - frame))
    top.add_height(-gl * 0.2, 1.0)
    top.albedo *= (1 - 0.45 * gl)[..., None]
    top.set_spec(smooth=0.42, smooth_var=0.4)

    def side_panel(with_tools):
        s = base.copy()
        legs = ((xx < 0.12) | (xx > 0.88) | (yy < 0.1)).astype(np.float32)
        s = mix(s, dark.rot90(1), legs)
        eb = np.minimum(np.abs(xx - 0.12), np.abs(xx - 0.88)) * RES
        eb = np.minimum(eb, np.where(xx > 0.12, np.abs(yy - 0.1) * RES, 1e3))
        s.add_height((bevel(eb, scaled(3)) - 1) * 0.15, 1.0)
        if with_tools:
            metal, handle = tool_shapes()
            tm = new_mat(color=hex_rgb("8a8d90"))
            mt = load("Metal032", zoom=4, relief=0.05)
            tm.albedo = mt.albedo * 0.8
            tm.normal = mt.normal
            tm.height = np.full((RES, RES), 1.0, np.float32)
            tm.set_spec(smooth=0.55, metal=230)
            hm = dark.copy()
            hm.height[:] = 1.0
            s.ao *= 1 - 0.5 * clamp01(blur(metal + handle, scaled(3)) - (metal + handle))
            s = mix(s, hm, handle)
            s = mix(s, tm, metal)
        return s

    return {"crafting_table_top": top, "crafting_table_side": side_panel(False),
            "crafting_table_front": side_panel(True)}


@recipe
def furnace():
    stone = m_stone()
    stone.match_color(hex_rgb("6f6f6f"), contrast=1.1, saturation=0.1)
    side = bricks_from(stone, m_mortar_grey(), "furn", rows=4, cols=2, offsets=[0, 0.5, 0, 0.5], mortar_px=4,
                       bevel_px=6)
    top = polished(m_stone(), "furn-top", smooth=0.4)
    xx, yy = grid()
    e = box_edge(0.22, 0.48, 0.78, 0.88)
    opening = smoothstep(0, scaled(1.5), e)
    lintel = clamp01(1 - np.abs(e) / scaled(6)) * (e > -scaled(6))
    front = side.copy()
    front.add_height(-lintel * 0.0, 0.0)
    interior = new_mat(color=hex_rgb("0d0b0a"))
    depth = clamp01(e / scaled(40))
    interior.height = 0.25 - depth * 0.2
    interior.normal = normal_from_height(interior.height, 1.0)
    interior.ao = 0.3 + 0.3 * (1 - depth)
    interior.set_spec(smooth=0.05, porosity=0.0)
    soot = clamp01(blur((e > -scaled(10)).astype(np.float32), scaled(6)) - opening) * (yy < 0.5)
    front.albedo *= (1 - 0.6 * soot)[..., None]
    # cast-iron grate across the opening
    bars = ((np.abs(((xx - 0.22) / 0.56 * 5) % 1 - 0.5) < 0.09) & (e > 0)).astype(np.float32)
    grate = new_mat(color=hex_rgb("2c2a28"))
    grate.height = np.full((RES, RES), 0.75, np.float32)
    bx = np.abs(((xx - 0.22) / 0.56 * 5) % 1 - 0.5) / 0.09
    grate.normal = normal_from_height(np.sqrt(clamp01(1 - bx ** 2)) * 0.1, 1.0)
    grate.set_spec(smooth=0.35, metal=230)
    interior = mix(interior, grate, bars * (yy > 0.6))
    f_off = mix(front, interior, opening)
    on = interior.copy()
    bars_on = bars * (yy > 0.6)
    fire = noise("fire", 6, 4, aniso=(1, 0.4))
    heat = clamp01((yy - 0.55) / 0.3) * (0.6 + 0.6 * fire)
    on.albedo = lerp(col("2a0f05"), lerp(col("ff6a10"), col("ffd27a"), clamp01(heat * 1.3 - 0.4)), clamp01(heat))
    on.emit = clamp01(heat * 1.2)
    glow = clamp01(blur(opening, scaled(10)) - opening) * 0.4
    on = mix(on, grate, bars_on)
    f_on = mix(front, on, opening)
    f_on.albedo = lerp(f_on.albedo, col("ff8a30"), glow * 0.5)
    return {"furnace_side": side, "furnace_top": top, "furnace_front": f_off, "furnace_front_on": f_on}


# --------------------------------------------------------------------------- #
@recipe
def quartz():
    q = load("Marble012", zoom=1.6, relief=0.03)
    q.match_color(hex_rgb("ebe5de"), contrast=0.8, saturation=0.4)
    q.set_spec(smooth=0.78, smooth_var=0.2, f0=0.045)
    side = polished(q, "qs", border=True, smooth=0.8)
    bottom = polished(q, "qb", border=False, smooth=0.8)
    qb = bricks_from(q, m_mortar_grey().match_color(hex_rgb("cfc8bf")), "qbr", rows=4, cols=2,
                     offsets=[0, 0.5, 0, 0.5], mortar_px=3, bevel_px=4)
    xx, yy = grid()
    pillar = q.rot90(1)
    flutes = 0.5 + 0.5 * np.cos(xx * 2 * np.pi * 6)
    edge_band = (xx < 0.08) | (xx > 0.92)
    pillar.add_height((flutes - 1) * 0.08 * (~edge_band), 1.0)
    pillar.set_spec(smooth=0.75, smooth_var=0.2)
    ptop = polished(q, "qpt", border=True, smooth=0.8)
    rr = np.hypot(xx - 0.5, yy - 0.5)
    ring = smoothstep(0.012, 0.0, np.abs(rr - 0.36))
    ptop.add_height(-ring * 0.1, 1.0)
    return {"quartz_block_side": side, "quartz_block_top": side.copy(), "quartz_block_bottom": bottom,
            "quartz_bricks": qb, "quartz_pillar": pillar, "quartz_pillar_top": ptop}


def plate(asset, color, metal_id, smooth, seed, zoom=2.0, contrast=0.9, sat=1.0, grooves=0, rivets=True):
    m = load(asset, zoom=zoom, relief=0.03)
    m.match_color(hex_rgb(color), contrast=contrast, saturation=sat)
    m.set_spec(smooth=smooth, smooth_var=0.4, metal=metal_id)
    e = box_edge(0, 0, 1, 1)
    b = bevel(e, scaled(6), 0.6)
    m.add_height((b - 1) * 0.15, 1.0)
    m.albedo *= (0.82 + 0.18 * b)[..., None]
    xx, yy = grid()
    for i in range(grooves):
        t = (i + 1) / (grooves + 1)
        g = smoothstep(scaled(2.0) / RES, 0, np.abs(yy - t)) * (xx > 0.08) * (xx < 0.92)
        m.add_height(-g * 0.06, 1.0)
        m.albedo *= (1 - 0.15 * g)[..., None]
    if rivets:
        for cx in (0.07, 0.93):
            for cy in (0.07, 0.93):
                d = np.hypot(xx - cx, yy - cy) * RES
                rv = clamp01(1 - (d / scaled(5)) ** 2)
                m.add_height(np.sqrt(rv) * 0.06, 1.0)
    return m


def gem_block(color_a, color_b, f0, seed, cells=4):
    xx, yy = grid()
    m = new_mat()
    # faceted tiles
    cid, u, v, edge, cw, rh = rect_cells(cells, cells)
    lu, lv = u / cw - 0.5, v / rh - 0.5
    pyramid = 1 - 2 * np.maximum(np.abs(lu), np.abs(lv))
    h = 0.9 + 0.1 * clamp01(pyramid * 2.5)
    m.height = h
    m.normal = normal_from_height(h, 0.5)
    r = rng(("gem", seed))
    shade = r.random(cid.max() + 1).astype(np.float32)[cid]
    facet = np.where(np.abs(lu) > np.abs(lv), np.sign(lu) * 0.12, np.sign(lv) * -0.08)
    c = lerp(col(color_b), col(color_a), clamp01(0.55 + facet + (shade - 0.5) * 0.25 + noise(("gn", seed), 20, 2) * 0.15))
    gap = smoothstep(scaled(2), 0, edge)
    m.albedo = c * (1 - 0.45 * gap[..., None])
    m.add_height(-gap * 0.1, 1.0)
    m.set_spec(smooth=0.94, f0=f0, sss=0.15)
    return m


@recipe
def metal_blocks():
    iron = plate("Metal032", "dcdcdc", 230, 0.6, "iron", grooves=3)
    gold = plate("Metal034", "f8d94c", 231, 0.8, "gold", contrast=0.8, grooves=0)
    nether = plate("Metal038", "3f3a3c", 230, 0.5, "nether", contrast=1.0, sat=0.3, grooves=2)
    copper = plate("Metal009", "c26a4a", 234, 0.6, "copper", contrast=0.9, rivets=False)

    def patina(m, amount, color, seed):
        p = load("Concrete034", zoom=2.5, offset=(0.3, 0.6), relief=0.05)
        p.match_color(hex_rgb(color), contrast=1.4, saturation=1.0)
        p.set_spec(smooth=0.2, f0=0.04, porosity=0.3)
        n = noise(("pat", seed), 5, 4)
        t = smoothstep(1 - amount - 0.1, 1 - amount + 0.1, n)
        return mix(m, p, t)

    exposed = patina(copper, 0.35, "a17e63", "exp")
    exposed = patina(exposed, 0.12, "6aa58a", "exp2")
    weathered = patina(copper, 0.7, "6c9a7a", "wea")
    oxidized = patina(copper, 1.05, "52a387", "oxi")

    def cut(m):
        c = m.copy()
        cid, u, v, edge, _, _ = rect_cells(2, 2)
        b = bevel(edge, scaled(5), 0.6)
        c.add_height((b - 1) * 0.15, 1.0)
        c.albedo *= (0.85 + 0.15 * b)[..., None]
        return c

    diamond = gem_block("aef6f1", "37c4bd", 0.17, "diamond", 4)
    emerald = gem_block("5df08f", "0d8a3e", 0.06, "emerald", 3)
    lapis = load("Marble012", zoom=2, offset=(0.4, 0.4), relief=0.05)
    lapis.match_color(hex_rgb("1f43a6"), contrast=1.3, saturation=1.2)
    py = smoothstep(0.88, 0.95, noise("pyrite", 60, 1))
    lapis.albedo = lerp(lapis.albedo, col("d9b65a"), py)
    lapis.set_spec(smooth=0.6, smooth_var=0.3, f0=0.05)
    lapis.metal = np.where(py > 0.5, 231, 0).astype(np.int32)
    lapis = polished(lapis, "lapis", smooth=0.62)
    red = load("Rock029", zoom=2, relief=0.3)
    red.match_color(hex_rgb("a8160b"), contrast=1.3, saturation=1.2)
    cid, f1, f2 = voronoi("redstone", 140)
    e = smoothstep(0.006, 0.0, f2 - f1)
    red.add_height(-e * 0.15, 1.0)
    red.albedo *= (1 - 0.5 * e)[..., None]
    red.set_spec(smooth=0.5, smooth_var=0.4, f0=0.05, emit=0.15)
    coal = load("Marble016", zoom=1.6, relief=0.2)
    coal.match_color(hex_rgb("1b1b1d"), contrast=1.2, saturation=0.2)
    cid, f1, f2 = voronoi("coal", 30)
    ee = smoothstep(0.008, 0.0, f2 - f1)
    coal.add_height(-ee * 0.2 + f1 * 0.5, 0.7)
    coal.set_spec(smooth=0.55, smooth_var=0.4, f0=0.05)
    return {
        "iron_block": iron, "gold_block": gold, "netherite_block": nether,
        "copper_block": copper, "exposed_copper": exposed, "weathered_copper": weathered,
        "oxidized_copper": oxidized,
        "cut_copper": cut(copper), "exposed_cut_copper": cut(exposed), "weathered_cut_copper": cut(weathered),
        "oxidized_cut_copper": cut(oxidized),
        "diamond_block": diamond, "emerald_block": emerald, "lapis_block": lapis,
        "redstone_block": red, "coal_block": coal,
    }


@recipe
def hay():
    from recipes_plants import scatter
    xx, yy = grid()

    def straw(seed, angles, scale, count):
        m = scatter("Foliage001", seed, count, scale, angle_range=angles, coverage=0.995)
        lum = m.albedo.mean(-1)
        solid = m.alpha > 0.5
        mu = lum[solid].mean() if solid.any() else 0.5
        rel = clamp01(lum / (mu + 1e-6))
        m.albedo = clamp01(rel[..., None] * hex_rgb("d4b04a") * (0.55 + 0.45 * m.ao[..., None]))
        m.albedo = np.where(solid[..., None], m.albedo, col("4a3810"))
        m.height = np.where(solid, 0.55 + 0.45 * m.meta["layer"], 0.4)
        m.alpha = None
        m.set_spec(smooth=0.35, f0=0.04, porosity=0.6)
        return m

    side = straw("hay-side", (84, 96), (0.9, 1.4), 900)
    band = (np.abs(yy - 0.22) < 0.045) | (np.abs(yy - 0.78) < 0.045)
    rope = noise("rope", 30, 2, aniso=(0.2, 1.0))
    twist = 0.5 + 0.5 * np.sin((xx * 40 + yy * 10) * np.pi)
    side.albedo = np.where(band[..., None], lerp(col("4a2410"), col("8a4a24"), (rope * 0.5 + twist * 0.5)[..., None]),
                           side.albedo)
    side.height = np.where(band, 0.97 + 0.03 * twist, side.height)
    side.normal = np.where(band[..., None], normal_from_height(side.height, 1.0), side.normal)
    top = straw("hay-top", (0, 360), (0.25, 0.45), 1500)
    return {"hay_block_side": side, "hay_block_top": top}
