from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_all_pages(tmp_path,monkeypatch):
    monkeypatch.setenv('MERCADO_DATA_DIR',str(tmp_path))
    at=AppTest.from_file(Path(__file__).resolve().parents[1]/'app.py').run(timeout=30)
    assert not at.exception
    for page in ['商品管理','图片生成','任务进度','图片预览审核','标题和详情编辑','批量下载','API 设置','费用统计']:
        at.sidebar.radio[0].set_value(page).run(timeout=30)
        assert not at.exception, page


def test_populated_pages(prepared,monkeypatch):
    from mercado.engine import enqueue,tick
    s,pid=prepared;enqueue(s,pid,'mock')
    while tick(s): pass
    monkeypatch.setenv('MERCADO_DATA_DIR',str(s.root))
    at=AppTest.from_file(Path(__file__).resolve().parents[1]/'app.py').run(timeout=30)
    for page in ['商品管理','图片生成','任务进度','图片预览审核','标题和详情编辑','批量下载','费用统计']:
        at.sidebar.radio[0].set_value(page).run(timeout=30)
        assert not at.exception,page
