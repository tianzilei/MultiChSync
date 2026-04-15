# Signal-Level Quality Metrics for fNIRS Hb Signals (HbO and HbR)

## Scope

This document defines a signal-level quality assessment framework for fNIRS hemoglobin signals only. It assumes that the inputs are oxyhemoglobin (`HbO`) and deoxyhemoglobin (`HbR`) time series extracted from SNIRF files. All metrics related to raw optical intensity, optical density, dual-wavelength coupling, or OD-derived quality indices are intentionally excluded.

The framework is designed to be applicable to both task-based and resting-state paradigms.

## Notation

For one channel, let:

- `h_o[n]` denote the HbO sequence
- `h_r[n]` denote the HbR sequence
- `n = 1, 2, ..., N`
- `f_s` denote the sampling frequency in Hz

Define the following basic quantities for any signal `x[n]`:

- Mean:

  `mu(x) = (1 / N) * sum_{n=1..N} x[n]`

- Standard deviation:

  `sigma(x) = sqrt( (1 / N) * sum_{n=1..N} (x[n] - mu(x))^2 )`

- First difference:

  `dx[n] = x[n] - x[n-1]`, for `n = 2, ..., N`

- Median absolute deviation:

  `MAD(x) = median_n | x[n] - median_m x[m] |`

- Welch power spectral density:

  `P_x(f) = WelchPSD(x, f_s)`

- Pearson correlation:

  `corr(x, y) = Cov(x, y) / (sigma(x) * sigma(y))`

Use small positive constants `epsilon_mu`, `epsilon_sigma`, and `epsilon_MAD` for numerical stability where needed.

---

## Signal-Level Metrics

All metrics below are defined at the full-signal level for each channel. Compute them separately for HbO and HbR unless otherwise stated.

### 1. Near-flatline indicator

For any signal `x`:

`Range(x) = max_n x[n] - min_n x[n]`

Define the near-flatline indicator:

`Flat(x) = 1, if Range(x) < tau_flat`
`Flat(x) = 0, otherwise`

This is a hard-failure metric indicating an almost constant signal.

---

### 2. Signal coefficient of variation

For any signal `x`:

`CV(x) = sigma(x) / ( |mu(x)| + epsilon_mu )`

This quantifies relative amplitude variability.

---

### 3. Temporal signal-to-noise ratio

For any signal `x`:

`tSNR(x) = |mu(x)| / ( sigma(x) + epsilon_sigma )`

This is a signal stability metric. Larger values indicate a more stable time series.

---

### 4. Robust derivative index

For any signal `x`:

`RDI(x) = median_{n=2..N} |dx[n]| / ( MAD(x) + epsilon_MAD )`

This quantifies abrupt changes, spikes, or motion-like contamination relative to the signal scale.

---

### 5. Baseline drift index

Fit a linear model to the signal:

`x[n] = beta_0 + beta_1 * n + e[n]`

Then define:

`Drift(x) = |beta_1| / ( sigma(x) + epsilon_sigma )`

This measures low-frequency trend or baseline drift normalized by signal variability.

---

### 6. Spectral entropy

Let the discrete PSD values over the analysis band be `p_k`, normalized so that:

`q_k = p_k / sum_j p_j`

Then define spectral entropy:

`SpecEnt(x) = - sum_k q_k * log(q_k + epsilon_mu)`

A highly disordered or broadband-noise-dominated signal tends to have larger entropy, whereas a structured signal tends to have lower entropy.

---

### 7. Physiological-band power ratios

For any signal `x`, define the integrated band power over a frequency band `B`:

`Pow_B(x) = integral_{f in B} P_x(f) df`

Typical bands may include:

- Low-frequency band: `B_low = [0.01, 0.08] Hz`
- Mayer-wave band: `B_mayer = [0.08, 0.15] Hz`
- Respiration band: `B_resp = [0.15, 0.40] Hz`

Then define ratios such as:

`MayerRatio(x) = Pow_B_mayer(x) / ( Pow_B_low(x) + Pow_B_resp(x) + epsilon_mu )`

`RespRatio(x) = Pow_B_resp(x) / ( Pow_B_low(x) + Pow_B_mayer(x) + epsilon_mu )`

These ratios characterize whether the signal is dominated by narrow-band physiology or by other frequency content.

---

### 8. HbO-HbR full-signal correlation

For the paired channel:

`R_oh = corr(h_o, h_r)`

This is a cross-signal metric. It should be treated as a soft descriptor, not as a standalone hard gate, because its sign and magnitude may vary with physiology, preprocessing, and paradigm.

---

