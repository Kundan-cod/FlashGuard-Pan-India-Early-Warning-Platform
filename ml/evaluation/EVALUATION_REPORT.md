# FlashGuard AI/ML Evaluation Report (Phase C)

**Generated:** 2026-09-26T09:00:20Z  
**Status:** **NOT VALIDATED** (Honest Demonstration Baseline)  
**Pipeline:** Separate Flood & Landslide Dual-Model Architecture  

---

## 1. Executive Summary & Scientific Honesty Declaration

> [!IMPORTANT]
> **ABSOLUTELY NO FAKE AI:**
> FlashGuard strictly refuses to claim operational validation without verified ground-truth censuses. While authoritative catalogs exist (NRSC/ISRO Landslide Atlas 1998–2022, NRSC Flood Hazard Zonation, Bhuvan Flood Inundation layers), they catalog positive historical events without nationwide confirmed negative observations. Converting unobserved areas into negatives (-1 to 0) introduces extreme false-negative bias. 
> Therefore, this model is trained on a **deterministic physically-ordered dataset** to prove the complete end-to-end ML architecture, probability calibration, recall-optimized thresholding, and risk-fusion pipeline.

---

## 2. Model Architecture & Data Contract

```
                     NORMALIZED INTERNAL FEATURES
                                  │
                 ┌────────────────┴────────────────┐
                 ▼                                 ▼
           FLOOD MODEL                      LANDSLIDE MODEL
        (Gradient Boosted)                 (Gradient Boosted)
                 │                                 │
         Raw Probability                    Raw Probability
                 │                                 │
           Platt Sigmoid                     Platt Sigmoid
            Calibration                       Calibration
                 │                                 │
        Calibrated Probability            Calibrated Probability
                 └────────────────┬────────────────┘
                                  ▼
                             RISK ENGINE
                                  │
                    ├── Multi-Hazard Risk Fusion
                    ├── Physical Override Floors
                    ├── Independent Confidence Engine
                    ├── Windowed Lead-Time Estimation
                    └── Additive Path Explainability
                                  │
                                  ▼
                         PREDICTION / ALERT
```

---

## 3. Dataset & Split Methodology

* **Dataset Size:** 1,200 samples per hazard (100% labeled, three-state filter applied).
* **Class Distribution:**
  * Flood: 44.0% Positives (672 Negatives, 528 Positives)
  * Landslide: 48.8% Positives (615 Negatives, 585 Positives)
* **Split Strategy:** Contiguous Block Temporal Partition:
  * **Train Set (60%):** 720 samples
  * **Validation Set (20%):** 240 samples (used strictly for Platt calibration & threshold tuning)
  * **Test Set (20%):** 240 samples (held-out, touched ONCE for final generalization evaluation)

---

## 4. Flood Model Evaluation

* **Model Version:** `flood-gbt-de05ad0f076b237e-20260906183021`
* **Operating Threshold:** `0.25` *(Objective: F-beta with $\beta=2.0$ prioritizing recall for disaster early warning, minimum specificity $\ge 0.25$)*
* **Calibration Method:** Platt Scaling (Sigmoid)
  * Validation Brier Score: `0.2125` (before) → `0.2002` (after calibration)
  * Test Brier Score: `0.1943`
  * Expected Calibration Error (ECE): `0.0819`

### Held-out Test Metrics (240 unseen samples)
| Metric | Score | Note |
| :--- | :--- | :--- |
| **ROC-AUC** | **0.7630** | Area under ROC curve |
| **PR-AUC (Average Precision)** | **0.7030** | Area under Precision-Recall curve |
| **Recall / Sensitivity** | **95.7%** | 90 of 94 flood events successfully detected |
| **Precision** | **46.2%** | Precision at recall-optimized threshold |
| **Specificity** | **28.1%** | True negative rate |
| **F1 Score** | **0.6228** | Harmonic mean of precision and recall |
| **F2 Score** | **0.7881** | Recall-weighted F-beta |
| **Brier Score** | **0.1943** | Probabilistic accuracy score |

