"""DuckDB 表 schema（版本化认知运行时）"""

# DDL 集合，幂等执行
CREATE_TABLES_DDL = [
    # ── Tree ──
    """
    CREATE SEQUENCE IF NOT EXISTS seq_soil_event START 1
    """,
    """
    CREATE TABLE IF NOT EXISTS tree (
        tree_id VARCHAR PRIMARY KEY,
        tenant_id VARCHAR DEFAULT 'default',
        name VARCHAR NOT NULL,
        bounded_context VARCHAR DEFAULT '',
        owner VARCHAR DEFAULT '',
        ontology_version VARCHAR DEFAULT '1',
        active_ring_id VARCHAR,
        capabilities JSON,
        access_policy VARCHAR DEFAULT 'default',
        retrieval_policy VARCHAR DEFAULT 'default',
        status VARCHAR DEFAULT 'active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(tenant_id, name)
    )
    """,
    # ── Cognitive Node (stable identity) ──
    """
    CREATE TABLE IF NOT EXISTS cognitive_node (
        node_id VARCHAR PRIMARY KEY,
        tree_id VARCHAR NOT NULL,
        domain_id INTEGER,
        domain_path VARCHAR DEFAULT '',
        role VARCHAR NOT NULL,
        created_by VARCHAR DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tree_id) REFERENCES tree(tree_id)
    )
    """,
    # ── Node Revision (immutable content) ──
    """
    CREATE TABLE IF NOT EXISTS node_revision (
        revision_id VARCHAR PRIMARY KEY,
        node_id VARCHAR NOT NULL,
        tree_id VARCHAR NOT NULL,
        parent_revision_id VARCHAR,
        role VARCHAR DEFAULT 'fact',
        title VARCHAR DEFAULT '',
        summary VARCHAR DEFAULT '',
        payload JSON,
        status VARCHAR DEFAULT 'candidate',
        utility DOUBLE DEFAULT 0.5,
        confidence DOUBLE DEFAULT 0.5,
        freshness DOUBLE DEFAULT 0.5,
        risk DOUBLE DEFAULT 0.0,
        valid_from TIMESTAMP,
        valid_until TIMESTAMP,
        evidence_refs JSON,
        change_reason VARCHAR DEFAULT '',
        author_type VARCHAR DEFAULT 'system',
        author_id VARCHAR DEFAULT '',
        content_hash VARCHAR DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (node_id) REFERENCES cognitive_node(node_id),
        FOREIGN KEY (tree_id) REFERENCES tree(tree_id)
    )
    """,
    # ── Cognitive Edge (stable identity) ──
    """
    CREATE TABLE IF NOT EXISTS cognitive_edge (
        edge_id VARCHAR PRIMARY KEY,
        tree_id VARCHAR NOT NULL,
        source_node_id VARCHAR NOT NULL,
        target_node_id VARCHAR NOT NULL,
        relation VARCHAR NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tree_id) REFERENCES tree(tree_id),
        FOREIGN KEY (source_node_id) REFERENCES cognitive_node(node_id),
        FOREIGN KEY (target_node_id) REFERENCES cognitive_node(node_id),
        UNIQUE(tree_id, source_node_id, target_node_id, relation)
    )
    """,
    # ── Edge Revision (immutable) ──
    """
    CREATE TABLE IF NOT EXISTS edge_revision (
        revision_id VARCHAR PRIMARY KEY,
        edge_id VARCHAR NOT NULL,
        tree_id VARCHAR NOT NULL,
        parent_revision_id VARCHAR,
        source_node_id VARCHAR NOT NULL,
        target_node_id VARCHAR NOT NULL,
        relation VARCHAR DEFAULT 'enables',
        weight DOUBLE DEFAULT 0.5,
        confidence DOUBLE DEFAULT 0.5,
        applicability DOUBLE DEFAULT 1.0,
        propagation_policy VARCHAR DEFAULT 'default',
        evidence_refs JSON,
        valid_from TIMESTAMP,
        valid_until TIMESTAMP,
        status VARCHAR DEFAULT 'candidate',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (edge_id) REFERENCES cognitive_edge(edge_id),
        FOREIGN KEY (tree_id) REFERENCES tree(tree_id)
    )
    """,
    # ── Ring ──
    """
    CREATE TABLE IF NOT EXISTS ring (
        ring_id VARCHAR PRIMARY KEY,
        tree_id VARCHAR NOT NULL,
        sequence INTEGER NOT NULL,
        lifecycle_status VARCHAR DEFAULT 'growing',
        health_status VARCHAR DEFAULT 'healthy',
        parent_ring_ids JSON,
        soil_checkpoint VARCHAR,
        ontology_version VARCHAR DEFAULT '1',
        policy_version VARCHAR DEFAULT '1',
        evaluation_report_ref VARCHAR,
        quality_metrics JSON,
        content_hash VARCHAR DEFAULT '',
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        sealed_at TIMESTAMP,
        UNIQUE(tree_id, sequence)
    )
    """,
    # ── Ring mappings ──
    """
    CREATE TABLE IF NOT EXISTS ring_node_revision (
        ring_id VARCHAR NOT NULL,
        node_id VARCHAR NOT NULL,
        revision_id VARCHAR NOT NULL,
        PRIMARY KEY (ring_id, node_id),
        FOREIGN KEY (ring_id) REFERENCES ring(ring_id),
        FOREIGN KEY (node_id) REFERENCES cognitive_node(node_id),
        FOREIGN KEY (revision_id) REFERENCES node_revision(revision_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ring_edge_revision (
        ring_id VARCHAR NOT NULL,
        edge_id VARCHAR NOT NULL,
        revision_id VARCHAR NOT NULL,
        PRIMARY KEY (ring_id, edge_id),
        FOREIGN KEY (ring_id) REFERENCES ring(ring_id),
        FOREIGN KEY (edge_id) REFERENCES cognitive_edge(edge_id),
        FOREIGN KEY (revision_id) REFERENCES edge_revision(revision_id)
    )
    """,
    # ── Soil ──
    """
    CREATE TABLE IF NOT EXISTS soil_event (
        event_id VARCHAR PRIMARY KEY,
        event_type VARCHAR NOT NULL,
        tenant_id VARCHAR DEFAULT 'default',
        actor_id VARCHAR DEFAULT '',
        subject_id VARCHAR DEFAULT '',
        source_type VARCHAR DEFAULT '',
        source_ref VARCHAR DEFAULT '',
        payload JSON,
        observed_at TIMESTAMP,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        valid_from TIMESTAMP,
        valid_until TIMESTAMP,
        trust_level DOUBLE DEFAULT 0.5,
        integrity_hash VARCHAR DEFAULT '',
        access_scope VARCHAR DEFAULT 'default',
        contamination_status VARCHAR DEFAULT 'clean',
        correlation_id VARCHAR,
        causation_id VARCHAR,
        idempotency_key VARCHAR DEFAULT '',
        checkpoint INTEGER DEFAULT nextval('seq_soil_event'),
        UNIQUE(tenant_id, idempotency_key)
    )
    """,
    """
    ALTER TABLE soil_event ADD COLUMN IF NOT EXISTS actor_id VARCHAR DEFAULT ''
    """,
    """
    CREATE TABLE IF NOT EXISTS evidence (
        evidence_id VARCHAR PRIMARY KEY,
        event_id VARCHAR NOT NULL,
        media_type VARCHAR DEFAULT 'application/json',
        object_ref VARCHAR DEFAULT '',
        content_hash VARCHAR DEFAULT '',
        classification VARCHAR DEFAULT 'general',
        access_scope VARCHAR DEFAULT 'default',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (event_id) REFERENCES soil_event(event_id)
    )
    """,
    # ── Agent Run ──
    """
    CREATE TABLE IF NOT EXISTS agent_run (
        run_id VARCHAR PRIMARY KEY,
        tenant_id VARCHAR DEFAULT 'default',
        intent VARCHAR DEFAULT '',
        forest_release_id VARCHAR,
        soil_checkpoint VARCHAR,
        prompt_context_hash VARCHAR,
        selected_skill_revision_id VARCHAR,
        decision_trace_ref VARCHAR,
        result_ref VARCHAR,
        status VARCHAR DEFAULT 'running',
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP
    )
    """,
    # ── Run references ──
    """
    CREATE TABLE IF NOT EXISTS run_node_reference (
        run_id VARCHAR NOT NULL,
        revision_id VARCHAR NOT NULL,
        rank INTEGER DEFAULT 0,
        score DOUBLE DEFAULT 0.0,
        usage_type VARCHAR DEFAULT 'retrieved',
        PRIMARY KEY (run_id, revision_id),
        FOREIGN KEY (run_id) REFERENCES agent_run(run_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS run_edge_reference (
        run_id VARCHAR NOT NULL,
        revision_id VARCHAR NOT NULL,
        PRIMARY KEY (run_id, revision_id),
        FOREIGN KEY (run_id) REFERENCES agent_run(run_id)
    )
    """,
    # ── Action result ──
    """
    CREATE TABLE IF NOT EXISTS action_result (
        run_id VARCHAR NOT NULL,
        skill_revision_id VARCHAR NOT NULL,
        input_payload JSON,
        input_hash VARCHAR DEFAULT '',
        output_ref VARCHAR DEFAULT '',
        status VARCHAR DEFAULT 'completed',
        started_at TIMESTAMP,
        completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (run_id, skill_revision_id),
        FOREIGN KEY (run_id) REFERENCES agent_run(run_id)
    )
    """,
    # ── Evaluation ──
    """
    CREATE TABLE IF NOT EXISTS evaluation (
        evaluation_id VARCHAR PRIMARY KEY,
        run_id VARCHAR NOT NULL,
        evaluator_type VARCHAR DEFAULT 'system',
        technical_success DOUBLE DEFAULT 0.0,
        task_success DOUBLE DEFAULT 0.0,
        result_quality DOUBLE DEFAULT 0.0,
        safety DOUBLE DEFAULT 1.0,
        user_feedback VARCHAR,
        delayed_outcome VARCHAR,
        attribution JSON,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (run_id) REFERENCES agent_run(run_id)
    )
    """,
    # ── Forest Release ──
    """
    CREATE TABLE IF NOT EXISTS forest_release (
        release_id VARCHAR PRIMARY KEY,
        sequence INTEGER DEFAULT 1,
        status VARCHAR DEFAULT 'draft',
        content_hash VARCHAR DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        activated_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS forest_release_ring (
        release_id VARCHAR NOT NULL,
        tree_id VARCHAR NOT NULL,
        ring_id VARCHAR NOT NULL,
        PRIMARY KEY (release_id, tree_id),
        FOREIGN KEY (release_id) REFERENCES forest_release(release_id)
    )
    """,
    # ── Index outbox ──
    """
    CREATE TABLE IF NOT EXISTS index_outbox (
        id VARCHAR PRIMARY KEY,
        aggregate_type VARCHAR NOT NULL,
        aggregate_id VARCHAR NOT NULL,
        operation VARCHAR NOT NULL,
        payload_hash VARCHAR DEFAULT '',
        status VARCHAR DEFAULT 'pending',
        attempts INTEGER DEFAULT 0,
        available_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        processed_at TIMESTAMP,
        last_error VARCHAR
    )
    """,
]
