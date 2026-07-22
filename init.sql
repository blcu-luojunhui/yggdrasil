-- ============================================
-- Yggdrasil 世界树认知引擎 - 数据库初始化
-- ============================================

-- 创建数据库（如果不存在）
-- CREATE DATABASE IF NOT EXISTS yggdrasil CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
-- USE yggdrasil;

-- --------------------------------------------
-- 领域表 - 领域分层骨架
-- --------------------------------------------
CREATE TABLE IF NOT EXISTS domains (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    parent_id BIGINT UNSIGNED NULL,
    domain_name VARCHAR(128) NOT NULL COMMENT '领域名称，如 database/sql',
    full_path VARCHAR(512) NOT NULL COMMENT '完整路径，如 database/sql',
    depth INT NOT NULL DEFAULT 1 COMMENT '深度，从 1 开始',
    season ENUM('spring', 'summer', 'autumn', 'winter') NOT NULL DEFAULT 'spring' COMMENT '当前季节',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_full_path (full_path),
    KEY idx_parent_id (parent_id),
    FOREIGN KEY (parent_id) REFERENCES domains(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='领域分层';

-- --------------------------------------------
-- 认知原子节点表
-- --------------------------------------------
CREATE TABLE IF NOT EXISTS cog_nodes (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    domain_id BIGINT UNSIGNED NOT NULL,
    role ENUM('capacity', 'schema', 'heuristic', 'case', 'fact', 'state') NOT NULL COMMENT '节点角色',
    node_name VARCHAR(256) NOT NULL COMMENT '节点名称',
    description TEXT NULL COMMENT '节点描述',
    content LONGTEXT NULL COMMENT '节点内容，JSON 或 Markdown',
    embedding BLOB NULL COMMENT '向量嵌入，float32 二进制存储，可选择使用专用向量库',
    strength DOUBLE NOT NULL DEFAULT 0.5 COMMENT '强度 [0,1]，越高表示越有用',
    health DOUBLE NOT NULL DEFAULT 1.0 COMMENT '健康度 [0,1]，越低表示越可能有害',
    is_isolated BOOLEAN NOT NULL DEFAULT FALSE COMMENT '是否被隔离',
    last_used_at DATETIME NULL COMMENT '最后使用时间',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_domain_id (domain_id),
    KEY idx_role (role),
    KEY idx_strength (strength),
    KEY idx_health (health),
    KEY idx_is_isolated (is_isolated),
    KEY idx_last_used_at (last_used_at),
    FOREIGN KEY (domain_id) REFERENCES domains(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='认知原子节点';

-- --------------------------------------------
-- 认知边表 - 有向有权关联网络
-- --------------------------------------------
CREATE TABLE IF NOT EXISTS cog_edges (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    from_node_id BIGINT UNSIGNED NOT NULL,
    to_node_id BIGINT UNSIGNED NOT NULL,
    relation_type ENUM(
        'enables', 'triggers', 'evidences',
        'contradicts', 'strengthens', 'weakens'
    ) NOT NULL COMMENT '关系类型',
    strength DOUBLE NOT NULL DEFAULT 0.5 COMMENT '边强度 [0,1]',
    source VARCHAR(128) NULL COMMENT '强度来源：execution/reflection/inspection',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_from_to_type (from_node_id, to_node_id, relation_type),
    KEY idx_from_node_id (from_node_id),
    KEY idx_to_node_id (to_node_id),
    KEY idx_relation_type (relation_type),
    KEY idx_strength (strength),
    FOREIGN KEY (from_node_id) REFERENCES cog_nodes(id) ON DELETE CASCADE,
    FOREIGN KEY (to_node_id) REFERENCES cog_nodes(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='认知有向边';

-- --------------------------------------------
-- 认知快照表 - 用于回滚自愈
-- --------------------------------------------
CREATE TABLE IF NOT EXISTS cog_snapshots (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    domain_id BIGINT UNSIGNED NOT NULL,
    snapshot_version INT NOT NULL COMMENT '快照版本，递增',
    snapshot_hash VARCHAR(64) NOT NULL COMMENT '快照哈希，用于校验',
    node_count INT NOT NULL COMMENT '节点数量',
    edge_count INT NOT NULL COMMENT '边数量',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_domain_id (domain_id),
    KEY idx_created_at (created_at),
    FOREIGN KEY (domain_id) REFERENCES domains(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='认知快照，用于回滚';

-- --------------------------------------------
-- 变更日志表 - 所有修改可追溯
-- --------------------------------------------
CREATE TABLE IF NOT EXISTS cog_change_log (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    node_id BIGINT UNSIGNED NULL,
    edge_id BIGINT UNSIGNED NULL,
    operation ENUM('create', 'update_strength', 'update_health', 'isolate', 'merge', 'delete') NOT NULL,
    old_values JSON NULL COMMENT '修改前的值',
    new_values JSON NULL COMMENT '修改后的值',
    reason VARCHAR(512) NULL COMMENT '变更原因',
    trace_id VARCHAR(128) NULL COMMENT '触发变更的 trace id',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_node_id (node_id),
    KEY idx_edge_id (edge_id),
    KEY idx_operation (operation),
    KEY idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='认知变更日志，可审计';

-- --------------------------------------------
-- 沙盒分支表 - 隔离的探索分支
-- --------------------------------------------
CREATE TABLE IF NOT EXISTS sandboxes (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    base_domain_id BIGINT UNSIGNED NOT NULL,
    sandbox_name VARCHAR(128) NOT NULL,
    status ENUM('active', 'merged', 'discarded') NOT NULL DEFAULT 'active',
    created_by VARCHAR(128) NULL COMMENT '创建来源 trace_id 或 user',
    assessment_result BOOLEAN NULL COMMENT '评估结果：true=合并，false=丢弃',
    assessment_reason TEXT NULL COMMENT '评估理由',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME NULL,
    KEY idx_base_domain_id (base_domain_id),
    KEY idx_status (status),
    FOREIGN KEY (base_domain_id) REFERENCES domains(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='沙盒分支，安全探索';

-- --------------------------------------------
-- 沙盒节点变更表 - 记录沙盒中的修改
-- --------------------------------------------
CREATE TABLE IF NOT EXISTS sandbox_node_changes (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    sandbox_id BIGINT UNSIGNED NOT NULL,
    node_id BIGINT UNSIGNED NULL,
    change_type ENUM('create', 'update', 'delete') NOT NULL,
    original_node JSON NULL COMMENT '原始节点数据（仅更新/删除）',
    changed_node JSON NOT NULL COMMENT '变更后节点数据',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_sandbox_id (sandbox_id),
    KEY idx_node_id (node_id),
    FOREIGN KEY (sandbox_id) REFERENCES sandboxes(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='沙盒节点变更';

-- --------------------------------------------
-- 沙盒边变更表
-- --------------------------------------------
CREATE TABLE IF NOT EXISTS sandbox_edge_changes (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    sandbox_id BIGINT UNSIGNED NOT NULL,
    edge_id BIGINT UNSIGNED NULL,
    change_type ENUM('create', 'update', 'delete') NOT NULL,
    original_edge JSON NULL COMMENT '原始边数据',
    changed_edge JSON NOT NULL COMMENT '变更后边数据',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_sandbox_id (sandbox_id),
    KEY idx_edge_id (edge_id),
    FOREIGN KEY (sandbox_id) REFERENCES sandboxes(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='沙盒边变更';
