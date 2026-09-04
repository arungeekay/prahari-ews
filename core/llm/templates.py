"""Deterministic Jinja2 templates - the keyless fallback for every narrative type.

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
before the account crosses into 90+ DPD. Acting now - while conduct is still clean - preserves \
roughly {{ inr(provision_saved) }} of provisioning versus acting at NPA.""",

    "sma_memo": """\
EARLY WARNING MEMO (behavioural, model-assisted)
Account: {{ name }}  |  Borrower ID: {{ borrower_id }}  |  Facility: {{ loan_type }} {{ inr(sanctioned_limit) }}
Branch review as of {{ as_of_label }}
Statutory status (RBI, days past due): {{ statutory_sma | default('Standard') }} at {{ dpd | default(0) }} DPD
Model-implied SMA-equivalent (behaviour): {{ model_implied_sma | default('Standard (no model flag)') }}  |  PRAHARI grade {{ grade | default('-') }} ({{ bucket }})

1. Summary
   {{ name }} is exhibiting early signs of stress on leading behavioural indicators while its \
statutory classification remains {{ statutory_sma | default('Standard') }}. Calibrated probability of \
default over the next 12 months is {{ (pd * 100) | round(1) }}%, with an estimated runway of \
{{ runway_months }} months. Exposure at risk: {{ inr(exposure) }}.

2. Reason codes (model-derived, most material first)
{% for r in reasons %}   {{ loop.index }}. {{ r }}
{% endfor %}
{% if note_citation %}3. Officer observation on file ({{ note_date }})
   "{{ note_citation }}"

4. Recommended action
{% else %}3. Recommended action
{% endif %}   {{ recommended_action | default('Enhanced monitoring; obtain latest stock and receivables statement; review limit utilisation.') }}

{% if note_citation %}5.{% else %}4.{% endif %} Provisioning impact
   Acting at the current stage preserves approximately {{ inr(provision_saved) }} relative to \
provisioning at NPA (IRAC sub-standard). The model flag is an early-warning input for officer \
judgement; the statutory SMA ladder continues to be driven by days past due.""",

    "crilc_report": """\
{% if eligible %}CRILC NOTE (aggregate exposure {{ inr(exposure) }}, at or above the {{ inr(threshold) }} reporting threshold)
Account: {{ name }}  |  Borrower ID: {{ borrower_id }}  |  As of {{ as_of_label }}
Statutory status: {{ statutory_sma }} ({{ dpd_band }} past due). Model-implied SMA-equivalent: {{ model_implied_sma }} (grade {{ grade }}).

{% if statutory_sma == 'SMA-2' or statutory_sma == 'NPA' %}The account is statutorily {{ statutory_sma }}. Under the Central Repository of Information on Large \
Credits framework this status is to be reported within the stipulated timeline. Behavioural drivers are \
detailed in the associated early-warning memo.{% else %}The account is not yet statutorily SMA-2, so no CRILC report is due. This note is prepared so the \
branch is ready: the behavioural model places the account at {{ model_implied_sma }}, and a slip to \
61+ days past due would trigger CRILC reporting within 7 days. Behavioural drivers are detailed in \
the associated early-warning memo.{% endif %}{% else %}CRILC READINESS NOTE
Account: {{ name }}  |  Borrower ID: {{ borrower_id }}  |  As of {{ as_of_label }}
Aggregate exposure {{ inr(exposure) }} is below the {{ inr(threshold) }} CRILC threshold; no CRILC reporting \
obligation arises for this borrower. Statutory status: {{ statutory_sma }} ({{ dpd_band }} past due). \
Model-implied SMA-equivalent: {{ model_implied_sma }} (grade {{ grade }}). Monitoring continues under the \
bank's internal early-warning framework.{% endif %}""",

    "portfolio_commentary": """\
PORTFOLIO EARLY-WARNING COMMENTARY - {{ as_of_label }}
Monitored book: {{ n_accounts }} MSME accounts, {{ inr(total_exposure) }} exposure.

Red bucket: {{ n_red }} accounts ({{ inr(red_exposure) }}). Amber: {{ n_amber }}. \
Average projected runway across the red bucket is {{ avg_runway }} months. {{ n_movers | default(0) }} \
accounts moved up materially in PD this month. The watch-list holds {{ n_new_watch | default(0) }} \
priority accounts; measured anchor payment stress re-bucketed {{ n_contagion | default(0) }} supplier \
accounts whose own conduct is still clean.

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
broken ({{ consistency }}/100). {{ detail }} - a pattern consistent with {{ hypothesis }}. \
Recommend physical verification before any sanction.{% endif %}""",

    "prescription": """\
DATA-COMPLETENESS PRESCRIPTION
Applicant: {{ name }}. Current confidence: {{ (confidence * 100) | round(0) }}% ({{ bucket }} - \
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
{{ product }} of up to {{ inr(ticket_size) }} at an indicative EMI of {{ inr(emi) }}/month - \
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
{{ projected_conversions }} conversions - a {{ uplift_x }}x improvement - for the same call volume.""",
}
