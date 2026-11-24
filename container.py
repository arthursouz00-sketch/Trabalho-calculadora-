"""Composição das dependências (banco -> repositórios -> serviços)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app import config
from app.database.connection import Database
from app.database.repositories import (
    AppointmentRepository,
    CalcHistoryRepository,
    MessageRepository,
    PersonRepository,
    SettingsRepository,
    TransactionRepository,
)
from app.services.appointment_service import AppointmentService
from app.services.finance_service import FinanceService
from app.services.image_service import PhotoStorage
from app.services.people_service import PeopleService
from app.services.whatsapp import SandboxGateway, WhatsAppAutomation
from app.services.whatsapp.live import LiveWhatsApp


@dataclass
class Services:
    db: Database
    people: PeopleService
    appointments: AppointmentService
    finance: FinanceService
    calc_history: CalcHistoryRepository
    whatsapp: WhatsAppAutomation
    settings: SettingsRepository
    live: LiveWhatsApp


def build_services(db_path: Path | str | None = None, photos_dir: Path | str | None = None) -> Services:
    db = Database(db_path or config.db_path())
    finance = FinanceService(TransactionRepository(db))
    settings = SettingsRepository(db)
    automation = WhatsAppAutomation(SandboxGateway(), MessageRepository(db), finance)
    return Services(
        db=db,
        people=PeopleService(PersonRepository(db), PhotoStorage(Path(photos_dir or config.photos_dir()))),
        appointments=AppointmentService(AppointmentRepository(db)),
        finance=finance,
        calc_history=CalcHistoryRepository(db),
        whatsapp=automation,
        settings=settings,
        live=LiveWhatsApp(settings, automation),
    )
