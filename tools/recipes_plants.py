"""Grass blocks, soils with fringes, leaves and grass plants.

Leaves and grass blades are built from CC0 photo atlases: every leaf of the atlas
is cut out by its opacity mask and scattered (wrapping) with random rotation and
scale, so the result is a seamless cut-out texture with real leaf photos.
"""
import functools

import numpy as np
from PIL import Image
from scipy import ndimage

import pbrlib
from pbrlib import (RES, blur, clamp01, hex_rgb, lerp, load, load_source, mix, new_mat, noise, normal_from_height,
                    normalize_v, rng, scaled, smoothstep)
from recipes_natural import m_dirt

R = {}


def recipe(fn):
    R[fn.__name__] = fn
    return fn


# --------------------------------------------------------------------------- #
# Atlas sprites
# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=None)
def sprites(asset, min_area=400):
    src = load_source(asset)
    op = src["opacity"]
    lab, n = ndimage.label(op > 0.5)
    objs = ndimage.find_objects(lab)
    out = []
    for i, sl in enumerate(objs):
        if sl is None:
            continue
        mask = lab[sl] == i + 1
        if mask.sum() < min_area:
            continue
        pad = 2
        y0, y1 = max(sl[0].start - pad, 0), min(sl[0].stop + pad, op.shape[0])
        x0, x1 = max(sl[1].start - pad, 0), min(sl[1].stop + pad, op.shape[1])
        a = op[y0:y1, x0:x1] * (lab[y0:y1, x0:x1] == i + 1)
        out.append({
            "alpha": a.astype(np.float32),
            "albedo": src["albedo"][y0:y1, x0:x1],
            "normal": src["normal"][y0:y1, x0:x1],
            "height": src["height"][y0:y1, x0:x1],
            "rough": src["rough"][y0:y1, x0:x1],
        })
    return out


def _transform(spr, scale, angle, flip):
    """Scale + rotate a sprite (angle in degrees, CCW).  Rotates normal vectors too."""
    h, w = spr["alpha"].shape
    nw, nh = max(2, int(w * scale)), max(2, int(h * scale))

    def tf(a, resample=Image.BILINEAR):
        im = Image.fromarray(a.astype(np.float32), "F").resize((nw, nh), Image.LANCZOS)
        if flip:
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        im = im.rotate(angle, resample=resample, expand=True)
        return np.asarray(im, np.float32)

    out = {"alpha": clamp01(tf(spr["alpha"])), "height": tf(spr["height"]), "rough": tf(spr["rough"])}
    out["albedo"] = np.stack([tf(spr["albedo"][..., c]) for c in range(3)], -1)
    nx, ny, nz = (tf(spr["normal"][..., c]) for c in range(3))
    if flip:
        nx = -nx
    t = np.deg2rad(angle)
    c, s = np.cos(t), np.sin(t)
    out["normal"] = normalize_v(np.stack([nx * c + ny * s, -nx * s + ny * c, np.maximum(nz, 0.05)], -1))
    return out


