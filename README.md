# Smart Spending Analyzer

A full-stack financial intelligence web application that helps users track, analyze, and improve their spending behavior.

Live Demo:
Frontend: https://smart-spending-analyzer.vercel.app  
Backend API: https://smart-spending-analyzer.onrender.com

---

## Overview

Smart Spending Analyzer is more than a transaction tracker.  
It is designed as a foundation for an intelligent financial assistant that:

- Tracks income and expenses
- Automatically imports transaction data
- Detects spending patterns
- Identifies overspending risks
- Provides personalized financial insights
- Acts as an AI-powered financial assistant

---

## Features

### Core System
- User authentication with JWT
- Secure PostgreSQL database
- FastAPI backend with structured services
- React frontend with modern UI

### Transactions
- Manual transaction creation/edit/delete
- CSV import with:
  - encoding handling
  - duplicate detection
  - validation system

### Analytics
- Monthly financial summaries
- Category breakdown
- Top expense category detection
- Trend analysis (month-over-month)
- Overspending alerts
- Recent transactions tracking

### Smart Assistant
- Natural-language financial queries
- Context-aware responses
- Spending insights and recommendations
- Actionable suggestions:
  - navigate to analytics
  - filter transactions
  - review categories

### Smart Categorization
- Rule-based transaction classification
- Bulk categorization suggestions
- Confidence scoring
- Apply suggestions automatically

### Data Simulation
- Realistic financial data generator:
  - salary
  - groceries
  - transport
  - subscriptions
  - spikes (travel, shopping)
- Used for testing analytics and assistant logic

---

## Tech Stack

### Backend
- FastAPI
- SQLAlchemy
- PostgreSQL (Render)
- JWT authentication

### Frontend
- React (Vite)
- Recharts (data visualization)
- Axios

### Deployment
- Backend: Render
- Frontend: Vercel

---

## Architecture

The backend follows a service-based architecture:
routes → services → database

This structure improves:
- maintainability
- scalability
- separation of concerns

---

## Key Engineering Highlights

### Performance Optimization
- SQL aggregation instead of Python loops
- Database indexing for:
  - owner_id
  - date
  - category
- bulk insert for CSV imports

### Clean Backend Refactor
- Reduced 1000+ line route files into service layer
- Modular analytics system
- Reusable query builder

### Smart Assistant Logic
- Intent classification (balance, trends, alerts, etc.)
- Context-aware responses
- Multi-source reasoning:
  - summary
  - trends
  - alerts
  - recent data

---

## Security

- Password hashing (PBKDF2)
- JWT authentication
- Environment-based configuration
- `.env` excluded from repository

---

## How to Run Locally

### Backend
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload


### Frontend
cd frontend
npm install
npm run dev


---

## Environment Variables

Create a `.env` file in the root:
DATABASE_URL=your_database_url
SECRET_KEY=your_secret
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
FRONTEND_URL=http://localhost:5173

VITE_API_BASE_URL=http://localhost:8000

---

## Future Roadmap

- AI/LLM-powered assistant (OpenAI / local model)
- Bank API integration (Plaid or similar)
- Automatic transaction syncing
- Advanced anomaly detection
- Budget planning system
- Mobile app version

---

## Author

Mohammadreza Alijani  
Toronto, Canada  

GitHub: https://github.com/pooriaaj

---

## Final Note

This project demonstrates:

- Full-stack development
- Data engineering & analytics
- Backend architecture design
- Product thinking
- AI system design foundations