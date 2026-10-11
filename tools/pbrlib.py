"""Core library of the texture generator.

A block texture is described by a `Mat` (material) holding float32 maps of the
same size.  Everything is tileable: noise is generated in the frequency domain,
photo sources are seamless and every geometric operation wraps around.

Conventions
-----------
* albedo  - HxWx3, sRGB, 0..1
* height  - HxW, 1 = surface top, 0 = deepest point (25 % of a block in labPBR)
* normal  - HxWx3 unit vectors, DirectX / labPBR convention: +x right, +y DOWN
            (image rows), +z out of the surface
* ao      - HxW, 1 = unoccluded
* smooth  - HxW perceptual smoothness (labPBR red channel)
* f0      - HxW dielectric reflectance 0..0.9 (labPBR green 0..229)
* metal   - HxW int, 0 = dielectric, 230..255 = labPBR metal id
* porosity- HxW 0..1 (labPBR blue 0..64)
* sss     - HxW 0..1 (labPBR blue 65..255)
* emit    - HxW 0..1 (labPBR specular alpha 0..254)
* alpha   - HxW or None (albedo alpha, e.g. leaves, glass)
"""
from __future__ import annotations

import functools
import os
from dataclasses import dataclass, field, replace

import numpy as np
from PIL import Image
from scipy import ndimage

import fetch

# --------------------------------------------------------------------------- #
# Global settings (set by build.py)
# --------------------------------------------------------------------------- #
RES = 256          # output resolution of a block face
QUALITY = "1K-JPG"  # ambientCG source quality


def set_resolution(res):
    global RES, QUALITY
    RES = res
    QUALITY = "2K-JPG" if res > 256 else "1K-JPG"


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def rng(seed):
    return np.random.default_rng(abs(hash(str(seed))) % (2 ** 32))


def clamp01(a):
    return np.clip(a, 0.0, 1.0)


def smoothstep(e0, e1, x):
    t = clamp01((x - e0) / (e1 - e0 + 1e-9))
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    if isinstance(t, np.ndarray) and isinstance(a, np.ndarray) and a.ndim == 3 and t.ndim == 2:
        t = t[..., None]
    return a + (b - a) * t


def normalize_v(n):
    return n / np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-6)


def flat_normal(h, w):
    n = np.zeros((h, w, 3), np.float32)
    n[..., 2] = 1
    return n


def stretch(a, lo=1, hi=99):
    """Normalise a map to 0..1 using percentiles."""
    p0, p1 = np.percentile(a, [lo, hi])
    return clamp01((a - p0) / (p1 - p0 + 1e-6)).astype(np.float32)


def blur(a, sigma):
    if sigma <= 0:
        return a
    if a.ndim == 3:
        return np.stack([ndimage.gaussian_filter(a[..., c], sigma, mode="wrap") for c in range(a.shape[2])], -1)
    return ndimage.gaussian_filter(a, sigma, mode="wrap")


def luminance(rgb):
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722


def hex_rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], np.float32)


# --------------------------------------------------------------------------- #
# Tileable procedural noise
# --------------------------------------------------------------------------- #
def noise(seed, scale=8.0, octaves=5, persistence=0.5, size=None, aniso=(1.0, 1.0)):
    """Periodic fractal noise in 0..1.  `scale` is the base feature count per tile.

    Built by filtering white noise in the frequency domain, so it tiles perfectly.
    `aniso` stretches features: (2, 1) -> features twice as long along x.
    """
    size = size or RES
    r = rng(("noise", seed, scale, octaves, persistence, size, aniso))
    white = r.standard_normal((size, size))
    f = np.fft.fft2(white)
    fy = np.fft.fftfreq(size)[:, None] * size * aniso[1]
    fx = np.fft.fftfreq(size)[None, :] * size * aniso[0]
    k = np.sqrt(fx * fx + fy * fy) + 1e-6
    amp = np.zeros_like(k)
    for o in range(octaves):
        fc = scale * (2 ** o)
        amp += (persistence ** o) * np.exp(-((np.log(k / fc)) ** 2) / (2 * 0.35 ** 2))
    out = np.real(np.fft.ifft2(f * amp))
    return stretch(out, 0.5, 99.5)