def scatter(asset, seed, count, scale_range, coverage=None, angle_range=(0, 360), y_bias=None,
            anchor_bottom=False, size=None):
    """Scatter atlas sprites on a wrapping canvas.  Returns a Mat with alpha."""
    size = size or RES
    sp = sprites(asset)
    r = rng(("scatter", asset, seed))
    src_size = load_source(asset)["albedo"].shape[0]
    alb = np.zeros((size, size, 3), np.float32)
    alpha = np.zeros((size, size), np.float32)
    nrm = np.zeros((size, size, 3), np.float32)
    nrm[..., 2] = 1
    hgt = np.zeros((size, size), np.float32)
    rough = np.ones((size, size), np.float32)
    layer = np.zeros((size, size), np.float32)
    i = 0
    while i < count:
        s = sp[r.integers(len(sp))]
        sc = r.uniform(*scale_range) * size / src_size
        ang = r.uniform(*angle_range)
        t = _transform(s, sc, ang, bool(r.integers(2)))
        th, tw = t["alpha"].shape
        if anchor_bottom:
            x = int(r.integers(size)) - tw // 2
            y = int(size - th * r.uniform(0.85, 1.0))
            offsets = [(0, 0), (-size, 0), (size, 0)]
        else:
            x = int(r.integers(size))
            y = int(r.integers(size)) if y_bias is None else int(y_bias(r) * size)
            offsets = [(ox, oy) for ox in (0, -size) for oy in (0, -size)]
        depth = i / max(count - 1, 1)
        for ox, oy in offsets:
            X, Y = x + ox, y + oy
            xs0, ys0 = max(X, 0), max(Y, 0)
            xs1, ys1 = min(X + tw, size), min(Y + th, size)
            if xs1 <= xs0 or ys1 <= ys0:
                continue
            sl = (slice(ys0, ys1), slice(xs0, xs1))
            tl = (slice(ys0 - Y, ys1 - Y), slice(xs0 - X, xs1 - X))
            a = t["alpha"][tl]
            m = a > 0.5
            alb[sl][m] = t["albedo"][tl][m]
            nrm[sl][m] = t["normal"][tl][m]
            hgt[sl][m] = 0.6 * depth + 0.4 * t["height"][tl][m]
            rough[sl][m] = t["rough"][tl][m]
            layer[sl][m] = depth
            alpha[sl] = np.maximum(alpha[sl], a)
        i += 1
        if coverage is not None and i % 8 == 0 and (alpha > 0.5).mean() >= coverage:
            break
    m = new_mat(size)
    m.albedo = clamp01(alb)
    m.alpha = (alpha > 0.5).astype(np.float32)
    m.normal = normalize_v(nrm)
    m.height = hgt
    m.smooth = clamp01(1 - rough)
    # leaves underneath are shadowed by the ones on top
    m.ao = clamp01(0.55 + 0.45 * layer)
    m.meta["layer"] = layer
    return m


# --------------------------------------------------------------------------- #
# Grass block & co
# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=None)
def _grass_top():
    m = load("Grass004", zoom=1.6, relief=0.45)
    m.grayscale(mean=0.6, contrast=1.35)
    return m.set_spec(smooth=0.22, smooth_var=0.5, f0=0.03, sss=0.35)


def grass_top():
    return _grass_top().copy()


