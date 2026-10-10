"""Leakage-safe Ames Housing feature-selection benchmark."""
from pathlib import Path
import time
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.base import BaseEstimator, TransformerMixin, clone
from sklearn.compose import ColumnTransformer, make_column_selector
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.feature_selection import SelectKBest, f_regression, mutual_info_regression, RFE, SelectFromModel
from sklearn.linear_model import Ridge, Lasso
from sklearn.ensemble import RandomForestRegressor
from sklearn.svm import SVR
from sklearn.model_selection import KFold
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parent
SEED = 42


class HousingSemantics(TransformerMixin, BaseEstimator):
    """Apply the original EDA rules; learn imputation only on training rows."""
    def fit(self, X, y=None):
        self.feature_names_in_ = np.asarray(X.columns, dtype=object)
        cleaned = self._domain_rules(X)
        self.frontage_by_neighborhood_ = cleaned.groupby('Neighborhood')['LotFrontage'].median()
        self.frontage_fallback_ = cleaned['LotFrontage'].median()
        cleaned['LotFrontage'] = cleaned['LotFrontage'].fillna(
            cleaned['Neighborhood'].map(self.frontage_by_neighborhood_)).fillna(self.frontage_fallback_)
        self.fill_values_ = {}
        for col in cleaned:
            if pd.api.types.is_numeric_dtype(cleaned[col]):
                value = cleaned[col].median()
                self.fill_values_[col] = 0 if pd.isna(value) else value
            else:
                modes = cleaned[col].dropna().mode()
                self.fill_values_[col] = modes.iloc[0] if len(modes) else 'None'
        return self

    def _domain_rules(self, X):
        X = X.copy()
        # Structural missing values: original EDA recommendations.
        absence = ['PoolQC', 'MiscFeature', 'Alley', 'Fence', 'FireplaceQu',
                   'GarageType', 'GarageFinish', 'GarageQual', 'GarageCond',
                   'BsmtExposure', 'BsmtFinType1', 'BsmtFinType2', 'BsmtQual', 'BsmtCond', 'MasVnrType']
        for col in absence:
            if col in X:
                X[col] = X[col].fillna('None')
        zero_cols = ['GarageYrBlt', 'GarageArea', 'GarageCars', 'BsmtFinSF1',
                     'BsmtFinSF2', 'BsmtUnfSF', 'TotalBsmtSF', 'BsmtFullBath',
                     'BsmtHalfBath', 'MasVnrArea']
        # The EDA identifies GarageYrBlt=2207; use YearBuilt on that row.
        incorrect_year = X['GarageYrBlt'].eq(2207)
        X.loc[incorrect_year, 'GarageYrBlt'] = X.loc[incorrect_year, 'YearBuilt']
        for col in zero_cols:
            if col in X:
                X[col] = X[col].fillna(0)
        for col in ['MSSubClass', 'MoSold', 'YrSold']:
            if col in X:
                X[col] = X[col].astype('str')
        # Normalize pandas string extension columns for sklearn imputation.
        for col in X.select_dtypes(exclude=np.number):
            X[col] = X[col].astype(object).where(X[col].notna(), np.nan)
        return X

    def transform(self, X):
        X = self._domain_rules(X)
        X['LotFrontage'] = X['LotFrontage'].fillna(
            X['Neighborhood'].map(self.frontage_by_neighborhood_)).fillna(self.frontage_fallback_)
        return X.fillna(self.fill_values_)

    def get_feature_names_out(self, input_features=None):
        return self.feature_names_in_


class NearZeroVariance(TransformerMixin, BaseEstimator):
    """Drop original columns with >=99% identical values on training data."""
    def fit(self, X, y=None):
        self.feature_names_in_ = np.asarray(X.columns, dtype=object)
        self.dropped_columns_ = [c for c in X if X[c].value_counts(normalize=True, dropna=False).iloc[0] >= 0.99]
        self.kept_columns_ = [c for c in X if c not in self.dropped_columns_]
        return self

    def transform(self, X):
        return X.loc[:, self.kept_columns_].copy()

    def get_feature_names_out(self, input_features=None):
        return np.asarray(self.kept_columns_, dtype=object)


