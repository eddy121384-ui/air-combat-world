"""Negative delivery-contract tests using the actual committed art planes."""
import unittest

import numpy as np
from PIL import Image

from build_xinyi_shared_masks import PACK, NAMES, check_edges, check_packed, mobile


class PackagingContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.planes = [mobile(Image.open(PACK/"planes"/(name+".png"))) for name in NAMES["facade"]]
        cls.packed = Image.open(PACK/"textures/T_XinyiFacadeAge.png")

    def test_actual_art_matches_all_four_channels(self):
        check_packed(self.packed, self.planes, "facade")

    def test_rejects_swapped_red_green(self):
        r, g, b, a = self.packed.split()
        self.assertFalse(np.array_equal(np.asarray(r), np.asarray(g)))
        with self.assertRaisesRegex(AssertionError, "R channel packing mismatch"):
            check_packed(Image.merge("RGBA", (g, r, b, a)), self.planes, "swapped")

    def test_rejects_opacity_alpha(self):
        corrupt = self.packed.copy(); corrupt.putalpha(255)
        with self.assertRaisesRegex(AssertionError, "A channel packing mismatch"):
            check_packed(corrupt, self.planes, "opaque-alpha")

    def test_rejects_lost_fourth_channel(self):
        with self.assertRaisesRegex(AssertionError, "four 512-square channels"):
            check_packed(self.packed.convert("RGB"), self.planes, "alpha-lost")

    def test_rejects_single_boundary_damage(self):
        corrupt = np.asarray(self.planes[0]).copy()
        corrupt[37, 0] = 0
        with self.assertRaisesRegex(AssertionError, "horizontal boundary mismatch"):
            check_edges(corrupt, "bad-seam")


if __name__ == "__main__":
    unittest.main()
