"""Read-only hash gate for the frozen PR #68 assets, evidence and staged inputs."""
import hashlib
import json
from pathlib import Path
import subprocess

REPO=Path(__file__).resolve().parents[4]
EVIDENCE=REPO/'docs/evidence/xinyi-walkup-exemplar-269873'


def digest(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            value.update(chunk)
    return value.hexdigest()


def main():
    frozen=json.loads((EVIDENCE/'protected-pr68.json').read_text())
    changes=[]
    for row in frozen['files']:
        path=REPO/row['path']
        if not path.is_file() or digest(path)!=row['sha256']:
            changes.append(row['path'])
    retained=json.loads((EVIDENCE/'retained-investigation.json').read_text())
    for row in retained:
        path=REPO/row['path']
        if not path.is_file() or digest(path)!=row['sha256']:
            changes.append(row['path'])
    originals=json.loads((REPO/'investigation/staged-inputs.json').read_text(encoding='utf-8-sig'))
    for row in originals:
        for root in (REPO,Path(r'D:\Users\EDDY\Documents\GitHub\air-combat-world')):
            path=root/row['relative_path']
            if not path.is_file() or digest(path)!=row['source_sha256']:
                changes.append(str(path))
    git=['git','-c','safe.directory='+REPO.as_posix(),'-C',str(REPO)]
    old_branch=subprocess.check_output(git+['rev-parse','test/xinyi-shared-masks-ue58-round1'],text=True).strip()
    assert old_branch=='a6b0d3536ac00e12214e78665750c9994518dd44'
    report={'status':'PASS_PROTECTED' if not changes else 'FAIL_PROTECTED',
            'frozen_files_checked':len(frozen['files']),'source_inputs_checked_per_location':len(originals),
            'retained_investigation_files_checked':len(retained),
            'locations':2,'changes':changes,'pr68_branch':old_branch,'read_only_D_drive':True}
    EVIDENCE.mkdir(parents=True,exist_ok=True)
    (EVIDENCE/'source-immutability.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    assert not changes


if __name__=='__main__':
    main()
