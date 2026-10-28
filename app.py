import json
import os
import sqlite3
from pathlib import Path
import streamlit as st
from dotenv import load_dotenv
from mercado.store import Store
from mercado.content import CATEGORIES, SLOTS
from mercado.engine import enqueue, start_worker, estimate, regenerate
from mercado.downloads import approved, bundle
from mercado.imaging import export_image

load_dotenv()
st.set_page_config(page_title='Mercado AI Studio',page_icon='🛍️',layout='wide')
store=Store(Path(os.getenv('MERCADO_DATA_DIR','data')).resolve())
st.title('Mercado AI Studio')
st.caption('墨西哥美客多 · 商品内容工作台 | 真实商品优先 · 人工审核后导出')
page=st.sidebar.radio('工作区',['商品上传','商品管理','图片生成','任务进度','图片预览审核','标题和详情编辑','批量下载','API 设置','费用统计'])
mode=store.setting('mode','mock')
st.sidebar.info('当前：模拟模式（不调用付费 API）' if mode=='mock' else '当前：真实 API 模式（会产生费用）')
products=store.rows('SELECT id,sku,payload,created FROM products ORDER BY created DESC')
labels={r['id']:r['sku']+' · '+json.loads(r['payload']).get('name','') for r in products}
pricing=store.setting('pricing',{'image_reserve':0.25,'text_reserve':0.05,'budget':20.0,'interval':2.0})


def choose():
    if not products:
        st.info('请先上传商品'); return None
    return st.selectbox('选择商品',list(labels),format_func=labels.get)


def fields(prefix, p=None):
    p=p or {}
    values={}
    for key,label in [('sku','SKU 编号'),('name','商品名称'),('color','颜色'),('material','材质'),('quantity','实际数量'),('package','包装中包含的商品及配件'),('selling_points','主要卖点（真实依据）'),('selling_es','图片07西班牙语卖点（请确认翻译准确）'),('width','实际宽度'),('height','实际高度'),('other','其他已确认参数/深度/适用场景')]:
        values[key]=st.text_input(label,value=str(p.get(key,'')),key=prefix+key)
    values['category']=st.selectbox('商品类别',list(CATEGORIES),index=list(CATEGORIES).index(p.get('category',next(iter(CATEGORIES)))),key=prefix+'category')
    values['unit']=st.selectbox('尺寸单位',['cm','mm'],index=['cm','mm'].index(p.get('unit','cm')),key=prefix+'unit')
    values['title_limit']=st.number_input('已核对的类目标题字符上限',min_value=1,max_value=200,value=int(p.get('title_limit',60)),key=prefix+'limit')
    for key,label in [('truth_confirmed','以上参数与实际商品一致，卖点有依据'),('angle_confirmed','第二张照片为同一商品的其他真实角度'),('policy_confirmed','已核对当前类目主图、分辨率和标题规则（系统不自动获取平台规则）')]:
        values[key]=st.checkbox(label,value=p.get(key,False),key=prefix+key)
    return values


if page=='商品上传':
    st.write('一次录入 1–50 款，每款可上传多张照片。第1张用于主图与局部处理，第2张用于其他角度。')
    st.warning('主图保留原照片背景并等比留白，不自动抠图。请上传干净背景、完整商品照片。尺寸标注方向须与正面照片一致。')
    count=st.number_input('本批商品数量',1,50,1)
    with st.form('upload'):
        entries=[]
        for i in range(count):
            with st.expander(f'商品 {i+1}',expanded=count==1):
                p=fields(f'upload{i}')
                files=st.file_uploader('参考照片（JPG / PNG，最多10张，每张≤20MB）',type=['jpg','jpeg','png'],accept_multiple_files=True,key=f'files{i}')
                entries.append((p,files))
        submitted=st.form_submit_button('保存本批商品')
    if submitted:
        for i,(p,files) in enumerate(entries):
            try:
                if len(files)>10 or any(f.size>20*1024*1024 for f in files): raise ValueError('照片数量或文件大小超限')
                if not p['name']: raise ValueError('请填写商品名称')
                store.add_product(p,[f.getvalue() for f in files]); st.success(f"已保存 {p['sku']}")
            except Exception as e: st.error(f'商品{i+1}保存失败：'+('SKU 已存在' if isinstance(e,sqlite3.IntegrityError) else str(e)))
