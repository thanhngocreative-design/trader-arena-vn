"""Public read-only JSON bridge for the GitHub Pages iPhone dashboard."""
from __future__ import annotations
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from live.paper import LivePaper
from live.feed import DNSEMarketWorker

logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(name)s %(message)s")
book=LivePaper(os.environ.get("LIVE_DB_PATH","/data/live-papers.sqlite"))
worker=DNSEMarketWorker(book)

@asynccontextmanager
async def lifespan(app:FastAPI):
    worker.task=asyncio.create_task(worker.run())
    try:
        yield
    finally:
        worker.task.cancel()
        try:
            await worker.task
        except asyncio.CancelledError:
            pass
        book.close()

app=FastAPI(title="Trader Arena VN Paper-Only Quote Bridge",lifespan=lifespan,
            openapi_url=None,docs_url=None,redoc_url=None)
app.add_middleware(CORSMiddleware,
    allow_origins=["https://thanhngocreative-design.github.io"],
    allow_methods=["GET"],allow_headers=[])

@app.get("/health")
def health():
    # Deployed ≠ connected to quote feed. A healthy web server is not proof
    # that exchange data is available.
    return {"service":"online","stream":worker.status()["connected"],
            "configured":worker.configured}

@app.get("/api/live")
def live():
    result=book.snapshot()
    result["feed"]=worker.status()
    result["warning"]="Bid/ask-based paper estimates, not confirmed exchange executions. Never contains brokerage orders."
    return JSONResponse(result,headers={"Cache-Control":"no-store, max-age=0"})

@app.get("/")
def root():
    return {"name":"Trader Arena VN quote-feed bridge","paper_only":True,
            "info":"Only /health and /api/live are exposed. No trading order endpoint."}
