from .config import App, lifespan
from .routers import router as default_router
import logging

logging.basicConfig(level=logging.INFO)

app = App(lifespan=lifespan, title="MiniTTS API", description="API for MiniTTS")
app.include_router(default_router)
