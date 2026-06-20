import psycopg2
from pgvector.psycopg2 import register_vector
import numpy as np
import xgboost as xgb
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    mean_absolute_error, mean_squared_error, r2_score
)
import pickle
import logging
from pathlib import Path
from env import DATABASE_URL

DB_URL = DATABASE_URL

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).parent / "models"
MODELS_DIR.mkdir(exist_ok=True)

POLITICAL_TOPICS = {'politics', 'economy', 'justice', 'foreign_affairs'}


def load_training_data(conn):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            a.id,
            a.embedding,
            a.llm_coalition,
            a.llm_eu_axis,
            a.llm_topic,
            CASE WHEN a.llm_topic IN ('politics', 'economy', 'justice', 'foreign_affairs')
                 THEN 1 ELSE 0 END AS is_political
        FROM articles a
        WHERE a.llm_scored_at IS NOT NULL
        ORDER BY a.id
    """)
    
    rows = cursor.fetchall()
    article_ids = []
    embeddings = []
    coalition_scores = []
    eu_axis_scores = []
    political_labels = []
    
    for article_id, embedding, coalition, eu_axis, topic, is_political in rows:
        article_ids.append(article_id)
        embeddings.append(embedding)
        coalition_scores.append(coalition)
        eu_axis_scores.append(eu_axis)
        political_labels.append(is_political)
    
    cursor.close()
    
    X = np.array([np.array(emb) for emb in embeddings])
    y_political = np.array(political_labels)
    y_coalition = np.array(coalition_scores)
    y_eu_axis = np.array(eu_axis_scores)
    
    logger.info(f"Loaded {len(X)} training articles")
    logger.info(f"  Political: {np.sum(y_political)} | Apolitical: {len(y_political) - np.sum(y_political)}")
    
    return X, y_political, y_coalition, y_eu_axis, article_ids


def train_gatekeeper(X, y_political):
    logger.info("\n=== Stage 1: Training Gatekeeper Classifier ===")
    
    gatekeeper = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        verbosity=0,
        n_jobs=-1,
    )
    
    gatekeeper.fit(X, y_political)
    
    y_pred = gatekeeper.predict(X)
    y_proba = gatekeeper.predict_proba(X)[:, 1]
    
    acc = accuracy_score(y_political, y_pred)
    prec = precision_score(y_political, y_pred, zero_division=0)
    rec = recall_score(y_political, y_pred, zero_division=0)
    f1 = f1_score(y_political, y_pred, zero_division=0)
    
    logger.info(f"  Accuracy:  {acc:.4f}")
    logger.info(f"  Precision: {prec:.4f}")
    logger.info(f"  Recall:    {rec:.4f}")
    logger.info(f"  F1 Score:  {f1:.4f}")
    
    feature_importance = gatekeeper.feature_importances_
    top_indices = np.argsort(feature_importance)[-10:][::-1]
    logger.info(f"  Top 10 important embedding dims: {top_indices}")
    
    return gatekeeper, y_proba


def train_bias_regressors(X, y_political, y_coalition, y_eu_axis):
    logger.info("\n=== Stage 2: Training Bias Score Regressors ===")
    
    political_mask = y_political == 1
    X_political = X[political_mask]
    y_coalition_political = y_coalition[political_mask]
    y_eu_axis_political = y_eu_axis[political_mask]
    
    logger.info(f"  Training on {len(X_political)} political articles")
    
    logger.info("  Training coalition axis regressor...")
    coalition_model = xgb.XGBRegressor(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        verbosity=0,
        n_jobs=-1,
    )
    coalition_model.fit(X_political, y_coalition_political)
    
    y_coal_pred = coalition_model.predict(X_political)
    coal_mae = mean_absolute_error(y_coalition_political, y_coal_pred)
    coal_rmse = np.sqrt(mean_squared_error(y_coalition_political, y_coal_pred))
    coal_r2 = r2_score(y_coalition_political, y_coal_pred)
    
    logger.info(f"    Coalition MAE:  {coal_mae:.4f}")
    logger.info(f"    Coalition RMSE: {coal_rmse:.4f}")
    logger.info(f"    Coalition R²:   {coal_r2:.4f}")
    
    logger.info("  Training EU axis regressor...")
    eu_model = xgb.XGBRegressor(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        verbosity=0,
        n_jobs=-1,
    )
    eu_model.fit(X_political, y_eu_axis_political)
    
    y_eu_pred = eu_model.predict(X_political)
    eu_mae = mean_absolute_error(y_eu_axis_political, y_eu_pred)
    eu_rmse = np.sqrt(mean_squared_error(y_eu_axis_political, y_eu_pred))
    eu_r2 = r2_score(y_eu_axis_political, y_eu_pred)
    
    logger.info(f"    EU axis MAE:  {eu_mae:.4f}")
    logger.info(f"    EU axis RMSE: {eu_rmse:.4f}")
    logger.info(f"    EU axis R²:   {eu_r2:.4f}")
    
    return coalition_model, eu_model


def save_models(gatekeeper, coalition_model, eu_model):
    """Save trained models to disk for inference."""
    with open(MODELS_DIR / "gatekeeper.pkl", "wb") as f:
        pickle.dump(gatekeeper, f)
    logger.info(f"Saved gatekeeper to {MODELS_DIR / 'gatekeeper.pkl'}")
    
    with open(MODELS_DIR / "coalition_regressor.pkl", "wb") as f:
        pickle.dump(coalition_model, f)
    logger.info(f"Saved coalition regressor to {MODELS_DIR / 'coalition_regressor.pkl'}")
    
    with open(MODELS_DIR / "eu_regressor.pkl", "wb") as f:
        pickle.dump(eu_model, f)
    logger.info(f"Saved EU regressor to {MODELS_DIR / 'eu_regressor.pkl'}")


def score_full_corpus(conn, gatekeeper, coalition_model, eu_model):
    logger.info("\n=== Inference: Scoring Full Corpus ===")
    
    cursor = conn.cursor()
    update_cursor = conn.cursor()   
    
    cursor.execute("""
        SELECT COUNT(*) FROM articles 
        WHERE embedding IS NOT NULL 
          AND pred_scored_at IS NULL
    """)
    total_unscored = cursor.fetchone()[0]
    logger.info(f"Found {total_unscored} unscored articles with embeddings")
    
    BATCH_SIZE = 1000
    processed = 0
    
    cursor.execute("""
        SELECT id, embedding FROM articles
        WHERE embedding IS NOT NULL 
          AND pred_scored_at IS NULL
        ORDER BY id
    """)
    
    batch_ids = []
    batch_embeddings = []
    
    for row in cursor:
        article_id, embedding = row
        batch_ids.append(article_id)
        batch_embeddings.append(embedding)
        
        if len(batch_ids) == BATCH_SIZE:
            # Process batch
            X_batch = np.array([np.array(emb) for emb in batch_embeddings])

            gatekeeper_pred = gatekeeper.predict(X_batch)

            coalition_scores = np.full(len(X_batch), np.nan)
            eu_scores = np.full(len(X_batch), np.nan)
            
            political_mask = gatekeeper_pred == 1
            if np.any(political_mask):
                coalition_scores[political_mask] = coalition_model.predict(X_batch[political_mask])
                eu_scores[political_mask] = eu_model.predict(X_batch[political_mask])
            
            coalition_scores = np.clip(coalition_scores, -2.0, 2.0)
            eu_scores = np.clip(eu_scores, -2.0, 2.0)

            for i, article_id in enumerate(batch_ids):
                is_political = int(gatekeeper_pred[i].item())
                
                if is_political == 1:
                    coalition_val = float(coalition_scores[i].item())
                    eu_val = float(eu_scores[i].item())
                else:
                    coalition_val = None
                    eu_val = None
                
                update_cursor.execute("""
                    UPDATE articles
                    SET pred_is_political   = %s,
                        pred_coalition      = %s,
                        pred_eu_axis        = %s,
                        pred_scored_at      = NOW()
                    WHERE id = %s
                """, (is_political, coalition_val, eu_val, article_id))
            
            conn.commit()
            
            processed += len(batch_ids)
            if processed % 5000 == 0:
                logger.info(f"  Processed {processed}/{total_unscored} articles")
            
            batch_ids = []
            batch_embeddings = []
    
    # Final batch
    if batch_ids:
        X_batch = np.array([np.array(emb) for emb in batch_embeddings])
        gatekeeper_pred = gatekeeper.predict(X_batch)
        
        coalition_scores = np.full(len(X_batch), np.nan)
        eu_scores = np.full(len(X_batch), np.nan)
        
        political_mask = gatekeeper_pred == 1
        if np.any(political_mask):
            coalition_scores[political_mask] = coalition_model.predict(X_batch[political_mask])
            eu_scores[political_mask] = eu_model.predict(X_batch[political_mask])
        
        coalition_scores = np.clip(coalition_scores, -2.0, 2.0)
        eu_scores = np.clip(eu_scores, -2.0, 2.0)
        
        for i, article_id in enumerate(batch_ids):
            is_political = int(gatekeeper_pred[i].item())
            
            if is_political == 1:
                coalition_val = float(coalition_scores[i].item())
                eu_val = float(eu_scores[i].item())
            else:
                coalition_val = None
                eu_val = None
            
            update_cursor.execute("""
                UPDATE articles
                SET pred_is_political   = %s,
                    pred_coalition      = %s,
                    pred_eu_axis        = %s,
                    pred_scored_at      = NOW()
                WHERE id = %s
            """, (is_political, coalition_val, eu_val, article_id))
        
        conn.commit()
        processed += len(batch_ids)
    
    logger.info(f"  Completed. Processed {processed} articles total")
    cursor.close()


def outlet_sanity_check(conn):
    """
    Post-scoring: aggregate predicted scores by outlet and compare against LLM scores.
    """
    logger.info("\n=== Outlet-Level Sanity Check ===")
    
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            o.name, 
            o.outlet_type,
            COUNT(a.id)                                              AS n,
            COUNT(CASE WHEN a.pred_is_political = 1 THEN 1 END)      AS n_political,
            ROUND(COUNT(CASE WHEN a.pred_is_political = 1 THEN 1 END)::numeric 
                  / COUNT(a.id) * 100, 1)                            AS pct_political,
            ROUND(AVG(a.pred_coalition)::numeric, 2)                 AS pred_coal_avg,
            ROUND(AVG(a.pred_eu_axis)::numeric, 2)                   AS pred_eu_avg,
            ROUND(AVG(a.llm_coalition)::numeric, 2)                  AS llm_coal_avg,
            ROUND(AVG(a.llm_eu_axis)::numeric, 2)                    AS llm_eu_avg
        FROM articles a
        JOIN outlets o ON a.outlet_id = o.id
        WHERE a.pred_scored_at IS NOT NULL
        GROUP BY o.name, o.outlet_type
        ORDER BY pred_coal_avg ASC
    """)
    
    print(f"\n{'Outlet':<25} {'Type':<18} {'N':>6}  {'Pol%':>6}  "
          f"{'Pred Coal':>9}  {'LLM Coal':>9}  {'Pred EU':>8}  {'LLM EU':>8}")
    print("-" * 105)
    
    for row in cursor.fetchall():
        outlet, outlet_type, n, n_pol, pct_pol, pred_coal, pred_eu, llm_coal, llm_eu = row
        
        llm_c_str = f"{llm_coal:>+9.2f}" if llm_coal is not None else "     NULL"
        llm_e_str = f"{llm_eu:>+8.2f}" if llm_eu is not None else "    NULL"
        
        print(f"{outlet:<25} {outlet_type:<18} {n:>6}  {pct_pol:>5.1f}%  "
              f"{pred_coal:>+9.2f}  {llm_c_str}  {pred_eu:>+8.2f}  {llm_e_str}")
    
    cursor.close()


def main():
    conn = psycopg2.connect(DB_URL)
    register_vector(conn)
    
    logger.info("Loading LLM-scored training data...")
    X, y_political, y_coalition, y_eu_axis, article_ids = load_training_data(conn)
    
    logger.info("Training gatekeeper classifier...")
    gatekeeper, gatekeeper_proba = train_gatekeeper(X, y_political)
    
    logger.info("Training bias regressors...")
    coalition_model, eu_model = train_bias_regressors(X, y_political, y_coalition, y_eu_axis)
    
    logger.info("Saving models...")
    save_models(gatekeeper, coalition_model, eu_model)
    
    logger.info("Scoring full corpus...")
    score_full_corpus(conn, gatekeeper, coalition_model, eu_model)
    
    logger.info("Running outlet sanity check...")
    outlet_sanity_check(conn)
    
    conn.close()
    logger.info("\nPipeline complete.")


if __name__ == '__main__':
    main()
