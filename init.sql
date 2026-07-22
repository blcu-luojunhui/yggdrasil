-- ============================================
-- Yggdrasil 世界树认知引擎 - 数据库参考 Schema
--
-- 实际运行时 DuckDB 自动创建表，此文件仅作参考
-- 如果你使用 MySQL 替代 DuckDB，执行此文件
-- ============================================

-- 领域表
CREATE TABLE IF NOT EXISTS domains (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    parent_id INTEGER NULL,
    domain_name VARCHAR(128) NOT NULL,
    full_path VARCHAR(512) NOT NULL UNIQUE,
    depth INTEGER NOT NULL DEFAULT 1,
    season VARCHAR(16) NOT NULL DEFAULT 'spring',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_id) REFERENCES domains(id) ON DELETE CASCADE
);

-- 认知边表
CREATE TABLE IF NOT EXISTS cog_edges (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    from_node_id VARCHAR(64) NOT NULL,
    to_node_id VARCHAR(64) NOT NULL,
    relation_type VARCHAR(16) NOT NULL,
    strength DOUBLE NOT NULL DEFAULT 0.5,
    source VARCHAR(128) NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_from_to_type (from_node_id, to_node_id, relation_type)
);

-- 变更日志表
CREATE TABLE IF NOT EXISTS cog_change_log (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    node_id VARCHAR(64) NULL,
    edge_id INTEGER NULL,
    operation VARCHAR(32) NOT NULL,
    old_values JSON NULL,
    new_values JSON NULL,
    reason VARCHAR(512) NULL,
    trace_id VARCHAR(128) NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 沙盒分支表
CREATE TABLE IF NOT EXISTS sandboxes (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    base_domain_id INTEGER NOT NULL,
    sandbox_name VARCHAR(128) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    created_by VARCHAR(128) NULL,
    assessment_result BOOLEAN NULL,
    assessment_reason TEXT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME NULL,
    FOREIGN KEY (base_domain_id) REFERENCES domains(id) ON DELETE CASCADE
);