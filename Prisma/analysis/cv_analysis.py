import psycopg2
from pgvector.psycopg2 import register_vector
import numpy as np
import xgboost as xgb
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.metrics import classification_report, mean_absolute_error
from env import DATABASE_URL

DB_URL = DATABASE_URL

def main():
    conn = psycopg2.connect(DB_URL)
    register_vector(conn)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            a.embedding,
            a.llm_coalition,
            a.llm_eu_axis,
            CASE WHEN a.llm_topic IN ('politics', 'economy', 'justice', 'foreign_affairs')
                 THEN 1 ELSE 0 END AS is_political
        FROM articles a
        WHERE a.llm_scored_at IS NOT NULL
        ORDER BY a.id
    """)
    
    embeddings, coalition_scores, eu_axis_scores, political_labels = [], [], [], []
    for row in cursor.fetchall():
        embeddings.append(row[0])
        coalition_scores.append(row[1])
        eu_axis_scores.append(row[2])
        political_labels.append(row[3])
    
    X = np.vstack(embeddings).astype(np.float32)
    y_political = np.array(political_labels)
    y_coalition = np.array(coalition_scores)
    y_eu_axis = np.array(eu_axis_scores)
    
    gatekeeper = xgb.XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.1, subsample=0.8, colsample_bytree=0.8, random_state=42, n_jobs=-1)
    coalition_model = xgb.XGBRegressor(n_estimators=200, max_depth=6, learning_rate=0.1, subsample=0.8, colsample_bytree=0.8, random_state=42, n_jobs=-1)
    eu_model = xgb.XGBRegressor(n_estimators=200, max_depth=6, learning_rate=0.1, subsample=0.8, colsample_bytree=0.8, random_state=42, n_jobs=-1)

    print("=== Stage 1: Gatekeeper Cross-Validation ===")
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    y_pred_cv = cross_val_predict(gatekeeper, X, y_political, cv=skf, method='predict')
    
    print(classification_report(y_political, y_pred_cv, target_names=['apolitical', 'political']))

    print("\n=== Stage 2: Regressor Cross-Validation (Political articles only) ===")
    political_mask = y_political == 1
    X_pol = X[political_mask]
    
    coal_pred_cv = cross_val_predict(coalition_model, X_pol, y_coalition[political_mask], cv=5)
    eu_pred_cv = cross_val_predict(eu_model, X_pol, y_eu_axis[political_mask], cv=5)

    print(f"Coalition MAE (CV): {mean_absolute_error(y_coalition[political_mask], coal_pred_cv):.4f}")
    print(f"EU axis MAE (CV):   {mean_absolute_error(y_eu_axis[political_mask], eu_pred_cv):.4f}")

    conn.close()

if __name__ == '__main__':
    main()