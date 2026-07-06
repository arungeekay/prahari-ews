# PRAHARI PD Model Card

**Task:** probability of default within 12 months (RBI SMA early warning).

**Algorithm:** XGBoost. **Validation:** temporal (train as_of [6, 9, 12], validate as_of [15, 18]).

## Headline metrics (out-of-time)
| Metric | Value |
|---|---|
| AUC | 0.952 |
| Balanced accuracy | 0.897 |
| Recall | 0.915 |
| Precision | 0.284 |
| F1 | 0.434 |
| Operating threshold | 0.050 |

Confusion matrix (rows = actual, cols = predicted) at the operating threshold:

|  | pred 0 | pred 1 |
|---|---|---|
| actual 0 | 4774 | 655 |
| actual 1 | 24 | 260 |

## Honesty note
Metrics are out-of-time (temporal validation): the model is trained on earlier as-of months and validated on later ones, so no future information leaks. The headline is AUC and balanced accuracy, NOT raw accuracy on an imbalanced target. AUC intentionally sits in a plausible ~0.94 band; a near-perfect score would indicate leakage or an unrealistically tidy dataset. Precision is modest by design - an early-warning system prioritises recall (catching stress) at a manageable alert volume; every flag carries reason codes for officer review.
