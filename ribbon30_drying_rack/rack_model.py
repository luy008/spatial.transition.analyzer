"""RIBBON/30 drying rack: 3D model, load cases and checks. Writes results.json.

Geometry is the one in the earlier preliminary report (recovered from its drawing):
frame centreline feet at x=0/1200, leg points (0,180), (30,750), (90,1050),
parabolic top arc from x=90 to 1110 peaking at y=1200, frames at z=0 and z=1000,
18 rods at x = 90 + 60 i.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from fem3d import Model, Spring, box_section, stress_check, tube_section

G = 9.81
RHO = 7.85e-6  # kg/mm^3
FY = 235.0
E = 200_000.0
FRAME = box_section(40, 20, 1)  # 40 mm in the frame plane
ROD = tube_section(16, 1)
DEPTH = 1000.0
ROD_X = [90.0 + 60.0 * i for i in range(18)]
ROD_SEG = 20
RIGID = 1e10  # effectively rigid (1e7 already gives <2% difference)
K_TRANS = 1e8

LAUNDRY_KG = 30.0
GAMMA_G, GAMMA_Q = 1.35, 1.5  # EN 1990 STR-type factors, used here as a design assumption


def arc_y(x: float) -> float:
    return 1200.0 - 150.0 * ((x - 600.0) / 510.0) ** 2


def frame_outline():
    """Polyline of one frame (closed loop) as list of (point, segments-to-next)."""
    left = [((0, 0), 2), ((0, 180), 6), ((30, 750), 4)]
    arc = []
    for i in range(len(ROD_X) - 1):
        for j in range(2):
            x = ROD_X[i] + 30.0 * j
            arc.append(((x, arc_y(x)), 1))
    arc.append(((ROD_X[-1], arc_y(ROD_X[-1])), 4))
    right = [((1170, 750), 6), ((1200, 180), 2), ((1200, 0), 12)]
    return left + arc + right  # last returns to (0,0)


def build(k_rot: float = RIGID, k_tors: float = RIGID, braces: bool = False):
    m = Model(E=E)
    frames = []
    for z in (0.0, DEPTH):
        outline = frame_outline()
        first = None
        prev = None
        index = {}
        for i, (p, nseg) in enumerate(outline):
            a = np.array([p[0], p[1], z])
            b_p = outline[(i + 1) % len(outline)][0]
            b = np.array([b_p[0], b_p[1], z])
            na = prev if prev is not None else m.add_node(a)
            if first is None:
                first = na
            nb = first if i == len(outline) - 1 else None
            ids = m.add_line(a, b, nseg, FRAME, "frame", ref=(0, 0, 1), na=na, nb=nb)
            index[tuple(np.round(a[:2], 6))] = na
            prev = ids[-1]
        frames.append(index)
    rods = []
    for x in ROD_X:
        y = arc_y(x)
        f0 = frames[0][(round(x, 6), round(y, 6))]
        f1 = frames[1][(round(x, 6), round(y, 6))]
        ids = m.add_line((x, y, 0.0), (x, y, DEPTH), ROD_SEG, ROD, "rod", ref=(1, 0, 0))
        k = np.array([K_TRANS, K_TRANS, K_TRANS, k_rot, k_rot, k_tors])
        m.springs.append(Spring(f0, ids[0], k, "joint"))
        m.springs.append(Spring(f1, ids[-1], k, "joint"))
        rods.append(ids)
    if braces:
        # side X-braces in the Y-Z plane of each end leg: foot of one frame to the knee (y=750)
        # of the other frame; the two diagonals are not connected where they cross
        for x0, xk in ((0.0, 30.0), (1200.0, 1170.0)):
            for fa, fb in ((0, 1), (1, 0)):
                na, nb = frames[fa][(x0, 0.0)], frames[fb][(xk, 750.0)]
                m.add_line(m.nodes[na], m.nodes[nb], 12, ROD, "brace", ref=(1, 0, 0), na=na, nb=nb)
    feet = {"A": frames[0][(0.0, 0.0)], "B": frames[0][(1200.0, 0.0)],
            "C": frames[1][(0.0, 0.0)], "D": frames[1][(1200.0, 0.0)]}
    # point contact on the floor, held horizontally by friction (checked afterwards), free to rotate
    m.fixed = {n: [0, 1, 2] for n in feet.values()}
    tops = [frames[0][(570.0, round(arc_y(570.0), 6))], frames[1][(570.0, round(arc_y(570.0), 6))]]
    return m, rods, feet, tops


# ---------------- loads ----------------
def self_weight(m: Model) -> np.ndarray:
    F = np.zeros(m.ndof)
    for el in m.elements:
        L = np.linalg.norm(m.nodes[el.n2] - m.nodes[el.n1])
        w = RHO * el.sec.A * L * G
        F[6 * el.n1 + 1] -= w / 2
        F[6 * el.n2 + 1] -= w / 2
    return F


def rod_load(m, rod_ids, kg, front_share=0.5, point=False):
    """Laundry on one rod: uniform along length (front half gets front_share), or a midspan point."""
    F = np.zeros(m.ndof)
    if point:
        F[6 * rod_ids[ROD_SEG // 2] + 1] -= kg * G
        return F
    half = ROD_SEG // 2
    for part, share in ((range(0, half), front_share), (range(half, ROD_SEG), 1 - front_share)):
        w = kg * share * G / half
        for s in part:
            F[6 * rod_ids[s] + 1] -= w / 2
            F[6 * rod_ids[s + 1] + 1] -= w / 2
    return F


def laundry_case(m, rods, name, kg=LAUNDRY_KG):
    F = np.zeros(m.ndof)
    left = [i for i, x in enumerate(ROD_X) if x < 600]
    if name == "uniform":
        for r in rods:
            F += rod_load(m, r, kg / 18)
    elif name == "one_side":
        for i in left:
            F += rod_load(m, rods[i], kg / 9)
    elif name == "front70":
        for r in rods:
            F += rod_load(m, r, kg / 18, front_share=0.7)
    elif name == "corner":
        for i in left:
            F += rod_load(m, rods[i], kg / 9, front_share=0.7)
    elif name == "rod5":
        F += rod_load(m, rods[8], 5.0 * kg / 30, point=True)
        for i, r in enumerate(rods):
            if i != 8:
                F += rod_load(m, r, (kg - 5.0 * kg / 30) / 17)
    else:
        raise KeyError(name)
    return F


def horizontal(m, tops, direction, total_N):
    F = np.zeros(m.ndof)
    for n in tops:
        F[6 * n + direction] += total_N / len(tops)
    return F


CASES = {
    "U": ("균등 배치", "uniform", None),
    "W": ("폭 한쪽(9개 봉)", "one_side", None),
    "L70": ("길이 편중 70%", "front70", None),
    "C": ("한쪽 + 앞쪽 70% (모서리)", "corner", None),
    "R5": ("가운데 봉 1개에 5kg 집중 + 나머지 균등", "rod5", None),
    "HX": ("균등 + 폭방향 수평 15N", "uniform", 0),
    "HZ": ("균등 + 길이방향 수평 15N", "uniform", 2),
}
H_SERVICE = 15.0


# ---------------- post-processing ----------------
def member_stresses(m, u):
    res = {"frame": [0.0, 0.0], "rod": [0.0, 0.0], "brace": [0.0, 0.0], "frame_comp": 0.0}
    for el, (L, f) in zip(m.elements, m.element_forces(u)):
        for end in (f[:6], -f[6:]):
            sig, vm = stress_check(el.sec, end)
            r = res[el.group]
            r[0] = max(r[0], sig)
            r[1] = max(r[1], vm)
        if el.group == "frame":
            N = f[6]
            if N < 0:
                res["frame_comp"] = max(res["frame_comp"], -N / el.sec.A + max(
                    abs(f[4]), abs(f[10])) / el.sec.Sy + max(abs(f[5]), abs(f[11])) / el.sec.Sz)
    return res


def joint_moments(m, u):
    """Max bending moment (N*mm) transmitted through the rod-frame joints."""
    best = 0.0
    for sp in m.springs:
        d1, d2 = 6 * sp.n1, 6 * sp.n2
        dr = u[d2 + 3:d2 + 5] - u[d1 + 3:d1 + 5]
        best = max(best, float(np.hypot(*(sp.k[3:5] * dr))))
    return best


def displacements(m, u, rods):
    frame_nodes = sorted({n for el in m.elements if el.group == "frame" for n in (el.n1, el.n2)})
    disp = np.array([np.linalg.norm(u[6 * n:6 * n + 3]) for n in frame_nodes])
    sag = 0.0
    for r in rods:
        ends = 0.5 * (u[6 * r[0] + 1] + u[6 * r[-1] + 1])
        sag = max(sag, max(ends - u[6 * n + 1] for n in r))
    return float(disp.max()), float(sag)


def max_lateral(m, u, tops):
    return {"x": float(max(abs(u[6 * n]) for n in tops)), "z": float(max(abs(u[6 * n + 2]) for n in tops))}


def first_yield_factor(m, uG, uQ, gG=1.0, limit=FY, alpha_ref=None, WG=0.0, WQ=0.0):
    """Largest lambda with stresses(gG*G + lambda*Q) <= limit everywhere (bisection).

    With alpha_ref (critical factor of the reference design load gG*G + 1.5*Q), stresses are
    amplified by 1/(1 - 1/alpha) with alpha scaled by total vertical load (EN 1993-1-1 5.2.2 style).
    """
    def ok(lam):
        amp = 1.0
        if alpha_ref is not None:
            alpha = alpha_ref * (gG * WG + GAMMA_Q * WQ) / (gG * WG + lam * WQ)
            if alpha <= 1.0:
                return False
            amp = 1 / (1 - 1 / alpha)
        s = member_stresses(m, gG * uG + lam * uQ)
        return amp * max(s["frame"][1], s["rod"][1]) <= limit
    lo, hi = 0.0, 1.0
    while ok(hi):
        lo, hi = hi, hi * 2
        if hi > 1e4:
            return float("inf")
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if ok(mid) else (lo, mid)
    return lo


def mode_shape(m, phi):
    """Share of modal translation in X / Y / Z over all nodes."""
    t = phi.reshape(-1, 6)[:, :3] ** 2
    tot = t.sum(axis=0)
    share = tot / tot.sum()
    names = ["폭방향(X) 횡변형", "수직(Y)", "길이방향(Z) 흔들림(래킹)"]
    return names[int(np.argmax(share))], [float(x) for x in share]


def joint_resistance_indicative():
    """EN 1993-1-8 Table 7.14 style chord-face resistance, CHS brace on RHS face, x pi/4.

    Outside the code scope (it requires t0 >= 2.5 mm) - indicative only.
    """
    b0, t0, d1 = 40.0, 1.0, 16.0  # rod lands on the 40 mm face of the frame tube
    beta = d1 / b0
    eta = d1 / b0
    m_ip = FY * t0**2 * d1 * (1 / (2 * eta) + 2 / np.sqrt(1 - beta) + eta / (1 - beta)) * np.pi / 4
    m_op = FY * t0**2 * (d1 * (1 + beta) / (2 * (1 - beta))
                         + np.sqrt(2 * b0 * d1 * (1 + beta) / (1 - beta))) * np.pi / 4
    m_pl_rod = FY * (16.0**3 - 14.0**3) / 6
    return {"beta": beta, "M_ip_Nmm": m_ip, "M_op_Nmm": m_op, "M_pl_rod_Nmm": m_pl_rod}


def local_buckling():
    t = 1.0
    eps = np.sqrt(235.0 / FY)
    web_c, flange_c = 40 - 3 * t, 20 - 3 * t  # EN 1993-1-1 Table 5.2 (RHS: c = b - 3t)
    plate = np.pi**2 * E / (12 * (1 - 0.3**2))
    return {
        "web_c_t": web_c / t, "flange_c_t": flange_c / t,
        "class_web_compression": 1 if web_c / t <= 33 * eps else 2 if web_c / t <= 38 * eps else 3 if web_c / t <= 42 * eps else 4,
        "class_web_bending": 1 if web_c / t <= 72 * eps else 2,
        "class_flange_compression": 1 if flange_c / t <= 33 * eps else 2,
        "rod_d_t": 16.0 / 1.0, "class_rod": 1 if 16.0 <= 50 * eps**2 else 2,
        # elastic plate buckling stress of the 40 mm wall (midline width 39 mm), k=4 uniform compression
        "sigma_cr_web_compression": 4 * plate * (t / 39.0) ** 2,
        "sigma_cr_web_bending": 23.9 * plate * (t / 39.0) ** 2,
        "sigma_cr_flange_compression": 4 * plate * (t / 19.0) ** 2,
    }


def ltb():
    """Elastic LTB moment of the frame tube over its longest unbraced length (uniform moment)."""
    Gm = E / 2.6
    out = {}
    for name, L in (("arc_span_1020", 1020.0), ("leg_570", 571.0)):
        out[name] = np.pi / L * np.sqrt(E * FRAME.Iy * Gm * FRAME.J)
    out["M_el_strong"] = FY * FRAME.Sz
    return out


def tipping(mass_rack):
    """Horizontal force at the top (1200 mm) that starts overturning; rigid body, no sliding."""
    h = 1200.0
    Wr = mass_rack * G
    Wq = LAUNDRY_KG * G
    rows = []
    # (label, half base, laundry eccentricity toward the tipping edge)
    for label, half, ecc, q in (
        ("빈 건조대 · 길이방향(발 간격 1.0m)", 500.0, 0.0, 0.0),
        ("빈 건조대 · 폭방향(발 간격 1.2m)", 600.0, 0.0, 0.0),
        ("30kg 균등 · 길이방향", 500.0, 0.0, Wq),
        ("30kg 균등 · 폭방향", 600.0, 0.0, Wq),
        ("30kg 앞쪽 70% · 길이방향, 치우친 쪽으로", 500.0, 100.0, Wq),
        ("30kg 한쪽 9개 봉 · 폭방향, 치우친 쪽으로", 600.0, 270.0, Wq),
    ):
        H = (Wr * half + q * (half - ecc)) / h
        rows.append({"case": label, "H_tip_N": H, "W_total_N": Wr + q})
    return rows


def wind_speed_for(force_N, area_m2=1.0, cf=1.2, rho=1.225):
    return float(np.sqrt(2 * force_N / (rho * cf * area_m2)))


def run():
    out = {"inputs": {
        "frame_section": FRAME.name, "rod_section": ROD.name, "E": E, "fy": FY, "rho_kg_mm3": RHO,
        "g": G, "laundry_kg": LAUNDRY_KG, "gamma_G": GAMMA_G, "gamma_Q": GAMMA_Q,
        "frame_props": {"A": FRAME.A, "I_strong": FRAME.Iz, "I_weak": FRAME.Iy, "J": FRAME.J},
        "rod_props": {"A": ROD.A, "I": ROD.Iz, "J": ROD.J},
    }}
    m, rods, feet, tops = build()
    mass_frame = sum(RHO * el.sec.A * np.linalg.norm(m.nodes[el.n2] - m.nodes[el.n1])
                     for el in m.elements if el.group == "frame")
    mass_rod = sum(RHO * el.sec.A * np.linalg.norm(m.nodes[el.n2] - m.nodes[el.n1])
                   for el in m.elements if el.group == "rod")
    out["mass"] = {"frames_kg": mass_frame, "rods_kg": mass_rod, "total_kg": mass_frame + mass_rod}

    # ----- rigid joints: all cases -----
    K = m.assemble_K()
    FG = self_weight(m)
    uG, RG = m.solve(FG, K)
    cases = {}
    for key, (label, pattern, hdir) in CASES.items():
        FQ = laundry_case(m, rods, pattern)
        FH = horizontal(m, tops, hdir, H_SERVICE) if hdir is not None else np.zeros(m.ndof)
        uQ, _ = m.solve(FQ + FH, K)
        us, Rs = m.solve(FG + FQ + FH, K)
        ud, _ = m.solve(GAMMA_G * FG + GAMMA_Q * (FQ + FH), K)
        s_serv = member_stresses(m, us)
        s_uls = member_stresses(m, ud)
        dmax, sag = displacements(m, us, rods)
        reactions = {k: [float(Rs[6 * n]), float(Rs[6 * n + 1]), float(Rs[6 * n + 2])] for k, n in feet.items()}
        lam, modes = m.buckling_factor(ud, K, nmodes=1)
        WG, WQ = -FG[1::6].sum(), -FQ[1::6].sum()
        lam_y_service = first_yield_factor(m, uG, uQ)
        # design: 1.35 G + lambda * Q <= fy, lambda includes gamma_Q, second-order amplified
        lam_y_design = first_yield_factor(m, uG, uQ, gG=GAMMA_G, alpha_ref=lam[0],
                                          WG=WG, WQ=WQ) / GAMMA_Q
        cases[key] = {
            "label": label,
            "service": {"frame_disp_mm": dmax, "rod_sag_mm": sag,
                        "frame_sigma": s_serv["frame"][0], "frame_vm": s_serv["frame"][1],
                        "rod_sigma": s_serv["rod"][0], "rod_vm": s_serv["rod"][1],
                        "joint_M_Nmm": joint_moments(m, us), "lateral_mm": max_lateral(m, us, tops),
                        "foot_reactions_N": reactions,
                        "horizontal_reaction_N": float(np.hypot(Rs[0::6][list(feet.values())].sum(),
                                                                Rs[2::6][list(feet.values())].sum()))},
            "uls": {"frame_vm": s_uls["frame"][1], "rod_vm": s_uls["rod"][1],
                    "frame_comp": s_uls["frame_comp"], "joint_M_Nmm": joint_moments(m, ud)},
            "alpha_cr_uls": lam[0] if lam else float("inf"),
            "mode": mode_shape(m, modes[0]) if modes else None,
            "foot_friction_demand": max(float(np.hypot(Rs[6 * n], Rs[6 * n + 2]) / Rs[6 * n + 1])
                                        for n in feet.values()),
            "laundry_at_first_yield_kg": lam_y_service * LAUNDRY_KG,
            "laundry_design_capacity_kg": lam_y_design * LAUNDRY_KG,
        }
    out["rigid"] = cases

    # ----- pinned rods (simply supported) for the rod itself, as in the first report -----
    rod_ss = {}
    I, S, Ar = ROD.Iz, ROD.Sy, ROD.A
    w_self = RHO * Ar * G
    for label, kg in (("18개 균등(1.67kg)", 30 / 18), ("9개 집중(3.33kg)", 30 / 9), ("한 봉 5kg", 5.0)):
        P = kg * G
        d = P * 1000**3 / (48 * E * I) + 5 * w_self * 1000**4 / (384 * E * I)
        M = P * 1000 / 4 + w_self * 1000**2 / 8
        rod_ss[label] = {"sag_mm": d, "sigma": M / S}
    P_cap = (FY / GAMMA_Q * S - GAMMA_G * w_self * 1000**2 / 8) * 4 / 1000 / G
    out["rod_simply_supported"] = {"cases": rod_ss, "design_point_capacity_kg": P_cap,
                                   "first_yield_point_kg": (FY * S - w_self * 1000**2 / 8) * 4 / 1000 / G}

    # ----- joint stiffness sweep (the folding / connection question) -----
    sweep = []
    for k in (RIGID, 1e7, 3e6, 1e6, 3e5, 1e5, 3e4, 1e4, 3e3, 1e3):
        mk, rk, fk, tk = build(k_rot=k)
        Kk = mk.assemble_K()
        FG_k = self_weight(mk)
        FQ_k = laundry_case(mk, rk, "uniform")
        try:
            ud, _ = mk.solve(GAMMA_G * FG_k + GAMMA_Q * FQ_k, Kk)
            lam, modes = mk.buckling_factor(ud, Kk, nmodes=1)
            uh, _ = mk.solve(horizontal(mk, tk, 2, H_SERVICE), Kk)
            us, _ = mk.solve(FG_k + FQ_k, Kk)
            s = member_stresses(mk, us)
            _, sag = displacements(mk, us, rk)
            us5, _ = mk.solve(FG_k + laundry_case(mk, rk, "rod5"), Kk)
            _, sag5 = displacements(mk, us5, rk)
            s5 = member_stresses(mk, us5)
            sweep.append({"k_Nmm_per_rad": k, "alpha_cr": lam[0] if lam else float("inf"),
                          "mode": mode_shape(mk, modes[0])[0] if modes else None,
                          "sway_z_per_15N_mm": max_lateral(mk, uh, tk)["z"],
                          "rod_sag_uniform_mm": sag, "rod_sag_rod5_mm": sag5,
                          "rod_vm_rod5": s5["rod"][1], "joint_M_rod5_Nmm": joint_moments(mk, us5),
                          "frame_vm_uniform": s["frame"][1]})
        except np.linalg.LinAlgError:
            sweep.append({"k_Nmm_per_rad": k, "alpha_cr": 0.0, "mechanism": True})
    # fully pinned rods: the racking mode is a mechanism
    mp, rp, fp, tp = build(k_rot=0.0)
    Kp = mp.assemble_K()
    f = mp.free_dofs()
    ev = np.linalg.eigvalsh(Kp[np.ix_(f, f)])
    out["pinned_joint_min_eig"] = float(ev[0])
    out["rigid_joint_min_eig"] = float(np.linalg.eigvalsh(K[np.ix_(f, f)])[0])
    out["joint_sweep"] = sweep

    # pinned rod joints + side X-braces (scissor-type, compatible with folding)
    mb, rb, fb, tb = build(k_rot=0.0, braces=True)
    Kb = mb.assemble_K()
    FGb, FQb = self_weight(mb), laundry_case(mb, rb, "uniform")
    udb, _ = mb.solve(GAMMA_G * FGb + GAMMA_Q * FQb, Kb)
    lamb, modesb = mb.buckling_factor(udb, Kb, nmodes=1)
    uhb, _ = mb.solve(horizontal(mb, tb, 2, H_SERVICE), Kb)
    usb, _ = mb.solve(FGb + FQb, Kb)
    us5b, _ = mb.solve(FGb + laundry_case(mb, rb, "rod5"), Kb)
    sb = member_stresses(mb, mb.solve(GAMMA_G * FGb + GAMMA_Q * laundry_case(mb, rb, "corner"), Kb)[0])
    brace_N = max(abs(f[6]) for el, (L, f) in zip(mb.elements, mb.element_forces(
        mb.solve(GAMMA_G * FGb + GAMMA_Q * (FQb + horizontal(mb, tb, 2, H_SERVICE)), Kb)[0]))
        if el.group == "brace")
    out["braced_pinned"] = {
        "alpha_cr": lamb[0], "mode": mode_shape(mb, modesb[0])[0],
        "sway_z_per_15N_mm": max_lateral(mb, uhb, tb)["z"],
        "frame_disp_uniform_mm": displacements(mb, usb, rb)[0],
        "rod_sag_rod5_mm": displacements(mb, us5b, rb)[1],
        "uls_corner_frame_vm": sb["frame"][1], "uls_corner_rod_vm": sb["rod"][1],
        "uls_brace_max_N": float(brace_N),
        "brace_euler_N": float(np.pi**2 * E * ROD.Iz / 1250.4**2),
        "added_mass_kg": sum(RHO * el.sec.A * np.linalg.norm(mb.nodes[el.n2] - mb.nodes[el.n1])
                             for el in mb.elements if el.group == "brace"),
    }

    # sensitivity: feet free to slide (only minimum horizontal restraint)
    ms, rs_, fs, ts = build()
    ms.fixed = {fs["A"]: [0, 1, 2], fs["B"]: [1, 2], fs["C"]: [0, 1], fs["D"]: [1]}
    uss, _ = ms.solve(self_weight(ms) + laundry_case(ms, rs_, "uniform"))
    out["feet_sliding_sensitivity"] = {"frame_disp_mm": displacements(ms, uss, rs_)[0],
                                       "frame_sigma": member_stresses(ms, uss)["frame"][0],
                                       "top_z_mm": max_lateral(ms, uss, ts)["z"]}

    out["joint_resistance"] = joint_resistance_indicative()
    out["local_buckling"] = local_buckling()
    out["ltb"] = ltb()
    tip = tipping(out["mass"]["total_kg"])
    for row in tip:
        if row["W_total_N"] > out["mass"]["total_kg"] * G + 1:  # wind only meaningful with laundry
            row["v_wind_tip_ms"] = wind_speed_for(row["H_tip_N"] * 1200 / 900)  # resultant ~0.9 m
            row["v_wind_slide_mu03_ms"] = wind_speed_for(0.3 * row["W_total_N"])
        row["H_slide_mu03_N"] = 0.3 * row["W_total_N"]
        row["H_slide_mu05_N"] = 0.5 * row["W_total_N"]
    out["tipping"] = tip

    # fatigue (indicative, EN 1993-1-9 lowest common detail category 36, m = 3)
    cycles = 2 * 365 * 15
    dsr = 36.0 * (2e6 / cycles) ** (1 / 3)
    out["fatigue"] = {"cycles": cycles, "delta_sigma_R": dsr, "gamma_Mf": 1.35,
                      "allowable": dsr / 1.35,
                      "rod_range_rod5": rod_ss["한 봉 5kg"]["sigma"] - w_self * 1000**2 / 8 / S,
                      "frame_range_max": max(c["service"]["frame_sigma"] for c in cases.values())}
    return out


if __name__ == "__main__":
    res = run()
    Path(__file__).with_name("results.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("mass", "pinned_joint_min_eig", "rigid_joint_min_eig")}, indent=1))