### 9. HbO-HbR variance ratio

For the paired channel:

`VarRatio_oh = sigma(h_o) / ( sigma(h_r) + epsilon_sigma )`

This measures imbalance between HbO and HbR dynamic ranges. Extremely large or small values may indicate asymmetric corruption or scaling problems.

---

### 10. HbO-HbR derivative consistency

Let:

`d_o[n] = h_o[n] - h_o[n-1]`
`d_r[n] = h_r[n] - h_r[n-1]`

Define:

`DerivCorr_oh = corr(d_o, d_r)`

This measures similarity in temporal change structure between HbO and HbR. It is useful as a soft metric for motion-like shared transients or asymmetric instability.

---

### 11. Task event contrast-to-noise ratio

This metric is only used in task-based designs.

For event `e`, let `B_e` be its baseline index set and `R_e` its response index set for signal `x`. Then:

`CNR_e(x) = | mean(x[B_e]) - mean(x[R_e]) | / sqrt( var(x[B_e]) + var(x[R_e]) + epsilon_sigma )`

Aggregate across all events:

`MedianCNR(x) = median_e CNR_e(x)`

This quantifies event-related detectability at the signal level.

---

### 12. Good-event fraction

This metric is only used in task-based designs.

For each event `e`, mark it good if it satisfies all event-level acceptability rules, for example:

- baseline drift below threshold
- event CNR above threshold
- no overlap with severe artifact intervals
- no near-flatline signal during baseline or response period

Then define:

`GoodEventFrac(x) = (number of good events for x) / (total number of events)`

---

### 13. Resting-state split-half reliability

This metric is only used in resting-state designs.

Split the retained signal into two halves `A` and `B`. For a multichannel Hb dataset, compute functional connectivity matrices:

`FC_A = corr_matrix(Hb_A)`
`FC_B = corr_matrix(Hb_B)`

Vectorize the upper triangles:

`v_A = vec_upper(FC_A)`
`v_B = vec_upper(FC_B)`

Then define:

`Rel_split = corr(v_A, v_B)`

This is a run-level reliability metric reflecting whether the resting-state connectivity pattern is reproducible within the run.

---

### 14. Retained usable duration fraction

This metric is used in both paradigms after signal-level hard rejection and bad-segment masking.

Let `T_good` be the total duration of retained usable data and `T_total` the original duration. Then:

`DurFrac = T_good / T_total`

This is a critical summary metric because a run with insufficient retained duration should fail even if some remaining segments look clean.

---

## Pseudocode: Task-Based Design

