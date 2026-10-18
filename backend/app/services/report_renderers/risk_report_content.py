import json


def risk_report_sections(report):
    s = report["snapshot"]
    c = s["conclusion"]
    demo = s.get('execution_mode') == 'demo'
    label = '（演示）' if demo else ''
    probability = '未知' if c.get('probability') is None else str(c['probability'])
    model = '是（仅表示发生调用）' if s.get('llm_called') else '未记录实际调用（规则、人工或历史未记录）'
    sections = [{"title": "性质、对象与版本", "paragraphs": [s["boundary"],
        f"事项：{s['case_code']} / {s['case_title']}", f"对象：{s['object_name']}",
        f"研判：第 {s['assessment_version']} 版 / {s['assessment_id']}",
        f"报告快照时间（UTC）：{report['frozen_at']}", f"快照摘要：{report['snapshot_hash']}"]},
        {"title": "研判结论与分析", "paragraphs": [c["summary"], c["reasoning"],
            f"风险等级{label}：{ {'unknown':'未知','low':'低','medium':'中','high':'高','critical':'严重'}.get(c.get('risk_level'),'未知')}；发生概率：{probability}；真实模型调用：{'否' if demo else model}。"]},
        {"title": "限制与证据缺口", "paragraphs": [c["limitations"], *c.get("missing_inputs", [])]},
        {"title": "独立复核", "paragraphs": [f"编写人：{s['review']['author_name']} / {s['review']['author_id']}",
            f"独立复核人：{s['review']['reviewer_id']}；{'演示复核通过' if demo else '独立复核通过'}；时间（UTC）：{s['review']['at']}", s["review"]["comment"]]}]
    if not demo:
        calls = s.get('model_call') or {}
        sections[1]['paragraphs'].append(f"模型请求次数：{calls.get('attempted_calls') if calls.get('attempted_calls') is not None else '未记录'}；已解析返回次数：{calls.get('successful_calls') if calls.get('successful_calls') is not None else '未记录'}；推理流程状态：{calls.get('inference_status') or '规则流程或历史未记录'}。调用返回不等于业务结论正确。")
    labs = s["laboratory"]
    sections.append({"title": "可选实验室验证", "paragraphs": ["未选择实验室分支；分析流程不依赖检测任务。"] if not labs else [
        f"原研判第 {l['assessment_version']} 版：{'跳过验证' if l['mode']=='skip' else '关联验证'}；目的：{l['purpose']}；"
        f"状态：{ {'demo_skipped':'演示已跳过','demo_requested':'演示待资料','demo_returned':'演示资料已回流'}.get(l['status'],l['status'])}；"
        f"任务：{l.get('task_id') or '未关联'}；返回资料：{'、'.join(l.get('record_ids',[])) or '无'}；"
        f"说明：{l.get('return_note') or '未返回资料'}" for l in labs]})
    suggestions = [f"研判建议：{text}" for text in c.get("recommendations", [])]
    for item in s["sampling"]:
        suggestions.extend([f"{item['title']}；生成时有效性：{ '待重评' if item['effective_status']=='needs_reassessment' else ('演示建议' if demo else '抽查建议')}；原研判第 {item['snapshot']['assessment_version']} 版。",
            f"理由：{item['content']['rationale']}", f"关注：{item['content']['focus']}", f"限制：{item['content']['limitations']}",
            "执行数量、批次、地点和时间仅为建议；未下达执行任务。"])
    if not any(item["snapshot"]["assessment_id"] == s["assessment_id"] and item["status"] == ("demo_confirmed" if demo else 'confirmed') and item["effective_status"] != "needs_reassessment" for item in s["sampling"]):
        suggestions.append("本研判版本尚无当前有效的已固定抽查建议；旧建议需按新证据重新核对。")
    sections.append({"title": "抽查建议", "paragraphs": suggestions})
    for index, record in enumerate(s["records"], 1):
        nature = {'synthetic':'模拟', 'observed':'原始资料', 'inferred':'推断'}.get(record.get('data_nature'), '性质待确认')
        sections.append({"title": f"来源 {index}（{nature}）", "paragraphs": [f"受理编号：{record['id']}；类型：{record['type']}；出处：{record['origin']}",
            f"发生时间：{record.get('occurred_at') or '未知'}；原文指纹：{record['content_hash']}",
            json.dumps(record["content"], ensure_ascii=False), f"附件引用：{'、'.join(record['attachment_ids']) or '无'}"]})
    sections.append({"title": "证据与附件原件索引", "paragraphs": [
        *[f"证据 {e['id']} → 来源 {e['source_record_id']}：{e.get('text') or json.dumps(e.get('structured_data') or {}, ensure_ascii=False)}" for e in s["evidence"]],
        *[f"附件 {a['id']} / {a['name']} / SHA256 {a['sha256']}" for a in s["attachments"]]]})
    return sections
