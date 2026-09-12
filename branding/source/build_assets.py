"""Build Muta's font-free SVG masters and deterministic raster derivatives.

Run from any directory: python branding/source/build_assets.py
Requires fonttools, Pillow, hb-shape, and rsvg-convert. All output stays in branding/.
The approved raster concept is a reference; these are intentionally redrawn vector masters.
"""
from pathlib import Path
import html
import json
import subprocess
from functools import lru_cache
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.boundsPen import BoundsPen

ROOT = Path(__file__).resolve().parents[1]
PALETTE = dict(forest='#1D251F', ink='#171C18', ivory='#F5F1E7', paper='#FAF9F5', terracotta='#AD4F31', terracottaLight='#E58C69')
THEMES = {
    'on-light': dict(cover=PALETTE['forest'], left=PALETTE['ivory'], right=PALETTE['terracotta'], dot=PALETTE['terracotta'], ink=PALETTE['ink']),
    'on-dark': dict(cover=PALETTE['ivory'], left=PALETTE['ivory'], right=PALETTE['terracottaLight'], dot=PALETTE['terracottaLight'], ink=PALETTE['ivory']),
    'black': dict.fromkeys(['cover','left','right','dot','ink'], '#000000'),
    'white': dict.fromkeys(['cover','left','right','dot','ink'], '#FFFFFF'),
}

def svg(width, height, content, title, background=None):
    bg = f'<rect width="{width}" height="{height}" fill="{background}"/>' if background else ''
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title, quote=True)}"><title>{html.escape(title)}</title>{bg}{content}</svg>\n'

def nested(x,y,width,height,viewbox,content):
    return f'<svg x="{x}" y="{y}" width="{width}" height="{height}" viewBox="{viewbox}" overflow="visible">{content}</svg>'

def dot(x=236, y=427, size=40, color='#AD4F31', tail=True):
    # Body stays square and optically centered. Tail is 0.18 of body height and
    # remains inside the body's horizontal footprint.
    tailpart = 'H10L0 47.2V3' if tail else 'H3Q0 40 0 37V3'
    return f'<path transform="translate({x} {y}) scale({size/40})" d="M3 0H37Q40 0 40 3V37Q40 40 37 40{tailpart}Q0 0 3 0Z" fill="{color}"/>'

def book(theme='on-light', include_dot=True):
    c=THEMES[theme]
    # The cover and pages follow natural book curves; there is no letter skeleton.
    leftcover='M48 109Q40 106 40 114V366Q40 373 47 370C117 350 198 357 251 396C211 351 149 329 73 335Q61 335 61 324V113Z'
    rightcover='M464 109Q472 106 472 114V366Q472 373 465 370C395 350 314 357 261 396C301 351 363 329 439 335Q451 335 451 324V113Z'
    leftpage='M76 64C145 69 207 92 243 126Q252 135 252 149V382C205 342 143 318 76 322Q68 322 68 314V72Q68 63 76 64Z'
    rightpage='M269 126C313 88 376 63 436 56Q444 55 444 64V314Q444 322 436 322C369 320 307 342 260 382V149Q260 135 269 126Z'
    parts=[f'<path d="{leftcover}" fill="{c["cover"]}"/>', f'<path d="{rightcover}" fill="{c["cover"]}"/>']
    # A dark contour keeps the ivory leaf visible on a light canvas. Inner page
    # areas are solid color and the two broad leaves remain clear.
    monochrome = theme in ('black', 'white')
    outline = f' stroke="{c["cover"]}" stroke-width="{6 if monochrome else 2}" stroke-linejoin="round"' if monochrome or theme=='on-light' else ''
    leftfill = 'none' if monochrome else c['left']
    parts += [f'<path d="{leftpage}" fill="{leftfill}"{outline}/>', f'<path d="{rightpage}" fill="{c["right"]}"/>']
    if include_dot: parts.append(dot(color=c['dot']))
    return ''.join(parts)

