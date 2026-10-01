"""
=============================================================================
DỰ ĐOÁN GIÁ NHÀ (AMES HOUSING) VỚI 6 MÔ HÌNH MACHINE LEARNING
=============================================================================
Các mô hình: LightGBM, XGBoost, CatBoost, Random Forest, Ridge, ElasticNet
Các bước tiền xử lý:
  - Loại outlier: GrLivArea > 4000 & SalePrice < 300000
  - Điền NaN có nghĩa -> "None" / 0
  - Điền LotFrontage theo median nhóm Neighborhood
  - Điền các NaN còn lại theo mode/median
  - Log-transform biến mục tiêu SalePrice: y = log1p(SalePrice)
  - Loại bỏ cột near-zero variance (>99% giá trị đồng nhất)
  - One-Hot Encoding cho các biến phân loại, chuẩn hóa cho Ridge & ElasticNet
Đánh giá & Trực quan hóa:
  1. Bảng tổng hợp metrics 5-Fold CV (RMSE, MAE, R2, Train Time, USD error)
  2. Bar chart so sánh RMSE giữa các model (kèm error bar std)
  3. Heatmap tương quan giữa các dự đoán (OOF predictions correlation)
  4. Scatter Actual vs Predicted (lưới 2x3)
  5. Residual plot (lưới 2x3)
  6. Feature Importance so sánh 4 model cây (LightGBM, XGBoost, CatBoost, RF)
  7. Box plot phân phối RMSE qua các fold CV
  - Dự đoán trên test set & xuất file submission
=============================================================================
"""

import os
import sys
import io
import re
import time
import warnings
# pyrefly: ignore [missing-import]
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Ensure UTF-8 output encoding on Windows consoles
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from sklearn.model_selection import KFold
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.linear_model import Ridge, ElasticNet
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

from lightgbm import LGBMRegressor
from xgboost import XGBRegressor
from catboost import CatBoostRegressor

# Cấu hình môi trường và cảnh báo
warnings.filterwarnings('ignore')
plt.style.use('seaborn-v0_8-whitegrid')
plt.rcParams['font.sans-serif'] = 'DejaVu Sans'
plt.rcParams['font.size'] = 10
plt.rcParams['figure.autolayout'] = True

PLOTS_DIR = os.path.join(os.path.dirname(__file__), 'plots')
os.makedirs(PLOTS_DIR, exist_ok=True)


# =============================================================================
# 1. TẢI DỮ LIỆU & TIỀN XỬ LÝ
# =============================================================================