def fringe_mask(seed, depth=0.2, spikes=0.2, spike_scale=40):
    """Hanging fringe (grass, snow, podzol) at the top of a side texture."""
    yy = (np.mgrid[0:RES, 0:RES][0].astype(np.float32) + 0.5) / RES
    wave = noise(("fr", seed), 4, 3)[RES // 3]
    jag = noise(("frs", seed), spike_scale, 2)[RES // 2]
    fine = noise(("frf", seed), spike_scale * 2.5, 1)[RES // 5]
    lim = depth + (wave - 0.5) * 0.07 + clamp01((jag - 0.35) * 1.6) ** 1.5 * spikes \
        + clamp01((fine - 0.55) * 2.5) * spikes * 0.5
    return clamp01((lim[None, :] - yy) * RES / 1.2)


@recipe
def grass_block():
    top = grass_top()
    dirt = m_dirt()
    mask = fringe_mask("grass")
    # untinted base: dirt with a dull green fringe (visible only far away / without overlay)
    side = dirt.copy()
    side.albedo = lerp(side.albedo, np.ones_like(side.albedo) * hex_rgb("5d7a3a") * (0.8 + 0.4 * top.albedo), mask)
    side.ao *= 1 - 0.3 * clamp01(blur(mask, scaled(3)) - mask)
    # overlay: grey grass seen from the side, cut out by the fringe
    ov = load("Grass004", zoom=1.6, offset=(0.4, 0.1), relief=0.3)
    ov.grayscale(mean=0.62, contrast=1.3)
    streak = noise("grass-streak", 30, 2, aniso=(1.0, 0.1))
    ov.albedo *= (0.85 + 0.3 * streak)[..., None]
    ov.alpha = (mask > 0.5).astype(np.float32)
    ov.set_spec(smooth=0.22, f0=0.03, sss=0.35)
    # shadow under the overhanging grass
    under = clamp01(blur(mask, scaled(4)) * 1.5) * (1 - mask)
    side.albedo *= (1 - 0.35 * under)[..., None]
    snow_mask = fringe_mask("snow", depth=0.18, spikes=0.06, spike_scale=12)
    sn = load("Snow006", zoom=1.5, relief=0.12)
    sn.match_color(hex_rgb("f3f8fa"), contrast=1.2, saturation=0.4)
    sn.set_spec(smooth=0.45, f0=0.02, sss=0.6)
    sn.height = sn.height * 0.3 + 0.7
    snow_side = mix(dirt, sn, snow_mask)
    snow_side.ao *= 1 - 0.3 * clamp01(blur(snow_mask, scaled(3)) - snow_mask)
    return {
        "grass_block_top": top,
        "grass_block_side": side,
        "grass_block_side_overlay": ("opts", {"flat_pom": True}, ov),
        "grass_block_snow": snow_side,
    }


@recipe
def podzol_path_farmland():
    dirt = m_dirt()
    pod = load("ScatteredLeaves009", zoom=1.6, relief=0.45)
    pod.match_color(hex_rgb("5c3f1c"), contrast=1.2, saturation=0.9)
    pod.set_spec(smooth=0.12, smooth_var=0.5, f0=0.03, porosity=0.7)
    pmask = fringe_mask("podzol", depth=0.18, spikes=0.08, spike_scale=25)
    pod_side = mix(dirt, pod, pmask)

    path = load("Ground109", zoom=1.6, relief=0.18)
    path.match_color(hex_rgb("947a45"), contrast=1.1, saturation=0.9)
    path.set_spec(smooth=0.15, smooth_var=0.5, f0=0.04, porosity=0.5)
    yy = (np.mgrid[0:RES, 0:RES][0] + 0.5) / RES
    path_mask = clamp01((0.18 + (noise("pathfr", 6, 2)[0] - 0.5) * 0.05 - yy) * RES / 1.5)
    path_side = mix(dirt, path, path_mask)
    # the path block is 15/16 tall: the top row of its side texture is cut off
    path_side.ao *= 1 - 0.25 * clamp01(blur(path_mask, scaled(3)) - path_mask)

    farm = dirt.copy()
    furrow = 0.5 + 0.5 * np.cos(yy * 2 * np.pi * 4)
    farm.add_height((furrow - 1) * 0.35, 1.0)
    farm.albedo *= (0.8 + 0.2 * furrow)[..., None]
    moist = farm.copy()
    moist.albedo = clamp01(moist.albedo * 0.55)
    moist.set_spec(smooth=0.5, smooth_var=0.4, porosity=0.2)
    return {"podzol_top": pod, "podzol_side": pod_side, "dirt_path_top": path, "dirt_path_side": path_side,
            "farmland": farm, "farmland_moist": moist}


@recipe
def mycelium():
    dirt = m_dirt()
    top = load("Ground037", zoom=1.6, relief=0.3)
    top.match_color(hex_rgb("6f6265"), contrast=1.2, saturation=0.4)
    fil = noise("myc", 50, 2)
    top.albedo = lerp(top.albedo, np.ones_like(top.albedo) * hex_rgb("9c8f97"), smoothstep(0.7, 0.85, fil) * 0.6)
    top.set_spec(smooth=0.12, f0=0.03, porosity=0.6)
    mask = fringe_mask("myc", depth=0.16, spikes=0.06, spike_scale=20)
    return {"mycelium_top": top, "mycelium_side": mix(dirt, top, mask)}


@recipe
def moss():
    m = load("Moss002", zoom=1.6, relief=0.5)
    m.match_color(hex_rgb("596e2d"), contrast=1.2, saturation=1.0)
    m.set_spec(smooth=0.08, smooth_var=0.5, f0=0.03, sss=0.45, porosity=0.9)
    return {"moss_block": m}


# --------------------------------------------------------------------------- #
# Leaves
# --------------------------------------------------------------------------- #
LEAVES = {
    # name: atlas, leaf size range (fraction of the atlas leaf -> block), coverage, tinted, colour (untinted)
    "oak_leaves":      ("LeafSet024", (0.55, 0.85), 0.82, True, None),
    "spruce_leaves":   ("LeafSet019", (0.45, 0.75), 0.80, True, None),
    "birch_leaves":    ("LeafSet022", (0.45, 0.7), 0.78, True, None),
    "jungle_leaves":   ("LeafSet023", (0.6, 0.95), 0.84, True, None),
    "acacia_leaves":   ("LeafSet013", (0.7, 1.0), 0.76, True, None),
    "dark_oak_leaves": ("LeafSet024", (0.7, 1.0), 0.86, True, None),
    "mangrove_leaves": ("LeafSet022", (0.55, 0.8), 0.82, True, None),
    "cherry_leaves":   ("LeafSet024", (0.5, 0.75), 0.84, False, "e9a7c0"),
    "azalea_leaves":   ("LeafSet017", (0.4, 0.6), 0.84, False, "617a2b"),
    "pale_oak_leaves": ("LeafSet017", (0.45, 0.65), 0.82, False, "8f9a84"),
}


def leaves(name):
    asset, scale, cov, tinted, color = LEAVES[name]
    m = scatter(asset, name, 400, scale, coverage=cov)
    solid = m.alpha > 0.5
    if tinted:
        lum = m.albedo.mean(-1)
        mu = lum[solid].mean() if solid.any() else 0.5
        g = clamp01((lum - mu) * 1.4 + 0.56)
        m.albedo = np.repeat(g[..., None], 3, -1)
    else:
        lum = m.albedo.mean(-1)
        mu = lum[solid].mean() if solid.any() else 0.5
        rel = clamp01(lum / (mu + 1e-6))
        m.albedo = clamp01(rel[..., None] * hex_rgb(color))
    m.albedo *= (0.65 + 0.35 * m.ao)[..., None]
    m.set_spec(smooth=0.42, smooth_var=0.5, f0=0.03, sss=0.7)
    if name == "cherry_leaves":
        # blossoms: a few bright petals
        pet = scatter("LeafSet022", "cherry-petals", 40, (0.18, 0.26), coverage=None)
        pm = pet.alpha > 0.5
        m.albedo[pm] = hex_rgb("f7cde0") * (0.85 + 0.15 * pet.albedo[pm].mean(-1, keepdims=True))
        m.alpha = np.maximum(m.alpha, pet.alpha)
        m.normal[pm] = pet.normal[pm]
        m.ao[pm] = 1.0
        m.sss[pm] = 0.8
    return ("opts", {"flat_pom": True, "normal_ao": False}, m)


for _n in LEAVES:
    R[_n] = (lambda n: (lambda: {n: leaves(n)}))(_n)


# --------------------------------------------------------------------------- #
# Grass plants (cross models)
# --------------------------------------------------------------------------- #
def blades(seed, count, scale, height_frac, color=None):
    m = scatter("Foliage001", seed, count, scale, angle_range=(-12, 12), anchor_bottom=True)
    solid = m.alpha > 0.5
    lum = m.albedo.mean(-1)
    mu = lum[solid].mean() if solid.any() else 0.5
    if color is None:
        g = clamp01((lum - mu) * 1.3 + 0.55)
        m.albedo = np.repeat(g[..., None], 3, -1)
    else:
        m.albedo = clamp01((lum / (mu + 1e-6))[..., None] * hex_rgb(color))
    yy = (np.mgrid[0:RES, 0:RES][0] + 0.5) / RES
    m.albedo *= (0.6 + 0.4 * (1 - yy) ** 0.5)[..., None]
    m.set_spec(smooth=0.35, f0=0.03, sss=0.75)
    return ("opts", {"flat_pom": True, "normal_ao": False}, m)


@recipe
def grass_plants():
    short = blades("short", 70, (0.6, 1.0), 0.6)
    tall_bottom = blades("tallb", 90, (1.0, 1.4), 1.0)
    tall_top = blades("tallt", 60, (0.6, 1.0), 0.7)
    fern = scatter("LeafSet019", "fern", 14, (0.6, 0.9), angle_range=(60, 120), anchor_bottom=True)
    lum = fern.albedo.mean(-1)
    solid = fern.alpha > 0.5
    mu = lum[solid].mean() if solid.any() else 0.5
    fern.albedo = np.repeat(clamp01((lum - mu) * 1.3 + 0.55)[..., None], 3, -1)
    fern.set_spec(smooth=0.35, f0=0.03, sss=0.75)
    fern = ("opts", {"flat_pom": True, "normal_ao": False}, fern)
    return {"short_grass": short, "grass": short, "tall_grass_bottom": tall_bottom, "tall_grass_top": tall_top,
            "fern": fern}
