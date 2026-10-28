from pathlib import Path
from PIL import Image, ImageOps, ImageDraw, ImageFont


def font(size):
    for candidate in ['C:/Windows/Fonts/arial.ttf','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']:
        if Path(candidate).exists(): return ImageFont.truetype(candidate,size)
    return ImageFont.load_default(size=size)


def render(p, slot, output):
    source=p['refs'][1 if slot==8 else 0]
    with Image.open(source) as raw:
        im=raw.convert('RGB')
        if slot==6:
            # User confirms the crop is visible in the original; never synthesize details.
            w,h=im.size
            im=im.crop((w*.2,h*.2,w*.8,h*.8))
        canvas=ImageOps.pad(im,(1200,1200),color='white')
    draw=ImageDraw.Draw(canvas)
    if slot==5:
        canvas=Image.new('RGB',(1200,1200),'white')
        product=ImageOps.contain(im,(850,850))
        canvas.paste(product,((1200-product.width)//2,(1100-product.height)//2))
        draw=ImageDraw.Draw(canvas)
        draw.line((140,1050,1060,1050),fill='black',width=4)
        for x in (140,1060): draw.line((x,1030,x,1070),fill='black',width=4)
        draw.text((350,1090),f"Ancho: {p['width']} {p['unit']}",fill='black',font=font(38))
        draw.line((1100,140,1100,1000),fill='black',width=4)
        draw.text((80,35),f"Alto: {p['height']} {p['unit']}",fill='black',font=font(38))
    if slot==7:
        # Spanish claims are explicitly supplied and confirmed by the user.
        text=p.get('selling_es','').strip()
        if not text: raise ValueError('请填写已确认的西班牙语卖点，用于图片07')
        import textwrap
        lines='\n'.join(textwrap.wrap(text, width=42))
        if len(lines.splitlines())>4: raise ValueError('西班牙语图片卖点过长，请缩短')
        draw.rectangle((0,960,1200,1200),fill='white')
        draw.multiline_text((45,980),lines,font=font(36),fill='#17372b',spacing=8)
    canvas.save(output)


def export_image(path, size=600, fmt='JPG'):
    import io
    if size not in (600,1200) or fmt not in ('JPG','PNG'): raise ValueError('不支持的输出格式')
    with Image.open(path) as im:
        im=ImageOps.pad(im.convert('RGB'),(size,size),color='white',method=Image.Resampling.LANCZOS)
        b=io.BytesIO(); im.save(b,format='JPEG' if fmt=='JPG' else 'PNG',quality=95)
        return b.getvalue()
