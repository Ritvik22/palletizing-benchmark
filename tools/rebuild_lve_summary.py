"""Recompute per-pack LVE for a sparse checkout, without changing pack artifacts.

Explicitly reads committed packs from HEAD and overlays locally present packs.
The generated summary records that source revision. Never reciprocates means.
"""
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]

def main():
    spec=importlib.util.spec_from_file_location('summary_builder',ROOT/'build_benchmark_summary.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    directories=sorted({row[2] for row in module.METHODS+[module.BASELINE]})
    tracked=subprocess.check_output(['git','ls-tree','--name-only','HEAD'],cwd=ROOT,text=True).splitlines()
    committed=[d for d in directories if d in tracked]
    data=subprocess.check_output(['git','archive','--format=zip','HEAD',*committed],cwd=ROOT)
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    with tempfile.TemporaryDirectory(prefix='lve-v2-') as folder:
        target=Path(folder).resolve()
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for member in archive.infolist():
                dest=(target/member.filename).resolve()
                if not dest.is_relative_to(target): raise ValueError('Unsafe archive member')
            archive.extractall(target)
        for d in directories:
            if (ROOT/d).exists():
                shutil.copytree(ROOT/d,target/d,dirs_exist_ok=True)
        module.HERE=str(target)  # DB stays explicitly pinned to the local order DB.
        module.main()
        result=json.loads((target/'benchmark_summary.json').read_text())
        result['pack_source']={'git_revision':revision,'local_pack_overrides':True}
        (ROOT/'benchmark_summary.json').write_text(json.dumps(result,indent=1),encoding='utf-8')

if __name__=='__main__':main()