```text
INPUT:
  HbO[ch, t], HbR[ch, t], fs
  event_onsets, event_durations
  signal-level thresholds
  soft-score anchor values
  weights for composite scoring

FOR each channel c:

  hbo = HbO[c, :]
  hbr = HbR[c, :]

  # -------------------------
  # 1. Compute signal-level metrics
  # -------------------------

  Flat_hbo = near_flatline(hbo, tau_flat)
  Flat_hbr = near_flatline(hbr, tau_flat)

  CV_hbo = std(hbo) / (abs(mean(hbo)) + epsilon_mu)
  CV_hbr = std(hbr) / (abs(mean(hbr)) + epsilon_mu)

  tSNR_hbo = abs(mean(hbo)) / (std(hbo) + epsilon_sigma)
  tSNR_hbr = abs(mean(hbr)) / (std(hbr) + epsilon_sigma)

  RDI_hbo = median(abs(diff(hbo))) / (MAD(hbo) + epsilon_MAD)
  RDI_hbr = median(abs(diff(hbr))) / (MAD(hbr) + epsilon_MAD)

  Drift_hbo = abs(linear_slope(hbo)) / (std(hbo) + epsilon_sigma)
  Drift_hbr = abs(linear_slope(hbr)) / (std(hbr) + epsilon_sigma)

  SpecEnt_hbo = spectral_entropy(hbo, fs)
  SpecEnt_hbr = spectral_entropy(hbr, fs)

  MayerRatio_hbo = band_power_ratio(hbo, fs, B_mayer, B_low_union_other)
  MayerRatio_hbr = band_power_ratio(hbr, fs, B_mayer, B_low_union_other)

  RespRatio_hbo = band_power_ratio(hbo, fs, B_resp, B_low_union_other)
  RespRatio_hbr = band_power_ratio(hbr, fs, B_resp, B_low_union_other)

  R_oh = corr(hbo, hbr)
  VarRatio_oh = std(hbo) / (std(hbr) + epsilon_sigma)
  DerivCorr_oh = corr(diff(hbo), diff(hbr))

  # -------------------------
  # 2. Compute task-only metrics
  # -------------------------

  CNR_list_hbo = []
  CNR_list_hbr = []
  event_good_flags = []

  FOR each event e:
      B_e = baseline indices for event e
      R_e = response indices for event e

      cnr_hbo = abs(mean(hbo[B_e]) - mean(hbo[R_e])) /
                sqrt(var(hbo[B_e]) + var(hbo[R_e]) + epsilon_sigma)

      cnr_hbr = abs(mean(hbr[B_e]) - mean(hbr[R_e])) /
                sqrt(var(hbr[B_e]) + var(hbr[R_e]) + epsilon_sigma)

      baseline_drift_hbo = abs(linear_slope(hbo[B_e]))
      baseline_drift_hbr = abs(linear_slope(hbr[B_e]))

      event_is_good = TRUE

      IF cnr_hbo < tau_cnr_hbo AND cnr_hbr < tau_cnr_hbr:
          event_is_good = FALSE

      IF baseline_drift_hbo > tau_event_drift OR baseline_drift_hbr > tau_event_drift:
          event_is_good = FALSE

      IF severe_artifact_overlap(event e) == TRUE:
          event_is_good = FALSE

      append cnr_hbo to CNR_list_hbo
      append cnr_hbr to CNR_list_hbr
      append event_is_good to event_good_flags

  MedianCNR_hbo = median(CNR_list_hbo)
  MedianCNR_hbr = median(CNR_list_hbr)
  GoodEventFrac = mean(event_good_flags)

  # -------------------------
  # 3. Hard gating
  # -------------------------

  fail_channel = FALSE

  IF Flat_hbo == 1 OR Flat_hbr == 1:
      fail_channel = TRUE

  IF DurFrac(channel c) < tau_durfrac_task:
      fail_channel = TRUE

  IF GoodEventFrac < tau_good_event_frac:
      fail_channel = TRUE

  IF CV_hbo > tau_cv_hbo OR CV_hbr > tau_cv_hbr:
      fail_channel = TRUE

  IF RDI_hbo > tau_rdi_hbo OR RDI_hbr > tau_rdi_hbr:
      fail_channel = TRUE

  # -------------------------
  # 4. Soft scoring
  # -------------------------

  IF fail_channel == TRUE:
      Q_channel[c] = 0
      label[c] = "fail"
  ELSE:
      S_cv_hbo = map_lower_better(CV_hbo, a_cv_hbo, b_cv_hbo)
      S_cv_hbr = map_lower_better(CV_hbr, a_cv_hbr, b_cv_hbr)

      S_tsnr_hbo = map_higher_better(tSNR_hbo, a_tsnr_hbo, b_tsnr_hbo)
      S_tsnr_hbr = map_higher_better(tSNR_hbr, a_tsnr_hbr, b_tsnr_hbr)

      S_rdi_hbo = map_lower_better(RDI_hbo, a_rdi_hbo, b_rdi_hbo)
      S_rdi_hbr = map_lower_better(RDI_hbr, a_rdi_hbr, b_rdi_hbr)

      S_drift_hbo = map_lower_better(Drift_hbo, a_drift_hbo, b_drift_hbo)
      S_drift_hbr = map_lower_better(Drift_hbr, a_drift_hbr, b_drift_hbr)

      S_entropy_hbo = map_lower_better(SpecEnt_hbo, a_entropy_hbo, b_entropy_hbo)
      S_entropy_hbr = map_lower_better(SpecEnt_hbr, a_entropy_hbr, b_entropy_hbr)

      S_pair_corr = map_pair_metric(R_oh, a_pair_corr, b_pair_corr)
      S_var_ratio = map_ratio_metric(VarRatio_oh, a_var_ratio, b_var_ratio)
      S_deriv_pair = map_pair_metric(DerivCorr_oh, a_deriv_pair, b_deriv_pair)

      S_cnr_hbo = map_higher_better(MedianCNR_hbo, a_cnr_hbo, b_cnr_hbo)
      S_cnr_hbr = map_higher_better(MedianCNR_hbr, a_cnr_hbr, b_cnr_hbr)

      S_good_events = map_higher_better(GoodEventFrac, a_good_events, b_good_events)
      S_durfrac = map_higher_better(DurFrac(channel c), a_durfrac, b_durfrac)

      Q_channel[c] =
          w1 * mean(S_cv_hbo, S_cv_hbr) +
          w2 * mean(S_tsnr_hbo, S_tsnr_hbr) +
          w3 * mean(S_rdi_hbo, S_rdi_hbr) +
          w4 * mean(S_drift_hbo, S_drift_hbr) +
          w5 * mean(S_entropy_hbo, S_entropy_hbr) +
          w6 * S_pair_corr +
          w7 * S_var_ratio +
          w8 * S_deriv_pair +
          w9 * mean(S_cnr_hbo, S_cnr_hbr) +
          w10 * S_good_events +
          w11 * S_durfrac

      label[c] = classify_from_score(Q_channel[c])

# -------------------------
# 5. Run-level aggregation
# -------------------------

FailedChannelFrac = fraction of channels with label == "fail"
Q_run = trimmed_mean(Q_channel over channels, trim = 0.10) * (1 - lambda * FailedChannelFrac)

IF FailedChannelFrac > tau_failed_channel_frac_run:
    RunLabel = "fail"
ELSE:
    RunLabel = classify_from_score(Q_run)

OUTPUT:
  per-channel signal-level metrics
  per-channel composite scores
  run-level composite score
  run-level quality label
```