### Confusion Matrix (Test Set)
| | Predicted Negative (0) | Predicted Positive (1) |
| :--- | :--- | :--- |
| **Actual Negative (0)** | **41** (TN) | **105** (FP) |
| **Actual Positive (1)** | **4** (FN) | **90** (TP) |

### Top Features by Gain Importance
- **rain_3h** (`mm`): 18.8% gain (IMD/GPM)
- **river_rate_of_rise_1h** (`m/h`): 16.4% gain (CWC/IoT Gauge)
- **rain_24h** (`mm`): 14.7% gain (IMD/GPM)
- **rain_intensity** (`mm/hr`): 14.6% gain (IMD/AWS/Radar)
- **flow_accumulation** (`cells`): 12.4% gain (CartoDEM/HydroSHEDS)

---

## 5. Landslide Model Evaluation

* **Model Version:** `landslide-gbt-c7182575b8fb7bc5-20260906183022`
* **Operating Threshold:** `0.4` *(Objective: F-beta with $\beta=2.0$, min_specificity $\ge 0.25$)*
* **Calibration Method:** Platt Scaling (Sigmoid)
  * Validation Brier Score: `0.2617` → `0.2349`
  * Test Brier Score: `0.2296`
  * Expected Calibration Error (ECE): `0.0372`

### Held-out Test Metrics (240 unseen samples)
| Metric | Score | Note |
| :--- | :--- | :--- |
| **ROC-AUC** | **0.6603** | Area under ROC curve |
| **PR-AUC (Average Precision)** | **0.6140** | Area under Precision-Recall curve |
| **Recall / Sensitivity** | **81.1%** | 90 of 111 landslide events detected |
| **Precision** | **54.2%** | Precision at operating threshold |
| **Specificity** | **41.1%** | True negative rate |
| **F1 Score** | **0.6498** | Harmonic mean |
| **F2 Score** | **0.7377** | Recall-weighted |
| **Brier Score** | **0.2296** | Probabilistic accuracy |

### Confusion Matrix (Test Set)
| | Predicted Negative (0) | Predicted Positive (1) |
| :--- | :--- | :--- |
| **Actual Negative (0)** | **53** (TN) | **76** (FP) |
| **Actual Positive (1)** | **21** (FN) | **90** (TP) |

### Top Features by Gain Importance
- **slope** (`degrees`): 15.8% gain (Bhuvan/SRTM DEM)
- **curvature** (`index`): 15.8% gain (Bhuvan/SRTM DEM)
- **rain_24h** (`mm`): 15.0% gain (IMD/GPM)
- **rain_3h** (`mm`): 14.4% gain (IMD/GPM)
- **susceptibility** (`index`): 14.0% gain (GSI Landslide Atlas)

---

## 6. Confidence & Risk Separation

* **Risk Probability:** Output of calibrated ensemble models for each hazard.
* **Confidence Metric:** Independent quality function factoring:
  1. **Feature Completeness** (have / expected sources)
  2. **Telemetry Freshness** (stale sensor penalty)
  3. **Source Quality Flags** (penalty for non-GOOD status)
  4. **Missing Critical Features** (penalty if core precursors like 3h rain or soil moisture are missing)
  5. **Model Validation State** (capped at 0.85 when unvalidated)

---

## 7. Known Limitations & Production Readiness

1. **Synthetic Training Foundation:** Shipped models are trained on deterministic synthetic distributions to prove the pipeline without external API credentials.
2. **Catalog vs. Census Gap:** Official historical catalogs (NRSC Landslide Atlas, Bhuvan Flood Inundation) must be matched with negative observation censuses before declaring operational validation.
3. **Threshold Status:** Stored thresholds (`0.25` for flood, `0.40` for landslide) are machine-learning decision thresholds optimized for recall, NOT official government disaster warning thresholds.
