# Bathroom Design — AI Stijltool

## Lokaal testen (5 minuten)

```bash
# 1. Installeer dependencies
pip install -r requirements.txt

# 2. Maak .env aan (kopieer van .env.example)
cp .env.example .env
# Vul je keys in het .env bestand

# 3. Start de server
uvicorn main:app --reload

# 4. Open http://localhost:8000
```

## Deployen op Railway (gratis)

1. Ga naar https://railway.app
2. "New Project" → "Deploy from GitHub repo"
3. Push deze map naar een GitHub repo
4. Voeg environment variables toe in Railway dashboard:
   - REPLICATE_API_TOKEN = r8_xxx...
   - ANTHROPIC_API_KEY = sk-ant-xxx... (optioneel)
5. Klaar — Railway geeft je een gratis .railway.app URL

## Leads bekijken

GET /api/leads  →  JSON lijst van alle leads
Bestand: leads.jsonl (lokaal) of Railway volume

## Model info

Model: rocketdigitalai/interior-design-sdxl-lightning
Kost: ~$0.011 per render (~90 renders per $1)
Tijd: ~9 seconden per render