def fit_training_pipeline(pipeline, X, y):
    """Filter EDA outliers only on training rows, never on validation/test."""
    y = np.asarray(y)
    outliers = (X['GrLivArea'].to_numpy() > 4000) & (np.expm1(y) < 300000)
    pipeline.fit(X.loc[~outliers], y[~outliers])
    pipeline.training_outliers_removed_ = int(outliers.sum())
    pipeline.training_rows_used_ = int((~outliers).sum())
    return pipeline


def load_data(root=ROOT):
    train = pd.read_csv(Path(root) / 'house-prices-advanced-regression-techniques/train.csv')
    test = pd.read_csv(Path(root) / 'house-prices-advanced-regression-techniques/test.csv')
    assert train['Id'].is_unique and test['Id'].is_unique
    assert train['SalePrice'].notna().all() and (train['SalePrice'] > 0).all()
    X = train.drop(columns=['Id', 'SalePrice'])
    X_test = test.drop(columns='Id').reindex(columns=X.columns)
    # Keep every labeled observation: no target-based filtering of validation rows.
    return X, np.log1p(train['SalePrice'].to_numpy()), X_test, test['Id'].to_numpy()


def make_preprocessor():
    numeric = Pipeline([('imputer', SimpleImputer(strategy='median', keep_empty_features=True))])
    categorical = Pipeline([
        ('imputer', SimpleImputer(strategy='most_frequent', keep_empty_features=True)),
        ('encoder', OneHotEncoder(handle_unknown='ignore', sparse_output=False)),
    ])
    return Pipeline([
        ('semantics', HousingSemantics()),
        ('near_zero_variance', NearZeroVariance()),
        ('columns', ColumnTransformer([
            ('num', numeric, make_column_selector(dtype_include=np.number)),
            ('cat', categorical, make_column_selector(dtype_exclude=np.number)),
        ], sparse_threshold=0)),
    ])


def mi_score(X, y):
    # One-hot columns are discrete; scaled values still identify their categories.
    discrete = np.array([np.unique(X[:, j]).size <= 2 for j in range(X.shape[1])])
    return mutual_info_regression(X, y, discrete_features=discrete, random_state=SEED)


def get_selectors(k=30):
    return {
        'All features': 'passthrough',
        'F-regression': SelectKBest(f_regression, k=k),
        'Mutual Information': SelectKBest(mi_score, k=k),
        'RFE (Ridge)': RFE(Ridge(alpha=10), n_features_to_select=k, step=0.2),
        'Lasso': SelectFromModel(Lasso(alpha=0.002, max_iter=20000), threshold=1e-8,
                                 max_features=k),
        'RF importance': SelectFromModel(
            RandomForestRegressor(n_estimators=100, random_state=SEED, n_jobs=2),
            threshold=-np.inf, max_features=k),
    }


def get_models():
    return {
        'SVR': SVR(kernel='rbf', C=10, epsilon=0.05, gamma='scale'),
        'XGBoost': XGBRegressor(n_estimators=250, learning_rate=0.05, max_depth=3,
                              subsample=0.8, colsample_bytree=0.8,
                              objective='reg:squarederror', random_state=SEED, n_jobs=2),
        'Random Forest': RandomForestRegressor(n_estimators=150, min_samples_leaf=2,
                                               max_features=0.8, random_state=SEED, n_jobs=2),
    }


def make_pipeline(selector, model):
    return Pipeline([
        ('preprocessor', make_preprocessor()),
        ('scaler', StandardScaler()),
        ('selector', clone(selector) if selector != 'passthrough' else 'passthrough'),
        ('model', clone(model)),
    ])