def warp(a, dx, dy):
    """Displace a map by per-pixel offsets in pixels (wrap)."""
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    coords = [(yy + dy) % h, (xx + dx) % w]
    if a.ndim == 3:
        return np.stack([ndimage.map_coordinates(a[..., c], coords, order=1, mode="grid-wrap")
                         for c in range(a.shape[2])], -1)
    return ndimage.map_coordinates(a, coords, order=1, mode="grid-wrap")


def voronoi(seed, n_points, size=None, jitter=1.0, aniso=(1.0, 1.0)):
    """Tileable Voronoi on a jittered grid.  Returns (cell_id, f1, f2), distances in tile units."""
    size = size or RES
    g = max(1, int(round(np.sqrt(n_points))))
    r = rng(("vor", seed, n_points, size))
    jit = (0.5 + (r.random((g, g, 2)) - 0.5) * jitter).astype(np.float32)
    yy, xx = (np.mgrid[0:size, 0:size].astype(np.float32) + 0.5) / size * g
    cy, cx = np.floor(yy).astype(np.int32), np.floor(xx).astype(np.int32)
    f1 = np.full((size, size), 1e9, np.float32)
    f2 = np.full((size, size), 1e9, np.float32)
    cid = np.zeros((size, size), np.int32)
    for oy in (-1, 0, 1):
        for ox in (-1, 0, 1):
            ny, nx = cy + oy, cx + ox
            wy, wx = ny % g, nx % g
            px = nx + jit[wy, wx, 0]
            py = ny + jit[wy, wx, 1]
            dx = (xx - px) * aniso[0]
            dy = (yy - py) * aniso[1]
            d = np.sqrt(dx * dx + dy * dy)
            closer = d < f1
            f2 = np.where(closer, f1, np.minimum(f2, d))
            cid = np.where(closer, wy * g + wx, cid)
            f1 = np.where(closer, d, f1)
    return cid, f1 / g, f2 / g


def grains(seed, n, palette, weights=None, size=None):
    """Igneous-rock style crystal mosaic.  Returns (rgb, cell_id, f1, f2, pick)."""
    size = size or RES
    cid, f1, f2 = voronoi(("grain", seed), n, size)
    r = rng(("grainc", seed))
    k = len(palette)
    w = np.asarray(weights if weights is not None else [1] * k, np.float64)
    pick = r.choice(k, size=cid.max() + 1, p=w / w.sum())
    pal = np.stack([hex_rgb(c) for c in palette])
    var = (1 + (r.random(cid.max() + 1) - 0.5) * 0.25).astype(np.float32)
    rgb = clamp01(pal[pick][cid] * var[cid][..., None])
    return rgb, cid, f1, f2, pick[cid]


# --------------------------------------------------------------------------- #
# Material
# --------------------------------------------------------------------------- #
SCALAR_FIELDS = ("height", "ao", "smooth", "f0", "porosity", "sss", "emit")


