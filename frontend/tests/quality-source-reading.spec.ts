import { describe, expect, it } from 'vitest';
import { isPdfAttachment, readSourceText, safeSourceUrl } from '@/utils/quality-source-reading';

describe('reading government webpage text without changing source facts', () => {
  it('removes recognizable webpage navigation and fragmented metadata, retaining the complete article', () => {
    const raw = ['2024年产品质量抽查情况通报', '你的位置:', '首页', '>', '政务', '标', '题：', '2024年产品质量抽查情况通报', '索', '引', '号：', '111/2025', '发布时间：2025-04-07 05:14', '2024年产品质量', '抽查情况通报', '2024年，组织抽查。', '一、基本情况', '抽查80批次，发现4批次不合格。', '二、检测值', '汇总30.8 km/h、51.4 kg、73 dB(A)，范围75至100 dB(A)。', '附件1 原始表格.xlsx'].join('\n');
    const reading = readSourceText(raw, true);
    expect(reading.cleaned).toBe(true);
    expect(reading.title).toBe('2024年产品质量抽查情况通报');
    expect(reading.paragraphs).toEqual(['2024年，组织抽查。', '一、基本情况', '抽查80批次，发现4批次不合格。', '二、检测值', '汇总30.8 km/h、51.4 kg、73 dB(A)，范围75至100 dB(A)。', '附件1 原始表格.xlsx']);
    expect(raw).toContain('标\n题：');
  });
  it('joins inline article spans while preserving dates and standard identifiers', () => {
    const title = '公布电动自行车违法典型案例';
    const raw = [title+' - 官方网站','您当前的位置：','首页','>','公告','[ 发布日期 ]','2025-12-19',title,'2024','年','6','月，检查发现不符合','GB17761','—','2018','标准要求。','一、案例事实','罚款','5.5','万元。'].join('\n');
    expect(readSourceText(raw, true).paragraphs).toEqual(['2024年6月，检查发现不符合GB17761—2018标准要求。','一、案例事实','罚款5.5万元。']);
  });
  it('keeps adjacent numeric lines separate instead of turning two values into one', () => {
    const raw = ['公开产品检验资料的正文标题','你的位置：','首页','>','资料','标题：','公开产品检验资料的正文标题','发布时间：2025-01-01','结果编号','1','2','分别记录。'].join('\n');
    const output = readSourceText(raw,true).paragraphs.join('\n');
    expect(output).toContain('1\n2');
    expect(output).not.toContain('12');
  });
  it('does not guess the body of arbitrary text or OCR output', () => {
    const raw = '5 . 4 . 3\n1\n2\n不能据此猜测数值或公式';
    expect(readSourceText(raw,true)).toEqual({title:'',paragraphs:[raw],cleaned:false});
    expect(readSourceText('你的位置：\n说明文字',false).cleaned).toBe(false);
  });
  it('recognizes actual PDF resources and only accepts web source protocols', () => {
    expect(isPdfAttachment({file_name:'报告.PDF',mime_type:'application/octet-stream'})).toBe(true);
    expect(isPdfAttachment({file_name:'文字.txt',mime_type:'text/plain'})).toBe(false);
    expect(safeSourceUrl({source_url:'javascript:alert(1)'})).toBe('');
    expect(safeSourceUrl({origin_label:'https://example.gov.cn/report.pdf'})).toBe('https://example.gov.cn/report.pdf');
  });
});