elif page=='商品管理':
    pid=choose()
    if pid:
        p=store.product(pid)
        st.image(p['refs'],width=180)
        active=store.rows("SELECT id FROM tasks WHERE product_id=? AND status IN ('queued','running','paused','failed')",(pid,))
        with st.form('edit'):
            values=fields('edit',p)
            save=st.form_submit_button('保存参数（已生成内容需重新审核）',disabled=bool(active))
        if save:
            try:
                payload=dict(p,**values); payload.pop('id',None)
                store.execute('UPDATE products SET sku=?,payload=? WHERE id=?',(values['sku'],json.dumps(payload,ensure_ascii=False),pid))
                store.execute('UPDATE assets SET approved=0 WHERE product_id=?',(pid,)); store.execute('UPDATE copy SET approved=0 WHERE product_id=?',(pid,))
                st.success('已保存。参数改变后，请取消旧结果并创建新任务，避免继续使用旧内容。')
            except sqlite3.IntegrityError: st.error('SKU 已存在')
        if active: st.info('有未完成任务时不可修改参数，请先取消任务。')
        replacement=st.file_uploader('补充/替换整组参考照片（第1张主视图、第2张其他角度）',type=['jpg','jpeg','png'],accept_multiple_files=True)
        if st.button('保存新照片并清除旧生成内容',disabled=bool(active) or not replacement):
            try:
                store.replace_references(pid,[f.getvalue() for f in replacement]); st.success('参考照片已更新，请重新核对参数并生成。')
            except Exception as e: st.error(str(e))

        clear=st.checkbox('确认删除该商品的已生成内容和文案（保留参考图、历史与费用）')
        if st.button('清除旧内容以全款重新生成',disabled=bool(active) or not clear):
            store.execute('DELETE FROM assets WHERE product_id=?',(pid,))
            store.execute('DELETE FROM copy WHERE product_id=?',(pid,))
            for path in (store.root/'products'/pid).glob('*.pending.png'): path.unlink()
            st.success('旧内容已清除，可重新排队。')

elif page=='图片生成':
    selected=st.multiselect('选择1–50款商品',list(labels),format_func=labels.get)
    total=sum(estimate(store.product(pid),mode,pricing) for pid in selected)
    st.metric('本批基础费用预估 / USD',f'{total:.2f}')
    st.caption('预估包括3次场景编辑和5次文本/视觉请求。重试另计；本地5张处理不收API费。预估不是报价或实际账单。')
    consent=st.checkbox('我已检查商品资料，理解预估与实际费用的区别，并同意按当前模式生成')
    if st.button('开始生成',disabled=not consent):
        if not 1<=len(selected)<=50: st.error('请选择1–50款商品')
        else:
            for pid in selected:
                try:
                    if store.rows('SELECT * FROM assets WHERE product_id=?',(pid,)):
                        raise ValueError('已有生成记录，请使用单图重生成；或在管理页清除旧内容后生成')
                    enqueue(store,pid,mode); st.success(labels[pid]+' 已排队')
                except Exception as e: st.error(labels[pid]+'：'+('已有未完成任务' if isinstance(e,sqlite3.IntegrityError) else str(e)))
            start_worker(store)
elif page=='任务进度':
    st.caption('暂停在当前API请求结束后生效。关闭应用会停止后台进程；重启后点击继续队列。任务与已完成图片保存在SQLite和磁盘。')
    if st.button('继续队列 / 恢复运行中的任务'): start_worker(store)
    if st.button('刷新进度'): st.rerun()
    for t in store.rows('SELECT * FROM tasks ORDER BY created DESC LIMIT 200'):
        with st.expander(f"{labels.get(t['product_id'],t['product_id'])} | {t['status']} | {t['step']}/10"):
            st.progress(min(t['step']/10,1.0))
            if t['error']: st.error(t['error'])
            a,b,c=st.columns(3)
            if a.button('暂停',key=t['id']+'pause',disabled=t['status'] not in ['queued','running']):
                store.execute("UPDATE tasks SET status='paused' WHERE id=?",(t['id'],)); st.rerun()
            if b.button('继续 / 失败重试',key=t['id']+'resume',disabled=t['status'] not in ['paused','failed']):
                store.execute("UPDATE tasks SET status='queued',error='' WHERE id=?",(t['id'],)); start_worker(store); st.rerun()
            if c.button('取消',key=t['id']+'cancel',disabled=t['status'] in ['review','cancelled','running']):
                store.execute("UPDATE tasks SET status='cancelled' WHERE id=?",(t['id'],)); st.rerun()
            st.dataframe(store.rows('SELECT created,message FROM logs WHERE task_id=? ORDER BY created',(t['id'],)),hide_index=True)
elif page=='图片预览审核':
    pid=choose()
    if pid:
        st.warning('AI 审核仅供参考。逐张确认颜色、数量、结构、配件、尺寸、文字及类目要求。AI场景无法保证完全一致。')
        for a in store.rows('SELECT * FROM assets WHERE product_id=? ORDER BY slot',(pid,)):
            with st.expander(f"{a['slot']:02} · {SLOTS[a['slot']-1]}",expanded=True):
                st.image(a['path'],width=420); st.caption(a['note'])
                checked=st.checkbox('人工审核通过',value=bool(a['approved']),key=f"approve{pid}{a['slot']}")
                if checked!=bool(a['approved']): store.execute('UPDATE assets SET approved=? WHERE product_id=? AND slot=?',(int(checked),pid,a['slot']))
                if checked: st.download_button('下载该图 JPG 600',export_image(a['path']),file_name=f"{a['slot']:02}.jpg",key=f"dl{a['slot']}")
                st.caption(f"单图重生成预估 USD {(pricing['image_reserve']+pricing['text_reserve']) if mode=='live' and a['slot'] in (2,3,4) else 0:.2f}")
                confirm=st.checkbox('确认按当前模式重新生成该图',key=f"regenconfirm{a['slot']}")
                if st.button('重新生成该图',key=f"regen{a['slot']}",disabled=not confirm):
                    try: regenerate(store,pid,a['slot'],mode); start_worker(store); st.rerun()
                    except Exception as e: st.error(str(e))