@dataclass
class Mat:
    albedo: np.ndarray
    height: np.ndarray
    normal: np.ndarray
    ao: np.ndarray
    smooth: np.ndarray
    f0: np.ndarray
    metal: np.ndarray
    porosity: np.ndarray
    sss: np.ndarray
    emit: np.ndarray
    alpha: np.ndarray | None = None
    meta: dict = field(default_factory=dict)

    @property
    def size(self):
        return self.height.shape[0]

    def copy(self):
        return Mat(**{k: (v.copy() if isinstance(v, np.ndarray) else (dict(v) if isinstance(v, dict) else v))
                      for k, v in self.__dict__.items()})

    # -- geometric ops (all wrap-aware) ------------------------------------ #
    def _apply(self, fn, normal_fn=None):
        out = {}
        for k, v in self.__dict__.items():
            if k == "normal":
                out[k] = normal_fn(v) if normal_fn else fn(v)
            elif isinstance(v, np.ndarray):
                out[k] = fn(v)
            else:
                out[k] = v
        return Mat(**out)

    def roll(self, dx, dy):
        return self._apply(lambda a: np.roll(a, (int(dy), int(dx)), axis=(0, 1)))

    def rot90(self, k=1):
        """Rotate counter-clockwise k*90 deg, rotating tangent normals as well."""
        k %= 4
        if k == 0:
            return self.copy()

        def nf(n):
            n = np.rot90(n, k, axes=(0, 1)).copy()
            for _ in range(k):
                x, y = n[..., 0].copy(), n[..., 1].copy()
                n[..., 0], n[..., 1] = y, -x
            return n
        return self._apply(lambda a: np.rot90(a, k, axes=(0, 1)).copy(), nf)

    def flip_x(self):
        def nf(n):
            n = n[:, ::-1].copy()
            n[..., 0] *= -1
            return n
        return self._apply(lambda a: a[:, ::-1].copy(), nf)

    def resize(self, size):
        if size == self.size:
            return self.copy()
        return self._apply(lambda a: resize_wrap(a, size), lambda n: normalize_v(resize_wrap(n, size)))

    # -- height / normal helpers ------------------------------------------- #
    def add_height(self, delta, strength=1.0):
        """Add a height layer and bend the normals accordingly."""
        self.height = self.height + delta
        if strength:
            self.normal = blend_normals(self.normal, normal_from_height(delta, strength))
        return self

    def set_relief(self, relief):
        """Rescale the height so it spans `relief` of the POM depth (top stays at 1)."""
        h = stretch(self.height, 0.5, 99.8)
        self.height = 1 - relief * (1 - h)
        return self

    # -- colour helpers ---------------------------------------------------- #
    def tint(self, color, amount=1.0):
        """Recolour keeping luminance detail: albedo -> lum * colour / mean."""
        color = np.asarray(color, np.float32)
        lum = luminance(self.albedo)
        rel = lum / (lum.mean() + 1e-6)
        tinted = clamp01(rel[..., None] * color[None, None, :])
        self.albedo = lerp(self.albedo, tinted, amount)
        return self

    def match_color(self, mean, contrast=1.0, saturation=1.0):
        """Shift mean colour to `mean` (sRGB), scale contrast and saturation."""
        mean = np.asarray(mean, np.float32)
        a = self.albedo
        m = a.reshape(-1, 3).mean(0)
        a = (a - m) * contrast + mean
        lum = luminance(a)[..., None]
        a = lum + (a - lum) * saturation
        self.albedo = clamp01(a)
        return self

    def adjust(self, brightness=1.0, contrast=1.0, saturation=1.0, gamma=1.0):
        a = clamp01(self.albedo) ** gamma
        m = a.mean()
        a = (a - m) * contrast + m
        lum = luminance(a)[..., None]
        a = lum + (a - lum) * saturation
        self.albedo = clamp01(a * brightness)
        return self

    def grayscale(self, mean=0.55, contrast=1.0):
        """Biome-tinted textures (grass, leaves) must be grey in vanilla."""
        lum = luminance(self.albedo)
        lum = (lum - lum.mean()) * contrast + mean
        self.albedo = np.repeat(clamp01(lum)[..., None], 3, axis=2)
        return self

    def set_spec(self, smooth=None, f0=None, metal=None, porosity=None, sss=None, emit=None,
                 smooth_var=None):
        sz = self.height.shape
        if smooth is not None:
            if smooth_var is not None:
                # keep the photo roughness variation but recentre it
                s = self.smooth
                s = (s - s.mean()) * smooth_var + smooth
                self.smooth = clamp01(s)
            else:
                self.smooth = np.full(sz, smooth, np.float32) if np.isscalar(smooth) else smooth
        if f0 is not None:
            self.f0 = np.full(sz, f0, np.float32) if np.isscalar(f0) else f0
        if metal is not None:
            self.metal = np.full(sz, metal, np.int32) if np.isscalar(metal) else metal
        if porosity is not None:
            self.porosity = np.full(sz, porosity, np.float32) if np.isscalar(porosity) else porosity
        if sss is not None:
            self.sss = np.full(sz, sss, np.float32) if np.isscalar(sss) else sss
        if emit is not None:
            self.emit = np.full(sz, emit, np.float32) if np.isscalar(emit) else emit
        return self


