"""sync_orm_models_audit_logs_and_cleanup

Revision ID: 0046
Revises: 0045_merge_post_branch_heads
Create Date: 2026-05-21 18:42:36.394575

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from app.models.base import UUIDBinary

revision = "0046"
down_revision = "0045_merge_post_branch_heads"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    original_create_table = op.create_table
    original_create_index = op.create_index
    original_drop_index = op.drop_index
    original_drop_column = op.drop_column
    original_drop_table_comment = op.drop_table_comment
    original_alter_column = op.alter_column

    def _inspector():
        return sa.inspect(bind)

    def _has_table(table_name: str) -> bool:
        return table_name in _inspector().get_table_names()

    def _has_column(table_name: str, column_name: str) -> bool:
        if not _has_table(table_name):
            return False
        return any(column["name"] == column_name for column in _inspector().get_columns(table_name))

    def _has_index(table_name: str, index_name: str) -> bool:
        if not _has_table(table_name):
            return False
        return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))

    def safe_create_table(table_name: str, *columns, **kwargs):
        if _has_table(table_name):
            return None
        try:
            return original_create_table(table_name, *columns, **kwargs)
        except Exception:
            return None

    def safe_create_index(index_name: str, table_name: str, columns, **kwargs):
        if not _has_table(table_name) or _has_index(table_name, index_name):
            return None
        try:
            return original_create_index(index_name, table_name, columns, **kwargs)
        except Exception:
            return None

    def safe_drop_index(index_name: str, table_name: str | None = None, **kwargs):
        if table_name and not _has_index(table_name, index_name):
            return None
        try:
            return original_drop_index(index_name, table_name=table_name, **kwargs)
        except Exception:
            return None

    def safe_drop_column(table_name: str, column_name: str, **kwargs):
        if not _has_column(table_name, column_name):
            return None
        try:
            return original_drop_column(table_name, column_name, **kwargs)
        except Exception:
            return None

    def safe_drop_table_comment(table_name: str, **kwargs):
        if not _has_table(table_name):
            return None
        try:
            return original_drop_table_comment(table_name, **kwargs)
        except Exception:
            return None

    def safe_alter_column(table_name: str, column_name: str, *args, **kwargs):
        if not _has_column(table_name, column_name):
            return None
        try:
            return original_alter_column(table_name, column_name, *args, **kwargs)
        except Exception:
            return None

    # Create audit_logs (was deleted by cleanup before)
    if not _has_table("audit_logs"):
        safe_create_table(
            "audit_logs",
            sa.Column("id", UUIDBinary(length=16), nullable=False),
            sa.Column("org_id", UUIDBinary(length=16), nullable=False),
            sa.Column("actor_id", UUIDBinary(length=16), nullable=False),
            sa.Column("actor_role", sa.String(length=32), nullable=False),
            sa.Column("resource_type", sa.String(length=64), nullable=False),
            sa.Column("resource_id", UUIDBinary(length=16), nullable=True),
            sa.Column("action", sa.String(length=32), nullable=False),
            sa.Column("payload_hash", sa.String(length=64), nullable=True),
            sa.Column("request_id", sa.String(length=64), nullable=True),
            sa.Column("ip_address", sa.String(length=45), nullable=True),
            sa.Column("user_agent", sa.String(length=512), nullable=True),
            sa.Column("result_code", sa.SmallInteger(), nullable=True),
            sa.Column("occurred_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    safe_create_index(op.f("ix_audit_logs_actor_id"), "audit_logs", ["actor_id"], unique=False)
    safe_create_index(op.f("ix_audit_logs_org_id"), "audit_logs", ["org_id"], unique=False)

    # Drop FKs first (some may have been dropped by the earlier attempt)
    for fk_spec in [
        ("alert_events", "fk_alert_events_rule_id"),
        ("alert_events", "alert_events_ibfk_1"),
        ("inspection_results", "inspection_results_ibfk_1"),
        ("inspection_results", "inspection_results_ibfk_2"),
        ("inspection_tasks", "inspection_tasks_ibfk_1"),
        ("inspection_tasks", "inspection_tasks_ibfk_2"),
        ("stability_reports", "stability_reports_ibfk_1"),
        ("stability_reports", "stability_reports_ibfk_2"),
        ("user_token_usage_summary", "user_token_usage_summary_ibfk_1"),
        ("user_token_usage_summary", "user_token_usage_summary_ibfk_2"),
        ("users", "users_ibfk_1"),
    ]:
        try:
            op.drop_constraint(fk_spec[1], fk_spec[0], type_="foreignkey")
        except Exception:
            pass

    # Drop tables that were removed from ORM (IF EXISTS for idempotency)
    op.execute("DROP TABLE IF EXISTS agent_execution_metrics")
    op.execute("DROP TABLE IF EXISTS agent_config_versions")

    # --- alert_events ---
    safe_drop_index(op.f("idx_alert_events_org_created"), table_name="alert_events")
    safe_drop_index(op.f("ix_alert_events_rule_id"), table_name="alert_events")
    safe_create_index(op.f("ix_alert_events_org_id"), "alert_events", ["org_id"], unique=False)

    # --- alert_rules ---
    safe_drop_index(op.f("ix_alert_rules_alert_type"), table_name="alert_rules")
    safe_drop_index(op.f("ix_alert_rules_enabled"), table_name="alert_rules")

    # --- chat_message_scores ---
    safe_drop_index(op.f("idx_chat_message_scores_message"), table_name="chat_message_scores")
    safe_drop_index(op.f("idx_chat_message_scores_session"), table_name="chat_message_scores")
    safe_drop_index(op.f("idx_chat_message_scores_user"), table_name="chat_message_scores")
    safe_create_index(op.f("ix_chat_message_scores_assistant_message_id"), "chat_message_scores", ["assistant_message_id"], unique=False)
    safe_create_index(op.f("ix_chat_message_scores_org_id"), "chat_message_scores", ["org_id"], unique=False)
    safe_create_index(op.f("ix_chat_message_scores_session_id"), "chat_message_scores", ["session_id"], unique=False)
    safe_create_index(op.f("ix_chat_message_scores_trace_id"), "chat_message_scores", ["trace_id"], unique=False)
    safe_create_index(op.f("ix_chat_message_scores_user_id"), "chat_message_scores", ["user_id"], unique=False)

    # --- chat_messages ---
    safe_drop_index(op.f("idx_chat_messages_org_session"), table_name="chat_messages")
    safe_drop_index(op.f("idx_chat_messages_session_seq"), table_name="chat_messages")
    safe_create_index(op.f("ix_chat_messages_org_id"), "chat_messages", ["org_id"], unique=False)
    safe_create_index(op.f("ix_chat_messages_session_id"), "chat_messages", ["session_id"], unique=False)
    safe_drop_table_comment("chat_messages", existing_comment="Chat messages for quality assistant")

    # --- chat_sessions ---
    safe_drop_index(op.f("idx_chat_sessions_org_status"), table_name="chat_sessions")
    safe_drop_index(op.f("idx_chat_sessions_org_user"), table_name="chat_sessions")
    safe_create_index(op.f("ix_chat_sessions_org_id"), "chat_sessions", ["org_id"], unique=False)
    safe_create_index(op.f("ix_chat_sessions_user_id"), "chat_sessions", ["user_id"], unique=False)
    safe_drop_table_comment("chat_sessions", existing_comment="Chat sessions for quality assistant")

    # --- dataset_alignment_pairs ---
    safe_drop_index(op.f("idx_dataset_alignment_pairs_alignment"), table_name="dataset_alignment_pairs")
    safe_create_index(op.f("ix_dataset_alignment_pairs_alignment_id"), "dataset_alignment_pairs", ["alignment_id"], unique=False)
    safe_create_index(op.f("ix_dataset_alignment_pairs_created_by"), "dataset_alignment_pairs", ["created_by"], unique=False)
    safe_create_index(op.f("ix_dataset_alignment_pairs_dataset_id"), "dataset_alignment_pairs", ["dataset_id"], unique=False)
    safe_create_index(op.f("ix_dataset_alignment_pairs_org_id"), "dataset_alignment_pairs", ["org_id"], unique=False)

    # --- dataset_alignments ---
    safe_drop_index(op.f("idx_dataset_alignments_dataset"), table_name="dataset_alignments")
    safe_create_index(op.f("ix_dataset_alignments_created_by"), "dataset_alignments", ["created_by"], unique=False)
    safe_create_index(op.f("ix_dataset_alignments_dataset_id"), "dataset_alignments", ["dataset_id"], unique=False)
    safe_create_index(op.f("ix_dataset_alignments_org_id"), "dataset_alignments", ["org_id"], unique=False)

    # --- dataset_async_jobs ---
    safe_drop_index(op.f("idx_dataset_async_jobs_dataset"), table_name="dataset_async_jobs")
    safe_create_index(op.f("ix_dataset_async_jobs_created_by"), "dataset_async_jobs", ["created_by"], unique=False)
    safe_create_index(op.f("ix_dataset_async_jobs_dataset_id"), "dataset_async_jobs", ["dataset_id"], unique=False)
    safe_create_index(op.f("ix_dataset_async_jobs_org_id"), "dataset_async_jobs", ["org_id"], unique=False)

    # --- dataset_augmentation_batches ---
    safe_drop_index(op.f("idx_dataset_augmentation_batches_dataset"), table_name="dataset_augmentation_batches")
    safe_create_index(op.f("ix_dataset_augmentation_batches_created_by"), "dataset_augmentation_batches", ["created_by"], unique=False)
    safe_create_index(op.f("ix_dataset_augmentation_batches_dataset_id"), "dataset_augmentation_batches", ["dataset_id"], unique=False)
    safe_create_index(op.f("ix_dataset_augmentation_batches_org_id"), "dataset_augmentation_batches", ["org_id"], unique=False)

    # --- dataset_augmentation_proposals ---
    safe_drop_index(op.f("idx_dataset_augmentation_proposals_batch"), table_name="dataset_augmentation_proposals")
    safe_create_index(op.f("ix_dataset_augmentation_proposals_batch_id"), "dataset_augmentation_proposals", ["batch_id"], unique=False)
    safe_create_index(op.f("ix_dataset_augmentation_proposals_created_by"), "dataset_augmentation_proposals", ["created_by"], unique=False)
    safe_create_index(op.f("ix_dataset_augmentation_proposals_dataset_id"), "dataset_augmentation_proposals", ["dataset_id"], unique=False)
    safe_create_index(op.f("ix_dataset_augmentation_proposals_org_id"), "dataset_augmentation_proposals", ["org_id"], unique=False)

    # --- dataset_exports ---
    safe_drop_index(op.f("idx_dataset_exports_dataset"), table_name="dataset_exports")
    safe_create_index(op.f("ix_dataset_exports_created_by"), "dataset_exports", ["created_by"], unique=False)
    safe_create_index(op.f("ix_dataset_exports_dataset_id"), "dataset_exports", ["dataset_id"], unique=False)
    safe_create_index(op.f("ix_dataset_exports_org_id"), "dataset_exports", ["org_id"], unique=False)

    # --- dataset_kg_entities ---
    safe_drop_index(op.f("idx_dataset_kg_entities_graph"), table_name="dataset_kg_entities")
    safe_create_index(op.f("ix_dataset_kg_entities_created_by"), "dataset_kg_entities", ["created_by"], unique=False)
    safe_create_index(op.f("ix_dataset_kg_entities_dataset_id"), "dataset_kg_entities", ["dataset_id"], unique=False)
    safe_create_index(op.f("ix_dataset_kg_entities_knowledge_graph_id"), "dataset_kg_entities", ["knowledge_graph_id"], unique=False)
    safe_create_index(op.f("ix_dataset_kg_entities_org_id"), "dataset_kg_entities", ["org_id"], unique=False)

    # --- dataset_kg_relations ---
    safe_drop_index(op.f("idx_dataset_kg_relations_graph"), table_name="dataset_kg_relations")
    safe_create_index(op.f("ix_dataset_kg_relations_created_by"), "dataset_kg_relations", ["created_by"], unique=False)
    safe_create_index(op.f("ix_dataset_kg_relations_dataset_id"), "dataset_kg_relations", ["dataset_id"], unique=False)
    safe_create_index(op.f("ix_dataset_kg_relations_knowledge_graph_id"), "dataset_kg_relations", ["knowledge_graph_id"], unique=False)
    safe_create_index(op.f("ix_dataset_kg_relations_org_id"), "dataset_kg_relations", ["org_id"], unique=False)
    safe_create_index(op.f("ix_dataset_kg_relations_source_entity_id"), "dataset_kg_relations", ["source_entity_id"], unique=False)
    safe_create_index(op.f("ix_dataset_kg_relations_target_entity_id"), "dataset_kg_relations", ["target_entity_id"], unique=False)

    # --- dataset_knowledge_graphs ---
    safe_drop_index(op.f("idx_dataset_knowledge_graphs_dataset"), table_name="dataset_knowledge_graphs")
    safe_create_index(op.f("ix_dataset_knowledge_graphs_created_by"), "dataset_knowledge_graphs", ["created_by"], unique=False)
    safe_create_index(op.f("ix_dataset_knowledge_graphs_dataset_id"), "dataset_knowledge_graphs", ["dataset_id"], unique=False)
    safe_create_index(op.f("ix_dataset_knowledge_graphs_org_id"), "dataset_knowledge_graphs", ["org_id"], unique=False)

    # --- dataset_samples ---
    safe_drop_index(op.f("idx_dataset_samples_augmented"), table_name="dataset_samples")
    safe_drop_index(op.f("idx_dataset_samples_dataset"), table_name="dataset_samples")
    safe_drop_index(op.f("idx_dataset_samples_owner"), table_name="dataset_samples")
    safe_create_index(op.f("ix_dataset_samples_created_by"), "dataset_samples", ["created_by"], unique=False)
    safe_create_index(op.f("ix_dataset_samples_dataset_id"), "dataset_samples", ["dataset_id"], unique=False)
    safe_create_index(op.f("ix_dataset_samples_org_id"), "dataset_samples", ["org_id"], unique=False)

    # --- dataset_upload_sessions ---
    safe_drop_index(op.f("idx_dataset_upload_sessions_dataset"), table_name="dataset_upload_sessions")
    safe_drop_index(op.f("idx_dataset_upload_sessions_owner"), table_name="dataset_upload_sessions")
    safe_create_index(op.f("ix_dataset_upload_sessions_created_by"), "dataset_upload_sessions", ["created_by"], unique=False)
    safe_create_index(op.f("ix_dataset_upload_sessions_dataset_id"), "dataset_upload_sessions", ["dataset_id"], unique=False)
    safe_create_index(op.f("ix_dataset_upload_sessions_org_id"), "dataset_upload_sessions", ["org_id"], unique=False)

    # --- datasets ---
    safe_drop_index(op.f("idx_datasets_org_owner"), table_name="datasets")
    safe_create_index(op.f("ix_datasets_created_by"), "datasets", ["created_by"], unique=False)
    safe_create_index(op.f("ix_datasets_org_id"), "datasets", ["org_id"], unique=False)

    # --- defect_taxonomy ---
    safe_drop_index(op.f("idx_defect_taxonomy_org_code"), table_name="defect_taxonomy")
    safe_create_index(op.f("ix_defect_taxonomy_defect_code"), "defect_taxonomy", ["defect_code"], unique=False)
    safe_create_index(op.f("ix_defect_taxonomy_org_id"), "defect_taxonomy", ["org_id"], unique=False)
    safe_drop_table_comment("defect_taxonomy", existing_comment="Reusable quality defect taxonomy")

    # --- evaluation_dataset_items ---
    safe_drop_index(op.f("idx_evaluation_dataset_items_set"), table_name="evaluation_dataset_items")
    safe_create_index(op.f("ix_evaluation_dataset_items_created_by"), "evaluation_dataset_items", ["created_by"], unique=False)
    safe_create_index(op.f("ix_evaluation_dataset_items_evaluation_dataset_id"), "evaluation_dataset_items", ["evaluation_dataset_id"], unique=False)
    safe_create_index(op.f("ix_evaluation_dataset_items_org_id"), "evaluation_dataset_items", ["org_id"], unique=False)
    safe_create_index(op.f("ix_evaluation_dataset_items_source_dataset_id"), "evaluation_dataset_items", ["source_dataset_id"], unique=False)

    # --- evaluation_datasets ---
    safe_drop_index(op.f("idx_evaluation_datasets_source"), table_name="evaluation_datasets")
    safe_create_index(op.f("ix_evaluation_datasets_created_by"), "evaluation_datasets", ["created_by"], unique=False)
    safe_create_index(op.f("ix_evaluation_datasets_org_id"), "evaluation_datasets", ["org_id"], unique=False)
    safe_create_index(op.f("ix_evaluation_datasets_source_dataset_id"), "evaluation_datasets", ["source_dataset_id"], unique=False)

    # --- experiments ---
    safe_drop_index(op.f("idx_experiments_owner"), table_name="experiments")
    safe_create_index(op.f("ix_experiments_created_by"), "experiments", ["created_by"], unique=False)
    safe_create_index(op.f("ix_experiments_org_id"), "experiments", ["org_id"], unique=False)

    # --- fine_tune_runs ---
    safe_drop_index(op.f("idx_fine_tune_runs_model_config"), table_name="fine_tune_runs")
    safe_drop_index(op.f("idx_fine_tune_runs_training_job"), table_name="fine_tune_runs")
    safe_create_index(op.f("ix_fine_tune_runs_created_by"), "fine_tune_runs", ["created_by"], unique=False)
    safe_create_index(op.f("ix_fine_tune_runs_model_config_id"), "fine_tune_runs", ["model_config_id"], unique=False)
    safe_create_index(op.f("ix_fine_tune_runs_org_id"), "fine_tune_runs", ["org_id"], unique=False)
    safe_create_index(op.f("ix_fine_tune_runs_training_job_id"), "fine_tune_runs", ["training_job_id"], unique=False)
    safe_drop_column("fine_tune_runs", "base_model")

    # --- inspection_result_evidence ---
    safe_drop_index(op.f("idx_result_evidence_result"), table_name="inspection_result_evidence")
    safe_drop_index(op.f("idx_result_evidence_task"), table_name="inspection_result_evidence")
    safe_create_index(op.f("ix_inspection_result_evidence_evidence_type"), "inspection_result_evidence", ["evidence_type"], unique=False)
    safe_create_index(op.f("ix_inspection_result_evidence_org_id"), "inspection_result_evidence", ["org_id"], unique=False)
    safe_create_index(op.f("ix_inspection_result_evidence_result_id"), "inspection_result_evidence", ["result_id"], unique=False)
    safe_create_index(op.f("ix_inspection_result_evidence_task_id"), "inspection_result_evidence", ["task_id"], unique=False)
    safe_drop_table_comment("inspection_result_evidence", existing_comment="Evidence links and payloads for inspection results")

    # --- inspection_results ---
    safe_drop_index(op.f("idx_inspection_results_org_created"), table_name="inspection_results")
    safe_drop_index(op.f("idx_inspection_results_org_task"), table_name="inspection_results")
    safe_drop_index(op.f("task_id"), table_name="inspection_results")
    safe_create_index(op.f("ix_inspection_results_task_id"), "inspection_results", ["task_id"], unique=False)

    # --- inspection_specs ---
    safe_drop_index(op.f("idx_spec_org_code_active"), table_name="inspection_specs")

    # --- inspection_tasks ---
    safe_drop_index(op.f("idx_inspection_tasks_org_created"), table_name="inspection_tasks")
    safe_create_index(op.f("ix_inspection_tasks_created_by"), "inspection_tasks", ["created_by"], unique=False)

    # --- intent_routes ---
    safe_drop_index(op.f("idx_org_active_priority"), table_name="intent_routes")
    safe_drop_index(op.f("idx_org_intent"), table_name="intent_routes")
    safe_create_index(op.f("ix_intent_routes_org_id"), "intent_routes", ["org_id"], unique=False)
    safe_drop_table_comment("intent_routes", existing_comment="Intent routing configuration for agent dispatch")

    # --- memory tables ---
    safe_drop_index(op.f("idx_mem_dep_edges_source"), table_name="memory_dependency_edges")
    safe_drop_index(op.f("idx_mem_dep_edges_target"), table_name="memory_dependency_edges")
    safe_drop_index(op.f("idx_mem_dep_edges_type"), table_name="memory_dependency_edges")
    safe_drop_table_comment("memory_dependency_edges", existing_comment="explicit dependency edges between memories")

    safe_drop_index(op.f("idx_memory_evaluations_rollback"), table_name="memory_evaluations")
    safe_drop_table_comment("memory_evaluations", existing_comment="post-rollback evaluation records")

    safe_drop_index(op.f("idx_memory_events_memory"), table_name="memory_events")
    safe_drop_index(op.f("idx_memory_events_org"), table_name="memory_events")
    safe_drop_index(op.f("idx_memory_events_trace"), table_name="memory_events")
    safe_drop_index(op.f("idx_memory_events_type"), table_name="memory_events")
    safe_drop_table_comment("memory_events", existing_comment="shared memory event log")

    safe_drop_index(op.f("idx_memory_items_memory_id"), table_name="memory_items")
    safe_drop_index(op.f("idx_memory_items_org_status"), table_name="memory_items")
    safe_drop_index(op.f("idx_memory_items_org_type"), table_name="memory_items")
    safe_drop_index(op.f("idx_memory_items_trace"), table_name="memory_items")
    safe_drop_index(op.f("idx_memory_items_user"), table_name="memory_items")
    safe_drop_table_comment("memory_items", existing_comment="shared memory items fact table")

    safe_drop_index(op.f("idx_memory_policies_key"), table_name="memory_policies")
    safe_drop_table_comment("memory_policies", existing_comment="memory governance policies")

    safe_drop_index(op.f("idx_memory_rollbacks_rollback"), table_name="memory_rollbacks")
    safe_drop_index(op.f("idx_memory_rollbacks_root"), table_name="memory_rollbacks")
    safe_drop_table_comment("memory_rollbacks", existing_comment="memory rollback records")

    # --- model_configs ---
    safe_drop_index(op.f("idx_model_configs_org_active_priority"), table_name="model_configs")
    safe_create_index(op.f("ix_model_configs_model_key"), "model_configs", ["model_key"], unique=False)
    safe_create_index(op.f("ix_model_configs_org_id"), "model_configs", ["org_id"], unique=False)

    # --- model_deployments ---
    safe_drop_index(op.f("idx_model_deployments_source"), table_name="model_deployments")
    safe_create_index(op.f("ix_model_deployments_created_by"), "model_deployments", ["created_by"], unique=False)
    safe_create_index(op.f("ix_model_deployments_org_id"), "model_deployments", ["org_id"], unique=False)
    safe_create_index(op.f("ix_model_deployments_source_id"), "model_deployments", ["source_id"], unique=False)

    # --- offline_evaluations ---
    safe_drop_index(op.f("idx_offline_evaluations_eval_set"), table_name="offline_evaluations")
    safe_create_index(op.f("ix_offline_evaluations_created_by"), "offline_evaluations", ["created_by"], unique=False)
    safe_create_index(op.f("ix_offline_evaluations_eval_set_id"), "offline_evaluations", ["eval_set_id"], unique=False)
    safe_create_index(op.f("ix_offline_evaluations_org_id"), "offline_evaluations", ["org_id"], unique=False)
    safe_create_index(op.f("ix_offline_evaluations_target_id"), "offline_evaluations", ["target_id"], unique=False)

    # --- online_validations ---
    safe_drop_index(op.f("idx_online_validations_deployment"), table_name="online_validations")
    safe_create_index(op.f("ix_online_validations_created_by"), "online_validations", ["created_by"], unique=False)
    safe_create_index(op.f("ix_online_validations_deployment_id"), "online_validations", ["deployment_id"], unique=False)
    safe_create_index(op.f("ix_online_validations_org_id"), "online_validations", ["org_id"], unique=False)

    # --- product_zone_maps ---
    safe_drop_index(op.f("idx_product_zone_maps_spec"), table_name="product_zone_maps")
    safe_create_index(op.f("ix_product_zone_maps_spec_row_id"), "product_zone_maps", ["spec_row_id"], unique=False)
    safe_create_index(op.f("ix_product_zone_maps_zone_code"), "product_zone_maps", ["zone_code"], unique=False)
    safe_drop_table_comment("product_zone_maps", existing_comment="Product zone map per inspection spec")

    # --- prompt_definitions ---
    safe_drop_index(op.f("uk_org_prompt_key"), table_name="prompt_definitions")

    # --- prompt_versions ---
    safe_drop_index(op.f("idx_org_name_version"), table_name="prompt_versions")
    safe_drop_index(op.f("idx_org_status"), table_name="prompt_versions")
    safe_create_index(op.f("ix_prompt_versions_org_id"), "prompt_versions", ["org_id"], unique=False)
    safe_drop_table_comment("prompt_versions", existing_comment="Prompt version management for agent configuration")

    # --- rag_document_chunks ---
    safe_drop_index(op.f("idx_rag_chunks_doc"), table_name="rag_document_chunks")
    safe_drop_index(op.f("idx_rag_chunks_space"), table_name="rag_document_chunks")
    safe_create_index(op.f("ix_rag_document_chunks_document_id"), "rag_document_chunks", ["document_id"], unique=False)
    safe_create_index(op.f("ix_rag_document_chunks_node_id"), "rag_document_chunks", ["node_id"], unique=False)
    safe_create_index(op.f("ix_rag_document_chunks_org_id"), "rag_document_chunks", ["org_id"], unique=False)
    safe_create_index(op.f("ix_rag_document_chunks_rag_space_id"), "rag_document_chunks", ["rag_space_id"], unique=False)

    # --- rag_documents ---
    safe_drop_index(op.f("idx_rag_documents_node"), table_name="rag_documents")
    safe_drop_index(op.f("idx_rag_documents_org"), table_name="rag_documents")
    safe_drop_index(op.f("idx_rag_documents_space"), table_name="rag_documents")
    safe_create_index(op.f("ix_rag_documents_node_id"), "rag_documents", ["node_id"], unique=False)
    safe_create_index(op.f("ix_rag_documents_org_id"), "rag_documents", ["org_id"], unique=False)
    safe_create_index(op.f("ix_rag_documents_rag_space_id"), "rag_documents", ["rag_space_id"], unique=False)
    safe_drop_table_comment("rag_documents", existing_comment="Document metadata for tree file nodes")

    # --- rag_index_jobs ---
    safe_drop_index(op.f("idx_rag_index_jobs_doc"), table_name="rag_index_jobs")
    safe_drop_index(op.f("idx_rag_index_jobs_space"), table_name="rag_index_jobs")
    safe_create_index(op.f("ix_rag_index_jobs_document_id"), "rag_index_jobs", ["document_id"], unique=False)
    safe_create_index(op.f("ix_rag_index_jobs_org_id"), "rag_index_jobs", ["org_id"], unique=False)
    safe_create_index(op.f("ix_rag_index_jobs_rag_space_id"), "rag_index_jobs", ["rag_space_id"], unique=False)

    # --- rag_nodes ---
    safe_drop_index(op.f("idx_rag_nodes_org"), table_name="rag_nodes")
    safe_drop_index(op.f("idx_rag_nodes_org_space"), table_name="rag_nodes")
    safe_drop_index(op.f("idx_rag_nodes_space_parent"), table_name="rag_nodes")
    safe_create_index(op.f("ix_rag_nodes_org_id"), "rag_nodes", ["org_id"], unique=False)
    safe_create_index(op.f("ix_rag_nodes_parent_id"), "rag_nodes", ["parent_id"], unique=False)
    safe_create_index(op.f("ix_rag_nodes_rag_space_id"), "rag_nodes", ["rag_space_id"], unique=False)
    safe_drop_table_comment("rag_nodes", existing_comment="Tree nodes for RAG spaces")

    # --- rag_query_logs ---
    safe_drop_index(op.f("idx_rag_query_logs_org_created"), table_name="rag_query_logs")
    safe_drop_index(op.f("idx_rag_query_logs_rag_space"), table_name="rag_query_logs")
    safe_drop_index(op.f("idx_rag_query_logs_session"), table_name="rag_query_logs")
    safe_create_index(op.f("ix_rag_query_logs_org_id"), "rag_query_logs", ["org_id"], unique=False)
    safe_create_index(op.f("ix_rag_query_logs_rag_space_id"), "rag_query_logs", ["rag_space_id"], unique=False)
    safe_create_index(op.f("ix_rag_query_logs_session_id"), "rag_query_logs", ["session_id"], unique=False)
    safe_create_index(op.f("ix_rag_query_logs_task_id"), "rag_query_logs", ["task_id"], unique=False)
    safe_create_index(op.f("ix_rag_query_logs_user_id"), "rag_query_logs", ["user_id"], unique=False)
    safe_drop_table_comment("rag_query_logs", existing_comment="RAG query traces for governance analytics")

    # --- rag_spaces ---
    safe_drop_index(op.f("idx_rag_spaces_org"), table_name="rag_spaces")
    safe_drop_index(op.f("idx_rag_spaces_org_name"), table_name="rag_spaces")
    safe_create_index(op.f("ix_rag_spaces_org_id"), "rag_spaces", ["org_id"], unique=False)
    safe_drop_table_comment("rag_spaces", existing_comment="User managed RAG spaces")

    # --- result_feedbacks ---
    safe_drop_index(op.f("idx_result_feedbacks_org_created"), table_name="result_feedbacks")
    safe_create_index(op.f("ix_result_feedbacks_actor_id"), "result_feedbacks", ["actor_id"], unique=False)
    safe_create_index(op.f("ix_result_feedbacks_org_id"), "result_feedbacks", ["org_id"], unique=False)
    safe_create_index(op.f("ix_result_feedbacks_result_id"), "result_feedbacks", ["result_id"], unique=False)

    # --- spec_aggregation_rules ---
    safe_drop_index(op.f("idx_spec_aggregation_rules_spec"), table_name="spec_aggregation_rules")
    safe_create_index(op.f("ix_spec_aggregation_rules_rule_code"), "spec_aggregation_rules", ["rule_code"], unique=False)
    safe_create_index(op.f("ix_spec_aggregation_rules_spec_row_id"), "spec_aggregation_rules", ["spec_row_id"], unique=False)
    safe_drop_table_comment("spec_aggregation_rules", existing_comment="Spec-level aggregation rules")

    # --- spec_change_logs ---
    safe_drop_index(op.f("idx_spec_change_logs_spec"), table_name="spec_change_logs")
    safe_create_index(op.f("ix_spec_change_logs_spec_row_id"), "spec_change_logs", ["spec_row_id"], unique=False)
    safe_drop_table_comment("spec_change_logs", existing_comment="Spec version change logs")

    # --- stability_reports ---
    safe_drop_index(op.f("idx_stability_reports_org_created"), table_name="stability_reports")
    safe_drop_index(op.f("result_id"), table_name="stability_reports")
    safe_create_index(op.f("ix_stability_reports_org_id"), "stability_reports", ["org_id"], unique=False)
    safe_create_index(op.f("ix_stability_reports_result_id"), "stability_reports", ["result_id"], unique=False)
    safe_create_index(op.f("ix_stability_reports_task_id"), "stability_reports", ["task_id"], unique=False)

    # --- task_execution_events ---
    safe_drop_index(op.f("idx_task_execution_events_task"), table_name="task_execution_events")
    safe_create_index(op.f("ix_task_execution_events_org_id"), "task_execution_events", ["org_id"], unique=False)
    safe_create_index(op.f("ix_task_execution_events_task_id"), "task_execution_events", ["task_id"], unique=False)

    # --- token_usage_ledger ---
    safe_drop_index(op.f("idx_token_ledger_org_created"), table_name="token_usage_ledger")
    safe_drop_index(op.f("idx_token_ledger_user"), table_name="token_usage_ledger")
    safe_create_index(op.f("ix_token_usage_ledger_model_config_id"), "token_usage_ledger", ["model_config_id"], unique=False)
    safe_create_index(op.f("ix_token_usage_ledger_model_key"), "token_usage_ledger", ["model_key"], unique=False)
    safe_create_index(op.f("ix_token_usage_ledger_org_id"), "token_usage_ledger", ["org_id"], unique=False)
    safe_create_index(op.f("ix_token_usage_ledger_product_line"), "token_usage_ledger", ["product_line"], unique=False)
    safe_create_index(op.f("ix_token_usage_ledger_result_id"), "token_usage_ledger", ["result_id"], unique=False)
    safe_create_index(op.f("ix_token_usage_ledger_task_id"), "token_usage_ledger", ["task_id"], unique=False)
    safe_create_index(op.f("ix_token_usage_ledger_trace_id"), "token_usage_ledger", ["trace_id"], unique=False)
    safe_create_index(op.f("ix_token_usage_ledger_user_id"), "token_usage_ledger", ["user_id"], unique=False)

    # --- tool_executions ---
    safe_alter_column(
        "tool_executions", "call_index",
        existing_type=mysql.SMALLINT(),
        type_=sa.Integer(),
        existing_nullable=False,
        existing_server_default=sa.text("'0'"),
    )
    safe_alter_column(
        "tool_executions", "error_message",
        existing_type=mysql.TEXT(collation="utf8mb4_unicode_ci"),
        type_=sa.String(length=1024),
        existing_nullable=True,
    )
    safe_drop_index(op.f("ix_tool_executions_trace_id"), table_name="tool_executions")
    safe_create_index(op.f("ix_tool_executions_org_id"), "tool_executions", ["org_id"], unique=False)
    safe_create_index(op.f("ix_tool_executions_task_id"), "tool_executions", ["task_id"], unique=False)
    safe_create_index(op.f("ix_tool_executions_tool_id"), "tool_executions", ["tool_id"], unique=False)

    # --- tool_registry ---
    safe_alter_column(
        "tool_registry", "rate_limit_rpm",
        existing_type=mysql.SMALLINT(),
        type_=sa.Integer(),
        existing_nullable=False,
        existing_server_default=sa.text("'60'"),
    )

    # --- training_jobs ---
    safe_drop_index(op.f("idx_training_jobs_model_config"), table_name="training_jobs")
    safe_drop_index(op.f("idx_training_jobs_source"), table_name="training_jobs")
    safe_create_index(op.f("ix_training_jobs_created_by"), "training_jobs", ["created_by"], unique=False)
    safe_create_index(op.f("ix_training_jobs_model_config_id"), "training_jobs", ["model_config_id"], unique=False)
    safe_create_index(op.f("ix_training_jobs_org_id"), "training_jobs", ["org_id"], unique=False)
    safe_create_index(op.f("ix_training_jobs_source_dataset_id"), "training_jobs", ["source_dataset_id"], unique=False)

    # --- user_token_usage_summary ---
    safe_drop_index(op.f("idx_user_token_usage_org"), table_name="user_token_usage_summary")
    safe_drop_index(op.f("idx_user_token_usage_total"), table_name="user_token_usage_summary")
    safe_create_index(op.f("ix_user_token_usage_summary_org_id"), "user_token_usage_summary", ["org_id"], unique=False)
    safe_drop_table_comment("user_token_usage_summary", existing_comment="Per-user token usage summary")

    # --- users ---
    safe_drop_index(op.f("uk_org_email"), table_name="users")
    safe_drop_index(op.f("uk_org_username"), table_name="users")


def downgrade():
    pass  # Non-transactional DDL makes downgrade impractical; restore from backup if needed
