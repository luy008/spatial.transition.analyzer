"""Small 3D frame (Euler-Bernoulli beam) solver used for the RIBBON/30 drying-rack check.

Units: N, mm, MPa. Six DOF per node: ux, uy, uz, rx, ry, rz.
Global axes: X = rack width, Y = up, Z = rod direction (depth).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import scipy.linalg as sla
import scipy.sparse as sp
import scipy.sparse.linalg as spla


@dataclass
class Section:
    name: str
    A: float
    Iy: float  # about local y
    Iz: float  # about local z
    J: float
    Sy: float  # elastic modulus for My
    Sz: float  # elastic modulus for Mz
    shape: str  # "box" or "tube"
    torsion_modulus: float  # tau = T / torsion_modulus
    shear_area_y: float
    shear_area_z: float


def box_section(h: float, b: float, t: float) -> Section:
    """Closed rectangular hollow section, sharp corners. h along local y, b along local z."""
    A = h * b - (h - 2 * t) * (b - 2 * t)
    Iz = (b * h**3 - (b - 2 * t) * (h - 2 * t) ** 3) / 12  # bending in local x-y plane
    Iy = (h * b**3 - (h - 2 * t) * (b - 2 * t) ** 3) / 12
    Am = (h - t) * (b - t)
    J = 4 * Am**2 * t / (2 * ((h - t) + (b - t)))  # Bredt
    return Section(f"RHS {h:g}x{b:g}x{t:g}", A, Iy, Iz, J, Iy / (b / 2), Iz / (h / 2), "box",
                   2 * Am * t, 2 * h * t, 2 * b * t)


def tube_section(d: float, t: float) -> Section:
    di = d - 2 * t
    A = np.pi / 4 * (d**2 - di**2)
    I = np.pi / 64 * (d**4 - di**4)
    J = 2 * I
    return Section(f"CHS {d:g}x{t:g}", A, I, I, J, I / (d / 2), I / (d / 2), "tube",
                   J / (d / 2), A / 2, A / 2)


@dataclass
class Element:
    n1: int
    n2: int
    sec: Section
    group: str
    ref: np.ndarray  # approximate local z direction (axis of the weak/"Iy" bending plane normal)


@dataclass
class Spring:
    """Zero-length 6-DOF spring between two nodes (global axes)."""
    n1: int
    n2: int
    k: np.ndarray  # 6 stiffnesses
    tag: str = ""


@dataclass
class Model:
    E: float = 200_000.0
    nu: float = 0.3
    nodes: list = field(default_factory=list)
    elements: list = field(default_factory=list)
    springs: list = field(default_factory=list)
    fixed: dict = field(default_factory=dict)  # node -> list of restrained dof indices

    @property
    def G(self) -> float:
        return self.E / (2 * (1 + self.nu))

    def add_node(self, xyz) -> int:
        self.nodes.append(np.asarray(xyz, float))
        return len(self.nodes) - 1

    def add_element(self, n1, n2, sec, group, ref=(0.0, 0.0, 1.0)):
        self.elements.append(Element(n1, n2, sec, group, np.asarray(ref, float)))

    def add_line(self, a, b, nseg, sec, group, ref=(0.0, 0.0, 1.0), na=None, nb=None):
        """Mesh straight line a->b into nseg elements; returns node ids."""
        a, b = np.asarray(a, float), np.asarray(b, float)
        ids = []
        for i in range(nseg + 1):
            if i == 0 and na is not None:
                ids.append(na)
            elif i == nseg and nb is not None:
                ids.append(nb)
            else:
                ids.append(self.add_node(a + (b - a) * i / nseg))
        for i in range(nseg):
            self.add_element(ids[i], ids[i + 1], sec, group, ref)
        return ids

    @property
    def ndof(self) -> int:
        return 6 * len(self.nodes)

    # ---------- element matrices ----------
    def transform(self, el: Element):
        p1, p2 = self.nodes[el.n1], self.nodes[el.n2]
        L = float(np.linalg.norm(p2 - p1))
        ex = (p2 - p1) / L
        ey = np.cross(el.ref, ex)
        if np.linalg.norm(ey) < 1e-9:
            raise ValueError("element reference vector parallel to axis")
        ey /= np.linalg.norm(ey)
        ez = np.cross(ex, ey)
        R = np.vstack([ex, ey, ez])
        T = np.zeros((12, 12))
        for i in range(4):
            T[3 * i:3 * i + 3, 3 * i:3 * i + 3] = R
        return L, T

    def k_local(self, el: Element, L: float) -> np.ndarray:
        E, G, s = self.E, self.G, el.sec
        k = np.zeros((12, 12))
        ea, gj = E * s.A / L, G * s.J / L
        k[0, 0] = k[6, 6] = ea
        k[0, 6] = k[6, 0] = -ea
        k[3, 3] = k[9, 9] = gj
        k[3, 9] = k[9, 3] = -gj
        # bending in x-y plane (v, rz) uses Iz
        a = E * s.Iz / L**3
        idx = [1, 5, 7, 11]
        kb = a * np.array([[12, 6 * L, -12, 6 * L],
                           [6 * L, 4 * L**2, -6 * L, 2 * L**2],
                           [-12, -6 * L, 12, -6 * L],
                           [6 * L, 2 * L**2, -6 * L, 4 * L**2]])
        k[np.ix_(idx, idx)] += kb
        # bending in x-z plane (w, ry) uses Iy
        a = E * s.Iy / L**3
        idx = [2, 4, 8, 10]
        kb = a * np.array([[12, -6 * L, -12, -6 * L],
                           [-6 * L, 4 * L**2, 6 * L, 2 * L**2],
                           [-12, 6 * L, 12, 6 * L],
                           [-6 * L, 2 * L**2, 6 * L, 4 * L**2]])
        k[np.ix_(idx, idx)] += kb
        return k

    def kg_local(self, el: Element, L: float, N: float) -> np.ndarray:
        """Geometric stiffness from axial force N (tension +)."""
        s = el.sec
        kg = np.zeros((12, 12))
        c = N / L
        idx = [1, 5, 7, 11]
        kg[np.ix_(idx, idx)] += c * np.array([[6 / 5, L / 10, -6 / 5, L / 10],
                                              [L / 10, 2 * L**2 / 15, -L / 10, -L**2 / 30],
                                              [-6 / 5, -L / 10, 6 / 5, -L / 10],
                                              [L / 10, -L**2 / 30, -L / 10, 2 * L**2 / 15]])
        idx = [2, 4, 8, 10]
        kg[np.ix_(idx, idx)] += c * np.array([[6 / 5, -L / 10, -6 / 5, -L / 10],
                                              [-L / 10, 2 * L**2 / 15, L / 10, -L**2 / 30],
                                              [-6 / 5, L / 10, 6 / 5, L / 10],
                                              [-L / 10, -L**2 / 30, L / 10, 2 * L**2 / 15]])
        ip = (s.Iy + s.Iz) / s.A
        kg[3, 3] = kg[9, 9] = c * ip
        kg[3, 9] = kg[9, 3] = -c * ip
        return kg

    @staticmethod
    def edofs(n1, n2):
        return np.r_[6 * n1:6 * n1 + 6, 6 * n2:6 * n2 + 6]

    # ---------- assembly / solve ----------
    def assemble_K(self) -> np.ndarray:
        K = np.zeros((self.ndof, self.ndof))
        for el in self.elements:
            L, T = self.transform(el)
            d = self.edofs(el.n1, el.n2)
            K[np.ix_(d, d)] += T.T @ self.k_local(el, L) @ T
        for sp in self.springs:
            d = self.edofs(sp.n1, sp.n2)
            ks = np.diag(sp.k)
            K[np.ix_(d, d)] += np.block([[ks, -ks], [-ks, ks]])
        return K

    def free_dofs(self) -> np.ndarray:
        mask = np.ones(self.ndof, bool)
        for n, dofs in self.fixed.items():
            for d in dofs:
                mask[6 * n + d] = False
        return np.flatnonzero(mask)

    def solve(self, F: np.ndarray, K: np.ndarray | None = None):
        K = self.assemble_K() if K is None else K
        f = self.free_dofs()
        Kff = K[np.ix_(f, f)]
        u = np.zeros(self.ndof)
        u[f] = sla.solve(Kff, F[f], assume_a="sym")
        R = K @ u - F
        return u, R

    def element_forces(self, u: np.ndarray):
        """Local end forces per element: [N, Vy, Vz, T, My, Mz] at end 1 and end 2 (internal sign)."""
        out = []
        for el in self.elements:
            L, T = self.transform(el)
            d = self.edofs(el.n1, el.n2)
            fl = self.k_local(el, L) @ (T @ u[d])
            out.append((L, fl))
        return out

    def assemble_Kg(self, u: np.ndarray) -> np.ndarray:
        Kg = np.zeros((self.ndof, self.ndof))
        for el in self.elements:
            L, T = self.transform(el)
            d = self.edofs(el.n1, el.n2)
            fl = self.k_local(el, L) @ (T @ u[d])
            N = fl[6]  # tension positive at end 2
            Kg[np.ix_(d, d)] += T.T @ self.kg_local(el, L, N) @ T
        return Kg

    def buckling_factor(self, u: np.ndarray, K: np.ndarray | None = None, nmodes: int = 3):
        """Smallest positive load factors lambda with (K + lambda*Kg) phi = 0.

        Solved as (-Kg) phi = mu K phi (K positive definite), lambda = 1/mu for the largest mu.
        """
        K = self.assemble_K() if K is None else K
        Kg = self.assemble_Kg(u)
        f = self.free_dofs()
        Kff, Gff = K[np.ix_(f, f)], -Kg[np.ix_(f, f)]
        if len(f) > 600:
            Ks, Gs = sp.csc_matrix(Kff), sp.csc_matrix(Gff)
            mu, vecs = spla.eigsh(Gs, k=nmodes + 2, M=Ks, which="LA")
        else:
            mu, vecs = sla.eigh(Gff, Kff)
        order = np.argsort(-mu)
        lams, modes = [], []
        for i in order:
            if mu[i] <= 1e-12:
                break
            lams.append(1 / mu[i])
            phi = np.zeros(self.ndof)
            phi[f] = vecs[:, i]
            modes.append(phi)
            if len(lams) == nmodes:
                break
        return lams, modes


def stress_check(sec: Section, f6: np.ndarray):
    """Max normal and von Mises stress at one element end from local forces [N,Vy,Vz,T,My,Mz]."""
    N, Vy, Vz, T, My, Mz = f6
    if sec.shape == "box":
        sig = abs(N) / sec.A + abs(My) / sec.Sy + abs(Mz) / sec.Sz
    else:
        sig = abs(N) / sec.A + np.hypot(My, Mz) / sec.Sy
    tau = abs(T) / sec.torsion_modulus + max(abs(Vy) / sec.shear_area_y, abs(Vz) / sec.shear_area_z)
    return sig, float(np.sqrt(sig**2 + 3 * tau**2))