def new_mat(size=None, color=(0.5, 0.5, 0.5)):
    size = size or RES
    sz = (size, size)
    return Mat(
        albedo=np.ones(sz + (3,), np.float32) * np.asarray(color, np.float32),
        height=np.ones(sz, np.float32),
        normal=flat_normal(size, size),
        ao=np.ones(sz, np.float32),
        smooth=np.full(sz, 0.2, np.float32),
        f0=np.full(sz, 0.04, np.float32),
        metal=np.zeros(sz, np.int32),
        porosity=np.zeros(sz, np.float32),
        sss=np.zeros(sz, np.float32),
        emit=np.zeros(sz, np.float32),
    )


def mix(a: Mat, b: Mat, t):
    """Blend two materials with a mask t (0 -> a, 1 -> b)."""
    t = clamp01(np.asarray(t, np.float32))
    if t.ndim == 0:
        t = np.full(a.height.shape, float(t), np.float32)
    out = {}
    for k, va in a.__dict__.items():
        vb = getattr(b, k)
        if k == "metal":
            out[k] = np.where(t > 0.5, vb, va)
        elif k == "normal":
            out[k] = normalize_v(lerp(va, vb, t))
        elif k == "alpha":
            if va is None and vb is None:
                out[k] = None
            else:
                va2 = va if va is not None else np.ones_like(t)
                vb2 = vb if vb is not None else np.ones_like(t)
                out[k] = lerp(va2, vb2, t)
        elif k == "meta":
            out[k] = dict(va)
        else:
            out[k] = lerp(va, vb, t)
    return Mat(**out)


def height_mix(a: Mat, b: Mat, t, sharp=8.0):
    """Height-aware blend: b shows where (b.height + t) wins over a.height."""
    hb = b.height + (t - 0.5) * 2.0
    mask = clamp01((hb - a.height) * sharp + 0.5)
    mask = np.where(t <= 0.001, 0.0, mask)
    return mix(a, b, mask)