@lru_cache(maxsize=16)
def outlined(text, fontname='LibreBaskerville-Regular.ttf'):
    fontpath=ROOT/'fonts'/fontname
    font=TTFont(fontpath); glyphs=font.getGlyphSet(); upem=font['head'].unitsPerEm
    shaped=json.loads(subprocess.check_output(['hb-shape',str(fontpath),text,'--font-size=1000','-O','json']))
    x=0; paths=[]; boxes=[]; clusters=[]
    for item in shaped:
        transform=(1000/upem,0,0,-1000/upem,x+item['dx'],-item['dy'])
        pen=SVGPathPen(glyphs); glyphs[item['g']].draw(TransformPen(pen,transform))
        if pen.getCommands(): paths.append(f'<path d="{pen.getCommands()}"/>')
        bounds=BoundsPen(glyphs); glyphs[item['g']].draw(TransformPen(bounds,transform))
        if bounds.bounds: boxes.append(bounds.bounds); clusters.append((item['cl'],bounds.bounds))
        x+=item['ax']
    box=(min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes))
    return ''.join(paths),box,clusters

def text_path(text,x,y,size,color,fontname='InstrumentSans-Regular.ttf'):
    paths,_,_=outlined(text,fontname)
    return f'<g fill="{color}" transform="translate({x} {y}) scale({size/1000})" aria-label="{html.escape(text,quote=True)}">{paths}</g>'

def wordmark(theme='on-light'):
    paths,box,clusters=outlined('Muta.')
    s=920/(box[2]-box[0]); tx=40-box[0]*s; ty=35-box[1]*s
    ubox=next(b for cl,b in clusters if cl==1)
    center=tx+(ubox[0]+ubox[2])*s/2
    bottom=ty+box[3]*s
    return f'<g transform="translate({tx:.6f} {ty:.6f}) scale({s:.8f})" fill="{THEMES[theme]["ink"]}">{paths}</g>'+dot(center-28,bottom+19,56,THEMES[theme]['dot'])

def mark(kind,theme='on-light'):
    if kind=='symbol': return 512,512,book(theme)
    if kind=='dot': return 64,64,dot(12,8,40,THEMES[theme]['dot'])
    if kind=='wordmark': return 1000,390,wordmark(theme)
    if kind=='stacked':
        return 1000,1030,nested(120,0,760,760,'0 0 512 512',book(theme,False))+nested(0,597,1000,390,'0 0 1000 390',wordmark(theme))
    if kind=='horizontal':
        return 1120,330,nested(10,8,290,290,'0 0 512 512',book(theme,False))+nested(310,0,800,312,'0 0 1000 390',wordmark(theme))
    raise ValueError(kind)

def app_icon(theme='on-dark',rounded=False):
    bg=PALETTE['forest'] if theme=='on-dark' else PALETTE['paper']
    tile=f'<rect width="512" height="512" rx="{112 if rounded else 0}" fill="{bg}"/>'
    return tile+f'<g transform="translate(28 22) scale(.89)">{book(theme)}</g>'

def optical_icon(size=32):
    # Dedicated 16-unit version: omit the cover layer and speech nib so these
    # cannot become accidental noise. Retain two leaves and the square body.
    if size==16:
        body='<rect width="16" height="16" rx="3.3" fill="#1D251F"/>'
        body+='<path d="M3 3.3C5 3.4 6.5 4 7.4 4.9V11.2C6.1 10.4 4.6 10 3 10.1Z" fill="#F5F1E7"/>'
        body+='<path d="M8.6 4.9C9.8 3.9 11.4 3.3 13 3.1V10.1C11.4 10 9.9 10.4 8.6 11.2Z" fill="#E58C69"/>'
        body+='<rect x="7" y="13" width="2" height="2" fill="#E58C69"/>'
        return 16,body
    body='<rect width="32" height="32" rx="6.6" fill="#1D251F"/>'
    body+='<path d="M5 6C8.8 6.1 11.8 7.2 14.8 9.6V22.5C11.9 20.6 8.7 19.8 5 20Z" fill="#F5F1E7"/>'
    body+='<path d="M17.2 9.6C20.2 7.2 23.2 6.1 27 5.6V20C23.3 19.8 20.1 20.6 17.2 22.5Z" fill="#E58C69"/>'
    body+=dot(14,25,4,'#E58C69')
    return 32,body

