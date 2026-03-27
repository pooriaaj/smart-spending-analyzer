from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import Base, engine
from app import models
from app.routes.auth_routes import router as auth_router
from app.routes.transaction_routes import router as transaction_router
from app.routes.analytics_routes import router as analytics_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Smart Spending Analyzer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(transaction_router)
app.include_router(analytics_router)


@app.get("/")
def root():
    return {"message": "Smart Spending Analyzer backend is running"}