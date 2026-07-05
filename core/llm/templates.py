"""Deterministic Jinja2 templates — the keyless fallback for every narrative type.

These must read naturally: they are what evaluators see when no API key is set. Banker
vocabulary throughout (RBI SMA ladder, IRAC, CRILC, RAG). Amounts are formatted in ₹ lakh/crore
by the `inr` filter registered in provider.py.
"""

from __future__ import annotations

# Each template receives a flat context dict. Missing keys should be guarded with `default`.
TEMPLATES = {
    # ---------------------------------------------------------------- PRAHARI
    "deterioration_storyline": """\
{{ name }} ({{ city }}, {{ sector }}) has moved from {{ from_bucket | default('green') }} to \
{{ to_bucket | default('amber') }} over the observation window. The account's stress is \
behavioural, not yet financial: repayment remains {{ repayment_state | default('current') }}, \
but leading indicators have turned.

Key beats:
{% for beat in beats %}  - Month {{ beat.month }}: {{ beat.text }}
{% endfor %}
On current trajectory the model projects an expected runway of about {{ runway_months }} months \
before the account crosses into 90+ DPD. Acting now — while conduct is still clean — preserves \
roughly {{ inr(provision_saved) }} of provisioning versus acting at NPA.""",

    "sma_memo": """\
SPECIAL MENTION ACCOUNT — EARLY WARNING MEMO
Account: {{ name }}  |  Borrower ID: {{ borrower_id }}  |  Facility: {{ loan_type }} {{ inr(sanctioned_limit) }}
Branch review as of {{ as_of_label }}  |  Current classification: {{ sma_stage | default('SMA-1') }} ({{ bucket }})

1. Summary
   {{ name }} is exhibiting early signs of stress consistent with the RBI SMA framework. \
Probability of default over the next 12 months is assessed at {{ (pd * 100) | round(1) }}%, with \
an estimated runway of {{ runway_months }} months. Exposure at risk: {{ inr(exposure) }}.

2. Reason codes (model-derived, most material first)
{% for r in reasons %}   {{ loop.index }}. {{ r }}
{% endfor %}
3. Recommended action
   {{ recommended_action | default('Enhanced monitoring; obtain latest stock and receivables statement; review limit utilisation.') }}

4. Provisioning impact
   Acting at the current stage preserves approximately {{ inr(provision_saved) }} relative to \
provisioning at NPA (IRAC sub-standard).""",

    "crilc_report": """\
CRILC REPORTING NOTE (aggregate exposure ≥ ₹5 crore)
Account: {{ name }}  |  Borrower ID: {{ borrower_id }}
Reporting trigger: SMA classification change to {{ sma_stage | default('SMA-2') }} as of {{ as_of_label }}.

Aggregate exposure: {{ inr(exposure) }}. The account has reported {{ sma_stage | default('SMA-2') }} \
status ({{ dpd_band | default('61-90 days') }} overdue equivalent on leading indicators). Per the \
Central Repository of Information on Large Credits framework, this status is to be reported within \
the stipulated timeline. Behavioural drivers are detailed in the associated early-warning memo.""",

    "portfolio_commentary": """\
PORTFOLIO EARLY-WARNING COMMENTARY — {{ as_of_label }}
Monitored book: {{ n_accounts }} MSME accounts, {{ inr(total_exposure) }} exposure.

Red bucket: {{ n_red }} accounts ({{ inr(red_exposure) }}). Amber: {{ n_amber }}. \
Average projected runway across the red bucket is {{ avg_runway }} months. This month the watch-list \
added {{ n_new_watch | default(0) }} accounts; contagion from anchor payment stress accounts for \
{{ n_contagion | default(0) }} of them.

Recommended focus: the {{ top_n | default(5) }} shortest-runway accounts concentrate \
{{ inr(top_exposure) }} of exposure and should be actioned first. Acting now across the red bucket \
preserves an estimated {{ inr(provision_saved) }} of provisioning versus acting at NPA.""",

    # ---------------------------------------------------------------- AROGYA
    "appraisal_note": """\
CREDIT APPRAISAL NOTE (alt-data health check)
Applicant: {{ name }}  |  {{ sector }}, {{ city }}  |  Requested view: origination snapshot

Unified health score: {{ score }}/1000 ({{ bucket }}). Confidence: {{ (confidence * 100) | round(0) }}%.

Pillar view:
{% for p in pillars %}  - {{ p.name }}: {{ p.value }}/100
{% endfor %}
Verification Triangle: {{ triangle_summary }}.

Assessment: {{ assessment }}

{% if bucket == 'REFER' %}Recommendation: REFER for officer review. {{ refer_reason | default('Score is in the borderline band; corroborate with one additional data source.') }}{% elif bucket == 'GO' %}Recommendation: proceed to sanction workflow, subject to standard verification.{% else %}Recommendation: decline at current data; see prescription for what would change the outcome.{% endif %}""",

    "triangle_hypothesis": """\
{% if consistent %}The {{ pair }} cross-check is consistent ({{ consistency }}/100): declared \
turnover moves in step with {{ corroborant }}. No anomaly.{% else %}The {{ pair }} cross-check is \
broken ({{ consistency }}/100). {{ detail }} — a pattern consistent with {{ hypothesis }}. \
Recommend physical verification before any sanction.{% endif %}""",

    "prescription": """\
DATA-COMPLETENESS PRESCRIPTION
Applicant: {{ name }}. Current confidence: {{ (confidence * 100) | round(0) }}% ({{ bucket }} — \
driven by a thin file, not by adverse signals).

To lift confidence:
{% for step in steps %}  - {{ step.text }} (adds ~{{ step.gain }} pts confidence)
{% endfor %}
Projected confidence after these steps: {{ (projected_confidence * 100) | round(0) }}%. \
The applicant should not be declined on data availability alone.""",

    # ---------------------------------------------------------------- DISHA
    "outreach_draft": """\
Subject: A loan option matched to how you actually earn

Hi {{ first_name }},

Based on your banking relationship with us, you may be a strong fit for a \
{{ product }} of up to {{ inr(ticket_size) }} at an indicative EMI of {{ inr(emi) }}/month — \
comfortably within your assessed repayment capacity.

{{ personalisation }}

If helpful, reply to this message or visit any branch and we'll walk you through it. There's no \
obligation, and your consent preferences remain fully in your control.

Warm regards,
Relationship Team, IDBI Bank""",

    "uplift_commentary": """\
CONVERSION UPLIFT SIMULATION
Last period: {{ n_enquiries }} enquiries → {{ n_conversions }} conversions ({{ base_rate }}%). \
Effort was spread evenly across the base.

Redirecting the same RM effort to the top {{ top_tier_n }} behaviourally-ranked leads \
(HOT + capacity-qualified) is projected to convert at ~{{ predicted_rate }}%, or about \
{{ projected_conversions }} conversions — a {{ uplift_x }}x improvement — for the same call volume.""",
}