def save_svg(relative,width,height,content,title,background=None,png_width=None):
    path=ROOT/relative;path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(svg(width,height,content,title,background))
    if png_width:
        render(path,path.with_suffix('.png'),png_width)
    return path

def render(source,target,width):
    subprocess.run(['rsvg-convert','-w',str(width),str(source),'-o',str(target)],check=True)

def build_preview():
    """A compact presentation board, separate from individual production marks."""
    p=PALETTE
    body=text_path('MUTA / BRAND ASSETS',70,64,19,p['ink'],'InstrumentSans-Bold.ttf')
    body+=text_path('Book + speaking dot',1110,64,19,p['ink'])
    body+='<path d="M70 92H1430" stroke="#d6d8ce"/>'
    w,h,content=mark('stacked')
    body+=nested(70,160,760,783,f'0 0 {w} {h}',content)
    body+='<rect x="920" y="150" width="510" height="480" fill="#1D251F"/>'
    body+=nested(1018,185,315,315,'0 0 512 512',book('on-dark'))
    body+=text_path('The standalone mark',987,579,19,p['ivory'])
    w,h,content=mark('horizontal','black')
    body+=nested(930,690,500,148,f'0 0 {w} {h}',content)
    body+=text_path('Single-color master',949,859,16,p['ink'])
    for i,key in enumerate(['forest','ivory','terracotta','terracottaLight']):
        body+=f'<rect x="{920+i*127.5}" y="922" width="127.5" height="68" fill="{p[key]}"/>'
    body+='<path d="M70 1038H1430" stroke="#d6d8ce"/>'
    body+=text_path('Vector logos / App icons / Social graphics / Brand guide',70,1071,16,p['ink'])
    body+=text_path('Identity kit 01',1315,1071,16,p['ink'])
    save_svg('brand-board.svg',1500,1100,body,'Muta brand asset overview',background=p['paper'],png_width=1500)

def main():
    for theme in THEMES:
        for kind in ['stacked','horizontal','wordmark','symbol','dot']:
            w,h,body=mark(kind,theme)
            save_svg(f'logos/muta-{kind}-{theme}.svg',w,h,body,f'Muta {kind} logo — {theme}',png_width=2000 if kind in ['stacked','horizontal','wordmark'] else 1024 if kind=='symbol' else 256)
    save_svg('icons/muta-app-master.svg',512,512,app_icon(), 'Muta full-bleed application icon',png_width=1024)
    for theme,label in [('on-dark','forest'),('on-light','paper')]:
        save_svg(f'icons/muta-avatar-{label}.svg',512,512,app_icon(theme,True),f'Muta rounded avatar on {label}',png_width=512)
    for size in [16,24,32,48,64]:
        v,body=optical_icon(size)
        save_svg(f'icons/muta-favicon-{size}.svg',v,v,body,f'Muta optical favicon {size}px',png_width=size)
    for size,label in [(180,'touch'),(192,'android-192'),(512,'android-512')]:
        render(ROOT/'icons/muta-app-master.svg',ROOT/f'icons/muta-{label}.png',size)
    from PIL import Image
    favicon_sizes=[16,32,48,64]
    images=[Image.open(ROOT/f'icons/muta-favicon-{s}.png') for s in favicon_sizes]
    images[-1].save(ROOT/'icons/favicon.ico',format='ICO',sizes=[(s,s) for s in favicon_sizes],append_images=images[:-1])
    (ROOT/'tokens.json').write_text(json.dumps({'name':'Muta','version':1,'colors':PALETTE,'fonts':{'logo':'Libre Baskerville Regular (outlined)','display':'Libre Baskerville','body':'Instrument Sans'},'dialogueDot':{'bodyToTailRatio':.18,'wordmarkPlacement':'optically centered below u'}},indent=2)+'\n')
    css=':root {\n'+''.join(f'  --muta-{k}: {v};\n' for k,v in PALETTE.items())+'  --muta-font-display: "Libre Baskerville", Georgia, serif;\n  --muta-font-body: "Instrument Sans", system-ui, sans-serif;\n}\n'
    (ROOT/'tokens.css').write_text(css)
    build_preview()
    print('Built font-free logo masters, PNGs, icons, and tokens in',ROOT)

if __name__=='__main__':main()
