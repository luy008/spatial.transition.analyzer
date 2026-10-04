"""Checks of fem3d against closed-form solutions. Run: python -m unittest test_fem3d -v"""
import unittest

import numpy as np

from fem3d import Model, Spring, box_section, tube_section

E = 200_000.0
BOX = box_section(40, 20, 1)
TUBE = tube_section(16, 1)


def line_model(direction, L, sec, nseg=10, ref=(0, 0, 1)):
    m = Model()
    d = np.asarray(direction, float) / np.linalg.norm(direction)
    ids = m.add_line(np.zeros(3), d * L, nseg, sec, "beam", ref=ref)
    return m, ids


class SectionTests(unittest.TestCase):
    def test_box_properties(self):
        self.assertAlmostEqual(BOX.A, 116.0)
        self.assertAlmostEqual(BOX.Iz, (20 * 40**3 - 18 * 38**3) / 12)
        self.assertAlmostEqual(BOX.Iy, (40 * 20**3 - 38 * 18**3) / 12)

    def test_tube_properties(self):
        self.assertAlmostEqual(TUBE.A, np.pi / 4 * (16**2 - 14**2))
        self.assertAlmostEqual(TUBE.Iz, np.pi / 64 * (16**4 - 14**4))


class StaticTests(unittest.TestCase):
    def test_cantilever_strong_axis(self):
        L, P = 1000.0, 50.0
        m, ids = line_model((1, 0, 0), L, BOX)
        m.fixed[ids[0]] = range(6)
        F = np.zeros(m.ndof)
        F[6 * ids[-1] + 1] = -P  # in-plane (local y = global Y)
        u, R = m.solve(F)
        self.assertAlmostEqual(u[6 * ids[-1] + 1], -P * L**3 / (3 * E * BOX.Iz), places=6)
        self.assertTrue(np.allclose(R[6 * ids[0]:6 * ids[0] + 3], [0, P, 0]))

    def test_cantilever_weak_axis_and_skew_orientation(self):
        L, P = 800.0, 20.0
        d = np.array([1.0, 1.0, 0.0]) / np.sqrt(2)
        m, ids = line_model(d, L, BOX)
        m.fixed[ids[0]] = range(6)
        F = np.zeros(m.ndof)
        F[6 * ids[-1] + 2] = P  # out of plane -> weak axis
        u, _ = m.solve(F)
        self.assertAlmostEqual(u[6 * ids[-1] + 2], P * L**3 / (3 * E * BOX.Iy), places=6)

    def test_torsion(self):
        L, T = 500.0, 1000.0
        m, ids = line_model((1, 0, 0), L, BOX)
        m.fixed[ids[0]] = range(6)
        F = np.zeros(m.ndof)
        F[6 * ids[-1] + 3] = T
        u, _ = m.solve(F)
        self.assertAlmostEqual(u[6 * ids[-1] + 3], T * L / (m.G * BOX.J), places=8)

    def test_fixed_fixed_center_load(self):
        L, P = 1000.0, 49.05
        m, ids = line_model((0, 0, 1), L, TUBE, nseg=10, ref=(0, 1, 0))
        m.fixed[ids[0]] = range(6)
        m.fixed[ids[-1]] = range(6)
        F = np.zeros(m.ndof)
        F[6 * ids[5] + 1] = -P
        u, _ = m.solve(F)
        self.assertAlmostEqual(u[6 * ids[5] + 1], -P * L**3 / (192 * E * TUBE.Iz), places=6)
        L1, f = m.element_forces(u)[0]
        self.assertAlmostEqual(float(np.hypot(f[4], f[5])), P * L / 8, places=3)

    def test_simply_supported_udl_lumped(self):
        L, w, n = 1000.0, 0.01, 40
        m, ids = line_model((0, 0, 1), L, TUBE, nseg=n, ref=(0, 1, 0))
        m.fixed[ids[0]] = [0, 1, 2, 5]  # pin + torsion restraint about the rod axis (Z)
        m.fixed[ids[-1]] = [0, 1]
        F = np.zeros(m.ndof)
        for i in ids:
            F[6 * i + 1] -= w * L / n * (0.5 if i in (ids[0], ids[-1]) else 1.0)
        u, _ = m.solve(F)
        exact = 5 * w * L**4 / (384 * E * TUBE.Iz)
        self.assertAlmostEqual(-u[6 * ids[n // 2] + 1] / exact, 1.0, delta=2e-3)  # lumped-load error

    def test_spring_rigid_link_equals_continuous(self):
        L, P = 1000.0, 30.0
        m = Model()
        a = m.add_line((0, 0, 0), (0, 0, 500), 5, TUBE, "b", ref=(0, 1, 0))
        b0 = m.add_node((0, 0, 500))
        b = m.add_line((0, 0, 500), (0, 0, 1000), 5, TUBE, "b", ref=(0, 1, 0), na=b0)
        m.springs.append(Spring(a[-1], b0, np.full(6, 1e12)))
        m.fixed[a[0]] = range(6)
        F = np.zeros(m.ndof)
        F[6 * b[-1] + 1] = -P
        u, _ = m.solve(F)
        self.assertAlmostEqual(u[6 * b[-1] + 1] / (-P * L**3 / (3 * E * TUBE.Iz)), 1.0, places=4)


class BucklingTests(unittest.TestCase):
    def test_euler_pinned_column(self):
        L, P = 1000.0, 1.0
        m, ids = line_model((0, 1, 0), L, BOX, nseg=16)
        m.fixed[ids[0]] = [0, 1, 2, 4]  # pin + torsion restraint about the column axis (Y)
        m.fixed[ids[-1]] = [0, 2]
        F = np.zeros(m.ndof)
        F[6 * ids[-1] + 1] = -P
        u, _ = m.solve(F)
        lams, _ = m.buckling_factor(u)
        self.assertAlmostEqual(lams[0] / (np.pi**2 * E * BOX.Iy / L**2), 1.0, places=3)

    def test_euler_cantilever_column(self):
        L, P = 1000.0, 1.0
        m, ids = line_model((0, 1, 0), L, TUBE, nseg=16, ref=(1, 0, 0))
        m.fixed[ids[0]] = range(6)
        F = np.zeros(m.ndof)
        F[6 * ids[-1] + 1] = -P
        u, _ = m.solve(F)
        lams, _ = m.buckling_factor(u)
        self.assertAlmostEqual(lams[0] / (np.pi**2 * E * TUBE.Iz / (4 * L**2)), 1.0, places=3)


if __name__ == "__main__":
    unittest.main()
