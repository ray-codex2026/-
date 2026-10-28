import base64
import json
import os
import math
from pathlib import Path

CATEGORIES = {
    '厨房置物架': ('storage', 'Cocina mexicana luminosa, encimera ordenada', 'Comedor y despensa'),
    '微波炉架': ('storage', 'Cocina doméstica, área de preparación', 'Despensa organizada'),
    '家用收纳架': ('storage', 'Sala de hogar mexicano contemporáneo', 'Área de organización doméstica'),
    '家具配件': ('storage', 'Entorno de mueble compatible confirmado', 'Mesa de trabajo doméstica'),
    '儿童牛仔裤': ('clothing', 'Prenda sobre superficie de dormitorio infantil', 'Composición de ropa sin modelo humano'),
    '童装裤子': ('clothing', 'Prenda en dormitorio infantil', 'Ropa sobre mesa de preparación'),
    '童装上衣': ('clothing', 'Prenda en habitación infantil luminosa', 'Perchero sin accesorios añadidos al producto'),
    '儿童套装': ('clothing', 'Conjunto completo en dormitorio infantil', 'Composición plana de las prendas incluidas'),
    '厨房收纳产品': ('kitchen', 'Cocina mexicana limpia y luminosa', 'Despensa doméstica'),
    '小家电支架': ('kitchen', 'Cocina doméstica sin electrodomésticos no confirmados', 'Área de organización en cocina'),
    '日常厨房配件': ('kitchen', 'Cocina doméstica contemporánea', 'Mesa de preparación de alimentos'),
}
SLOTS = ['主图','家庭使用场景','第二使用场景','第三使用场景','尺寸图','细节图','卖点图','其他真实角度']
POLICY = '''Use only supplied photographs and confirmed user facts. Never infer hidden geometry, dimensions,
quantity, material, accessories, certification, load rating, brand or performance. Preserve exact product
color, silhouette, structure and proportions. Missing information must be flagged, never invented.
All listing copy must be natural Mexican Spanish. Return JSON only. No markdown.'''


def validate(p):
    required = ['name','category','color','material','quantity','package','selling_points','selling_es','width','height','unit']
    missing = [x for x in required if not str(p.get(x, '')).strip()]
    for key in ['width','height']:
        try:
            if not math.isfinite(float(p.get(key, 0))) or float(p.get(key, 0)) <= 0: missing.append(key)
        except (ValueError, TypeError): missing.append(key)
    if p.get('unit') not in ['cm','mm']: missing.append('unit')
    if p.get('category') not in CATEGORIES: missing.append('category')
    if len(p.get('refs', [])) < 2 or not p.get('angle_confirmed'):
        missing.append('至少两张照片，并确认第二张为不同真实角度')
    if not p.get('truth_confirmed'): missing.append('真实参数确认')
    if not p.get('policy_confirmed'): missing.append('已核对该类目图片规则与标题长度')
    if missing: raise ValueError('请补充/确认：' + '、'.join(dict.fromkeys(missing)))


def data_url(path):
    return 'data:image/png;base64,' + base64.b64encode(Path(path).read_bytes()).decode()


