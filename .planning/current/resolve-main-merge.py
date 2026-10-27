import json
import subprocess
import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
def git(*args):
    return subprocess.check_output(['git', *args], cwd=root)

files = git('diff', '--name-only', '--diff-filter=U').decode().splitlines()
backup = root / '.planning/current/main-merge-backup'
backup.mkdir(exist_ok=True)
manifest = backup / 'manifest.json'
if not manifest.exists():
    manifest.write_text(json.dumps({'head': git('rev-parse','HEAD').decode().strip(),
        'merge':git('rev-parse','MERGE_HEAD').decode().strip(), 'files': files}, indent=2))
    for file in files:
        for label, rev in [('ours', 'HEAD'), ('theirs', 'MERGE_HEAD')]:
            target = backup / label / file
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(git('show', f'{rev}:{file}'))
        target = backup / 'conflicted' / file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((root/file).read_bytes())
print(f'Backed up {len(files)} conflicted files, both revisions and conflict markers')

if '--resolve' in sys.argv:
    theirs = {
        '.planning/current/findings.md', '.planning/current/progress.md',
        '.planning/current/task_plan.md', 'CODEX_HANDOFF.md',
        'backend/alembic/env.py',
        'backend/alembic/versions/20261022_0053_domestic_packing_production_compat.py',
        'backend/alembic/versions/20261022_0054_merge_walmart_identity_and_domestic_packing.py',
        'backend/app/db/domestic_ods_adopt.py',
        'backend/app/modules/iam/permission_catalog_v2.py',
        'backend/tests/db/test_alembic_scaffold.py',
        'backend/tests/modules/pmc_domestic/test_domestic_ods_adopt.py',
        'docs/BACKEND_MODULE_CATALOG.md', 'frontend/src/router/routes.tsx',
    }
    unions = {'docs/api/README.md', 'docs/data-registry/DATA_INTERFACE_REGISTRY.md',
              'docs/tasks/TASK_REGISTRY.md', 'frontend/src/pages/data-center/apiDocsMockData.ts'}
    manual = {'frontend/src/pages/data-center/integrationSyncTaskApi.ts',
              'backend/app/modules/integration_sync/repository.py'}
    pattern = re.compile(r'^<<<<<<<[^\n]*\n(.*?)^=======\n(.*?)^>>>>>>>[^\n]*\n', re.M | re.S)
    for file in files:
        if file in manual:
            continue
        if file in theirs:
            content = (backup/'theirs'/file).read_bytes()
        else:
            original = (backup/'conflicted'/file).read_text(encoding='utf-8')
            content = pattern.sub(lambda m: m[1] + (m[2] if file in unions else ''), original).encode()
        (root/file).write_bytes(content)
    print('Resolved reviewed local features and main safety/feature additions; shared integration conflicts remain manual')
