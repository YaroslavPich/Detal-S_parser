from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from app.parser.sites import get_all_prices
import sys
import asyncio
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

app = FastAPI(title="Detal-s Price Aggregator")

templates = Jinja2Templates(directory="app/templates")


@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse(
        request, "index.html", {"query": None, "results": []}
    )


@app.get("/search")
async def search_parts(request: Request, part_number: str):
    clean_part_number = part_number.strip().upper()
    results = await get_all_prices(clean_part_number)
    
    return templates.TemplateResponse(
        request, 
        "index.html", 
        {"query": clean_part_number, "results": results}
    )