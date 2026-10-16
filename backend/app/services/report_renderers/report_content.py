from typing import Any


def verdict_label(verdict: Any) -> str:
    return {
        "pass": "选定项目通过（整体未评定）", "fail": "选定项目不通过（整体未评定）", "uncertain": "暂未判定", "manual_required": "需人工复核",
    }.get(str(verdict or "").lower(), str(verdict or "暂未判定"))


def score_label(result: dict) -> str:
    if result.get("score_status") != "calibrated":
        return "未校准，仅供辅助分析"
    score = result.get("overall_score")
    return f"{float(score) * 100:.1f} 分" if score is not None else "未提供"


def citation_text(item: dict) -> str:
    source = str(item.get("source") or item.get("title") or item.get("source_id") or item.get("id") or "引用资料")
    quote = str(item.get("quote") or item.get("excerpt") or "未提供引用原文")
    return f"{source}：{quote}"


STAGES={'reviewed_selected_items':'已独立复核的选定项目记录','execution_draft':'待专业复核记录',
    'needs_reassessment':'来源需重新核验的历史记录','auxiliary_record':'图片 / 旧结果辅助记录'}
TYPES={'inspection_requirement':'产品检测要求','method_condition':'试验方法 / 条件','body_clause':'参考正文','unclassified':'用途待核对'}
CHECKS={'pass':'本项目符合','fail':'本项目不符合','incomplete':'不完整','uncertain':'不确定','manual_required':'需人工核对','missing':'缺少观测'}
STATUSES={'accepted':'已独立确认','draft':'待复核','rejected':'已驳回','awaiting_evidence':'等待补证','needs_reassessment':'需重新核验',
    'accept':'确认选定项目','reject':'驳回','request_evidence':'要求补证'}


