-- ==============================================================================
-- 裁判書搜尋系統 (Judgment-Search) 效能極速優化索引腳本 (可直接在 pgAdmin 按 F5 執行)
-- ==============================================================================

-- 1. 啟用 pg_trgm 模組
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 2. 案由與主文 GIN 索引 (文字長度適中，建立僅需約 10~15 秒)
CREATE INDEX IF NOT EXISTS idx_judgments_title_trgm 
ON judgments USING gin (title gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_judgments_maintext_trgm 
ON judgments USING gin (main_text gin_trgm_ops);

-- 3. 裁判日期 B-Tree 索引 (加速預設 ORDER BY date DESC 與期間篩選，約 2 秒)
CREATE INDEX IF NOT EXISTS idx_judgments_date_desc 
ON judgments (date DESC);

-- 4. 法院代碼函式索引 (加速法院分群與代碼比對，約 2 秒)
CREATE INDEX IF NOT EXISTS idx_judgments_court_prefix 
ON judgments ((SUBSTRING(id, 1, 3)));

-- 5. 裁判案號數字函式索引 (加速案號起訖範圍查詢與案號排序，約 2 秒)
CREATE INDEX IF NOT EXISTS idx_judgments_case_no_num 
ON judgments ((NULLIF(SUBSTRING(case_no FROM '^[0-9]+'), '')::bigint));

-- 6. 案件類別與裁判書類別索引 (民事/刑事/行政、判決/裁定篩選，約 1 秒)
CREATE INDEX IF NOT EXISTS idx_judgments_cat_doctype 
ON judgments (case_category_name, doc_type);

-- 7. 歷審爬蟲快取索引 (確保快取命中 < 1 毫秒)
CREATE INDEX IF NOT EXISTS idx_crawler_cache_jid 
ON crawler_cache (judgment_id);

-- 8. 重新分析資料表 (讓 PostgreSQL 查詢規劃器立即採用全新索引)
ANALYZE judgments;
ANALYZE crawler_cache;

-- 9. (選用) 全文 content 索引：因 120 萬筆長文巨大，建議於空閒時單獨執行
-- SET maintenance_work_mem = '2GB';
-- CREATE INDEX IF NOT EXISTS idx_judgments_content_trgm ON judgments USING gin (content gin_trgm_ops);
