import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from experiment_results import ClusterExperimentResults, CLUSTER_DATASET, order_revisions, result_router


class ClusterResultTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.oid='ORD-08511033'
        inputs={self.oid:[dict(sku_id='SKU-A',width=.2,depth=.2,height=.1,weight=1)]}
        (self.root/'inputs.json').write_text(json.dumps(inputs))
        (self.root/'packs').mkdir()
        self.pack=dict(order_id=self.oid,container=dict(width=.8,depth=1.2,height=2),boxes=[])
        self.path=self.root/'packs'/(self.oid+'.packformation.json')
        self.path.write_text(json.dumps(self.pack))
        meta=dict(kind='ep-only',dataset=CLUSTER_DATASET,label='Cluster run',
            suite_commit='abc',suite_repository='https://example.test/repo',
            run_started_at='2026-09-11T18:00:00Z',run_completed_at='2026-09-11T19:00:00Z',
            inputs_file_sha256=hashlib.sha256((self.root/'inputs.json').read_bytes()).hexdigest(),
            pack_sha256={self.oid:hashlib.sha256(self.path.read_bytes()).hexdigest()},ep_subject='EP only')
        (self.root/'viewer.json').write_text(json.dumps(meta))
        self.library=ClusterExperimentResults(self.root)

    def test_inventory_pack_and_provenance_belong_to_cluster_run(self):
        self.assertEqual(self.library.orders()[0]['total_boxes'],1)
        result=self.library.ep_result(self.oid)
        self.assertEqual(result['pack'],self.pack)
        self.assertEqual(result['provenance']['experiment'],CLUSTER_DATASET)
        self.assertIn(CLUSTER_DATASET,result['provenance']['source_file'])
        self.assertFalse(self.library.teacher_result(self.oid)['available'])

    def test_router_never_returns_historical_or_teacher_fallback(self):
        app=FastAPI();app.include_router(result_router(self.root,self.library))
        with TestClient(app) as client:
            base='/viz-api/experiments/'+CLUSTER_DATASET
            self.assertEqual(client.get(base+'/ep-result/'+self.oid).json()['pack'],self.pack)
            self.assertFalse(client.get(base+'/result/'+self.oid).json()['available'])
            self.assertFalse(client.get(base+'/ep-result/ORD-00000000').json()['available'])
            self.assertEqual(client.get(base+'/orders/ORD-00000000').status_code,404)

    def test_corrupt_pack_and_input_fail_closed(self):
        self.path.write_text('{}')
        with self.assertRaisesRegex(ValueError,'recorded revision'): self.library.ep_result(self.oid)
        (self.root/'inputs.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'recorded revision'): _=self.library.teachers

    def test_revision_is_only_listed_for_orders_with_actual_pack(self):
        class EmptyBaseline:
            teachers={}
            _check_id=staticmethod(ClusterExperimentResults._check_id)
        revisions=order_revisions(self.oid,EmptyBaseline(),self.root,lambda *_:None,[self.library])
        self.assertEqual([r['id'] for r in revisions],[CLUSTER_DATASET])
        revisions=order_revisions('ORD-00000000',EmptyBaseline(),self.root,lambda *_:None,[self.library])
        self.assertEqual([r['id'] for r in revisions],['published'])


class PublishedClusterArchiveTests(unittest.TestCase):
    def test_committed_six_order_archive_when_present(self):
        archive=Path(__file__).resolve().parents[1]/'experiments'/CLUSTER_DATASET
        if not (archive/'viewer.json').is_file():
            self.skipTest('Results are committed separately after generation and audit')
        library=ClusterExperimentResults(archive)
        summary=json.loads((archive/'summary.json').read_text())
        audit=json.loads((archive/'competition-audit.json').read_text())
        manifest=json.loads((archive/'manifest.json').read_text())
        self.assertEqual(len(library.orders()),6)
        self.assertEqual(sum(r['total_boxes'] for r in library.orders()),1076)
        self.assertEqual(library.metadata['suite_commit'],manifest['algorithm_commit'])
        for row in summary['orders']:
            oid=row['order_id'];pack=library.ep_result(oid)['pack']
            self.assertEqual(len(pack['boxes']),row['placed'])
            self.assertEqual(len({b['id'] for b in pack['boxes']}),row['placed'])
            self.assertEqual(row['placed'],audit['orders'][oid]['accepted_boxes'])
            self.assertTrue(audit['orders'][oid]['valid'])
            self.assertEqual(audit['orders'][oid]['complete'],row['placed']==row['total'])
            self.assertFalse(library.teacher_result(oid)['available'])
            top=max((b['position']['z']+b['dimensions']['height']/2 for b in pack['boxes']),default=0)
            self.assertAlmostEqual(top,row['top_m'])
            self.assertLessEqual(top,2.+1e-9)
        self.assertEqual(sum(r['placed'] for r in summary['orders']),summary['boxes_placed'])


if __name__=='__main__': unittest.main()