def evaluate_feature_selection(X, y, k=30, n_splits=5):
    splits = list(KFold(n_splits=n_splits, shuffle=True, random_state=SEED).split(X))
    fold_rows, predictions, selected_rows = [], {}, []
    for method, selector in get_selectors(k).items():
        for name, model in get_models().items():
            print(f'{method} / {name}', flush=True)
            oof = np.empty(len(y))
            for fold, (tr, va) in enumerate(splits, 1):
                pipeline = make_pipeline(selector, model)
                started = time.perf_counter()
                fit_training_pipeline(pipeline, X.iloc[tr], y[tr])
                fit_seconds = time.perf_counter() - started
                started = time.perf_counter()
                pred = pipeline.predict(X.iloc[va])
                predict_seconds = time.perf_counter() - started
                oof[va] = pred
                names = pipeline['preprocessor'].get_feature_names_out()
                fitted_selector = pipeline['selector']
                chosen = names if isinstance(fitted_selector, str) else names[fitted_selector.get_support()]
                if not len(chosen):
                    raise ValueError(f'{method} selected no features')
                selected_rows.extend({'Method': method, 'Model': name, 'Fold': fold, 'Feature': f}
                                     for f in chosen)
                fold_rows.append({
                    'Method': method, 'Model': name, 'Fold': fold,
                    'RMSE_log': np.sqrt(mean_squared_error(y[va], pred)),
                    'MAE_log': mean_absolute_error(y[va], pred),
                    'R2_log': r2_score(y[va], pred),
                    'RMSE_USD': np.sqrt(mean_squared_error(np.expm1(y[va]), np.expm1(pred))),
                    'MAE_USD': mean_absolute_error(np.expm1(y[va]), np.expm1(pred)),
                    'N_features': len(chosen), 'N_encoded': len(names),
                    'N_train_used': pipeline.training_rows_used_,
                    'N_outliers_removed': pipeline.training_outliers_removed_,
                    'N_near_constant_removed': len(pipeline['preprocessor']['near_zero_variance'].dropped_columns_),
                    'Fit_seconds': fit_seconds, 'Predict_seconds': predict_seconds,
                })
            predictions[f'{method} | {name}'] = oof
    folds = pd.DataFrame(fold_rows)
    summary = folds.groupby(['Method', 'Model'], sort=False).agg(
        RMSE_log_mean=('RMSE_log', 'mean'), RMSE_log_std=('RMSE_log', 'std'),
        MAE_log_mean=('MAE_log', 'mean'), R2_log_mean=('R2_log', 'mean'),
        RMSE_USD_mean=('RMSE_USD', 'mean'), MAE_USD_mean=('MAE_USD', 'mean'),
        N_features_mean=('N_features', 'mean'), N_features_min=('N_features', 'min'),
        N_features_max=('N_features', 'max'), Fit_seconds_mean=('Fit_seconds', 'mean'),
        N_outliers_removed_mean=('N_outliers_removed', 'mean'),
        N_near_constant_removed_mean=('N_near_constant_removed', 'mean'),
        Predict_seconds_mean=('Predict_seconds', 'mean'),
    ).reset_index()
    baseline = summary[summary.Method == 'All features'].set_index('Model').RMSE_log_mean
    summary['RMSE_improvement_pct'] = summary.apply(
        lambda r: 100 * (baseline[r.Model] - r.RMSE_log_mean) / baseline[r.Model], axis=1)
    oof = pd.DataFrame(predictions, index=X.index)
    oof.insert(0, 'Actual_log', y)
    return summary, folds, oof, pd.DataFrame(selected_rows)


def save_results(summary, folds, oof, selected, directory=None):
    directory = Path(directory or ROOT / 'plots/feature_selection')
    directory.mkdir(parents=True, exist_ok=True)
    for name, frame in [('metrics_summary', summary), ('fold_metrics', folds),
                        ('oof_predictions', oof), ('selected_features', selected)]:
        frame.to_csv(directory / f'{name}.csv', index=False)
    models = list(get_models())
    fig, axes = plt.subplots(1, 3, figsize=(17, 5), sharey=True)
    for ax, model in zip(axes, models):
        part = summary[summary.Model == model]
        ax.bar(part.Method, part.RMSE_log_mean, yerr=part.RMSE_log_std, capsize=4)
        ax.set_title(model)
        ax.tick_params(axis='x', rotation=65)
        ax.set_ylabel('5-fold RMSE on log1p(SalePrice)')
    fig.tight_layout()
    fig.savefig(directory / 'rmse_comparison.png', dpi=150)
    plt.close(fig)
    return directory


def main():
    X, y, X_test, test_ids = load_data()
    summary, folds, oof, selected = evaluate_feature_selection(X, y)
    directory = save_results(summary, folds, oof, selected)
    submission_pipeline = make_pipeline('passthrough', get_models()['XGBoost'])
    fit_training_pipeline(submission_pipeline, X, y)
    submission = pd.DataFrame({'Id': test_ids, 'SalePrice': np.expm1(submission_pipeline.predict(X_test))})
    submission.to_csv(directory / 'submission_xgboost_baseline.csv', index=False)
    print(summary.to_string(index=False))


if __name__ == '__main__':
    main()
