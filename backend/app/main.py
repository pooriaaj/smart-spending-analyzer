from fastapi import FastAPI
from app.database import Base, engine
from app import models
from app.routes.auth_routes import router as auth_router
from app.routes.transaction_routes import router as transaction_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Smart Spending Analyzer API")

app.include_router(auth_router)
app.include_router(transaction_router)


@app.get("/")
def root():
    return {"message": "Smart Spending Analyzer backend is running"}