"""Regras de negócio do calendário e compromissos."""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Optional

from app.database.models import Appointment
from app.database.repositories import AppointmentRepository
from app.utils.validators import ValidationError, parse_time, required


def month_grid(year: int, month: int) -> list[list[date]]:
    """Semanas (segunda a domingo) que cobrem o mês, incluindo dias vizinhos."""
    cal = calendar.Calendar(firstweekday=calendar.MONDAY)
    weeks = cal.monthdatescalendar(year, month)
    while len(weeks) < 6:  # altura fixa evita "pulos" no layout ao trocar de mês
        last = weeks[-1][-1]
        weeks.append([last + timedelta(days=i) for i in range(1, 8)])
    return weeks


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


class AppointmentService:
    def __init__(self, repo: AppointmentRepository):
        self.repo = repo

    def by_day(self, day: date) -> list[Appointment]:
        return self.repo.by_day(day)

    def counts_for_grid(self, weeks: list[list[date]]) -> dict[date, int]:
        return self.repo.counts_between(weeks[0][0], weeks[-1][-1])

    def upcoming(self, limit: int = 5) -> list[Appointment]:
        return self.repo.upcoming(date.today(), limit)

    @staticmethod
    def build(title: str, description: str, day: date, time_text: str,
              person_id: Optional[int] = None, appointment_id: Optional[int] = None) -> Appointment:
        title = required(title, "o título", "title")
        if len(title) > 80:
            raise ValidationError("Título muito longo (máximo 80 caracteres).", "title")
        description = (description or "").strip()
        if len(description) > 500:
            raise ValidationError("Descrição muito longa (máximo 500 caracteres).", "description")
        if day is None:
            raise ValidationError("Selecione uma data.", "date")
        return Appointment(
            id=appointment_id,
            title=title,
            description=description,
            date=day,
            time=parse_time(time_text, "time"),
            person_id=person_id,
        )

    def save(self, appointment: Appointment) -> Appointment:
        if appointment.id:
            self.repo.update(appointment)
        else:
            appointment.id = self.repo.add(appointment)
        return appointment

    def delete(self, appointment_id: int) -> None:
        self.repo.delete(appointment_id)