def load_and_clean_data(train_path, test_path):
    """
    Tải dữ liệu và thực hiện tiền xử lý theo đúng yêu cầu bài toán:
    - Loại bỏ outlier
    - Tách target & log-transform
    - Xử lý NaN có ý nghĩa
    - Impute LotFrontage theo Neighborhood median
    - Impute các NaN còn lại
    - Loại bỏ near-zero variance
    - One-hot encoding & chuẩn hóa tên cột
    """
    print("=" * 70)
    print("BƯỚC 1: TẢI VÀ TIỀN XỬ LÝ DỮ LIỆU")
    print("=" * 70)

    train = pd.read_csv(train_path)
    test = pd.read_csv(test_path)
    print(f"Kích thước ban đầu: Train = {train.shape}, Test = {test.shape}")

    # 1.1 Loại bỏ Outlier theo khuyến nghị: GrLivArea > 4000 & SalePrice < 300000
    outlier_cond = (train['GrLivArea'] > 4000) & (train['SalePrice'] < 300000)
    outlier_ids = train[outlier_cond]['Id'].tolist()
    print(f"-> Phát hiện {len(outlier_ids)} outlier khuyến nghị xoá (Ids: {outlier_ids})")
    train = train[~outlier_cond].reset_index(drop=True)
    print(f"-> Kích thước Train sau khi lọc outlier: {train.shape}")

    # 1.2 Tách biến mục tiêu và áp dụng Log-transform
    y_train = np.log1p(train['SalePrice']).values
    train_ids = train['Id'].values
    test_ids = test['Id'].values

    train_features = train.drop(columns=['Id', 'SalePrice'])
    test_features = test.drop(columns=['Id'])

    n_train = len(train_features)
    all_data = pd.concat([train_features, test_features], ignore_index=True)

    # 1.3 Điền NaN có ý nghĩa -> "None" (phân loại) / 0 (định lượng)
    none_cols = [
        'PoolQC', 'MiscFeature', 'Alley', 'Fence', 'FireplaceQu',
        'GarageType', 'GarageFinish', 'GarageQual', 'GarageCond',
        'BsmtExposure', 'BsmtFinType1', 'BsmtFinType2', 'BsmtQual', 'BsmtCond',
        'MasVnrType'
    ]
    for col in none_cols:
        if col in all_data.columns:
            all_data[col] = all_data[col].fillna('None')

    zero_cols = [
        'GarageYrBlt', 'GarageArea', 'GarageCars',
        'BsmtFinSF1', 'BsmtFinSF2', 'BsmtUnfSF', 'TotalBsmtSF',
        'BsmtFullBath', 'BsmtHalfBath', 'MasVnrArea'
    ]
    for col in zero_cols:
        if col in all_data.columns:
            all_data[col] = all_data[col].fillna(0)

    print(f"-> Đã điền 'None' cho {len(none_cols)} cột phân loại và 0 cho {len(zero_cols)} cột định lượng có ý nghĩa.")

    # 1.4 Điền LotFrontage theo median nhóm Neighborhood
    all_data['LotFrontage'] = all_data.groupby('Neighborhood')['LotFrontage'].transform(
        lambda x: x.fillna(x.median())
    )
    all_data['LotFrontage'] = all_data['LotFrontage'].fillna(all_data['LotFrontage'].median())
    print("-> Đã điền LotFrontage theo median nhóm Neighborhood thành công.")

    # 1.5 Điền các NaN còn lại theo mode (categoricals) và median (numericals)
    num_cols = all_data.select_dtypes(include=[np.number]).columns
    cat_cols = all_data.select_dtypes(include=['object', 'category', 'string']).columns

    for col in num_cols:
        if all_data[col].isnull().any():
            all_data[col] = all_data[col].fillna(all_data[col].median())

    for col in cat_cols:
        if all_data[col].isnull().any():
            all_data[col] = all_data[col].fillna(all_data[col].mode()[0])

    print(f"-> Đã điền các NaN còn lại: Số lượng NaN còn sót lại = {all_data.isnull().sum().sum()}")

    # Chuyển đổi các đặc trưng mang bản chất phân loại về kiểu chuỗi
    str_convert_cols = ['MSSubClass', 'MoSold', 'YrSold']
    for col in str_convert_cols:
        if col in all_data.columns:
            all_data[col] = all_data[col].astype(str)

    # 1.6 Bỏ cột gần như hằng số (Near-zero variance: tần suất giá trị phổ biến nhất >= 99%)
    train_subset = all_data.iloc[:n_train]
    nzv_cols = []
    for col in all_data.columns:
        top_freq = train_subset[col].value_counts(normalize=True).iloc[0]
        if top_freq >= 0.99:
            nzv_cols.append(col)

    print(f"-> Loại bỏ {len(nzv_cols)} cột near-zero variance (>99% đồng nhất): {nzv_cols}")
    all_data = all_data.drop(columns=nzv_cols)

    # 1.7 One-Hot Encoding
    all_data_encoded = pd.get_dummies(all_data, drop_first=True)
    # Chuẩn hóa tên cột (tránh ký tự đặc biệt gây lỗi cho LightGBM / XGBoost)
    all_data_encoded.columns = [re.sub(r'[\[\]<, ]', '_', c) for c in all_data_encoded.columns]

    X_train = all_data_encoded.iloc[:n_train].copy()
    X_test = all_data_encoded.iloc[n_train:].copy()

    feature_names = all_data_encoded.columns.tolist()
    print(f"-> Sau One-Hot Encoding: Số chiều đặc trưng = {len(feature_names)}")
    print(f"-> X_train shape = {X_train.shape}, X_test shape = {X_test.shape}")

    return X_train, y_train, X_test, feature_names, train_ids, test_ids


# =============================================================================
# 2. KHỞI TẠO 6 MÔ HÌNH VÀ ĐÁNH GIÁ 5-FOLD CROSS VALIDATION
# =============================================================================

