import io
import json
import re
import zipfile
from .imaging import export_image


def approved(store,pid):
    assets=store.rows('SELECT * FROM assets WHERE product_id=?',(pid,))
    copy=store.rows('SELECT * FROM copy WHERE product_id=?',(pid,))
    return len(assets)==8 and all(a['approved'] for a in assets) and bool(copy and copy[0]['approved'])


def bundle(store,pids,size=600,fmt='JPG'):
    if not pids: raise ValueError('请选择商品')
    if any(not approved(store,pid) for pid in pids): raise ValueError('所有8张图片及文案审核通过后才能下载')
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
        for pid in pids:
            p=store.product(pid)
            sku=re.sub(r'[^\w-]','_',p['sku'])[:70] or 'SKU'
            folder=f'{sku}_{pid[:8]}'
            for a in store.rows('SELECT * FROM assets WHERE product_id=? ORDER BY slot',(pid,)):
                z.writestr(f"{folder}/{a['slot']:02}.{fmt.lower()}",export_image(a['path'],size,fmt))
            copy=store.rows('SELECT * FROM copy WHERE product_id=?',(pid,))[0]
            z.writestr(f'{folder}/titulo.txt',copy['title'])
            z.writestr(f'{folder}/descripcion.txt',copy['description'])
            z.writestr(f'{folder}/manifest.json',json.dumps({'sku':p['sku'],'size':size,'mock':any('模拟' in a['note'] for a in store.rows('SELECT note FROM assets WHERE product_id=?',(pid,)))},ensure_ascii=False))
    return b.getvalue()
