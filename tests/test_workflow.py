import io
import zipfile
import pytest
from mercado.engine import enqueue,tick,regenerate,paid
from mercado.downloads import bundle,approved


def finish(s):
    for _ in range(30):
        if not tick(s): return
    raise AssertionError('queue did not drain')


def test_complete_review_download_regenerate(prepared):
    s,pid=prepared; tid=enqueue(s,pid,'mock'); finish(s)
    assert s.rows('SELECT status FROM tasks')[0]['status']=='review'
    assert len(s.rows('SELECT * FROM assets'))==8
    assert not s.rows('SELECT * FROM costs')
    with pytest.raises(ValueError): bundle(s,[pid])
    s.execute('UPDATE assets SET approved=1'); s.execute('UPDATE copy SET approved=1')
    assert approved(s,pid)
    with zipfile.ZipFile(io.BytesIO(bundle(s,[pid]))) as z:
        assert len(z.namelist())==11
        assert sum(x.endswith('.jpg') for x in z.namelist())==8
    old=s.rows('SELECT * FROM assets WHERE slot=1')[0]
    regenerate(s,pid,2,'mock'); finish(s)
    assert s.rows('SELECT * FROM assets WHERE slot=1')[0]==old
    assert not approved(s,pid)


def test_pause_resume_and_failure(prepared):
    s,pid=prepared; tid=enqueue(s,pid,'mock')
    s.execute("UPDATE tasks SET status='paused'")
    assert not tick(s)
    s.execute("UPDATE tasks SET status='queued'"); tick(s)
    p=s.product(pid)
    import json
    p['width']=''
    s.execute('UPDATE products SET payload=?',(json.dumps(p),)); tick(s)
    assert s.rows('SELECT status FROM tasks')[0]['status']=='failed'
    p['width']='30';s.execute('UPDATE products SET payload=?',(json.dumps(p),))
    s.execute("UPDATE tasks SET status='queued'");finish(s)
    assert s.rows('SELECT status FROM tasks')[0]['status']=='review'


def test_ambiguous_cost_retained(prepared):
    s,pid=prepared
    s.set_setting('pricing',dict(image_reserve=.5,text_reserve=.1,budget=.6,interval=0))
    def timeout(): raise TimeoutError()
    with pytest.raises(TimeoutError): paid(s,s.product(pid),'live','image',timeout)
    assert s.rows('SELECT status FROM costs')[0]['status']=='uncertain'
    with pytest.raises(ValueError): paid(s,s.product(pid),'live','image',lambda:{})


def test_pending_scene_cached_after_audit_failure(prepared,monkeypatch):
    from mercado.content import Provider
    s,pid=prepared; enqueue(s,pid,'mock')
    tick(s);tick(s);tick(s)
    original=Provider.audit
    monkeypatch.setattr(Provider,'audit',lambda *a: (_ for _ in ()).throw(ValueError('audit failure')))
    tick(s)
    assert s.rows('SELECT status FROM tasks')[0]['status']=='failed'
    monkeypatch.setattr(Provider,'audit',original)
    monkeypatch.setattr(Provider,'scene',lambda *a: (_ for _ in ()).throw(AssertionError('must use cache')))
    s.execute("UPDATE tasks SET status='queued'");tick(s)
    assert s.rows('SELECT step FROM tasks')[0]['step']==4