def get_models():
    """Khởi tạo 6 mô hình Machine Learning với siêu tham số tối ưu."""
    models = {
        'LightGBM': LGBMRegressor(
            n_estimators=850,
            learning_rate=0.03,
            max_depth=5,
            num_leaves=31,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            verbose=-1
        ),
        'XGBoost': XGBRegressor(
            n_estimators=850,
            learning_rate=0.03,
            max_depth=4,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            n_jobs=-1
        ),
        'CatBoost': CatBoostRegressor(
            iterations=950,
            learning_rate=0.03,
            depth=5,
            random_state=42,
            verbose=0
        ),
        'Random Forest': RandomForestRegressor(
            n_estimators=300,
            max_depth=15,
            max_features='sqrt',
            random_state=42,
            n_jobs=-1
        ),
        'Ridge': Pipeline([
            ('scaler', StandardScaler()),
            ('model', Ridge(alpha=15.0, random_state=42))
        ]),
        'ElasticNet': Pipeline([
            ('scaler', StandardScaler()),
            ('model', ElasticNet(alpha=0.005, l1_ratio=0.5, random_state=42, max_iter=3000))
        ])
    }
    return models


def evaluate_models_cv(X_train, y_train, models, n_splits=5, random_state=42):
    """
    Thực hiện 5-Fold Cross Validation trên cả 6 mô hình:
    - Thu thập Out-Of-Fold (OOF) predictions
    - Đo RMSE từng fold, tính mean ± std
    - Đo MAE, R², Train time
    - Tính RMSE & MAE trên thang đô la thực tế ($)
    - Trích xuất Feature Importance từ các model cây
    """
    print("\n" + "=" * 70)
    print(f"BƯỚC 2: TIẾN HÀNH ĐÁNH GIÁ {n_splits}-FOLD CROSS VALIDATION")
    print("=" * 70)

    kf = KFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    X_mat = X_train.values

    results = []
    oof_predictions = {}
    cv_fold_rmse = {}
    fitted_models = {}
    tree_importances = {}

    for name, model in models.items():
        print(f"-> Đang huấn luyện mô hình: {name:15s} ...", end="", flush=True)
        t0 = time.time()

        oof_pred = np.zeros(len(y_train))
        fold_rmses = []
        fold_models = []

        for fold_idx, (train_idx, val_idx) in enumerate(kf.split(X_mat, y_train)):
            X_tr, y_tr = X_mat[train_idx], y_train[train_idx]
            X_va, y_va = X_mat[val_idx], y_train[val_idx]

            model.fit(X_tr, y_tr)
            val_pred = model.predict(X_va)
            oof_pred[val_idx] = val_pred

            fold_rmse = np.sqrt(mean_squared_error(y_va, val_pred))
            fold_rmses.append(fold_rmse)
            fold_models.append(model)

        train_time = time.time() - t0
        print(f" Hoàn thành ({train_time:.2f}s)")

        oof_predictions[name] = oof_pred
        cv_fold_rmse[name] = fold_rmses
        fitted_models[name] = fold_models

        # Metrics trên log(SalePrice)
        mean_rmse = np.mean(fold_rmses)
        std_rmse = np.std(fold_rmses)
        mae = mean_absolute_error(y_train, oof_pred)
        r2 = r2_score(y_train, oof_pred)

        # Metrics quy đổi về giá thực tế (Dollars)
        y_real = np.expm1(y_train)
        pred_real = np.expm1(oof_pred)
        rmse_dollars = np.sqrt(mean_squared_error(y_real, pred_real))
        mae_dollars = mean_absolute_error(y_real, pred_real)

        results.append({
            'Model': name,
            'CV RMSE Mean': mean_rmse,
            'CV RMSE Std': std_rmse,
            'CV RMSE (mean ± std)': f"{mean_rmse:.4f} ± {std_rmse:.4f}",
            'CV MAE': mae,
            'CV R²': r2,
            'Train Time (s)': round(train_time, 2),
            'RMSE ($)': round(rmse_dollars, 2),
            'MAE ($)': round(mae_dollars, 2)
        })

    # Fit trên toàn bộ dữ liệu để trích xuất Feature Importance cho 4 model cây
    print("\n-> Đang trích xuất Feature Importance cho các mô hình cây...")
    for tree_name in ['LightGBM', 'XGBoost', 'CatBoost', 'Random Forest']:
        m = models[tree_name]
        m.fit(X_mat, y_train)
        if hasattr(m, 'feature_importances_'):
            imp = m.feature_importances_
        elif hasattr(m, 'get_feature_importance'):
            imp = m.get_feature_importance()
        else:
            imp = np.zeros(X_mat.shape[1])
        # Chuẩn hoá thành tỷ lệ % (tổng = 100)
        imp_norm = (imp / np.sum(imp)) * 100
        tree_importances[tree_name] = imp_norm

    results_df = pd.DataFrame(results).sort_values(by='CV RMSE Mean', ascending=True).reset_index(drop=True)
    oof_df = pd.DataFrame(oof_predictions)
    cv_fold_rmse_df = pd.DataFrame(cv_fold_rmse)

    return results_df, oof_df, cv_fold_rmse_df, fitted_models, tree_importances


