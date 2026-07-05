"""Contagion model (BUILD_SPEC §4.2) - the demo's signature reveal.

Directed anchor→supplier payment graph. Stress diffusion (auditable, documented math):

    Each node has own stress  s_i ∈ [0,1]  (suppliers: their PD; anchors: payment-disruption).
    Propagate downstream for 2 iterations:

        s_j  +=  Σ_i  w_ij · s_i · dependency_ij

    where  dependency_ij = payer i's share of payee j's inflows  (edge.inflow_share)
    and    w_ij          = payment regularity of the edge.

Output per node: contagion-adjusted PD, runway delta, and a plain-language "why" naming the
upstream cause. Pure-Python maths (networkx used only for optional export) so it always runs.
"""

from __future__ import annotations

import numpy as np

ITERATIONS = 2
# Anchor #1 cut payments 40% → high transmitted stress; other anchors are steady payers.
ANCHOR_STRESS = {"ANCH1": 0.85}
ANCHOR_STRESS_DEFAULT = 0.12


def _pd_to_runway_months(pd_value: float) -> float:
    pd_value = float(np.clip(pd_value, 1e-4, 0.999))
    monthly_h = 1 - (1 - pd_value) ** (1 / 12)
    return float(np.clip(1.0 / max(monthly_h, 1e-4), 0, 24))


class ContagionGraph:
    def __init__(self, frames: dict, pd_by_borrower: dict):
        self.frames = frames
        self.pd_by_borrower = pd_by_borrower
        self.anchors = frames["anchors"]
        self.edges = frames["edges"]
        self.borrowers = frames["borrowers"].set_index("borrower_id")
        self._own = {}         # node -> own stress
        self._adj = {}         # node -> adjusted stress after diffusion
        self._contrib = {}     # payee -> list of (payer, added_stress)
        self._diffuse()

    def _diffuse(self):
        # own stress
        own = {}
        for aid in self.anchors.anchor_id:
            own[aid] = ANCHOR_STRESS.get(aid, ANCHOR_STRESS_DEFAULT)
        for bid in self.edges.payee.unique():
            own[bid] = float(self.pd_by_borrower.get(bid, 0.05))
        stress = dict(own)
        contrib = {n: [] for n in own}
        edges = list(self.edges.itertuples(index=False))
        for _ in range(ITERATIONS):
            new = dict(stress)
            for e in edges:
                add = float(e.regularity) * stress.get(e.payer, 0.0) * float(e.inflow_share)
                new[e.payee] = min(1.0, new.get(e.payee, 0.0) + add)
            # record contributions on the final pass (approx: recompute from current stress)
            stress = new
        for e in edges:
            add = float(e.regularity) * stress.get(e.payer, 0.0) * float(e.inflow_share)
            if add > 0.01:
                contrib.setdefault(e.payee, []).append((e.payer, e.payer_name, round(add, 3)))
        self._own, self._adj, self._contrib = own, stress, contrib

    # ------------------------------------------------------------------ per-node results
    def adjusted_pd(self, borrower_id: str) -> float:
        own = float(self.pd_by_borrower.get(borrower_id, 0.05))
        added = max(0.0, self._adj.get(borrower_id, own) - own)
        return float(np.clip(own + added, 0, 0.99))

    def node_result(self, borrower_id: str) -> dict:
        own = float(self.pd_by_borrower.get(borrower_id, 0.05))
        adj = self.adjusted_pd(borrower_id)
        runway_own = _pd_to_runway_months(own)
        runway_adj = _pd_to_runway_months(adj)
        why = None
        contribs = sorted(self._contrib.get(borrower_id, []), key=lambda c: -c[2])
        if contribs:
            payer, payer_name, add = contribs[0]
            why = (f"{payer_name} slowed payments (≈{int(self.borrowers.at[borrower_id, 'anchor_share']*100)}% "
                   f"of this account's inflows); contagion adds {add:.0%} to PD.") if payer == "ANCH1" \
                else f"Upstream stress from {payer_name} adds {add:.0%} to PD."
        return dict(
            borrower_id=borrower_id,
            own_pd=round(own, 4), contagion_adjusted_pd=round(adj, 4),
            runway_months=round(runway_own, 1), contagion_runway_months=round(runway_adj, 1),
            runway_delta=round(runway_adj - runway_own, 1),
            why=why,
        )

    def graph_payload(self) -> dict:
        """Nodes + edges + stress for the force-directed frontend."""
        nodes = []
        for aid, name, sector, n_sup in self.anchors[["anchor_id", "name", "sector", "n_suppliers"]].itertuples(index=False):
            nodes.append(dict(id=aid, label=name, kind="anchor", sector=sector,
                              n_suppliers=int(n_sup), stress=round(self._own.get(aid, 0.1), 3)))
        for bid in self.edges.payee.unique():
            r = self.node_result(bid)
            row = self.borrowers.loc[bid]
            nodes.append(dict(id=bid, label=row["name"], kind="supplier", sector=row["sector"],
                              own_pd=r["own_pd"], stress=round(self._adj.get(bid, 0.0), 3),
                              contagion_adjusted_pd=r["contagion_adjusted_pd"],
                              runway_delta=r["runway_delta"], anchor_id=row["anchor_id"]))
        edges = [dict(source=e.payer, target=e.payee,
                      amount=float(e.avg_monthly_amount), inflow_share=float(e.inflow_share))
                 for e in self.edges.itertuples(index=False)]
        return dict(nodes=nodes, edges=edges)
