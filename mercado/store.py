import json
import sqlite3
import uuid
from pathlib import Path
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS products(id TEXT PRIMARY KEY, sku TEXT UNIQUE, payload TEXT, created TEXT);
            CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, product_id TEXT, status TEXT, step INTEGER DEFAULT 0, error TEXT DEFAULT '', created TEXT);
            CREATE UNIQUE INDEX IF NOT EXISTS active_product ON tasks(product_id) WHERE status IN ('queued','running','paused','failed');
            CREATE TABLE IF NOT EXISTS assets(product_id TEXT, slot INTEGER, path TEXT, approved INTEGER DEFAULT 0, note TEXT DEFAULT '', PRIMARY KEY(product_id,slot));
            CREATE TABLE IF NOT EXISTS copy(product_id TEXT PRIMARY KEY,title TEXT,description TEXT,approved INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS costs(id TEXT PRIMARY KEY, product_id TEXT, day TEXT, estimate REAL, actual REAL, status TEXT, usage TEXT);
            CREATE TABLE IF NOT EXISTS logs(created TEXT, task_id TEXT, message TEXT);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
            ''')

    def connect(self):
        c = sqlite3.connect(self.root / 'studio.db', timeout=30)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA busy_timeout=30000')
        return c

    def rows(self, sql, params=()):
        with self.connect() as c:
            return [dict(r) for r in c.execute(sql, params)]

    def execute(self, sql, params=()):
        with self.connect() as c:
            return c.execute(sql, params).rowcount

    def setting(self, key, default):
        rows = self.rows('SELECT value FROM settings WHERE key=?', (key,))
        return json.loads(rows[0]['value']) if rows else default

    def set_setting(self, key, value):
        self.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, json.dumps(value)))

    def add_product(self, payload, images):
        sku = payload['sku'].strip()
        if not sku or len(sku) > 100:
            raise ValueError('SKU 不能为空且最多100字符')
        if not images:
            raise ValueError('请上传商品参考图片')
        pid = uuid.uuid4().hex
        # Never use user-controlled SKU as a filesystem path.
        folder = self.root / 'products' / pid
        folder.mkdir(parents=True)
        from PIL import Image, ImageOps
        refs = []
        try:
            for i, raw in enumerate(images):
                import io
                with Image.open(io.BytesIO(raw)) as im:
                    if im.width * im.height > 40_000_000:
                        raise ValueError('单图不得超过4000万像素')
                    im = ImageOps.exif_transpose(im).convert('RGB')
                    im.thumbnail((2048, 2048))
                    path = folder / f'reference_{i}.png'
                    im.save(path)
                    refs.append(str(path.resolve()))
            payload = dict(payload, sku=sku, refs=refs)
            self.execute('INSERT INTO products VALUES (?,?,?,?)', (pid, sku, json.dumps(payload, ensure_ascii=False), now()))
        except Exception:
            import shutil
            shutil.rmtree(folder)
            raise
        return pid

    def replace_references(self, pid, images):
        if not 1 <= len(images) <= 10 or any(len(raw)>20*1024*1024 for raw in images):
            raise ValueError('请上传1–10张照片，每张不超过20MB')
        if self.rows("SELECT id FROM tasks WHERE product_id=? AND status IN ('queued','running','paused','failed')", (pid,)):
            raise ValueError('请先完成或取消现有任务')
        from PIL import Image, ImageOps
        import io
        import shutil
        folder = self.root/'products'/pid/('refs_'+uuid.uuid4().hex)
        folder.mkdir(parents=True)
        refs=[]
        try:
            for i,raw in enumerate(images):
                with Image.open(io.BytesIO(raw)) as im:
                    if im.width*im.height>40_000_000: raise ValueError('单图不得超过4000万像素')
                    im=ImageOps.exif_transpose(im).convert('RGB'); im.thumbnail((2048,2048))
                    path=folder/f'reference_{i}.png'; im.save(path); refs.append(str(path.resolve()))
            p=self.product(pid); p.pop('id'); p['refs']=refs
            with self.connect() as c:
                c.execute('UPDATE products SET payload=? WHERE id=?',(json.dumps(p,ensure_ascii=False),pid))
                c.execute('DELETE FROM assets WHERE product_id=?',(pid,))
                c.execute('DELETE FROM copy WHERE product_id=?',(pid,))
            for path in (self.root/'products'/pid).glob('*.pending.png'): path.unlink()
        except Exception:
            shutil.rmtree(folder)
            raise

    def product(self, pid):
        row = self.rows('SELECT * FROM products WHERE id=?', (pid,))[0]
        return dict(json.loads(row['payload']), id=pid)

    def enqueue(self, pid, mode="mock", step=0):
        tid = uuid.uuid4().hex
        with self.connect() as c:
            c.execute('INSERT INTO settings VALUES (?,?)', ('task_mode_'+tid, json.dumps(mode)))
            c.execute('INSERT INTO tasks(id,product_id,status,step,created) VALUES (?,?,?,?,?)', (tid, pid, 'queued', step, now()))
        return tid

    def log(self, tid, message):
        self.execute('INSERT INTO logs VALUES (?,?,?)', (now(), tid, message))

    def reserve(self, pid, estimate, budget):
        day = now()[:10]
        cid = uuid.uuid4().hex
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            total = c.execute("SELECT COALESCE(SUM(COALESCE(actual,estimate)),0) FROM costs WHERE day=? AND status!='released'", (day,)).fetchone()[0]
            if total + estimate > budget:
                raise ValueError('今日预算不足，请调整预算或明日重试')
            c.execute('INSERT INTO costs VALUES (?,?,?,?,?,?,?)', (cid, pid, day, estimate, None, 'reserved', '{}'))
        return cid
