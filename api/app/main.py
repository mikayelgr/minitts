from .config import App, lifespan
from .routers import router as default_router
import logging

logging.basicConfig(level=logging.INFO)

app = App(lifespan=lifespan)
app.include_router(default_router)