---

## Pseudocode: Resting-State Design

```text
INPUT:
  HbO[ch, t], HbR[ch, t], fs
  signal-level thresholds
  soft-score anchor values
  weights for composite scoring

FOR each channel c:

  hbo = HbO[c, :]
  hbr = HbR[c, :]

  # -------------------------
  # 1. Compute signal-level metrics
  # -------------------------

  Flat_hbo = near_flatline(hbo, tau_flat)
  Flat_hbr = near_flatline(hbr, tau_flat)

  CV_hbo = std(hbo) / (abs(mean(hbo)) + epsilon_mu)
  CV_hbr = std(hbr) / (abs(mean(hbr)) + epsilon_mu)

  tSNR_hbo = abs(mean(hbo)) / (std(hbo) + epsilon_sigma)
  tSNR_hbr = abs(mean(hbr)) / (std(hbr) + epsilon_sigma)

  RDI_hbo = median(abs(diff(hbo))) / (MAD(hbo) + epsilon_MAD)
  RDI_hbr = median(abs(diff(hbr))) / (MAD(hbr) + epsilon_MAD)

  Drift_hbo = abs(linear_slope(hbo)) / (std(hbo) + epsilon_sigma)
  Drift_hbr = abs(linear_slope(hbr)) / (std(hbr) + epsilon_sigma)

  SpecEnt_hbo = spectral_entropy(hbo, fs)
  SpecEnt_hbr = spectral_entropy(hbr, fs)

  MayerRatio_hbo = band_power_ratio(hbo, fs, B_mayer, B_low_union_other)
  MayerRatio_hbr = band_power_ratio(hbr, fs, B_mayer, B_low_union_other)

  RespRatio_hbo = band_power_ratio(hbo, fs, B_resp, B_low_union_other)
  RespRatio_hbr = band_power_ratio(hbr, fs, B_resp, B_low_union_other)

  R_oh = corr(hbo, hbr)
  VarRatio_oh = std(hbo) / (std(hbr) + epsilon_sigma)
  DerivCorr_oh = corr(diff(hbo), diff(hbr))

  DurFrac_c = retained_duration_fraction(channel c)

  # -------------------------
  # 2. Hard gating
  # -------------------------

  fail_channel = FALSE

  IF Flat_hbo == 1 OR Flat_hbr == 1:
      fail_channel = TRUE

  IF DurFrac_c < tau_durfrac_rest:
      fail_channel = TRUE

  IF CV_hbo > tau_cv_hbo OR CV_hbr > tau_cv_hbr:
      fail_channel = TRUE

  IF RDI_hbo > tau_rdi_hbo OR RDI_hbr > tau_rdi_hbr:
      fail_channel = TRUE

  # -------------------------
  # 3. Soft scoring
  # -------------------------

  IF fail_channel == TRUE:
      Q_channel[c] = 0
      label[c] = "fail"
  ELSE:
      S_cv_hbo = map_lower_better(CV_hbo, a_cv_hbo, b_cv_hbo)
      S_cv_hbr = map_lower_better(CV_hbr, a_cv_hbr, b_cv_hbr)

      S_tsnr_hbo = map_higher_better(tSNR_hbo, a_tsnr_hbo, b_tsnr_hbo)
      S_tsnr_hbr = map_higher_better(tSNR_hbr, a_tsnr_hbr, b_tsnr_hbr)

      S_rdi_hbo = map_lower_better(RDI_hbo, a_rdi_hbo, b_rdi_hbo)
      S_rdi_hbr = map_lower_better(RDI_hbr, a_rdi_hbr, b_rdi_hbr)

      S_drift_hbo = map_lower_better(Drift_hbo, a_drift_hbo, b_drift_hbo)
      S_drift_hbr = map_lower_better(Drift_hbr, a_drift_hbr, b_drift_hbr)

      S_entropy_hbo = map_lower_better(SpecEnt_hbo, a_entropy_hbo, b_entropy_hbo)
      S_entropy_hbr = map_lower_better(SpecEnt_hbr, a_entropy_hbr, b_entropy_hbr)

      S_mayer_hbo = map_band_metric(MayerRatio_hbo, a_mayer_hbo, b_mayer_hbo)
      S_mayer_hbr = map_band_metric(MayerRatio_hbr, a_mayer_hbr, b_mayer_hbr)

      S_resp_hbo = map_band_metric(RespRatio_hbo, a_resp_hbo, b_resp_hbo)
      S_resp_hbr = map_band_metric(RespRatio_hbr, a_resp_hbr, b_resp_hbr)

      S_pair_corr = map_pair_metric(R_oh, a_pair_corr, b_pair_corr)
      S_var_ratio = map_ratio_metric(VarRatio_oh, a_var_ratio, b_var_ratio)
      S_deriv_pair = map_pair_metric(DerivCorr_oh, a_deriv_pair, b_deriv_pair)

      S_durfrac = map_higher_better(DurFrac_c, a_durfrac, b_durfrac)

      Q_channel[c] =
          w1 * mean(S_cv_hbo, S_cv_hbr) +
          w2 * mean(S_tsnr_hbo, S_tsnr_hbr) +
          w3 * mean(S_rdi_hbo, S_rdi_hbr) +
          w4 * mean(S_drift_hbo, S_drift_hbr) +
          w5 * mean(S_entropy_hbo, S_entropy_hbr) +
          w6 * mean(S_mayer_hbo, S_mayer_hbr) +
          w7 * mean(S_resp_hbo, S_resp_hbr) +
          w8 * S_pair_corr +
          w9 * S_var_ratio +
          w10 * S_deriv_pair +
          w11 * S_durfrac

      label[c] = classify_from_score(Q_channel[c])

# -------------------------
# 4. Run-level resting-state reliability
# -------------------------

RetainedHb = remove_failed_channels_and_bad_segments(HbO, HbR)

Split retained data into temporal halves A and B

FC_A_hbo = corr_matrix(RetainedHb.HbO in half A)
FC_B_hbo = corr_matrix(RetainedHb.HbO in half B)

FC_A_hbr = corr_matrix(RetainedHb.HbR in half A)
FC_B_hbr = corr_matrix(RetainedHb.HbR in half B)

Rel_split_hbo = corr(vec_upper(FC_A_hbo), vec_upper(FC_B_hbo))
Rel_split_hbr = corr(vec_upper(FC_A_hbr), vec_upper(FC_B_hbr))

Rel_split = mean(Rel_split_hbo, Rel_split_hbr)

S_rel_split = map_higher_better(Rel_split, a_rel_split, b_rel_split)

# -------------------------
# 5. Run-level aggregation
# -------------------------

FailedChannelFrac = fraction of channels with label == "fail"

Q_run_base = trimmed_mean(Q_channel over channels, trim = 0.10) * (1 - lambda * FailedChannelFrac)

Q_run = Q_run_base * (0.5 + 0.5 * max(Rel_split, 0))

IF FailedChannelFrac > tau_failed_channel_frac_run:
    RunLabel = "fail"
ELSE IF retained_total_duration_fraction < tau_total_durfrac_rest:
    RunLabel = "fail"
ELSE:
    RunLabel = classify_from_score(Q_run)

OUTPUT:
  per-channel signal-level metrics
  per-channel composite scores
  run-level split-half reliability
  run-level composite score
  run-level quality label
```

---

## Suggested Quality Tiers

A simple score-to-label mapping for both paradigms:

- `Q < 0.50` -> `poor`
- `0.50 <= Q < 0.70` -> `fair`
- `0.70 <= Q < 0.85` -> `good`
- `Q >= 0.85` -> `excellent`

Any hard-gate violation should override the soft score and produce `fail`.

---

## Practical Notes

1. Use identical preprocessing conventions before computing these metrics across all runs in a study.
2. Keep HbO and HbR metrics separate in storage, even if you average them for scoring.
3. Treat `HbO-HbR correlation`, `variance ratio`, and `derivative consistency` as soft metrics only.
4. For task-based data, `MedianCNR` and `GoodEventFrac` are usually the most informative task-specific signal-level additions.
5. For resting-state data, `Rel_split` and retained usable duration are critical run-level summaries.

