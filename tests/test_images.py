import io
import pytest
from PIL import Image
from mercado.imaging import render,export_image
from mercado.content import Provider,validate


def test_eight_images(prepared,tmp_path):
    s,pid=prepared; p=s.product(pid); validate(p)
    for slot in range(1,9):
        output=tmp_path/f'{slot}.png'
        if slot in (2,3,4): Provider('mock').scene(p,slot,output)
        else: render(p,slot,output)
        for size in (600,1200):
            for fmt in ('JPG','PNG'):
                data=export_image(output,size,fmt)
                with Image.open(io.BytesIO(data)) as im: assert im.size==(size,size)


def test_missing_angle_or_size(prepared):
    s,pid=prepared; p=s.product(pid)
    for key,value in [('refs',p['refs'][:1]),('width',''),('height','-1'),('angle_confirmed',False)]:
        with pytest.raises(ValueError): validate(dict(p,**{key:value}))