def report_sections(data):
    """PDF and Word use the same sections and wording."""
    bundle=data.get('bundle')
    if not bundle:
        old=data.get('result') or {}
        bundle={'task':data.get('task') or {},'scope':{'stage':'auxiliary_record','label':verdict_label(old.get('verdict')),
            'boundary':'仅记录辅助分析及选定项目，产品整体未评定。'},'auxiliary':old,'risks':[],'source_refs':[]}
    scope=bundle['scope'];execution=bundle.get('execution');aux=bundle.get('auxiliary');task=bundle['task']
    sections=[{'title':'记录性质与适用边界','paragraphs':[STAGES.get(scope['stage'],'辅助记录'),scope['label'],scope['boundary'],
        '报告保存生成时的结果快照；后续撤回或来源变化请在平台核对当前有效性。'],
        'rows':[['任务编号',task.get('id','')],['对象',task.get('product_name') or task.get('product_id','')],
            ['产品整体','未评定'],['快照时间（UTC）',bundle.get('frozen_at_utc','未提供')],['结果版本摘要',bundle.get('result_token','未提供')]]}]
    if execution:
        snap=execution['snapshot'];evaluation=execution['evaluation'];context=(snap.get('task_context') or {}).get('scope') or {}
        sample_names={s['id']:s['label'] for s in (snap.get('task_context') or {}).get('selected_samples',[])}
        sections.append({'title':'本次执行范围','rows':[['执行编号 / 版本',f"{execution['id']} / {execution['row_version']}"],
            ['历史复核状态',STATUSES.get(execution['status'],execution['status'])],['当前有效状态',STATUSES.get(execution['effective_status'],execution['effective_status'])],['产品类别',snap.get('product_category','')],
            ['实际生产日期',snap.get('production_date','')],['生产批次',context.get('production_batch_ref') or '未登记'],
            ['单件标识',context.get('unit_serial_ref') or '未登记'],['本次样品','、'.join(sample_names.get(s,s) for s in snap['sample_ids'])],
            ['执行策略',f"{snap['policy'].get('name','默认复核策略')} / {snap['policy'].get('version','默认')} / {snap['policy'].get('publication_id','未绑定发布版')}"]]})
        for kind,title in [('inspection_requirement','选定产品检测项目'),('method_condition','试验方法与条件核对')]:
            checks=[c for c in evaluation['checks'] if c.get('candidate_type')==kind]
            if not checks:continue
            sections.append({'title':title,'columns':['样品','标准 / 条款','项目','结果 / 单位','方法','项目判定'],
                'widths':[22,30,30,30,24,24],
                'rows':[[sample_names.get(c['sample_id'],c['sample_id']),f"{c.get('standard_no','')} / {c.get('clause_no','')}",c['indicator'],
                    '；'.join(f"{f['value']} {c['unit']}" for f in c.get('findings',[])) or '无有效读数',c['method'],CHECKS.get(c['status'],'需核对')] for c in checks],
                'paragraphs':['条件通过只说明本次试验条件，不代替产品性能结论。'] if kind=='method_condition' else []})
        issues=list(dict.fromkeys([*execution.get('current_source_issues',[]),*evaluation.get('missing_inputs',[])]))
        sections.append({'title':'缺项与当前来源状态','paragraphs':issues or ['当前来源检查未发现阻断项；仍按上述项目范围记录。']})
        sections.append({'title':'标准依据与版本','columns':['标准 / 条款','修订 / 页码','原件哈希'], 'widths':[50,50,60],
            'rows':[[f"{s.get('standard_no','')} / {s.get('clause_no','')}",f"{s['revision_id']} / {s.get('page_number','未提供')}",s.get('file_hash') or '未提供'] for s in snap['source_refs']]})
        evidence=[]
        for obs in snap['observations']:
            locator=f"原报告第{obs.get('report_page')}页 / {obs.get('report_item')}" if obs['kind']=='report_attachment' else f"测量记录 {obs['evidence_id']} / {obs.get('event_id','')}"
            evidence.append([obs.get('sample_label') or sample_names.get(obs['sample_id'],obs['sample_id']),obs['measurement_key'],locator,
                obs.get('source_version') or '未提供'])
        sections.append({'title':'检测证据来源','columns':['样品','指标','原始定位','冻结来源版本'],'widths':[25,30,55,50],'rows':evidence})
        reviews=execution.get('review_history') or []
        sections.append({'title':'独立专业复核','rows':[[r['actor_id'],STATUSES.get(r['action'],r['action']),r['reason'],'；'.join(r.get('evidence_refs') or []),
            (r.get('verification_snapshot') or {}).get('checked_at') or r.get('created_at') or '未提供'] for r in reviews],
            'columns':['复核者','决定','说明','核对依据','核验时间'],'widths':[28,17,35,48,32],
            'paragraphs':[] if reviews else ['尚未记录独立专业复核，本文为待复核记录。']})
    if aux:
        sections.append({'title':'图片或历史辅助记录（独立保留）','paragraphs':[aux.get('notice') or '图片辅助分析不等于产品整体结论。',
            f"原记录项目状态：{verdict_label(aux.get('verdict'))}",f"评分说明：{score_label(aux)}"],
            'rows':[['原记录编号',aux.get('id','未提供')],['复核者',aux.get('reviewed_by') or '未复核'],['原复核意见',aux.get('review_note') or '未提供']]})
        if aux.get('summary'):sections.append({'title':'原辅助说明（原文保留，不替代本次判定）','paragraphs':[str(aux['summary'])]})
        defects=aux.get('defects') or []
        sections.append({'title':'辅助缺陷明细','columns':['序号','类型','说明'],'widths':[15,40,105],
            'rows':[[str(i+1),d.get('type',''),d.get('description','')] for i,d in enumerate(defects)],
            'paragraphs':[] if defects else ['原辅助结果未记录可定位缺陷；不能据此认定产品整体无缺陷。']})
        sections.append({'title':'辅助引用资料','paragraphs':[citation_text(c) for c in aux.get('citations',[])] or ['原辅助记录未提供可导出引用。']})
    risks=bundle.get('risks') or []
    sections.append({'title':'关联风险研判与边界','paragraphs':['项目符合性与风险等级分别确认；风险概率未校准时不显示虚构概率。']})
    for risk in risks:
        sections.append({'title':f"风险研判版本 {risk['version']}",'rows':[['研判编号',risk['id']],['当前状态',risk['effective_status']],
            ['风险类型',risk.get('risk_type') or '待识别'],['记录风险等级',risk['risk_level']],['风险概率','未校准' if risk['probability'] is None else str(risk['probability'])],
            ['政策版本',risk.get('policy_version') or '未指定'],['复核者',risk.get('reviewed_by') or '未复核']],
            'paragraphs':[*[b['message'] for b in risk['source_validation']['blockers']],*[str(x) for x in risk.get('recommendations',[])]]})
    if not risks:sections[-1]['paragraphs'].append('没有与本次执行版本关联且在授权范围内的风险研判，风险等级不由项目通过推定。')
    return sections
