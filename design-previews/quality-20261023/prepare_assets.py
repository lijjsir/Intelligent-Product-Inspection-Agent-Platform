"""Copy previously collected public originals into an isolated UI preview."""
from pathlib import Path
import json
import shutil

folder = Path(__file__).resolve().parent
source = folder.parents[1] / 'backend' / 'runtime' / 'real_quality_case_20261023'
assets = folder / 'assets'
assets.mkdir(exist_ok=True)
facts = json.loads((source / 'public-package' / 'public-facts-and-provenance.json').read_text(encoding='utf-8'))
js = json.dumps(facts, ensure_ascii=False, indent=2).replace('<', '\\u003c')
(folder / 'facts.js').write_text('window.PUBLIC_FACTS = ' + js + ';\n', encoding='utf-8')
for name in ['report-page-3.png', 'report-page-5.png']:
    shutil.copyfile(source / 'sources' / name, assets / name)
shutil.copyfile(source / 'sources' / 'report.pdf', assets / 'JG2128520085.pdf')
print('Prepared 5 public source records and 3 original assets. No application APIs called.')