# =============================================================================
# 3. CÁC HÀM TRỰC QUAN HÓA (7 YÊU CẦU)
# =============================================================================

def display_and_save_summary_table(results_df):
    """1. Bảng tổng hợp metrics (quan trọng nhất)."""
    print("\n" + "=" * 80)
    print("1. BẢNG TỔNG HỢP METRICS TRÊN LOG(SALEPRICE) & ĐÔ LA THỰC TẾ (5-FOLD CV)")
    print("=" * 80)
    display_df = results_df[[
        'Model', 'CV RMSE (mean ± std)', 'CV MAE', 'CV R²',
        'Train Time (s)', 'RMSE ($)', 'MAE ($)'
    ]]
    print(display_df.to_string(index=False))
    csv_path = os.path.join(PLOTS_DIR, 'metrics_summary.csv')
    display_df.to_csv(csv_path, index=False)
    print(f"\n-> Đã lưu bảng metrics vào: {csv_path}")


def plot_rmse_comparison(results_df, save_path):
    """2. Bar chart so sánh RMSE giữa các model."""
    plt.figure(figsize=(10, 6), dpi=300)
    sorted_df = results_df.sort_values(by='CV RMSE Mean', ascending=True)

    colors = ['#2b5c8f' if i == 0 else '#4c78a8' for i in range(len(sorted_df))]
    bars = plt.bar(
        sorted_df['Model'],
        sorted_df['CV RMSE Mean'],
        yerr=sorted_df['CV RMSE Std'],
        capsize=6,
        color=colors,
        edgecolor='black',
        alpha=0.88,
        width=0.55
    )

    best_model = sorted_df.iloc[0]['Model']
    best_rmse = sorted_df.iloc[0]['CV RMSE Mean']

    plt.title('2. So sánh CV RMSE giữa các Mô hình (Thấp hơn là Tốt hơn)', fontsize=14, fontweight='bold', pad=15)
    plt.xlabel('Mô hình Machine Learning', fontsize=12, labelpad=10)
    plt.ylabel('Mean CV RMSE [log(SalePrice)]', fontsize=12, labelpad=10)
    plt.ylim(0, max(sorted_df['CV RMSE Mean']) * 1.22)

    # Hiển thị giá trị cụ thể trên từng cột
    for bar, (_, row) in zip(bars, sorted_df.iterrows()):
        height = bar.get_height()
        plt.text(
            bar.get_x() + bar.get_width() / 2.,
            height + row['CV RMSE Std'] + 0.003,
            f"{row['CV RMSE Mean']:.4f}\n(±{row['CV RMSE Std']:.4f})",
            ha='center', va='bottom', fontsize=9.5, fontweight='bold'
        )

    plt.annotate(
        f'Tốt nhất: {best_model}\nRMSE = {best_rmse:.4f}',
        xy=(0, best_rmse),
        xytext=(0.4, best_rmse + 0.025),
        arrowprops=dict(facecolor='#d95f02', arrowstyle='->', lw=2),
        bbox=dict(boxstyle='round,pad=0.5', facecolor='#ffe6cc', edgecolor='#d95f02', lw=1.5),
        fontweight='bold', fontsize=10
    )

    plt.grid(axis='y', linestyle='--', alpha=0.6)
    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()
    print(f"-> Đã lưu: {save_path}")


