import io
import pytest
from PIL import Image
from mercado.store import Store


def photo():
    b=io.BytesIO(); Image.new('RGB',(100,120),'blue').save(b,format='PNG'); return b.getvalue()


def test_upload_and_duplicate(tmp_path):
    s=Store(tmp_path)
    pid=s.add_product({'sku':'../../sku','name':'架子'},[photo()])
    assert s.product(pid)['sku']=='../../sku'
    assert str(tmp_path) in s.product(pid)['refs'][0]
    with pytest.raises(Exception): s.add_product({'sku':'../../sku'},[photo()])
    assert len(s.rows('SELECT * FROM products'))==1


def test_budget_and_queue(tmp_path):
    s=Store(tmp_path); p=s.add_product({'sku':'A'},[photo()]); s.enqueue(p)
    with pytest.raises(Exception): s.enqueue(p)
    s.reserve(p,0.6,1)
    with pytest.raises(ValueError): s.reserve(p,0.6,1)


def test_replace_references(prepared):
    s,pid=prepared; original=s.product(pid)['refs']
    s.replace_references(pid,[photo(),photo()])
    assert s.product(pid)['refs']!=original
    s.enqueue(pid)
    with pytest.raises(ValueError):s.replace_references(pid,[photo()])
