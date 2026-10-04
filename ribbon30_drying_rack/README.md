# RIBBON/30 drying rack: structural check (2nd pass)

Re-checks the preliminary drying-rack study (30 kg wet-laundry target) with a 3D frame model.
Covers the items the first, 2D report left open: 3D torsion/sway, global buckling (racking),
rod–frame joint stiffness and moment, local and lateral-torsional buckling, sliding/tipping,
fatigue, stress concentration, and a basis for "4-person household wet laundry" mass.

| File | Purpose |
|---|---|
| `fem3d.py` | 3D Euler–Bernoulli frame solver (6 DOF/node, springs, linear buckling) |
| `test_fem3d.py` | 10 checks against closed-form solutions |
| `rack_model.py` | Geometry, load cases, checks → `results.json` |
| `build_report.py` | `results.json` → `report.html` (Korean) |

```bash
pip install numpy scipy
python3 -m unittest test_fem3d -v
python3 rack_model.py        # ~1.5 min
python3 build_report.py
```

Key result: member stresses stay below ~50 % of yield at design load (1.35 G + 1.5 Q),
but longitudinal stability depends entirely on the rod–frame joints. Pinned joints make
the rack a mechanism; a rotational stiffness of about 5×10⁵ N·mm/rad per joint (or side
X-braces) is needed. Preliminary engineering check only — not a product certification,
no physical tests performed.
