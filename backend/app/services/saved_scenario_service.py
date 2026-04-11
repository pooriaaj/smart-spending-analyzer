from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import SavedScenario
from app.schemas import SavedScenarioCreate, SavedScenarioResponse


def list_saved_scenarios(
    db: Session,
    owner_id: int,
    account_id: int | None = None,
) -> list[SavedScenarioResponse]:
    query = db.query(SavedScenario).filter(SavedScenario.owner_id == owner_id)

    if account_id is None:
        query = query.filter(SavedScenario.account_id.is_(None))
    else:
        query = query.filter(SavedScenario.account_id == account_id)

    scenarios = (
        query.order_by(SavedScenario.created_at.desc(), SavedScenario.id.desc())
        .all()
    )
    return [SavedScenarioResponse.model_validate(item) for item in scenarios]


def create_saved_scenario(
    db: Session,
    owner_id: int,
    payload: SavedScenarioCreate,
) -> SavedScenarioResponse:
    scenario = SavedScenario(
        name=payload.name.strip(),
        months=payload.months,
        income_adjustment=float(payload.income_adjustment or 0.0),
        expense_adjustment=float(payload.expense_adjustment or 0.0),
        target_balance=(
            float(payload.target_balance)
            if payload.target_balance is not None
            else None
        ),
        event_month_offset=payload.event_month_offset,
        event_amount=(
            float(payload.event_amount)
            if payload.event_amount is not None
            else None
        ),
        event_label=(payload.event_label.strip() if payload.event_label else None),
        owner_id=owner_id,
        account_id=payload.account_id,
    )
    db.add(scenario)
    db.commit()
    db.refresh(scenario)
    return SavedScenarioResponse.model_validate(scenario)


def update_saved_scenario(
    db: Session,
    scenario: SavedScenario,
    payload: SavedScenarioCreate,
) -> SavedScenarioResponse:
    scenario.name = payload.name.strip()
    scenario.months = payload.months
    scenario.income_adjustment = float(payload.income_adjustment or 0.0)
    scenario.expense_adjustment = float(payload.expense_adjustment or 0.0)
    scenario.target_balance = (
        float(payload.target_balance)
        if payload.target_balance is not None
        else None
    )
    scenario.event_month_offset = payload.event_month_offset
    scenario.event_amount = (
        float(payload.event_amount)
        if payload.event_amount is not None
        else None
    )
    scenario.event_label = payload.event_label.strip() if payload.event_label else None
    scenario.account_id = payload.account_id

    db.commit()
    db.refresh(scenario)
    return SavedScenarioResponse.model_validate(scenario)


def get_saved_scenario_for_user(
    db: Session,
    owner_id: int,
    scenario_id: int,
) -> SavedScenario | None:
    return (
        db.query(SavedScenario)
        .filter(
            SavedScenario.id == scenario_id,
            SavedScenario.owner_id == owner_id,
        )
        .first()
    )


def delete_saved_scenario(
    db: Session,
    scenario: SavedScenario,
) -> None:
    db.delete(scenario)
    db.commit()