def plot_correlation_heatmap(oof_df, save_path):
    """3. Heatmap tương quan giữa các dự đoán của model."""
    plt.figure(figsize=(9, 7.5), dpi=300)
    corr = oof_df.corr()

    sns.heatmap(
        corr,
        annot=True,
        fmt=".4f",
        cmap='YlGnBu',
        vmin=corr.min().min() - 0.01,
        vmax=1.0,
        square=True,
        linewidths=1.2,
        linecolor='white',
        cbar_kws={'label': 'Hệ số tương quan Pearson'}
    )

    plt.title('3. Ma trận Tương quan giữa Dự đoán của các Mô hình (OOF Predictions)', fontsize=13, fontweight='bold', pad=15)
    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()
    print(f"-> Đã lưu: {save_path}")


def plot_actual_vs_predicted(y_true, oof_df, results_df, save_path):
    """4. Scatter Actual vs Predicted (dạng lưới 2x3)."""
    fig, axes = plt.subplots(2, 3, figsize=(16, 10), dpi=300, sharex=True, sharey=True)
    axes = axes.flatten()

    y_min, y_max = y_true.min() - 0.1, y_true.max() + 0.1
    models_list = list(oof_df.columns)

    for i, name in enumerate(models_list):
        ax = axes[i]
        pred = oof_df[name]

        model_row = results_df[results_df['Model'] == name].iloc[0]
        rmse = model_row['CV RMSE Mean']
        r2 = model_row['CV R²']

        ax.scatter(y_true, pred, alpha=0.45, color='#1f77b4', edgecolors='none', s=22)
        # Đường tham chiếu lý tưởng y = x
        ax.plot([y_min, y_max], [y_min, y_max], 'r--', lw=1.8, label='Lý tưởng (y = x)')

        ax.set_title(f"{name}\nRMSE: {rmse:.4f} | R²: {r2:.4f}", fontsize=11.5, fontweight='bold')
        ax.set_xlabel('Actual log(SalePrice)', fontsize=10)
        ax.set_ylabel('Predicted log(SalePrice)', fontsize=10)
        ax.set_xlim(y_min, y_max)
        ax.set_ylim(y_min, y_max)
        ax.legend(loc='upper left', fontsize=8.5)
        ax.grid(True, linestyle=':', alpha=0.6)

    fig.suptitle('4. Biểu đồ Actual vs Predicted log(SalePrice) cho 6 Mô hình (Lưới 2x3)', fontsize=15, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()
    print(f"-> Đã lưu: {save_path}")


def plot_residuals(y_true, oof_df, results_df, save_path):
    """5. Residual plot (dạng lưới 2x3)."""
    fig, axes = plt.subplots(2, 3, figsize=(16, 10), dpi=300, sharex=True, sharey=True)
    axes = axes.flatten()

    models_list = list(oof_df.columns)

    for i, name in enumerate(models_list):
        ax = axes[i]
        pred = oof_df[name]
        residuals = y_true - pred

        ax.scatter(pred, residuals, alpha=0.45, color='#2ca02c', edgecolors='none', s=22)
        # Đường chuẩn y = 0
        ax.axhline(0, color='red', linestyle='--', lw=1.8, label='Residual = 0')

        # Thêm biên ± 2*std
        res_std = np.std(residuals)
        ax.axhline(2 * res_std, color='gray', linestyle=':', lw=1, alpha=0.7, label='±2 Std Dev')
        ax.axhline(-2 * res_std, color='gray', linestyle=':', lw=1, alpha=0.7)

        ax.set_title(f"{name}\nMean Residual: {residuals.mean():.4f} | Std: {res_std:.4f}", fontsize=11.5, fontweight='bold')
        ax.set_xlabel('Predicted log(SalePrice)', fontsize=10)
        ax.set_ylabel('Residual (Actual - Predicted)', fontsize=10)
        ax.legend(loc='upper right', fontsize=8)
        ax.grid(True, linestyle=':', alpha=0.6)

    fig.suptitle('5. Biểu đồ Phân tích Phần dư (Residuals vs Predicted) (Lưới 2x3)', fontsize=15, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()
    print(f"-> Đã lưu: {save_path}")


def plot_feature_importances(tree_importances, feature_names, save_path, top_n=15):
    """6. Feature Importance so sánh (cho 4 model cây: LightGBM, XGBoost, CatBoost, Random Forest)."""
    fig, axes = plt.subplots(2, 2, figsize=(16, 12), dpi=300)
    axes = axes.flatten()

    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']
    tree_models = ['LightGBM', 'XGBoost', 'CatBoost', 'Random Forest']

    for i, model_name in enumerate(tree_models):
        ax = axes[i]
        importances = tree_importances[model_name]

        top_indices = np.argsort(importances)[-top_n:]
        top_features = [feature_names[idx] for idx in top_indices]
        top_scores = importances[top_indices]

        bars = ax.barh(range(top_n), top_scores, color=colors[i], alpha=0.85, edgecolor='black', height=0.65)
        ax.set_yticks(range(top_n))
        ax.set_yticklabels(top_features, fontsize=9.5)
        ax.set_xlabel('Độ quan trọng chuẩn hóa (%)', fontsize=10)
        ax.set_title(f"Top {top_n} Features - {model_name}", fontsize=12, fontweight='bold')
        ax.grid(axis='x', linestyle='--', alpha=0.6)

        # Ghi giá trị % cuối thanh bar
        for bar in bars:
            width = bar.get_width()
            ax.text(width + 0.3, bar.get_y() + bar.get_height() / 2, f"{width:.1f}%",
                    va='center', ha='left', fontsize=8.5, fontweight='bold')

        ax.set_xlim(0, max(top_scores) * 1.18)

    fig.suptitle('6. So sánh Top 15 Đặc trưng Quan trọng (Feature Importance) giữa 4 Mô hình Cây', fontsize=15, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()
    print(f"-> Đã lưu: {save_path}")


def plot_cv_rmse_boxplot(cv_fold_rmse_df, save_path):
    """7. Box plot phân phối RMSE qua các fold CV."""
    plt.figure(figsize=(10, 6), dpi=300)

    # Sắp xếp theo thứ tự median RMSE tăng dần
    sorted_cols = cv_fold_rmse_df.median().sort_values().index.tolist()
    sorted_df = cv_fold_rmse_df[sorted_cols]

    # Vẽ boxplot
    box = plt.boxplot(
        [sorted_df[col] for col in sorted_cols],
        labels=sorted_cols,
        patch_artist=True,
        widths=0.45,
        medianprops=dict(color='darkred', lw=2),
        boxprops=dict(facecolor='#8ecae6', edgecolor='#023047', lw=1.5, alpha=0.8),
        whiskerprops=dict(color='#023047', lw=1.5),
        capprops=dict(color='#023047', lw=1.5)
    )

    # Vẽ các điểm jitter biểu thị từng fold
    for i, col in enumerate(sorted_cols):
        y_vals = sorted_df[col].values
        x_jitter = np.random.normal(i + 1, 0.04, size=len(y_vals))
        plt.scatter(x_jitter, y_vals, color='#d90429', s=45, zorder=4, alpha=0.85, label='Fold RMSE' if i == 0 else "")

    plt.title('7. Phân phối RMSE qua 5 Fold Cross Validation (Tính Ổn định)', fontsize=13, fontweight='bold', pad=15)
    plt.xlabel('Mô hình Machine Learning', fontsize=11, labelpad=10)
    plt.ylabel('RMSE [log(SalePrice)]', fontsize=11, labelpad=10)
    plt.legend(loc='upper left', fontsize=9.5)
    plt.grid(axis='y', linestyle='--', alpha=0.6)
    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()
    print(f"-> Đã lưu: {save_path}")


# =============================================================================
# 4. CHẠY DỰ ĐOÁN TRÊN TEST SET & XUẤT SUBMISSION
# =============================================================================

def predict_test_set(fitted_models, X_test, test_ids, output_path):
    """
    Dự đoán trên test.csv bằng phương pháp Bagging qua 5 Folds cho mỗi model.
    Tạo cột Ensemble kết hợp trung bình có trọng số của các model tốt nhất.
    Lưu file test_predictions.csv và file sample submission.
    """
    print("\n" + "=" * 70)
    print("BƯỚC 4: DỰ ĐOÁN TRÊN TẬP TEST (TEST.CSV)")
    print("=" * 70)

    X_test_mat = X_test.values
    test_preds_log = {}
    test_preds_dollars = {}

    for name, fold_models in fitted_models.items():
        # Dự đoán trung bình qua các model của 5 folds
        fold_preds = np.zeros(len(X_test))
        for m in fold_models:
            fold_preds += m.predict(X_test_mat) / len(fold_models)
        test_preds_log[name] = fold_preds
        test_preds_dollars[f"SalePrice_{name.replace(' ', '_')}"] = np.expm1(fold_preds)

    # Tạo mô hình Ensemble kết hợp các model mạnh nhất (CatBoost 35%, ElasticNet 25%, XGBoost 20%, LightGBM 20%)
    ensemble_log = (
        0.35 * test_preds_log['CatBoost'] +
        0.25 * test_preds_log['ElasticNet'] +
        0.20 * test_preds_log['XGBoost'] +
        0.20 * test_preds_log['LightGBM']
    )
    test_preds_dollars['SalePrice_Ensemble'] = np.expm1(ensemble_log)

    pred_df = pd.DataFrame({'Id': test_ids})
    for col_name, pred_vals in test_preds_dollars.items():
        pred_df[col_name] = pred_vals.round(2)

    pred_df.to_csv(output_path, index=False)
    print(f"-> Đã lưu file dự đoán chi tiết tất cả mô hình tại: {output_path}")

    # Xuất file submission chuẩn Kaggle (dùng kết quả Ensemble tối ưu)
    sub_path = os.path.join(os.path.dirname(output_path), 'submission.csv')
    sub_df = pd.DataFrame({
        'Id': test_ids,
        'SalePrice': test_preds_dollars['SalePrice_Ensemble'].round(2)
    })
    sub_df.to_csv(sub_path, index=False)
    print(f"-> Đã lưu file submission Kaggle chuẩn: {sub_path}")

    print("\nDemo 10 dòng đầu tiên của kết quả dự đoán Test Set:")
    display_cols = ['Id', 'SalePrice_CatBoost', 'SalePrice_ElasticNet', 'SalePrice_LightGBM', 'SalePrice_Ensemble']
    print(pred_df[display_cols].head(10).to_string(index=False))


# =============================================================================
# 5. HÀM CHÍNH ĐIỀU PHỐI (MAIN)
# =============================================================================

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    train_path = os.path.join(base_dir, 'house-prices-advanced-regression-techniques', 'train.csv')
    test_path = os.path.join(base_dir, 'house-prices-advanced-regression-techniques', 'test.csv')

    # 1. Tiền xử lý dữ liệu
    X_train, y_train, X_test, feature_names, train_ids, test_ids = load_and_clean_data(train_path, test_path)

    # 2. Khởi tạo 6 mô hình & Đánh giá 5-Fold Cross Validation
    models = get_models()
    results_df, oof_df, cv_fold_rmse_df, fitted_models, tree_importances = evaluate_models_cv(
        X_train, y_train, models, n_splits=5, random_state=42
    )

    # 3. Thực hiện 7 yêu cầu trực quan hóa
    display_and_save_summary_table(results_df)

    plot_rmse_comparison(results_df, os.path.join(PLOTS_DIR, '02_rmse_comparison_bar.png'))
    plot_correlation_heatmap(oof_df, os.path.join(PLOTS_DIR, '03_oof_correlation_heatmap.png'))
    plot_actual_vs_predicted(y_train, oof_df, results_df, os.path.join(PLOTS_DIR, '04_actual_vs_predicted_grid.png'))
    plot_residuals(y_train, oof_df, results_df, os.path.join(PLOTS_DIR, '05_residuals_grid.png'))
    plot_feature_importances(tree_importances, feature_names, os.path.join(PLOTS_DIR, '06_feature_importance_comparison.png'))
    plot_cv_rmse_boxplot(cv_fold_rmse_df, os.path.join(PLOTS_DIR, '07_cv_rmse_boxplot.png'))

    # 4. Dự đoán trên tập test
    output_pred_path = os.path.join(base_dir, 'test_predictions.csv')
    predict_test_set(fitted_models, X_test, test_ids, output_pred_path)

    print("\n" + "=" * 70)
    print("HOÀN THÀNH TOÀN BỘ QUY TRÌNH!")
    print(f"Các biểu đồ được lưu tại thư mục: {PLOTS_DIR}")
    print("=" * 70)


if __name__ == '__main__':
    main()