# --------------------------------------------------------------------------- #
# Resampling / normals
# --------------------------------------------------------------------------- #
def resize_wrap(a, size):
    """Wrap-aware Lanczos resize (keeps tiles seamless)."""
    h = a.shape[0]
    if h == size:
        return a.copy()
    pad = max(4, h // 16)
    big = np.pad(a, ((pad, pad), (pad, pad)) + ((0, 0),) * (a.ndim - 2), mode="wrap")
    scale = size / h
    out_big = int(round(big.shape[0] * scale))
    chans = [big] if big.ndim == 2 else [big[..., c] for c in range(big.shape[2])]
    res = []
    for c in chans:
        im = Image.fromarray(c.astype(np.float32), mode="F")
        im = im.resize((out_big, out_big), Image.LANCZOS)
        res.append(np.asarray(im, np.float32))
    r = res[0] if a.ndim == 2 else np.stack(res, -1)
    p = int(round(pad * scale))
    return r[p:p + size, p:p + size].copy()


def normal_from_height(h, strength=1.0):
    """DirectX tangent normal from a height map (height 1.0 == 25 % of a block)."""
    size = h.shape[0]
    k = strength * 0.25 * size  # height units -> pixels
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5 * k
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5 * k
    n = np.stack([-dx, -dy, np.ones_like(h)], -1)
    return normalize_v(n).astype(np.float32)


def blend_normals(base, detail):
    """Whiteout blend of two tangent-space normals."""
    n = np.stack([base[..., 0] + detail[..., 0],
                  base[..., 1] + detail[..., 1],
                  base[..., 2] * detail[..., 2]], -1)
    return normalize_v(n)


def scale_normal(n, s):
    n = n.copy()
    n[..., 0] *= s
    n[..., 1] *= s
    return normalize_v(n)


def cavity_ao(h, radius=4.0, strength=1.0):
    """Cheap ambient occlusion from height: pixels below their blurred surroundings."""
    r = radius * RES / 256
    hb = blur(h, r)
    occ = clamp01((hb - h) * 4.0 * strength)
    hb2 = blur(h, r * 3)
    occ2 = clamp01((hb2 - h) * 2.0 * strength)
    return clamp01(1 - 0.6 * occ - 0.4 * occ2)


# --------------------------------------------------------------------------- #
# Loading photo materials
# --------------------------------------------------------------------------- #
def _read(path, mode):
    im = Image.open(path)
    if mode == "RGB":
        return np.asarray(im.convert("RGB"), np.float32) / 255.0
    if im.mode in ("I;16", "I;16B", "I"):
        a = np.asarray(im, np.float32)
        return a / (65535.0 if a.max() > 255 else 255.0)
    return np.asarray(im.convert("L"), np.float32) / 255.0


@functools.lru_cache(maxsize=None)
def load_source(asset_id):
    """Full-resolution maps of an ambientCG material, as a dict of arrays."""
    d = fetch.fetch(asset_id, QUALITY)
    files = {f.split("_")[-1].split(".")[0]: os.path.join(d, f) for f in os.listdir(d)}
    out = {"albedo": _read(files["Color"], "RGB")}
    s = out["albedo"].shape[0]
    if "NormalDX" in files:
        n = _read(files["NormalDX"], "RGB") * 2 - 1
        out["normal"] = normalize_v(n)
    else:
        out["normal"] = flat_normal(s, s)
    out["height"] = _read(files["Displacement"], "L") if "Displacement" in files else luminance(out["albedo"])
    out["rough"] = _read(files["Roughness"], "L") if "Roughness" in files else np.full((s, s), 0.8, np.float32)
    out["ao"] = _read(files["AmbientOcclusion"], "L") if "AmbientOcclusion" in files else np.ones((s, s), np.float32)
    if "Metalness" in files:
        out["metalness"] = _read(files["Metalness"], "L")
    if "Opacity" in files:
        out["opacity"] = _read(files["Opacity"], "L")
    # some sources are 2:1 - repeat the short side so the result is square and still tiles
    h, w = out["albedo"].shape[:2]
    if h != w:
        reps = (max(1, w // h), 1) if h < w else (1, max(1, h // w))
        out = {k: np.tile(v, reps + (1,) * (v.ndim - 2)) for k, v in out.items()}
    return out


def seamless_crop(a, x0, y0, size, margin):
    """Crop a square region and make it tile again by cross-fading its borders."""
    h, w = a.shape[:2]
    ys = (np.arange(y0, y0 + size + margin)) % h
    xs = (np.arange(x0, x0 + size + margin)) % w
    r = a[ys][:, xs].astype(np.float32)
    if margin > 0:
        t = (np.arange(margin, dtype=np.float32) + 0.5) / margin
        t = t * t * (3 - 2 * t)
        # x direction
        sh = (1, margin) + (1,) * (a.ndim - 2)
        tx = t.reshape(sh)
        r[:, :margin] = r[:, size:size + margin] * (1 - tx) + r[:, :margin] * tx
        r = r[:, :size]
        ty = t.reshape((margin, 1) + (1,) * (a.ndim - 2))
        r[:margin] = r[size:size + margin] * (1 - ty) + r[:margin] * ty
        r = r[:size]
    return r


def load(asset_id, zoom=1.0, offset=(0.0, 0.0), rot=0, relief=0.35, size=None, normal_strength=1.0,
         smooth_mul=1.0):
    """Load an ambientCG material as a Mat.

    zoom   - >1 shows only 1/zoom of the source tile (bigger features), stays seamless
    offset - fractional offset into the source tile
    rot    - 90 deg CCW rotations
    relief - fraction of the POM depth used by the displacement
    """
    size = size or RES
    src = load_source(asset_id)
    s = src["albedo"].shape[0]
    if zoom > 1.0:
        c = int(round(s / zoom))
        margin = max(4, int(c * 0.18))
        x0, y0 = int(offset[0] * s), int(offset[1] * s)
        crop = lambda a: seamless_crop(a, x0, y0, c, margin)
    else:
        dx, dy = int(offset[0] * s), int(offset[1] * s)
        crop = lambda a: np.roll(a, (-dy, -dx), axis=(0, 1)) if (dx or dy) else a
    alb = resize_wrap(crop(src["albedo"]), size)
    nrm = normalize_v(resize_wrap(crop(src["normal"]), size))
    hgt = resize_wrap(crop(src["height"]), size)
    rough = resize_wrap(crop(src["rough"]), size)
    ao = resize_wrap(crop(src["ao"]), size)
    m = new_mat(size)
    m.albedo = clamp01(alb)
    m.normal = scale_normal(nrm, normal_strength)
    m.height = stretch(hgt, 0.5, 99.8)
    m.ao = clamp01(ao)
    m.smooth = clamp01(1 - rough) * smooth_mul
    if "metalness" in src:
        m.meta["metalness"] = clamp01(resize_wrap(crop(src["metalness"]), size))
    if "opacity" in src:
        m.alpha = clamp01(resize_wrap(crop(src["opacity"]), size))
    m.set_relief(relief)
    if rot:
        m = m.rot90(rot)
    return m


# --------------------------------------------------------------------------- #
# Layout helpers (bricks, tiles, planks)
# --------------------------------------------------------------------------- #
def rect_cells(rows, cols, offsets=None, size=None, widths=None):
    """Running-bond cell layout.

    Returns (cell_id, u, v, edge) where u/v are local coords in pixels from the
    cell's top-left and edge is the distance to the nearest cell border in
    pixels.  `offsets[r]` shifts row r by a fraction of a cell width.
    `widths[r]` (optional) is a list of fractional brick widths per row.
    """
    size = size or RES
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32) + 0.5
    rh = size / rows
    row = np.floor(yy / rh).astype(np.int32)
    v = yy - row * rh
    cid = np.zeros((size, size), np.int32)
    u = np.zeros((size, size), np.float32)
    cw_map = np.zeros((size, size), np.float32)
    for r in range(rows):
        sel = row == r
        if widths is not None:
            ws = np.asarray(widths[r], np.float32)
            ws = ws / ws.sum() * size
            edges = np.concatenate([[0], np.cumsum(ws)])
            off = (offsets[r] if offsets else 0) * size
            x = (xx[sel] - off) % size
            k = np.searchsorted(edges, x, side="right") - 1
            k = np.clip(k, 0, len(ws) - 1)
            cid[sel] = r * 100 + k
            u[sel] = x - edges[k]
            cw_map[sel] = ws[k]
        else:
            cw = size / cols
            off = (offsets[r] if offsets else 0) * cw
            x = (xx[sel] - off) % size
            k = np.floor(x / cw).astype(np.int32)
            cid[sel] = r * 100 + k
            u[sel] = x - k * cw
            cw_map[sel] = cw
    edge = np.minimum(np.minimum(u, cw_map - u), np.minimum(v, rh - v))
    return cid, u, v, edge, cw_map, rh


def fill_cells(cid, sources, seed, size=None, jitter_color=0.06, rot_choices=(0,)):
    """Fill each cell with a randomly offset (and optionally rotated) copy of a source Mat.

    `sources` is a list of Mats (seamless).  Returns a Mat.
    """
    size = size or RES
    r = rng(("fill", seed))
    out = sources[0].copy()
    ids = np.unique(cid)
    cache = {}
    for i in ids:
        mask = cid == i
        src = sources[r.integers(len(sources))]
        k = int(r.choice(rot_choices))
        key = (id(src), k)
        if key not in cache:
            cache[key] = src.rot90(k) if k else src
        m = cache[key].roll(r.integers(size), r.integers(size))
        cshift = 1 + (r.random(3) - 0.5) * 2 * jitter_color * 0.15
        bshift = 1 + (r.random() - 0.5) * 2 * jitter_color
        for k2, v in m.__dict__.items():
            if isinstance(v, np.ndarray):
                getattr(out, k2)[mask] = v[mask]
        out.albedo[mask] = clamp01(out.albedo[mask] * cshift * bshift)
    return out


def bevel(edge, width, curve=1.0):
    """0 at the border -> 1 inside, over `width` pixels."""
    return clamp01(edge / max(width, 1e-3)) ** curve


def scaled(px):
    """Convert a size given for 256x textures to the current resolution."""
    return px * RES / 256.0


# --------------------------------------------------------------------------- #
# Export (labPBR 1.3)
# --------------------------------------------------------------------------- #
def encode(m: Mat, normal_ao=True, flat_pom=False):
    """Return (albedo, normal, specular) PIL images in labPBR 1.3 format."""
    size = m.size
    a = clamp01(m.albedo)
    if m.alpha is not None:
        alb = np.concatenate([a, clamp01(m.alpha)[..., None]], -1)
        albedo = Image.fromarray(np.round(alb * 255).astype(np.uint8), "RGBA")
    else:
        albedo = Image.fromarray(np.round(a * 255).astype(np.uint8), "RGB")

    # ---- normal: RG = xy (DirectX), B = AO, A = height
    n = normalize_v(m.normal)
    h = m.height.astype(np.float32)
    if m.alpha is not None:
        solid = m.alpha > 0.5
        hs = h[solid] if solid.any() else h
        h = h - hs.max() + 1.0
    else:
        h = h - h.max() + 1.0
    if flat_pom:
        h = np.ones_like(h)
    ao = clamp01(m.ao) * (cavity_ao(m.height) if normal_ao else 1.0)
    if m.alpha is not None:
        transparent = m.alpha < 0.1
        n = np.where(transparent[..., None], np.array([0, 0, 1], np.float32), n)
        h = np.where(transparent, 1.0, h)
        ao = np.where(transparent, 1.0, ao)
    nr = np.round((n[..., 0] * 0.5 + 0.5) * 255)
    ng = np.round((n[..., 1] * 0.5 + 0.5) * 255)
    nb = np.round(clamp01(ao) * 255)
    na = np.clip(np.round(clamp01(h) * 255), 1, 255)
    normal = Image.fromarray(np.stack([nr, ng, nb, na], -1).astype(np.uint8), "RGBA")

    # ---- specular: R smoothness, G f0/metal, B porosity/SSS, A emission
    sr = np.round(clamp01(m.smooth) * 255)
    sg = np.where(m.metal >= 230, m.metal, np.clip(np.round(m.f0 * 255), 0, 229))
    sss = clamp01(m.sss)
    por = clamp01(m.porosity)
    sb = np.where(sss > 0.01, np.round(65 + sss * 190), np.round(por * 64))
    em = clamp01(m.emit)
    sa = np.where(em > 0.002, np.clip(np.round(em * 254), 1, 254), 255)
    if m.alpha is not None:
        transparent = m.alpha < 0.1
        sr = np.where(transparent, 0, sr)
        sg = np.where(transparent, 0, sg)
        sb = np.where(transparent, 0, sb)
        sa = np.where(transparent, 255, sa)
    spec = Image.fromarray(np.stack([sr, sg, sb, sa], -1).astype(np.uint8), "RGBA")
    return albedo, normal, spec


def save(m: Mat, out_dir, name, **kw):
    alb, nrm, spc = encode(m, **kw)
    os.makedirs(out_dir, exist_ok=True)
    alb.save(os.path.join(out_dir, f"{name}.png"), optimize=True)
    nrm.save(os.path.join(out_dir, f"{name}_n.png"), optimize=True)
    spc.save(os.path.join(out_dir, f"{name}_s.png"), optimize=True)


def save_animated(frames, out_dir, name, frametime=8, **kw):
    """Vertical strip animation (albedo + matching _n/_s strips) with .mcmeta."""
    parts = [encode(f, **kw) for f in frames]
    os.makedirs(out_dir, exist_ok=True)
    for idx, suffix in enumerate(("", "_n", "_s")):
        ims = [p[idx] for p in parts]
        w, h = ims[0].size
        strip = Image.new(ims[0].mode, (w, h * len(ims)))
        for i, im in enumerate(ims):
            strip.paste(im, (0, i * h))
        strip.save(os.path.join(out_dir, f"{name}{suffix}.png"), optimize=True)
    for suffix in ("", "_n", "_s"):
        with open(os.path.join(out_dir, f"{name}{suffix}.png.mcmeta"), "w") as f:
            f.write('{\n  "animation": {\n    "frametime": %d,\n    "interpolate": true\n  }\n}\n' % frametime)