elif page=='标题和详情编辑':
    pid=choose()
    if pid:
        rows=store.rows('SELECT * FROM copy WHERE product_id=?',(pid,))
        if not rows: st.info('请先生成文案')
        else:
            copy=rows[0]
            with st.form('copy'):
                title=st.text_input('墨西哥西班牙语标题',value=copy['title'])
                description=st.text_area('商品详情',value=copy['description'],height=420)
                ok=st.checkbox('确认西班牙语准确、所有描述有依据并通过人工审核',value=bool(copy['approved']))
                if st.form_submit_button('保存文案和审核状态'):
                    if not title.strip() or not description.strip(): st.error('标题和详情不能为空')
                    elif len(title)>store.product(pid).get('title_limit',60): st.error('标题超过设定上限')
                    else:
                        store.execute('UPDATE copy SET title=?,description=?,approved=? WHERE product_id=?',(title,description,int(ok),pid)); st.success('已保存')
elif page=='批量下载':
    ready=[pid for pid in labels if approved(store,pid)]
    selected=st.multiselect('审核完成的商品（选择一款或多款）',ready,format_func=labels.get)
    size=st.selectbox('导出分辨率',[600,1200]); fmt=st.selectbox('图片格式',['JPG','PNG'])
    st.caption('1200导出可能包含对1024场景图的等比放大，不代表新增真实细节。导出前请核对平台类目最低分辨率。')
    if st.button('制作 ZIP',disabled=not selected):
        st.download_button('下载 ZIP',bundle(store,selected,size,fmt),file_name='mercado_products.zip',mime='application/zip')
elif page=='API 设置':
    st.write('API Key 仅从环境变量 OPENAI_API_KEY 或本机 .env 读取。此页面不接收、显示或保存密钥。')
    st.write('密钥状态：'+('已配置' if os.getenv('OPENAI_API_KEY') else '未配置'))
    st.caption('文本模型：'+os.getenv('OPENAI_TEXT_MODEL','gpt-4.1-mini')+'；图片模型：'+os.getenv('OPENAI_IMAGE_MODEL','gpt-image-1'))
    with st.form('settings'):
        new_mode=st.selectbox('运行模式',['mock','live'],index=0 if mode=='mock' else 1)
        st.warning('以下金额为自行设置的单次预留上限，不是官方价格。请按模型最新定价设置保守额度；实际美元费用需从供应商账单核对。')
        image=st.number_input('每次图片请求预留 USD',min_value=0.01,value=float(pricing['image_reserve']))
        text=st.number_input('每次文本/视觉请求预留 USD',min_value=0.01,value=float(pricing['text_reserve']))
        budget=st.number_input('每日预算 USD（UTC日界）',min_value=0.01,value=float(pricing['budget']))
        interval=st.number_input('请求间隔秒（串行并发=1）',min_value=0.0,value=float(pricing['interval']))
        if st.form_submit_button('保存设置'):
            store.set_setting('mode',new_mode); store.set_setting('pricing',dict(image_reserve=image,text_reserve=text,budget=budget,interval=interval)); st.rerun()
    st.info('请同时在 OpenAI 账户设置消费限制。应用预算按预留/已核对费用计算；API未提供美元账单时不声称精确计费。')
elif page=='费用统计':
    rows=store.rows('SELECT * FROM costs ORDER BY day DESC')
    st.metric('已核对实际费用 USD',f"{sum(r['actual'] or 0 for r in rows):.4f}")
    st.metric('未核对预留 USD',f"{sum(r['estimate'] for r in rows if r['actual'] is None):.4f}")
    st.dataframe(rows,hide_index=True)
    st.caption('estimate=预留估算，actual=人工按供应商账单核对的实际金额，usage=API原始用量。超时请求可能已收费，预留不会自动释放。模拟不产生费用记录。')
    if rows:
        cid=st.selectbox('选择一条请求对账',[r['id'] for r in rows])
        actual=st.number_input('供应商账单确认金额 USD',min_value=0.0,step=0.001,format='%.4f')
        if st.button('确认实际费用'):
            store.execute("UPDATE costs SET actual=?,status='reconciled' WHERE id=?",(actual,cid)); st.rerun()
