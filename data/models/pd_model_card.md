# PRAHARI PD Model Card

**Task:** probability of default within 12 months (RBI SMA early warning).

**Algorithm:** XGBoost with isotonic calibration. **Validation:** borrower-disjoint + temporal: train fold A at as_of [6, 9, 12]; calibrate and choose thresholds on fold B at as_of [15, 18]; report fold C at as_of [15, 18] (borrowers never seen, dates after training). Deployed model = evaluated model, no refit.

## Headline metrics (validation fold C, borrowers never seen, later as-of months)
| Metric | Value |
|---|---|
| AUC | 0.962 (95% CI 0.9392 to 0.9794) |
| KS | 0.819 |
| Operating threshold (bank 90% accuracy point) | 0.058 |
| Accuracy | 0.902 |
| Balanced accuracy | 0.908 |
| Recall | 0.914 |
| Precision | 0.342 |
| Brier | 0.0277 |

Confusion matrix (rows = actual, cols = predicted) at the operating threshold:

|  | pred 0 | pred 1 |
|---|---|---|
| actual 0 | 934 | 102 |
| actual 1 | 5 | 53 |

## Operating points
| Point | Threshold | Accuracy | Bal. acc | Recall | Precision | Alerts | Missed |
|---|---|---|---|---|---|---|---|
| Maximum capture | 0.048 | 0.881 | 0.897 | 0.914 | 0.298 | 178 | 5 |
| Bank 90% accuracy | 0.058 | 0.902 | 0.908 | 0.914 | 0.342 | 155 | 5 |
| Precision weighted | 0.303 | 0.961 | 0.825 | 0.672 | 0.619 | 63 | 19 |

## Lead time (share of eventual defaulters already flagged)
| Months before 90+ DPD | n | Flagged |
|---|---|---|
| 1-3 | 24 | 1.0 |
| 4-6 | 16 | 0.875 |
| 7-9 | 11 | 0.9091 |
| 10-12 | 7 | 0.7143 |

## Baselines on the same fold
| Method | Recall | Precision | Alerts | PRAHARI recall at same alerts |
|---|---|---|---|---|
| Arrears rule | 0.328 | 1.000 | 19 | 0.293 |
| Arrears or utilisation rule | 0.655 | 0.372 | 102 | 0.845 |
| Logistic regression | 0.690 | 0.244 | 164 | 0.914 |

## Honesty note
Every number is computed on borrowers the model never saw, at as-of months after the training window (borrower-disjoint temporal validation), and the operating thresholds were chosen on a separate calibration fold. The deployed model is the evaluated model. The headline is reported at the operating point that meets the bank's stated 90 percent accuracy requirement; the maximum-capture point and the full threshold table are shown alongside so the bank can pick its own trade-off. Data is synthetic and cleaner than a real book, so these numbers are an upper bound on what the method would achieve on IDBI data; the method, not the number, is what transfers.
