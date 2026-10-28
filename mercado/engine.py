import json
import threading
import time
from pathlib import Path
from .content import Provider, validate
from .imaging import render

_THREADS = {}
_LOCK = threading.Lock()


def estimate(p, mode, settings):
    return 0.0 if mode=='mock' else 3*settings['image_reserve']+5*settings['text_reserve']


def paid(store, p, mode, kind, fn):
    if mode=='mock': return fn()
    cfg=store.setting('pricing',{'image_reserve':0.25,'text_reserve':0.05,'budget':20.0,'interval':2.0})
    reserve=cfg['image_reserve' if kind=='image' else 'text_reserve']
    cid=store.reserve(p['id'],reserve,cfg['budget'])
    try:
        result=fn()
        usage=result[1] if isinstance(result,tuple) else result
        store.execute('UPDATE costs SET status=?,usage=? WHERE id=?',('recorded',json.dumps(usage),cid))
        return result
    except Exception:
        # Charge may have happened before timeout; retain reservation conservatively.
        store.execute('UPDATE costs SET status=? WHERE id=?',('uncertain',cid))
        raise
    finally:
        time.sleep(max(0,float(cfg['interval'])))


def process_step(store, task, provider):
    p=store.product(task['product_id']); validate(p)
    step=task['step']; tid=task['id']; mode=provider.mode
    folder=store.root/'products'/p['id']; folder.mkdir(parents=True,exist_ok=True)
    if step==0:
        result,_=paid(store,p,mode,'text',lambda:provider.identify(p))
        store.log(tid, json.dumps(result,ensure_ascii=False))
        if result.get('issues'): raise ValueError('商品资料待确认：'+'；'.join(result['issues']))
    elif step==1:
        copy,usage=paid(store,p,mode,'text',lambda:provider.copy(p))
        if not copy.get('title') or not copy.get('description'): raise ValueError('文案响应缺失字段')
        if len(copy['title'])>int(p.get('title_limit',60)): raise ValueError('标题超出类目长度限制，请调整后重试')
        store.execute('INSERT OR REPLACE INTO copy VALUES (?,?,?,0)',(p['id'],copy['title'],copy['description']))
    else:
        slot=step-1
        existing=store.rows('SELECT * FROM assets WHERE product_id=? AND slot=?',(p['id'],slot))
        if existing and Path(existing[0]['path']).exists(): return
        path=folder/f'{slot:02}.png'
        note='原图处理；需要人工确认商品和类目合规'
        if slot in (2,3,4):
            # Persist generated output before advisory audit, so audit failure never regenerates paid image.
            pending=folder/f'{slot:02}.pending.png'
            if not pending.exists(): paid(store,p,mode,'image',lambda:provider.scene(p,slot,pending))
            audit,_=paid(store,p,mode,'text',lambda:provider.audit(p,pending))
            note=json.dumps(audit,ensure_ascii=False)
            pending.replace(path)
        else: render(p,slot,path)
        if mode=='mock': note='模拟输出，禁止直接上架；'+note
        store.execute('INSERT OR REPLACE INTO assets VALUES (?,?,?,0,?)',(p['id'],slot,str(path.resolve()),note))


def tick(store):
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute("SELECT * FROM tasks WHERE status IN ('running','queued') ORDER BY created LIMIT 1").fetchone()
        if not row: return False
        task=dict(row)
        c.execute("UPDATE tasks SET status='running' WHERE id=? AND status='queued'",(task['id'],))
    try:
        # Mode is snapshotted per queued task, not read from mutable UI configuration.
        mode=store.setting('task_mode_'+task['id'],'mock')
        provider=Provider(mode)
        process_step(store,task,provider)
        store.execute("UPDATE tasks SET step=step+1,status=CASE WHEN step>=9 THEN 'review' WHEN status IN ('paused','cancelled') THEN status ELSE 'running' END,error='' WHERE id=?",(task['id'],))
        store.log(task['id'],f"完成步骤 {task['step']+1}/10")
    except Exception as e:
        # Avoid logging API exception strings that may echo request content or credentials.
        message=str(e) if isinstance(e,ValueError) else f'{type(e).__name__}：请求失败，请检查网络、API权限或服务状态；可手动重试。'
        store.execute("UPDATE tasks SET status='failed',error=? WHERE id=?",(message,task['id']))
        store.log(task['id'],message)
    return True


def start_worker(store):
    key=str(store.root.resolve())
    with _LOCK:
        if key in _THREADS and _THREADS[key].is_alive(): return
        def run():
            # Cross-process lock prevents overlapping paid calls across duplicate app instances.
            from filelock import FileLock, Timeout
            try:
                with FileLock(str(store.root/'worker.lock'), timeout=0):
                    while True:
                        if not tick(store): time.sleep(0.5)
            except Timeout:
                return
        thread=threading.Thread(target=run,daemon=True)
        _THREADS[key]=thread; thread.start()


def enqueue(store,pid,mode):
    validate(store.product(pid))
    if mode=='live': Provider(mode)  # Check credential presence before queueing.
    tid=store.enqueue(pid,mode)
    return tid


def regenerate(store,pid,slot,mode):
    active=store.rows("SELECT id FROM tasks WHERE product_id=? AND status IN ('queued','running','paused','failed')",(pid,))
    if active: raise ValueError('请先完成、取消或恢复该商品现有任务')
    p=store.product(pid); validate(p)
    if mode=='live': Provider(mode)
    store.execute('DELETE FROM assets WHERE product_id=? AND slot=?',(pid,slot))
    (store.root/'products'/pid/f'{slot:02}.pending.png').unlink(missing_ok=True)
    tid=store.enqueue(pid,mode,slot+1)
    # Subsequent slots hit cache. Copy is preserved.
    return tid
