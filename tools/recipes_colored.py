"""16-colour families: wool, concrete, concrete powder, terracotta, stained glass."""
import functools

import numpy as np

from pbrlib import RES, bevel, clamp01, hex_rgb, lerp, load, mix, new_mat, noise, scaled

R = {}

COLORS = ["white", "orange", "magenta", "light_blue", "yellow", "lime", "pink", "gray", "light_gray", "cyan",
          "purple", "blue", "brown", "green", "red", "black"]

#            wool      concrete  powder    terracotta stained glass
PALETTE = {
    "white":      ("e9ecec", "cfd5d6", "e1e3e3", "d1b2a1", "ffffff"),
    "orange":     ("f07613", "e06100", "e3831f", "a15325", "d87f33"),
    "magenta":    ("bd44b3", "a9309f", "c053b8", "95586c", "b24cd8"),
    "light_blue": ("3aafd9", "2389c6", "4ab4d5", "716d8a", "6699d8"),
    "yellow":     ("f8c627", "f0af15", "e8c736", "ba8523", "e5e533"),
    "lime":       ("70b919", "5ea818", "7dbd29", "677535", "7fcc19"),
    "pink":       ("ed8dac", "d5658e", "e499b5", "a14e4e", "f27fa5"),
    "gray":       ("3e4447", "36393d", "4c5154", "392a23", "4c4c4c"),
    "light_gray": ("8e8e86", "7d7d73", "9a9a94", "876a61", "999999"),
    "cyan":       ("158991", "157788", "24939d", "575b5b", "4c7f99"),
    "purple":     ("792aac", "64209c", "8337b1", "764656", "7f3fb2"),
    "blue":       ("35399d", "2c2e8f", "4649a6", "4a3b5b", "334cb2"),
    "brown":      ("724728", "603b1f", "7d5435", "4d3323", "664c33"),
    "green":      ("546d1b", "495b24", "61772c", "4c532a", "667f33"),
    "red":        ("a12722", "8e2020", "a83632", "8f3d2e", "993333"),
    "black":      ("141519", "080a0f", "191a1f", "251610", "191919"),
}


def recolor(base, color, contrast=1.0):
    """Recolour a neutral base keeping its relative light/dark detail."""
    m = base.copy()
    c = hex_rgb(color)
    lum = m.albedo.mean(-1)
    rel = lum / (lum.mean() + 1e-6) - 1
    m.albedo = clamp01(c[None, None, :] * (1 + rel[..., None] * contrast))
    return m


@functools.lru_cache(maxsize=None)
def bases():
    wool = load("Fabric030", zoom=2.5, relief=0.35)
    wool.set_spec(smooth=0.06, smooth_var=0.3, f0=0.03, sss=0.25)
    # felted fibres: soft lumps on top of the weave
    lump = noise("wool-lump", 7, 4)
    wool.add_height((lump - 0.5) * 0.25, 0.8)
    concrete = load("Concrete034", zoom=2.0, relief=0.05)
    concrete.set_spec(smooth=0.35, smooth_var=0.4, f0=0.04, porosity=0.3)
    powder = load("Ground093C", zoom=2.2, offset=(0.2, 0.7), relief=0.2)
    powder.set_spec(smooth=0.1, smooth_var=0.3, f0=0.04, porosity=0.6)
    terra = load("Rock041", zoom=1.6, offset=(0.4, 0.2), relief=0.07)
    terra.set_spec(smooth=0.3, smooth_var=0.4, f0=0.04, porosity=0.45)
    return wool, concrete, powder, terra


def stained(color):
    m = new_mat(color=hex_rgb(color))
    yy, xx = (np.mgrid[0:RES, 0:RES].astype(np.float32) + 0.5) / RES
    e = np.minimum(np.minimum(xx, 1 - xx), np.minimum(yy, 1 - yy)) * RES
    frame = (e < scaled(5)).astype(np.float32)
    smudge = noise(("smudge", color), 4, 4)
    m.albedo = clamp01(hex_rgb(color)[None, None, :] * (0.9 + 0.2 * smudge[..., None]))
    m.albedo = lerp(m.albedo, m.albedo * 0.75, frame)
    m.alpha = np.where(frame > 0.5, 0.95, 0.45 + 0.1 * smudge).astype(np.float32)
    b = bevel(e, scaled(2.5), 0.8)
    m.add_height((b - 1) * 0.2 * frame, 1.0)
    m.set_spec(smooth=0.96, f0=0.04)
    return m


@functools.lru_cache(maxsize=None)
def _all():
    wool, concrete, powder, terra = bases()
    out = {}
    for c in COLORS:
        w, co, po, te, gl = PALETTE[c]
        out[f"{c}_wool"] = recolor(wool, w, 1.2)
        out[f"{c}_concrete"] = recolor(concrete, co, 0.8)
        out[f"{c}_concrete_powder"] = recolor(powder, po, 1.0)
        out[f"{c}_terracotta"] = recolor(terra, te, 1.0)
        sg = stained(gl)
        out[f"{c}_stained_glass"] = ("opts", {"flat_pom": True}, sg)
        out[f"{c}_stained_glass_pane_top"] = ("opts", {"flat_pom": True}, sg.copy())
    out["terracotta"] = recolor(terra, "985e43", 1.0)
    return out


def family(suffix):
    def fn():
        return {k: v for k, v in _all().items() if k.endswith(suffix) or (suffix == "_terracotta" and k == "terracotta")}
    return fn


for _s in ("_wool", "_concrete", "_concrete_powder", "_terracotta", "_stained_glass", "_stained_glass_pane_top"):
    R["colored" + _s] = family(_s)
