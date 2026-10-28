import io
import pytest
from PIL import Image
from mercado.store import Store


@pytest.fixture
def prepared(tmp_path):
    s=Store(tmp_path)
    def image(color):
        b=io.BytesIO(); Image.new('RGB',(300,450),color).save(b,format='PNG'); return b.getvalue()
    p={'sku':'MX001','name':'Organizador','category':'厨房置物架','color':'Azul','material':'Acero',
       'quantity':'1','package':'1 organizador','selling_points':'Organización','selling_es':'Organización para la cocina',
       'width':'30','height':'45','unit':'cm','title_limit':60,'truth_confirmed':True,'angle_confirmed':True,'policy_confirmed':True}
    pid=s.add_product(p,[image('blue'),image('navy')])
    return s,pid
