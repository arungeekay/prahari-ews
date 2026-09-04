"""Contagion model (BUILD_SPEC §4.2) - the demo's signature reveal.

Directed anchor→supplier payment graph. Stress diffusion (auditable, documented math):

    Each node has OWN stress  s_i ∈ [0,1]  (suppliers: their own PD; anchors: MEASURED payment
    stress, see below). Diffusion recomputes every node from its own stress each pass:

        s_j  =  min(1, own_j  +  Σ_i  w_ij · s_i · dependency_ij)

    where  dependency_ij = payer i's share of payee j's inflows  (edge.inflow_share)
    and    w_ij          = payment regularity of the edge.

    Recomputing from `own` each pass (Jacobi iteration) means a bipartite anchor→supplier graph
    converges after one pass and nothing is counted twice; multi-hop graphs converge in a few.

Anchor stress is measured, not assumed: for each anchor, the median decline in the anchor-
attributable inflow across its suppliers (recent months versus the baseline months, from the
`anchor_inflow` series - in production, statement credits grouped by payer) is multiplied by a
single documented elasticity (config CONTAGION.inflow_loss_to_stress) and clipped to [0, 1].

Output per node: contagion-adjusted PD, runway delta, and a plain-language "why" naming the
upstream cause. Pure-Python maths so it always runs; a credit officer can recompute any node by
hand from the edge table.
"""

from __future__ import annotations

import numpy as np

from ..datagen import config as C

ITERATIONS = 3                     # converges after 1 on a bipartite graph; 3 covers multi-hop
ANCHOR_STRESS_FALLBACK = 0.10      # used only when no anchor_inflow series exists at all
MIN_CONTRIBUTION = 0.01


def _pd_to_runway_months(pd_value: float) -> float:
    """PD-only fallback runway: the MEDIAN of an exponential survival curve whose 12-month default
    probability equals pd_value (the same formula as RunwayModel.runway_from_pd). Used only when
    no fitted runway model is supplied."""
    pd_value = float(np.clip(pd_value, 1e-5, 0.999))
    monthly_h = 1 - (1 - pd_value) ** (1 / 12)
    return float(np.clip(np.log(0.5) / np.log(1 - monthly_h), 0, 24))


def measure_anchor_stress(frames: dict, as_of: int | None = None) -> dict:
    """Per-anchor stress in [0, 1] measured from the observed decline in anchor inflows.

    decline_a = median over suppliers of  1 - mean(recent inflow) / mean(baseline inflow)
    stress_a  = clip(decline_a * inflow_loss_to_stress, 0, 1)
    Returns {anchor_id: {"stress", "inflow_decline", "n_suppliers_measured"}}."""
    mm = frames["msme_monthly"]
    borrowers = frames["borrowers"]
    out = {}
    if "anchor_inflow" not in mm.columns:
        for aid in frames["anchors"].anchor_id:
            out[aid] = dict(stress=ANCHOR_STRESS_FALLBACK, inflow_decline=None, n_suppliers_measured=0)
        return out
    as_of = int(mm.month_index.max()) if as_of is None else int(as_of)
    base_n = int(C.CONTAGION.get("stress_baseline_months", 12))
    recent_n = int(C.CONTAGION.get("stress_recent_months", 3))
    elasticity = float(C.CONTAGION.get("inflow_loss_to_stress", 2.0))
    sub = mm[(mm.month_index <= as_of) & (mm.anchor_inflow > 0)]
    for aid in frames["anchors"].anchor_id:
        sids = borrowers.loc[borrowers.anchor_id == aid, "borrower_id"]
        declines = []
        for sid in sids:
            g = sub[sub.borrower_id == sid].sort_values("month_index")
            if len(g) < base_n + recent_n:
                continue
            base = g.anchor_inflow.iloc[:base_n].mean()
            recent = g.anchor_inflow.iloc[-recent_n:].mean()
            if base > 0:
                declines.append(1.0 - recent / base)
        if declines:
            dec = float(np.median(declines))
            out[aid] = dict(stress=float(np.clip(max(0.0, dec) * elasticity, 0.0, 1.0)),
                            inflow_decline=round(dec, 4), n_suppliers_measured=len(declines))
        else:
            out[aid] = dict(stress=ANCHOR_STRESS_FALLBACK, inflow_decline=None, n_suppliers_measured=0)
    return out


