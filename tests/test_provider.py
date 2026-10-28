from types import SimpleNamespace
import base64
import io
import json
from PIL import Image
from mercado.content import Provider


def test_live_adapter_request_contract(prepared,tmp_path,monkeypatch):
    from openai import OpenAI
    calls=[]
    def chat(**kwargs):
        calls.append(('chat',kwargs))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({'summary':'matched','issues':[]})))],usage=SimpleNamespace(model_dump=lambda:{'total_tokens':123}))
    b=io.BytesIO();Image.new('RGB',(1024,1024)).save(b,format='PNG')
    def edit(**kwargs):
        assert all(not f.closed for f in kwargs['image'])
        calls.append(('image',kwargs))
        return SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(b.getvalue()).decode())],usage=SimpleNamespace(model_dump=lambda:{'total_tokens':456}))
    # Fake SDK only: no credential, network request or bill.
    monkeypatch.setenv('OPENAI_API_KEY','test-placeholder')
    monkeypatch.setattr('openai.OpenAI',lambda **kwargs:SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=chat)),images=SimpleNamespace(edit=edit)))
    provider=Provider('live');s,pid=prepared;p=s.product(pid)
    result,usage=provider.identify(p)
    assert result['issues']==[] and usage['total_tokens']==123
    out=tmp_path/'live.png';assert provider.scene(p,2,out)['total_tokens']==456
    with Image.open(out) as im: assert im.size==(1024,1024)
    assert calls[0][1]['response_format']=={'type':'json_object'}
    assert calls[1][1]['size']=='1024x1024'
    assert len(calls[1][1]['image'])==2


def test_sdk_supports_used_image_parameters():
    import inspect
    from openai.resources.images import Images
    params=inspect.signature(Images.edit).parameters
    assert {'image','prompt','model','size','quality','n'} <= set(params)
