-- 清理 cqupt 之外的旧演示数据（按 FK 依赖顺序）
SET @keep = (SELECT id FROM organizations WHERE slug='cqupt');

-- 1. 最外层的子表（无下级 FK 引用）
DELETE FROM chat_message_scores WHERE org_id != @keep;
DELETE FROM chat_messages WHERE org_id != @keep;
DELETE FROM chat_sessions WHERE org_id != @keep;
DELETE FROM agent_execution_metrics WHERE org_id != @keep;
DELETE FROM agent_route_logs WHERE org_id != @keep;
DELETE FROM agent_runtime_events WHERE org_id != @keep;
DELETE FROM agent_runtime_instances WHERE org_id != @keep;
DELETE FROM alert_events WHERE org_id != @keep;
DELETE FROM alert_rules WHERE org_id != @keep;

-- 2. 稳定性报告（引用 inspection_results 和 inspection_tasks）
DELETE FROM stability_reports WHERE org_id != @keep;

-- 3. 检测结果（引用 inspection_tasks 和 organizations）
DELETE FROM inspection_result_evidence WHERE org_id != @keep;
DELETE FROM inspection_results WHERE org_id != @keep;

-- 4. 检测任务（引用 organizations 和 users）
DELETE FROM inspection_tasks WHERE org_id != @keep;

-- 5. token 用量汇总（引用 users 和 organizations）
DELETE FROM user_token_usage_summary WHERE org_id != @keep;

-- 6. 用户（引用 organizations）
DELETE FROM users WHERE org_id != @keep;

-- 7. 组织
DELETE FROM organizations WHERE id != @keep;

SELECT CONCAT('OK. tasks=', (SELECT COUNT(*) FROM inspection_tasks), ' users=', (SELECT COUNT(*) FROM users), ' orgs=', (SELECT COUNT(*) FROM organizations)) AS result;
