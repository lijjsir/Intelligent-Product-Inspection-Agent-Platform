"""The same object checks apply at registration, ingestion and execution review."""


def sample_scope_issues(task, data, scope):
    issues = []
    if data.get('task_id') != task.id:
        issues.append('样品不属于当前检测任务')
    for key, expected, label in (
        ('product_sku_id', task.product_sku_id, '型号'),
        ('batch_id', task.batch_id, '型号批次'),
        ('quality_product_id', scope.get('quality_product_id'), '具体产品'),
        ('quality_batch_id', scope.get('quality_batch_id'), '质监批次'),
        ('production_batch_ref', scope.get('production_batch_ref'), '生产批次'),
        ('unit_serial_ref', scope.get('unit_serial_ref'), '单件标识'),
    ):
        actual = data.get(key)
        # Legacy samples identify their native batch by its verified batch_id.
        if key == 'production_batch_ref' and not scope.get('quality_product_id') and not actual:
            continue
        if expected and str(actual or '') != str(expected):
            issues.append(f'样品{label}缺失或与任务不一致')
        elif key.endswith('_id') and actual and not expected:
            issues.append(f'样品{label}未关联到当前任务')
    return issues
