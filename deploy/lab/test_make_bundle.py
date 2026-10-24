"""Host-only source bundle checks; never builds or deploys containers."""
import importlib.util,json,sys,tarfile,hashlib
from pathlib import Path

spec=importlib.util.spec_from_file_location('release_bundle',Path(__file__).with_name('make_bundle.py'))
bundle=importlib.util.module_from_spec(spec);spec.loader.exec_module(bundle)


def test_current_source_selection_includes_background_processing_and_schema():
    selected=set(bundle.selected_files())
    required={'backend/app/models/risk_analysis_job.py','backend/app/services/risk_analysis_job_service.py',
        'backend/worker/tasks/risk_analysis_task.py','backend/migrations/versions/0118_risk_analysis_jobs.py',
        'frontend/src/composables/useRiskAnalysisJob.ts','backend/app/services/standard_pdf_reading_text.py',
        'backend/scripts/verify_local_quality_release.py'}
    assert required<=selected
    assert not any('/runtime/' in path or Path(path).name.startswith('.env') for path in selected)


def test_archive_excludes_secrets_and_matches_its_manifest(tmp_path,monkeypatch):
    source=tmp_path/'source';source.mkdir()
    for path in bundle.SOURCE_FILES:
        file=source/path;file.parent.mkdir(exist_ok=True,parents=True);file.write_text('Source fixture',encoding='utf-8')
    for path in ['backend/app/real_source.py','backend/app/.env.local','backend/app/private.pem','backend/app/runtime/data.json','backend/app/tests/mock.json','frontend/src/local.spec.ts']:
        file=source/path;file.parent.mkdir(exist_ok=True,parents=True);file.write_text('Fixture',encoding='utf-8')
    monkeypatch.setattr(bundle,'ROOT',source)
    output=tmp_path/'source.tar.gz';monkeypatch.setattr(sys,'argv',['make_bundle.py',str(output)])
    bundle.main()
    manifest=json.loads(output.with_name(output.name+'.manifest.json').read_text(encoding='utf-8'))
    assert manifest['archive_sha256']==hashlib.sha256(output.read_bytes()).hexdigest()
    with tarfile.open(output) as archive:
        names=set(archive.getnames());assert 'backend/app/real_source.py' in names
        assert 'backend/app/.env.local' not in names and 'backend/app/private.pem' not in names
        assert 'backend/app/runtime/data.json' not in names and 'backend/app/tests/mock.json' not in names
        assert 'frontend/src/local.spec.ts' not in names
        for name in names:assert manifest['files'][name]==hashlib.sha256(archive.extractfile(name).read()).hexdigest()
