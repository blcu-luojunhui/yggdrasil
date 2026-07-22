-- ============================================
-- Yggdrasil 世界树认知引擎 - 参考 Schema
-- 实际运行时 DuckDB 自动建表，此文件仅作参考
-- ============================================

-- 领域表
CREATE TABLE IF NOT EXISTS domains (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    parent_id INTEGER NULL,
    domain_name VARCHAR(128) NOT NULL,
    full_path VARCHAR(512) NOT NULL UNIQUE,
    depth INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_id) REFERENCES domains(id) ON DELETE CASCADE
);

-- 认知节点表
CREATE TABLE cog_node (
    id              CHAR(36) PRIMARY KEY,
    role            VARCHAR(16) NOT NULL,
    domain_id       INTEGER NOT NULL,
    domain_path     VARCHAR(1024) NOT NULL,
    title           VARCHAR(255) NOT NULL,
    content         TEXT,
    strength        DOUBLE DEFAULT 0.5,
    health          DOUBLE DEFAULT 1.0,
    season          VARCHAR(16) DEFAULT 'spring',
    embedding_id    VARCHAR(255),
    tenant_id       VARCHAR(64) DEFAULT 'default',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed_at TIMESTAMP NULL,
    INDEX idx_domain_path (domain_path),
    INDEX idx_role (role),
    INDEX idx_strength (strength),
    INDEX idx_health (health),
    INDEX idx_season (season),
    INDEX idx_tenant (tenant_id),
    FOREIGN KEY (domain_id) REFERENCES domains(id) ON DELETE CASCADE
);

-- 认知边表
CREATE TABLE cog_edge (
    id              CHAR(36) PRIMARY KEY,
    source_id       CHAR(36) NOT NULL,
    target_id       CHAR(36) NOT NULL,
    relation        VARCHAR(16) NOT NULL,
    strength        DOUBLE DEFAULT 0.5,
    evidence_count  INT DEFAULT 1,
    last_activated  TIMESTAMP NULL,
    source_origin   VARCHAR(255),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_edge (source_id, target_id, relation),
    INDEX idx_source (source_id),
    INDEX idx_target (target_id),
    FOREIGN KEY (source_id) REFERENCES cog_node(id) ON DELETE CASCADE,
    FOREIGN KEY (target_id) REFERENCES cog_node(id) ON DELETE CASCADE
);

-- 操作日志表
CREATE TABLE tree_log (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    operation   VARCHAR(50) NOT NULL,
    entity_type VARCHAR(20) NOT NULL,
    entity_id   CHAR(36) NOT NULL,
    changes     JSON,
    operator    VARCHAR(255),
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 季节周期配置表
CREATE TABLE season_cycle (
    id                  INT PRIMARY KEY AUTO_INCREMENT,
    domain_path         VARCHAR(1024) DEFAULT '/',
    current_season      VARCHAR(16) DEFAULT 'spring',
    cycle_anchor        TIMESTAMP,
    cycle_duration_hours INT DEFAULT 168,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Phase 3-4 扩展

-- 分支表
CREATE TABLE branch (
    id              CHAR(36) PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    parent_branch_id CHAR(36),
    status          VARCHAR(16) DEFAULT 'active',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by      VARCHAR(255),
    FOREIGN KEY (parent_branch_id) REFERENCES branch(id)
);

-- 共现统计表
CREATE TABLE cooccurrence (
    node_a_id   CHAR(36) NOT NULL,
    node_b_id   CHAR(36) NOT NULL,
    count       INT DEFAULT 0,
    last_cooccur TIMESTAMP,
    PRIMARY KEY (node_a_id, node_b_id)
);