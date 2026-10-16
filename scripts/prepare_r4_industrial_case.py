"""Build a portable, source-linked case package; no platform approvals or tests-as-truth."""
import argparse, csv, hashlib, json, shutil
from pathlib import Path
from pypdf import PdfReader

CASE='REPORT_EBIKE_JG2128520085'
STANDARD_URL='https://scjgj.pds.gov.cn/attach/0/1908231116143354011.pdf'
STANDARD_INFO='https://openstd.samr.gov.cn/bzgk/gb/newGbInfo?hcno=72969DAA3DA5795AD2163528FF57166C'
REPORT_URL='https://www.qzlc.gov.cn/zwgk/qzbm/qscjdglj/zljg/202110/P020211028350036974001.pdf'


def checksum(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


def prepare(root,output):
    root=Path(root).resolve();output=Path(output).resolve();case=root/'05_cases'/CASE
    report=case/'input/inspection_report_5pages.pdf'
    raw=root/'04_reports/ebike_actual_inspection_report_JG2128520085_2021.pdf'
    standard=root/'01_standards/ebike/historical/GB-17761-2018.pdf'
    assert len(PdfReader(report).pages)==5 and len(PdfReader(standard).pages)==19
    # Preserve the old transcription before correcting its locator/model.
    backup=case/'reference/r4_preparation_backup_20261014'
    for path in [case/'input/actual_measurements.csv',case/'reference/criterion_candidates.json',case/'task_request.json']:
        backup.mkdir(parents=True,exist_ok=True)
        target=backup/path.name
        if not target.exists():shutil.copy2(path,target)
    with (case/'input/actual_measurements.csv').open(encoding='utf-8-sig',newline='') as handle:
        rows=list(csv.DictReader(handle))
    for row in rows:
        old=int(row.get('source_original_pdf_page') or row['source_pdf_page'])
        row.update(source_original_pdf_page=old,source_pdf_page=old-1,report_printed_page=old-1)
    with (case/'input/actual_measurements.csv').open('w',encoding='utf-8-sig',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    candidates=json.loads((case/'reference/criterion_candidates.json').read_text(encoding='utf-8'))
    for candidate in candidates:
        old=int(candidate.get('source_original_pdf_page') or candidate['source_report_page'])
        candidate.update(source_original_pdf_page=old,source_report_page=old-1,page_reference='uploaded_report_pdf')
    write_json(case/'reference/criterion_candidates.json',candidates)
    request=json.loads((case/'task_request.json').read_text(encoding='utf-8'))
    request['product']['model']='TDR009Z-2Z'
    request['report_page_mapping']={'original_file_offset':1,'uploaded_pdf_pages':5,'page_reference':'uploaded_report_pdf'}
    write_json(case/'task_request.json',request)
    output.mkdir(parents=True,exist_ok=True)
    assets=[]
    for kind,path in [('standard',standard),('report',report),('report_original',raw),
                      ('photo',case/'input/sample_photo_page.jpg'),('transcription',case/'input/actual_measurements.csv')]:
        target=output/path.name
        if target.exists() and checksum(target)!=checksum(path):
            raise ValueError('Existing package differs; choose a fresh output directory')
        shutil.copy2(path,target)
        assets.append({'kind':kind,'file_name':target.name,'sha256':checksum(target),'size_bytes':target.stat().st_size})
    by_key={row['indicator_ref']:row for row in rows}
    planned=[]
    for key,clause,page,method,method_page in [('whole_mass','6.1.3',8,'7.2.3',13),('horn_sound','6.2.3.3',10,'7.3.3.3',17)]:
        source=by_key[key];mass=key=='whole_mass'
        planned.append({'measurement_key':key,'indicator':source['indicator'],'clause_no':clause,'standard_page':page,
            'standard_printed_page':page-4,'method_clause':method,'method_page':method_page,
            'method':f'GB 17761-2018 {method}','conditions':
                '装配完整的电动自行车，按7.2.3称量；历史报告核对，不证明当前新样品状态。' if mass else
                '按7.3.3.3重复测量3次取算术平均值；声级计前方2m、高1.2m，其他要求参见7.2.7.2。公开报告未给出3次原始读数。',
            'requirement':'整车质量小于或等于55kg' if mass else '鸣号装置声压级75dB(A)至100dB(A)',
            'unit':source['unit'],'operator':'le' if mass else 'range','numeric_upper':55.0 if mass else 100.0,
            'numeric_lower':None if mass else 75.0,'numeric_aggregation':'all' if mass else 'mean',
            'minimum_observations':1 if mass else 3,'candidate_type':'inspection_requirement','execution_mode':'numeric',
            'value':float(source['measured_value']),'report_page':int(source['source_pdf_page']),
            'original_pdf_page':int(source['source_original_pdf_page']),'report_item':source['indicator'],
            'conditions_values':{},'transcription_status':'awaiting_independent_review',
            'single_report_value_sufficient_for_comparison':mass})
    manifest={'schema_version':1,'case_id':CASE,'kind':'historical_report_review',
        'title':'电动自行车历史报告核对 · JG2128520085','product':request['product'],
        'report_no':'JG2128520085','initial_execution_keys':['whole_mass'],
        'sampling_sheet_no':'01010590730114622','sample_label':'JG2128520085（原报告检验样品；备用样品不计作第二次观测）',
        'sampled_date':'2021-07-30','report_issued_date':'2021-09-03','assets':assets,'planned_items':planned,
        'standard_metadata':{'standard_no':'GB 17761-2018','standard_name':'电动自行车安全技术规范','standard_level':'GB',
            'standard_status':'废止','resource_type':'standard','domain':'电动自行车','product_category':'电动自行车',
            'source_url':STANDARD_INFO,'publisher':'国家市场监督管理总局、中国国家标准化管理委员会',
            'effective_from':'2019-04-15','effective_to':'2025-08-31','production_from':'2019-04-15','production_to':'2025-08-31',
            'scope_notes':'仅用于本案2019-08-01生产、2021年签发报告的历史核对；不得作为当前生产或销售准入结论。适用范围及日期待专家核验。'},
        'provenance':{'report_url':REPORT_URL,'standard_pdf_url':STANDARD_URL,'standard_info_url':STANDARD_INFO,
            'replacement_info_url':'https://www.miit.gov.cn/zwgk/zcjd/art/2025/art_52062523e41040f596a1651abc52c5b0.html',
            'preparation':'自动整理与原图对照，尚非人工专业审核','original_pdf_offset':1},
        'limitations':['历史公开报告核对，不是本平台重新实验或当前在售产品检测。',
            '一个报告汇总值只计一个来源，不作为三次独立原始观测。',
            '原始仪器、校准及各次鸣号读数未公开；图片不能证明质量或声压级。',
            '本案仅选定项目，产品整体未评定；技术候选需专家独立确认。']}
    write_json(output/'case.json',manifest)
    write_json(case/'reference/r4_case_manifest.json',manifest)
    print(json.dumps({'case_id':CASE,'package':str(output),'assets':len(assets),'selected_items':len(planned),
                      'page_locator_corrected':True,'professional_status':'awaiting_review'},ensure_ascii=False))
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--dataset-root',default=r'D:\dataset\industrial_qc_20261004')
    parser.add_argument('--output',required=True);args=parser.parse_args();prepare(args.dataset_root,args.output)
