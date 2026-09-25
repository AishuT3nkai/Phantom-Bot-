import io
import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W,H=1280,720

async def _image(url):
    if not url: return None
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url,timeout=aiohttp.ClientTimeout(total=12)) as r:
                if r.status!=200: return None
                return Image.open(io.BytesIO(await r.read())).convert("RGB")
    except Exception:
        return None

def _font(size,bold=False):
    p="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    try: return ImageFont.truetype(p,size)
    except OSError: return ImageFont.load_default()

def _time(ms):
    s=max(0,int(ms)//1000)
    return f"{s//60:02d}:{s%60:02d}"

async def render_card(track,position_ms,requester,paused=False):
    bg=await _image(track.artwork)
    if bg is None: bg=Image.new("RGB",(W,H),(18,20,25))
    bg.thumbnail((W,H))
    canvas=Image.new("RGB",(W,H),(18,20,25))
    canvas.paste(bg,((W-bg.width)//2,(H-bg.height)//2))
    canvas=canvas.filter(ImageFilter.GaussianBlur(2))
    canvas=Image.alpha_composite(canvas.convert("RGBA"),Image.new("RGBA",(W,H),(0,0,0,125)))
    d=ImageDraw.Draw(canvas)
    d.text((70,65),"PHANTOM",font=_font(25,True),fill="white")
    d.text((70,470),track.title[:42],font=_font(56,True),fill="white")
    d.text((72,540),track.author[:55],font=_font(31),fill=(220,220,220))
    total=max(int(track.length),1); cur=max(0,min(int(position_ms),total))
    x,y,w=72,610,W-144
    d.rounded_rectangle((x,y,x+w,y+8),4,fill=(100,100,100,170))
    progress=int(w*cur/total)
    d.rounded_rectangle((x,y,x+max(progress,8),y+8),4,fill="white")
    d.ellipse((x+progress-9,y-5,x+progress+9,y+13),fill="white")
    d.text((72,635),_time(cur),font=_font(23),fill="white")
    right=f"{_time(total)}  •  {'PAUSED' if paused else 'PLAYING'}"
    box=d.textbbox((0,0),right,font=_font(23))
    d.text((W-72-(box[2]-box[0]),635),right,font=_font(23),fill="white")
    d.text((72,675),f"Requested by {requester}",font=_font(22),fill=(205,205,205))
    out=io.BytesIO(); canvas.convert("RGB").save(out,"JPEG",quality=90); out.seek(0)
    return out
