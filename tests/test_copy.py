from mercado.content import Provider
from mercado.engine import enqueue,tick


def test_copy_sections(prepared):
    s,pid=prepared
    result,usage=Provider('mock').copy(s.product(pid))
    assert len(result['title'])<=60
    for section in ['Descripción del producto','Características principales','Especificaciones','Contenido del paquete','Recomendaciones de uso']:
        assert section in result['description']
    assert usage['mock']


def test_copy_persisted_before_images(prepared):
    s,pid=prepared; enqueue(s,pid,'mock')
    tick(s); tick(s)
    row=s.rows('SELECT * FROM copy')[0]
    assert row['approved']==0 and row['title']
    assert not s.rows('SELECT * FROM assets')
