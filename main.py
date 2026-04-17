import os, uuid, json, asyncio, datetime, smtplib, base64 as b64lib, io, logging
logging.basicConfig(level=logging.INFO, force=True)
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import httpx
import fastapi
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

REPLICATE_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")
SMTP_HOST       = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT       = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER       = os.getenv("SMTP_USER", "")
SMTP_PASS       = os.getenv("SMTP_PASS", "")
MAIL_FROM       = os.getenv("MAIL_FROM", SMTP_USER)
MAIL_BCC        = os.getenv("MAIL_BCC", "")
APP_URL         = os.getenv("APP_URL", "http://localhost:8000")

NEGATIVE_PROMPT = (
    "ugly, deformed, blurry, low quality, distorted, people, person, human, face, "
    "reflection of person, man, woman, selfie, watermark, logo, text, "
    "extra furniture, floating objects, unrealistic proportions, duplicate rooms, "
    "windows, natural light, sunlight, daylight, outdoor view"
)

STYLE_BASE = {
    "Modern & strak":  "modern minimalist bathroom, white walls, concrete floor, matte black fixtures, recessed lighting, frameless glass shower, ultra clean lines",
    "Scandinavisch":   "scandinavian bathroom, light oak wood accents, warm white walls, linen textures, simple elegant design",
    "Luxe klassiek":   "luxury classic bathroom, Carrara marble walls and floor, gold brass fixtures, freestanding bathtub, timeless elegance",
    "Industrieel":     "industrial bathroom, dark exposed brick, matte black steel, concrete look tiles, Edison bulbs, raw design",
    "Mediterraans":    "mediterranean bathroom, handmade terracotta tiles, warm ochre tones, natural stone, arched details",
    "Japans / Zen":    "japanese zen bathroom, hinoki wood, wabi-sabi stone, walk-in shower, minimal decor, serene atmosphere",
}

SFEER_MODIFIERS = {
    "Warm & gezellig":      "warm cozy atmosphere, soft warm lighting, amber tones",
    "Fris & luchtig":       "bright airy atmosphere, cool daylight, white and light tones, open feel",
    "Donker & dramatisch":  "dramatic dark atmosphere, moody low lighting, deep shadows, bold contrasts",
    "Rustig & sereen":      "calm serene atmosphere, soft diffused light, neutral palette, zen tranquility",
}

MATERIAAL_MODIFIERS = {
    "Natuursteen":    "natural stone surfaces, travertine tiles, organic textures",
    "Hout":           "warm wood panels, wood vanity, natural grain textures",
    "Beton & cement": "polished concrete walls and floor, cement look tiles, raw texture",
    "Marmer":         "luxurious marble surfaces, veined marble tiles, glossy finish",
    "Keramiek":       "large format ceramic tiles, clean grout lines, smooth matte finish",
}

LICHT_MODIFIERS = {
    "Indirecte verlichting": "soft indirect lighting, LED strips, warm glow behind mirrors, no windows",
    "Spots & accenten":      "recessed spotlights, accent lighting, dramatic highlights, no windows",
    "Donkere sfeer":         "minimal lighting, moody ambience, deep shadows, no windows",
    "Warm & sfeervol":       "warm ambient lighting, candle-like glow, soft shadows, no windows",
}

def build_prompt(style, sfeer, materiaal, licht):
    parts = [STYLE_BASE.get(style, "modern bathroom")]
    if sfeer in SFEER_MODIFIERS:     parts.append(SFEER_MODIFIERS[sfeer])
    if materiaal in MATERIAAL_MODIFIERS: parts.append(MATERIAAL_MODIFIERS[materiaal])
    if licht in LICHT_MODIFIERS:     parts.append(LICHT_MODIFIERS[licht])
    parts.append("photorealistic interior photography, 8k, high detail, professional render")
    return ", ".join(parts)


class RenderRequest(BaseModel):
    image_base64: str
    mime_type:    str = "image/jpeg"
    style:        str
    sfeer:        str = ""
    materiaal:    str = ""
    licht:        str = ""

class LeadRequest(BaseModel):
    name:       str
    email:      str
    style:      str
    sfeer:      str = ""
    materiaal:  str = ""
    licht:      str = ""
    render_url: str = ""


app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


_cached_logo = None

