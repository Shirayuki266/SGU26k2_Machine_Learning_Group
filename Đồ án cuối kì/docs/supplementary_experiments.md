# T17b supplementary experiments

## Result

The corrected full run completed successfully under parent run
`2512bc9c844a4b39a150c52f6bded9db`. It evaluated the predeclared 13 estimator
configurations and two causal baselines using three expanding train-only folds.
The pooled OOF set contains 76,102 samples. Validation metrics use 102,479
primary validation samples. The runner recorded `test_csv_accessed: false`;
candidate selection and tuning did not use test data.

The full design selected the best candidate in each family using pooled
train-CV MAE. Fusion uses the top three distinct model families, and the Ridge
stacker is fit only on their aligned train OOF predictions.

### CV and candidate validation results

Fold MAE mean ± std is descriptive (`ddof=0`); pooled metrics are computed
over all OOF samples. Empty validation cells mean that candidate was not
refit/scored on validation.

| Candidate | Pooled CV MAE | Pooled CV RMSE | Fold MAE mean ± std | Validation MAE |
|---|---:|---:|---:|---:|
| `rf_A_locked` | 10.0402 | 17.8444 | 10.0610 ± 1.3194 | 9.5615 |
| `rf_B_locked` | 9.7253 | 17.3142 | 9.7449 ± 1.2462 | 9.3798 |
| `rf_B_tuned_small` | 9.8955 | 17.6253 | 9.9155 ± 1.2705 | |
| `rf_B_tuned_more_trees` | 9.8872 | 17.6124 | 9.9073 ± 1.2778 | 9.5093 |
| `hgb_A_squared` | 9.8685 | 17.4567 | 9.8888 ± 1.2859 | |
| `hgb_A_absolute` | 9.7074 | 17.8785 | 9.7271 ± 1.2560 | |
| `hgb_B_squared` | 9.6660 | 17.0248 | 9.6843 ± 1.1638 | |
| `hgb_B_absolute` | 9.5185 | 17.5230 | 9.5376 ± 1.2123 | 9.4868 |
| `lasso_B_alpha_0_1` | 10.1203 | 17.7127 | 10.1400 ± 1.2576 | 9.8143 |
| `lasso_B_alpha_1` | 10.3376 | 18.3181 | 10.3583 ± 1.3160 | |
| `elastic_net_B_alpha_0_1` | 11.6974 | 19.7642 | 11.7232 ± 1.6404 | |
| `tree_B_depth_6` | 10.4585 | 18.5228 | 10.4790 ± 1.3063 | |
| `tree_B_depth_12` | 10.4540 | 18.3572 | 10.4734 ± 1.2363 | 9.8648 |
| `rolling_mean_3h` | 15.0656 | 26.2851 | 15.0985 ± 2.1053 | 14.0165 |
| `same_target_hour_yesterday` | 60.2176 | 87.6658 | 60.4071 ± 14.2492 | 50.4168 |
| `fusion_3_cv_champions` | 9.4997 | 17.2229 | 9.5187 ± 1.2054 | 9.2746 |

### Validation results

All rows below use the same primary validation cohort; these scores are
development evidence, not test results.

| Candidate | Validation MAE | Validation RMSE |
|---|---:|---:|
| `rf_A_locked` | 9.5615 | 18.9648 |
| `rf_B_locked` | 9.3798 | 18.6447 |
| `rf_B_tuned_more_trees` | 9.5093 | 18.7612 |
| `hgb_B_absolute` | 9.4868 | 20.1625 |
| `lasso_B_alpha_0_1` | 9.8143 | 18.4641 |
| `tree_B_depth_12` | 9.8648 | 19.1801 |
| `rolling_mean_3h` | 14.0165 | 26.8095 |
| `same_target_hour_yesterday` | 50.4168 | 84.3504 |
| `fusion_3_cv_champions` | 9.2746 | 18.5055 |
| `stack` (Ridge, alpha=1) | **9.2321** | 18.4718 |

The train-CV family winners were `rf_B_locked`, `hgb_B_absolute`,
`lasso_B_alpha_0_1`, and `tree_B_depth_12`. Fusion used the first three,
selected as the top distinct model families by train-CV MAE. The stacker’s
meta-fit used only aligned OOF train predictions; validation labels were
prediction-only. Although Stack has the lowest validation MAE in this
supplementary comparison, it does not replace the T12/T13 frozen model or
change the deployment decision.

The regenerated [T17a experiment summary](../reports/tables/experiment_summary.md)
has 27 model/candidate/ensemble rows and 412 passing consistency checks, with
no `KHÁC` or `CHƯA CÓ` checks. It reports test metrics only for the existing
T13 runs. Its audit export retains all 264 ledger records.

## Execution and audit notes

The original T13 run archive was restored with the official script after
verifying SHA-256
`5362ebf0c51961d96537f5c3a8ffae39b4e1da0b7f6daa6230593445a8e471c1`.
Restore verified 93 files without writing to the ledger or refitting models.
The smoke run then completed with 15 candidates and no failures.

The first full attempt completed the candidate/fold and validation work but
failed while logging Stack metadata because an OOF reference variable was
undefined. That failed parent and its completed child runs remain in the
ledger. The defect was fixed and covered by a regression test, then the same
frozen full design was run again successfully. This repeated full attempt
exceeded the predeclared compute budget; no candidates or hyperparameters were
added or changed. The summary model table uses children of the successful
full parent, while the audit export preserves the failed attempt and smoke
records.

No test samples were used to select, tune, fit, or score T17b candidates. The
T13 frozen recipe, model, and saved test artifacts were not modified.
