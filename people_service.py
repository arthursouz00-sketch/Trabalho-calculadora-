"""Regras de negócio do cadastro de pessoas."""
from __future__ import annotations

from datetime import date
from typing import Optional

from app.database.models import Person
from app.database.repositories import PersonRepository
from app.services.image_service import PhotoStorage
from app.utils.validators import (
    ValidationError,
    parse_date_br,
    required,
    validate_email,
    validate_phone,
)


class PeopleService:
    def __init__(self, repo: PersonRepository, photos: PhotoStorage):
        self.repo = repo
        self.photos = photos

    # ---------- consultas ----------
    def search(self, term: str = "") -> list[Person]:
        return self.repo.search(term)

    def get(self, person_id: int) -> Optional[Person]:
        return self.repo.get(person_id)

    def count(self) -> int:
        return self.repo.count()

    def birthdays_on(self, day: date) -> list[Person]:
        return [p for p in self.repo.search() if p.has_birthday_on(day)]

    def photo_bytes(self, person: Person, thumb: bool = False) -> Optional[bytes]:
        return self.photos.read(person.thumb_file if thumb else person.photo_file)

    # ---------- validação ----------
    @staticmethod
    def build(full_name: str, phone: str, email: str, birth: str, address: str,
              person_id: Optional[int] = None) -> Person:
        name = " ".join(required(full_name, "o nome completo", "full_name", min_len=3).split())
        if len(name) > 120:
            raise ValidationError("Nome muito longo (máximo 120 caracteres).", "full_name")
        birth_date = parse_date_br(birth, "birth_date", allow_empty=True)
        if birth_date:
            if birth_date > date.today():
                raise ValidationError("A data de nascimento não pode estar no futuro.", "birth_date")
            if birth_date.year < 1900:
                raise ValidationError("Ano de nascimento inválido.", "birth_date")
        return Person(
            id=person_id,
            full_name=name,
            phone=validate_phone(phone, "phone"),
            email=validate_email(email, "email"),
            birth_date=birth_date,
            address=(address or "").strip()[:250],
        )

    # ---------- escrita ----------
    def save(self, person: Person, new_photo: Optional[bytes] = None, remove_photo: bool = False) -> Person:
        """Insere ou atualiza. ``new_photo`` são os bytes originais da imagem escolhida."""
        old = self.repo.get(person.id) if person.id else None
        if old:
            person.photo_file, person.thumb_file = old.photo_file, old.thumb_file
        created_files: tuple[str, str] | None = None
        if new_photo:
            created_files = self.photos.save(new_photo)  # pode levantar ImageProcessingError
            person.photo_file, person.thumb_file = created_files
        elif remove_photo:
            person.photo_file = person.thumb_file = None
        try:
            if person.id:
                self.repo.update(person)
            else:
                person.id = self.repo.add(person)
        except Exception:
            if created_files:
                self.photos.delete(*created_files)
            raise
        if old and (old.photo_file != person.photo_file):
            self.photos.delete(old.photo_file, old.thumb_file)
        return person

    def delete(self, person_id: int) -> None:
        person = self.repo.get(person_id)
        self.repo.delete(person_id)
        if person:
            self.photos.delete(person.photo_file, person.thumb_file)
