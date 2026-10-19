"""Tileable value-noise texture for the forest-world Landscape material (offline, deterministic).

RGBA8 512 x 512, each channel an independent periodic band-limited noise (FFT-filtered white noise, so it tiles exactly):
R ~ 1/4 tile features, G ~ 1/16, B ~ 1/48, A ~ 1/128 (fine).  Writes <out>/T_NF_Noise.png.
    python tools/ntw/forest_world/make_noise.py <out_dir>
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

N = 512


def band(rng, freq):
    w = rng.normal(size=(N, N))
    fy = np.fft.fftfreq(N)[:, None] * N
    fx = np.fft.fftfreq(N)[None, :] * N
    r = np.hypot(fx, fy)
    filt = np.exp(-((r - freq) / (0.6 * freq)) ** 2)
    a = np.real(np.fft.ifft2(np.fft.fft2(w) * filt))
    lo, hi = np.percentile(a, 0.5), np.percentile(a, 99.5)
    return np.clip((a - lo) / (hi - lo), 0, 1)


def main(out):
    rng = np.random.default_rng(20261019)
    img = np.stack([band(rng, f) for f in (4, 16, 48, 128)], -1)
    Path(out).mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.round(img * 255).astype(np.uint8), "RGBA").save(Path(out) / "T_NF_Noise.png")


if __name__ == "__main__":
    main(sys.argv[1])