def get_logo_sync():
    """Laad logo uit static/logo.png (lokaal bestand — zie README)."""
    global _cached_logo
    if _cached_logo:
        return _cached_logo
    from PIL import Image
    logo_path = os.path.join(os.path.dirname(__file__), "static", "logo.png")
    if not os.path.exists(logo_path):
        print("[LOGO] static/logo.png niet gevonden — zie README voor instructies")
        return None
    logo = Image.open(logo_path).convert("RGBA")
    ratio = 180 / logo.width
    logo = logo.resize((180, int(logo.height * ratio)), Image.LANCZOS)
    _cached_logo = logo
    logging.info(f"[LOGO] Geladen: {logo.size}")
    return _cached_logo

@app.get("/api/proxy-image")
async def proxy_image(url: str):
    if "replicate" not in url:
        raise HTTPException(400, "Ongeldige URL")
    from PIL import Image, ImageDraw
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url)
        if r.status_code != 200:
            raise HTTPException(502, "Kon afbeelding niet ophalen")
    # BFL watermark wegcroppen (onderste 80px)
    img = Image.open(io.BytesIO(r.content)).convert("RGBA")
    w, h = img.size
    img = img.crop((0, 0, w, h - 80))
    w, h = img.size

    # Eigen logo plakken rechtsonder
    logo = get_logo_sync()
    img_rgb = img.convert("RGB")
    if logo:
        from PIL import ImageDraw
        margin = 14
        pad_x, pad_y = 12, 8
        lw, lh = logo.size
        # Donkere strook achter logo
        bar_x = w - lw - margin - pad_x * 2
        bar_y = h - lh - margin - pad_y * 2
        bar_w = w
        bar_h = h
        draw = ImageDraw.Draw(img_rgb)
        draw.rectangle([bar_x, bar_y, bar_w, bar_h], fill=(15, 15, 15))
        # Logo erop plakken
        pos_x = w - lw - margin - pad_x
        pos_y = h - lh - margin - pad_y
        img_rgb.paste(logo, (pos_x, pos_y), logo.split()[3])
        logging.info(f"[LOGO] Geplakt op ({pos_x},{pos_y}), afbeelding {w}x{h}")

    buf = io.BytesIO()
    img_rgb.save(buf, format="JPEG", quality=92)
    return Response(content=buf.getvalue(), media_type="image/jpeg")


@app.post("/api/render")
async def render(req: RenderRequest):
    if not REPLICATE_TOKEN:
        raise HTTPException(500, "REPLICATE_API_TOKEN niet ingesteld")

    prompt = build_prompt(req.style, req.sfeer, req.materiaal, req.licht)
    logging.info(f"[RENDER] Prompt: {prompt}")

    from PIL import Image

    # Afbeelding verkleinen naar max 1024px (base64 < 1MB vereist door Replicate)
    img_bytes = b64lib.b64decode(req.image_base64)
    img = Image.open(io.BytesIO(img_bytes))
    img.thumbnail((1024, 1024), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    resized_b64 = b64lib.b64encode(buf.getvalue()).decode()
    data_uri = f"data:image/jpeg;base64,{resized_b64}"
    logging.info(f"[RENDER] Afbeelding verkleind naar {img.size}, {len(buf.getvalue())//1024}KB")

    headers_json = {"Authorization": f"Token {REPLICATE_TOKEN}", "Content-Type": "application/json"}

    payload = {
        "input": {
            "control_image":   data_uri,
            "prompt":           prompt,
            "steps":            28,
            "guidance":         15,
            "safety_tolerance": 5,
            "output_format":    "jpg",
        }
    }

    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            "https://api.replicate.com/v1/models/black-forest-labs/flux-depth-pro/predictions",
            json=payload, headers=headers_json
        )
        logging.info(f"[RENDER] Replicate response status: {r.status_code}")
        logging.info(f"[RENDER] Replicate response body: {r.text[:500]}")
        if r.status_code != 201:
            raise HTTPException(500, f"Replicate fout: {r.text}")
        pred_id = r.json()["id"]
        logging.info(f"[RENDER] Prediction ID: {pred_id}")

        for _ in range(60):
            await asyncio.sleep(2)
            poll = await client.get(f"https://api.replicate.com/v1/predictions/{pred_id}", headers=headers_json)
            result = poll.json()
            status = result["status"]
            logging.info(f"[RENDER] Status: {status}")
            if status == "succeeded":
                remote_url = result["output"]
                if isinstance(remote_url, list):
                    remote_url = remote_url[0]
                proxy_url = f"/api/proxy-image?url={remote_url}"
                return {"url": proxy_url, "remote_url": remote_url, "prompt": prompt}
            if status == "failed":
                raise HTTPException(500, f"Render mislukt: {result.get('error','onbekend')}")

    raise HTTPException(504, "Render timeout na 120s")