class Provider:
    def __init__(self, mode):
        self.mode = mode
        if mode == 'live':
            from openai import OpenAI
            if not os.getenv('OPENAI_API_KEY'): raise ValueError('未配置 OPENAI_API_KEY 环境变量')
            # No implicit SDK retries: an ambiguous timeout may already have incurred a charge.
            self.client = OpenAI(timeout=180, max_retries=0)

    def json_call(self, prompt, refs):
        response = self.client.chat.completions.create(
            model=os.getenv('OPENAI_TEXT_MODEL','gpt-4.1-mini'),
            response_format={'type':'json_object'},
            messages=[{'role':'system','content':POLICY}, {'role':'user','content':
                [{'type':'text','text':prompt}] + [{'type':'image_url','image_url':{'url':data_url(r)}} for r in refs]}])
        return json.loads(response.choices[0].message.content), response.usage.model_dump()

    def identify(self, p):
        if self.mode == 'mock': return {'summary':'模拟识别：仅使用输入参数','issues':[]}, {'mock':True}
        facts = {k:v for k,v in p.items() if k not in ['refs','id']}
        return self.json_call('Check reference photos against these user facts: '+json.dumps(facts,ensure_ascii=False)+
            '. Return {"summary":"Chinese concise identification", "issues":["Chinese conflicts or insufficient visible evidence"]}. '
            'Do not assert that unobservable properties are verified. Flag incompatible photos and any clearly conflicting facts.', p['refs'])

    def copy(self, p):
        if self.mode == 'mock':
            title = f"{p['name']} {p['color']}"[:int(p.get('title_limit',60))]
            # Mock deliberately marks itself, and does not pretend to translate arbitrary Chinese facts.
            desc = ('Descripción del producto\nContenido de demostración; sustituir por texto revisado en español.\n\n'
                    'Características principales\nConsultar los datos confirmados.\n\nEspecificaciones\n'
                    f"Ancho: {p['width']} {p['unit']}; Alto: {p['height']} {p['unit']}\n\n"
                    'Contenido del paquete\nPendiente de revisión humana.\n\nRecomendaciones de uso\nSeguir las instrucciones del fabricante.')
            return {'title':title,'description':desc}, {'mock':True}
        facts = {k:v for k,v in p.items() if k not in ['refs','id']}
        return self.json_call('Generate {"title":"...","description":"..."} in Mexican Spanish using only '+
            json.dumps(facts,ensure_ascii=False)+f". Title at most {p.get('title_limit',60)} characters. "
            'Description sections: Descripción del producto, Características principales, Especificaciones, '
            'Contenido del paquete, Recomendaciones de uso. Translate confirmed facts. Omit unsupported advice and claims.', p['refs'])

    def scene(self, p, slot, output):
        from PIL import Image, ImageOps, ImageDraw
        if self.mode == 'mock':
            im=ImageOps.pad(Image.open(p['refs'][0]).convert('RGB'),(1024,1024),color='#e8e2d7')
            ImageDraw.Draw(im).text((20,20),f'MOCK - scene {slot}', fill='red')
            im.save(output)
            return {'mock':True}
        _, first, second = CATEGORIES[p['category']]
        scene = {2:first,3:second,4:'Tercera composición editorial en un espacio doméstico adecuado; diferente a las anteriores'}[slot]
        prompt = POLICY + '\nEdit the supplied product into this scene: '+scene+'\nConfirmed facts: '+json.dumps(
            {k:v for k,v in p.items() if k not in ['refs','id']}, ensure_ascii=False)+ \
            '\nNo text. Background props must not imply included accessories or unconfirmed functions. No hidden or invented product view.'
        from contextlib import ExitStack
        with ExitStack() as stack:
            files=[stack.enter_context(open(r,'rb')) for r in p['refs']]
            result=self.client.images.edit(model=os.getenv('OPENAI_IMAGE_MODEL','gpt-image-1'),
                image=files,prompt=prompt,size='1024x1024',quality='medium',n=1)
        if not result.data[0].b64_json: raise ValueError('API 未返回图片数据')
        Path(output).write_bytes(base64.b64decode(result.data[0].b64_json))
        usage=getattr(result,'usage',None)
        return usage.model_dump() if usage else {'usage_unavailable':True}

    def audit(self, p, path):
        if self.mode == 'mock': return {'issues':['模拟图片，不能作为真实生成结果上架'],'mock':True}, {'mock':True}
        return self.json_call('Compare last image (generated) with earlier references. Return '
            '{"issues":["Chinese description of any changed color, geometry, quantity, accessories, or uncertainty"]}. '
            'This is advisory; human review is mandatory.', p['refs']+[str(path)])