class ContagionGraph:
    def __init__(self, frames: dict, pd_by_borrower: dict, anchor_stress: dict | None = None, runway_fn=None):
        self.frames = frames
        self.pd_by_borrower = pd_by_borrower
        self._runway = runway_fn or _pd_to_runway_months     # the calibrated runway curve when available
        self.anchors = frames["anchors"]
        self.edges = frames["edges"]
        self.borrowers = frames["borrowers"].set_index("borrower_id")
        self.anchor_measure = anchor_stress or measure_anchor_stress(frames)
        self._own = {}         # node -> own stress
        self._adj = {}         # node -> adjusted stress after diffusion
        self._contrib = {}     # payee -> list of (payer, payer_name, added_stress)
        self._diffuse()

    def _diffuse(self):
        own = {}
        for aid in self.anchors.anchor_id:
            own[aid] = float(self.anchor_measure.get(aid, {}).get("stress", ANCHOR_STRESS_FALLBACK))
        for bid in self.edges.payee.unique():
            own[bid] = float(self.pd_by_borrower.get(bid, 0.05))
        edges = list(self.edges.itertuples(index=False))
        stress = dict(own)
        contrib = {n: [] for n in own}
        for _ in range(ITERATIONS):
            new = dict(own)                       # recompute from OWN stress: no double counting
            adds = {}
            for e in edges:
                add = float(e.regularity) * stress.get(e.payer, 0.0) * float(e.inflow_share)
                new[e.payee] = min(1.0, new.get(e.payee, 0.0) + add)
                adds.setdefault(e.payee, []).append((e.payer, e.payer_name, add))
            stress = new
        for payee, lst in adds.items():           # contributions from the SAME pass that was applied
            contrib[payee] = [(p, n, round(a, 4)) for p, n, a in lst if a > MIN_CONTRIBUTION]
        self._own, self._adj, self._contrib = own, stress, contrib

    # ------------------------------------------------------------------ per-node results
    def adjusted_pd(self, borrower_id: str) -> float:
        own = float(self.pd_by_borrower.get(borrower_id, 0.05))
        added = max(0.0, self._adj.get(borrower_id, own) - own)
        return float(np.clip(own + added, 0, 0.99))

    def node_result(self, borrower_id: str) -> dict:
        own = float(self.pd_by_borrower.get(borrower_id, 0.05))
        adj = self.adjusted_pd(borrower_id)
        runway_own = float(self._runway(own))
        runway_adj = float(self._runway(adj))
        why = None
        contribs = sorted(self._contrib.get(borrower_id, []), key=lambda c: -c[2])
        if contribs:
            payer, payer_name, add = contribs[0]
            share = float(self.borrowers.at[borrower_id, "anchor_share"]) if borrower_id in self.borrowers.index else 0.0
            meas = self.anchor_measure.get(payer, {})
            dec = meas.get("inflow_decline")
            dec_txt = f"payments from {payer_name} fell {dec:.0%}" if dec is not None else f"{payer_name} shows payment stress"
            why = (f"{dec_txt} (about {share:.0%} of this account's inflows); "
                   f"contagion adds {add:.0%} to PD. Own conduct: PD {own:.1%}.")
        return dict(
            borrower_id=borrower_id,
            own_pd=round(own, 4), contagion_adjusted_pd=round(adj, 4),
            runway_months=round(runway_own, 1), contagion_runway_months=round(runway_adj, 1),
            runway_delta=round(runway_adj - runway_own, 1),
            why=why,
            contributions=[dict(payer=p, payer_name=n, added_stress=a) for p, n, a in contribs],
        )

    def anchor_result(self, anchor_id: str) -> dict:
        m = self.anchor_measure.get(anchor_id, {})
        return dict(anchor_id=anchor_id, stress=round(self._own.get(anchor_id, 0.0), 3),
                    inflow_decline=m.get("inflow_decline"), n_suppliers_measured=m.get("n_suppliers_measured", 0),
                    elasticity=float(C.CONTAGION.get("inflow_loss_to_stress", 2.0)))

    def graph_payload(self) -> dict:
        """Nodes + edges + stress for the force-directed frontend."""
        nodes = []
        for aid, name, sector, n_sup in self.anchors[["anchor_id", "name", "sector", "n_suppliers"]].itertuples(index=False):
            a = self.anchor_result(aid)
            nodes.append(dict(id=aid, label=name, kind="anchor", sector=sector,
                              n_suppliers=int(n_sup), stress=a["stress"],
                              inflow_decline=a["inflow_decline"], n_suppliers_measured=a["n_suppliers_measured"]))
        for bid in self.edges.payee.unique():
            r = self.node_result(bid)
            row = self.borrowers.loc[bid]
            nodes.append(dict(id=bid, label=row["name"], kind="supplier", sector=row["sector"],
                              own_pd=r["own_pd"], stress=round(self._adj.get(bid, 0.0), 3),
                              contagion_adjusted_pd=r["contagion_adjusted_pd"],
                              runway_delta=r["runway_delta"], anchor_id=row["anchor_id"]))
        edges = [dict(source=e.payer, target=e.payee, amount=float(e.avg_monthly_amount),
                      inflow_share=float(e.inflow_share), regularity=float(e.regularity))
                 for e in self.edges.itertuples(index=False)]
        return dict(nodes=nodes, edges=edges, method=dict(
            equation="s_j = min(1, own_j + sum_i regularity_ij * s_i * inflow_share_ij)",
            iterations=ITERATIONS, anchor_stress="measured: clip(median inflow decline x elasticity, 0, 1)",
            elasticity=float(C.CONTAGION.get("inflow_loss_to_stress", 2.0))))