def send_mail(to, name, style, render_url):
    resend_key = os.getenv("RESEND_API_KEY", "")
    if not resend_key:
        logging.info("[MAIL] RESEND_API_KEY niet ingesteld — sla over")
        return

    if render_url and render_url.startswith("/"):
        full_url = f"{APP_URL}{render_url}"
    else:
        full_url = render_url

    render_block = (
        f'<p style="margin:16px 0"><a href="{full_url}" '
        f'style="color:#c8a96e;font-weight:500">Bekijk uw render →</a></p>'
        if full_url else ""
    )

    html = f"""
<div style="font-family:Georgia,serif;max-width:520px;margin:0 auto;color:#1a1a1a;background:#fff;padding:32px">
  <p style="font-size:11px;letter-spacing:3px;text-transform:uppercase;color:#c8a96e;margin-bottom:8px">Bathroom Design</p>
  <h2 style="font-weight:400;font-size:22px;margin-bottom:20px">Beste {name},</h2>
  <p style="line-height:1.7;color:#444">Bedankt voor het gebruik van onze gratis stijltool.
  Hieronder vindt u uw AI-visualisatie in de stijl <strong>{style}</strong>.</p>
  {render_block}
  <hr style="border:none;border-top:1px solid #e8e4de;margin:28px 0">
  <p style="line-height:1.7;color:#444">Wil u een echte offerte op maat?
  Onze specialist komt vrijblijvend bij u langs — inclusief 3D visualisatie.</p>
  <a href="https://bathroomdesign.be/contact/"
     style="display:inline-block;margin-top:12px;padding:14px 28px;background:#c8a96e;
            color:#000;text-decoration:none;font-size:12px;letter-spacing:2px;text-transform:uppercase">
    Gratis afspraak inplannen
  </a>
  <p style="font-size:11px;color:#999;margin-top:32px;line-height:1.6">
    Bathroom Design · info@bathroomdesign.be · +32 477 60 16 05<br>
    <a href="https://bathroomdesign.be" style="color:#c8a96e">bathroomdesign.be</a>
  </p>
</div>"""

    logging.info(f"[MAIL] Versturen via Resend naar {to}")
    try:
        import resend
        resend.api_key = resend_key
        params = {
            "from": "Bathroom Design <stino89@gmail.com>",
            "to": [to],
            "subject": f"Uw badkamer in stijl {style} — Bathroom Design",
            "html": html,
        }
        if MAIL_BCC:
            params["bcc"] = [MAIL_BCC]
        r = resend.Emails.send(params)
        logging.info(f"[MAIL] Verstuurd: {r}")
    except Exception as e:
        logging.info(f"[MAIL] Fout ({type(e).__name__}): {e}")


@app.post("/api/lead")
async def save_lead(lead: LeadRequest):
    entry = {
        "id": str(uuid.uuid4())[:8],
        "name": lead.name, "email": lead.email,
        "style": lead.style, "sfeer": lead.sfeer,
        "materiaal": lead.materiaal, "licht": lead.licht,
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }
    try:
        with open("leads.jsonl", "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logging.info(f"[LEAD] write error: {e}")
    logging.info(f"[LEAD] {entry}")
    import threading
    threading.Thread(target=send_mail, args=(lead.email, lead.name, lead.style, lead.render_url), daemon=True).start()
    return {"ok": True}


@app.get("/api/leads")
async def get_leads():
    leads = []
    try:
        with open("leads.jsonl") as f:
            for line in f:
                if line.strip():
                    leads.append(json.loads(line))
    except FileNotFoundError:
        pass
    return leads


app.mount("/", StaticFiles(directory="static", html=True), name="static")
