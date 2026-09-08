"""Transactional submission storage, separate from the shipped dataset DB."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import threading
import time

from .evaluator import VERSION, canonical, digest, evaluate, summarize
from .models import Pack


class Problem(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message
        super().__init__(message)


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def uid(prefix):
    return prefix + '_' + secrets.token_hex(12)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


class Store:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.evaluation_slots = threading.BoundedSemaphore(2)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users (
                  id TEXT PRIMARY KEY, provider TEXT NOT NULL, subject TEXT NOT NULL,
                  display_name TEXT NOT NULL, email TEXT NOT NULL, created TEXT NOT NULL,
                  UNIQUE(provider,subject));
                CREATE TABLE IF NOT EXISTS credentials (
                  hash TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id), name TEXT,
                  scopes TEXT NOT NULL, expires REAL NOT NULL, created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tickets (
                  hash TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS limits (key TEXT PRIMARY KEY, start REAL NOT NULL, count INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS benchmarks (
                  id TEXT PRIMARY KEY, name TEXT NOT NULL, hash TEXT NOT NULL, document TEXT NOT NULL,
                  created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS strategies (
                  id TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES users(id), name TEXT NOT NULL,
                  description TEXT NOT NULL, created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS revisions (
                  id TEXT PRIMARY KEY, strategy_id TEXT NOT NULL REFERENCES strategies(id),
                  benchmark_id TEXT NOT NULL REFERENCES benchmarks(id), parent_id TEXT REFERENCES revisions(id),
                  number INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'draft', notes TEXT NOT NULL,
                  code_revision TEXT NOT NULL, model_revision TEXT NOT NULL, config TEXT NOT NULL,
                  generation INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL, published TEXT,
                  summary TEXT, hash TEXT, UNIQUE(strategy_id,number));
                CREATE TABLE IF NOT EXISTS packs (
                  revision_id TEXT NOT NULL REFERENCES revisions(id), order_id TEXT NOT NULL,
                  artifact TEXT NOT NULL, report TEXT NOT NULL, PRIMARY KEY(revision_id,order_id));
                CREATE TABLE IF NOT EXISTS events (
                  id INTEGER PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL,
                  object_id TEXT NOT NULL, created TEXT NOT NULL);
                CREATE TRIGGER IF NOT EXISTS immutable_revision BEFORE UPDATE ON revisions
                  WHEN OLD.state='published' BEGIN SELECT RAISE(ABORT,'Published revision is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_pack_update BEFORE UPDATE ON packs
                  WHEN (SELECT state FROM revisions WHERE id=OLD.revision_id)='published'
                  BEGIN SELECT RAISE(ABORT,'Published pack is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_pack_delete BEFORE DELETE ON packs
                  WHEN (SELECT state FROM revisions WHERE id=OLD.revision_id)='published'
                  BEGIN SELECT RAISE(ABORT,'Published pack is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_pack_insert BEFORE INSERT ON packs
                  WHEN (SELECT state FROM revisions WHERE id=NEW.revision_id)='published'
                  BEGIN SELECT RAISE(ABORT,'Published pack is immutable'); END;
                PRAGMA user_version=1;
            ''')

    @contextmanager
    def connect(self, write=False):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            if write:
                db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def limit(self, key, count=30, seconds=60):
        key = token_hash(key)
        with self.connect(True) as db:
            row = db.execute('SELECT * FROM limits WHERE key=?', (key,)).fetchone()
            if row and time.time()-row['start'] < seconds:
                if row['count'] >= count:
                    raise Problem(429, 'Too many requests. Please try again later.')
                db.execute('UPDATE limits SET count=count+1 WHERE key=?', (key,))
            else:
                db.execute('INSERT OR REPLACE INTO limits VALUES (?,?,1)', (key, time.time()))
            db.execute('DELETE FROM limits WHERE start<?', (time.time()-86400,))

    def user(self, provider, subject, name, email):
        with self.connect(True) as db:
            db.execute('INSERT INTO users VALUES (?,?,?,?,?,?) ON CONFLICT(provider,subject) '
                       'DO UPDATE SET display_name=excluded.display_name,email=excluded.email',
                       (uid('usr'), provider, subject, name[:100], email, now()))
            return dict(db.execute('SELECT * FROM users WHERE provider=? AND subject=?', (provider, subject)).fetchone())

    def credential(self, user_id, name, scopes, ttl):
        raw = secrets.token_urlsafe(40)
        with self.connect(True) as db:
            db.execute('INSERT INTO credentials VALUES (?,?,?,?,?,?)',
                       (token_hash(raw), user_id, name, canonical(scopes), time.time()+ttl, now()))
        return raw

    def authenticate(self, raw):
        if not raw or len(raw) > 200:
            return None
        with self.connect() as db:
            row = db.execute('SELECT u.*,c.scopes,c.name AS token_name,c.hash AS credential_id FROM credentials c '
                             'JOIN users u ON u.id=c.user_id WHERE c.hash=? AND c.expires>?',
                             (token_hash(raw), time.time())).fetchone()
        if not row:
            return None
        return dict(row) | {'scopes': json.loads(row['scopes'])}

    def ticket(self, kind, payload, ttl=600):
        raw = secrets.token_urlsafe(40)
        with self.connect(True) as db:
            db.execute('DELETE FROM tickets WHERE expires<?', (time.time(),))
            db.execute('INSERT INTO tickets VALUES (?,?,?,?)', (token_hash(raw), kind, canonical(payload), time.time()+ttl))
        return raw

    def consume_ticket(self, kind, raw, binding):
        with self.connect(True) as db:
            row = db.execute('SELECT * FROM tickets WHERE hash=? AND kind=? AND expires>?',
                             (token_hash(raw), kind, time.time())).fetchone()
            if not row:
                raise Problem(400, 'Sign-in link expired or was already used. Start again.')
            payload = json.loads(row['payload'])
            if not binding or not secrets.compare_digest(payload['binding'], token_hash(binding)):
                raise Problem(400, 'Open this sign-in link in the browser where you requested it.')
            db.execute('DELETE FROM tickets WHERE hash=?', (token_hash(raw),))
            return payload

    def add_benchmark(self, doc):
        if doc['evaluator_version'] != VERSION or not doc['orders']:
            raise ValueError('Unsupported or empty benchmark.')
        body, checksum = canonical(doc), digest(doc)
        with self.connect(True) as db:
            existing = db.execute('SELECT hash FROM benchmarks WHERE id=?', (doc['id'],)).fetchone()
            if existing:
                if existing['hash'] != checksum:
                    raise Problem(409, 'Benchmark ID is immutable. Use a new version.')
                return
            db.execute('INSERT INTO benchmarks VALUES (?,?,?,?,?)', (doc['id'], doc['name'], checksum, body, now()))

    def benchmark(self, bid):
        with self.connect() as db:
            row = db.execute('SELECT document,hash FROM benchmarks WHERE id=?', (bid,)).fetchone()
        if not row:
            raise Problem(404, 'Benchmark not found.')
        return json.loads(row['document'])

    def benchmarks(self):
        with self.connect() as db:
            rows = db.execute('SELECT * FROM benchmarks ORDER BY created DESC').fetchall()
        result = []
        for row in rows:
            doc = json.loads(row['document'])
            result.append({'id': row['id'], 'name': row['name'], 'sha256': row['hash'], 'created': row['created'],
                           'orders': len(doc['orders']), 'boxes': sum(len(o['instances']) for o in doc['orders'].values()),
                           'container': doc['container'], 'evaluator_version': doc['evaluator_version'],
                           'stacking_rule': doc.get('stacking_rule', 'none'), 'license': doc.get('license', 'Not specified')})
        return result

    def create_strategy(self, owner, data):
        sid = uid('strategy')
        with self.connect(True) as db:
            db.execute('INSERT INTO strategies VALUES (?,?,?,?,?)', (sid, owner, data.name.strip(), data.description, now()))
        return {'id': sid}

    def create_revision(self, owner, sid, data):
        self.benchmark(data.benchmark_id)
        if len(canonical(data.config)) > 16000:
            raise Problem(422, 'Configuration metadata is too large.')
        rid = uid('revision')
        with self.connect(True) as db:
            if not db.execute('SELECT id FROM strategies WHERE id=? AND owner=?', (sid, owner)).fetchone():
                raise Problem(404, 'Strategy not found.')
            if data.parent_id:
                parent = db.execute('SELECT * FROM revisions WHERE id=? AND strategy_id=? AND benchmark_id=? AND state=?',
                                    (data.parent_id, sid, data.benchmark_id, 'published')).fetchone()
                if not parent:
                    raise Problem(422, 'Parent must be a published revision of this strategy and benchmark.')
            number = db.execute('SELECT COALESCE(MAX(number),0)+1 FROM revisions WHERE strategy_id=?', (sid,)).fetchone()[0]
            db.execute('INSERT INTO revisions (id,strategy_id,benchmark_id,parent_id,number,notes,code_revision,model_revision,config,created) '
                       'VALUES (?,?,?,?,?,?,?,?,?,?)', (rid,sid,data.benchmark_id,data.parent_id,number,data.notes,
                                                     data.code_revision,data.model_revision,canonical(data.config),now()))
            if data.parent_id:
                db.execute('INSERT INTO packs SELECT ?,order_id,artifact,report FROM packs WHERE revision_id=?', (rid,data.parent_id))
            db.execute('INSERT INTO events(actor,action,object_id,created) VALUES (?,?,?,?)', (owner,'revision-created',rid,now()))
        return {'id': rid, 'number': number, 'state': 'draft'}

    @staticmethod
    def _revision(db, rid, owner=None, write=False):
        r = db.execute('SELECT r.*,s.owner,s.name AS strategy_name,u.display_name AS author FROM revisions r '
                       'JOIN strategies s ON s.id=r.strategy_id JOIN users u ON u.id=s.owner WHERE r.id=?', (rid,)).fetchone()
        if not r or (r['owner'] != owner and (write or r['state'] != 'published')):
            raise Problem(404, 'Revision not found.')
        if write and r['state'] != 'draft':
            raise Problem(409, 'Published revisions are immutable. Create a new revision.')
        return dict(r)

    def revision(self, rid, owner=None):
        with self.connect() as db:
            r = self._revision(db, rid, owner)
            r['reports'] = {x['order_id']: {k:v for k,v in json.loads(x['report']).items() if k!='support_contacts'}
                            for x in db.execute('SELECT order_id,report FROM packs WHERE revision_id=?', (rid,))}
        r['config'] = json.loads(r['config'])
        r['summary'] = json.loads(r['summary']) if r['summary'] else summarize(self.benchmark(r['benchmark_id']), r['reports'])
        return r

    def put_packs(self, owner, rid, packs):
        if len({p.order_id for p in packs}) != len(packs):
            raise Problem(422, 'An order may appear only once in a batch.')
        with self.connect() as db:
            r = self._revision(db, rid, owner, True)
        benchmark = self.benchmark(r['benchmark_id'])
        if not self.evaluation_slots.acquire(blocking=False):
            raise Problem(503, 'Both evaluation slots are busy. Retry this batch shortly.')
        try:
            values = [(p.order_id, canonical(p.model_dump()), canonical(evaluate(benchmark,p))) for p in packs]
        except ValueError as e:
            raise Problem(422, str(e)) from e
        finally:
            self.evaluation_slots.release()
        with self.connect(True) as db:
            self._revision(db, rid, owner, True)
            db.executemany('INSERT INTO packs VALUES (?,?,?,?) ON CONFLICT(revision_id,order_id) DO UPDATE '
                           'SET artifact=excluded.artifact,report=excluded.report', [(rid,*v) for v in values])
            db.execute('UPDATE revisions SET generation=generation+1 WHERE id=?', (rid,))
            db.execute('INSERT INTO events(actor,action,object_id,created) VALUES (?,?,?,?)', (owner,'packs-uploaded',rid,now()))
        return {oid:json.loads(report) for oid, _, report in values}

    def publish(self, owner, rid):
        with self.connect(True) as db:
            r = self._revision(db,rid,owner)
            if r['owner'] != owner:
                raise Problem(404, 'Revision not found.')
            if r['state'] == 'published':
                return {'id': rid,'sha256':r['hash'],'state':'published'}
            packs = db.execute('SELECT * FROM packs WHERE revision_id=? ORDER BY order_id', (rid,)).fetchall()
            if not packs:
                raise Problem(422, 'Upload at least one pack before publishing.')
            # Reports were computed by this evaluator on receipt, not supplied by the client.
            reports = {p['order_id']:json.loads(p['report']) for p in packs}
            if any(v['evaluator_version'] != VERSION for v in reports.values()):
                raise Problem(409, 'Evaluator changed. Revalidate before publishing.')
            bench = self.benchmark(r['benchmark_id'])
            summary = summarize(bench,reports)
            snapshot = {'benchmark_sha256':digest(bench),'strategy_id':r['strategy_id'],'parent_id':r['parent_id'],
                        'notes':r['notes'],'code_revision':r['code_revision'],'model_revision':r['model_revision'],
                        'config':json.loads(r['config']),'evaluator_version':VERSION,
                        'packs':{p['order_id']:digest(json.loads(p['artifact'])) for p in packs}}
            checksum = digest(snapshot)
            db.execute('UPDATE revisions SET state=?,published=?,summary=?,hash=? WHERE id=?',
                       ('published',now(),canonical(summary),checksum,rid))
            db.execute('INSERT INTO events(actor,action,object_id,created) VALUES (?,?,?,?)', (owner,'revision-published',rid,now()))
        return {'id':rid,'state':'published','sha256':checksum}

    def artifact(self,rid,oid,owner=None):
        with self.connect() as db:
            self._revision(db,rid,owner)
            row = db.execute('SELECT artifact FROM packs WHERE revision_id=? AND order_id=?',(rid,oid)).fetchone()
        if not row:
            raise Problem(404,'Pack not found.')
        return json.loads(row['artifact'])

    def mine(self,owner):
        with self.connect() as db:
            strategies = [dict(r) for r in db.execute('SELECT * FROM strategies WHERE owner=? ORDER BY created DESC',(owner,))]
            for s in strategies:
                s['revisions'] = [dict(r) for r in db.execute('SELECT id,number,state,benchmark_id,created FROM revisions WHERE strategy_id=? ORDER BY number DESC',(s['id'],))]
        return strategies

    def leaderboard(self,bid):
        self.benchmark(bid)
        with self.connect() as db:
            entries = [dict(r) for r in db.execute('SELECT r.id,r.strategy_id,r.number,r.published,r.hash,r.summary,s.name,u.display_name '
                       'FROM revisions r JOIN strategies s ON s.id=r.strategy_id JOIN users u ON u.id=s.owner '
                       'WHERE r.benchmark_id=? AND r.state=? ORDER BY r.published DESC',(bid,'published'))]
        for e in entries:
            e['summary'] = json.loads(e['summary'])
        # Only fully completed benchmark revisions receive a compactness rank.
        full = sorted([e for e in entries if e['summary']['completion_fraction']==1],key=lambda e:(e['summary']['lve_complete_mean'],e['published'],e['id']))
        rank = {e['id']:i+1 for i,e in enumerate(full)}
        for e in entries:
            e['rank'] = rank.get(e['id'])
        return sorted(entries,key=lambda e:(e['rank'] or 10**9,-e['summary']['completion_fraction'],e['id']))
