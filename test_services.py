import io
from datetime import date, timedelta

import pytest
from PIL import Image

from app.database.models import EXPENSE, INCOME
from app.services.appointment_service import month_grid
from app.services.image_service import ImageProcessingError, process_photo
from app.utils.validators import ValidationError, parse_money


def _png(w=800, h=600):
    buf = io.BytesIO()
    Image.new("RGBA", (w, h), (200, 30, 30, 255)).save(buf, "PNG")
    return buf.getvalue()


def test_people_crud_with_photo(services):
    ps = services.people
    p = ps.build("  Maria   da Silva ", "(11) 98765-4321", "Maria@Email.com", "10/05/1990", "Rua A, 1")
    saved = ps.save(p, new_photo=_png())
    assert saved.id and saved.full_name == "Maria da Silva" and saved.phone == "11987654321"
    assert saved.email == "maria@email.com"
    photo = Image.open(io.BytesIO(ps.photo_bytes(saved)))
    thumb = Image.open(io.BytesIO(ps.photo_bytes(saved, thumb=True)))
    assert photo.size == (512, 512) and thumb.size == (128, 128) and photo.format == "JPEG"
    assert [x.full_name for x in ps.search("silva")] == ["Maria da Silva"]
    assert ps.search("98765")  # busca por telefone
    old_file = saved.photo_file
    edited = ps.build("Maria Souza", "", "", "", "", person_id=saved.id)
    ps.save(edited, new_photo=_png(300, 900))
    assert ps.get(saved.id).photo_file != old_file
    assert ps.photos.read(old_file) is None  # foto antiga removida
    ps.delete(saved.id)
    assert ps.count() == 0


@pytest.mark.parametrize("args,field", [
    (("Jo", "", "", "", ""), "full_name"),
    (("João Silva", "123", "", "", ""), "phone"),
    (("João Silva", "", "joao@", "", ""), "email"),
    (("João Silva", "", "", "31/02/2000", ""), "birth_date"),
    (("João Silva", "", "", (date.today() + timedelta(days=2)).strftime("%d/%m/%Y"), ""), "birth_date"),
])
def test_people_validation(services, args, field):
    with pytest.raises(ValidationError) as exc:
        services.people.build(*args)
    assert exc.value.field == field


def test_invalid_image():
    with pytest.raises(ImageProcessingError):
        process_photo(b"not an image")


def test_appointments_with_person_relationship(services):
    person = services.people.save(services.people.build("Ana Lima", "", "", "", ""))
    a_svc = services.appointments
    d = date(2026, 12, 24)
    a = a_svc.save(a_svc.build("Ceia", "Casa da vó", d, "20h", person_id=person.id))
    a_svc.save(a_svc.build("Compras", "", d, "9:15"))
    items = a_svc.by_day(d)
    assert [x.title for x in items] == ["Compras", "Ceia"]
    assert items[1].person_name == "Ana Lima"
    weeks = month_grid(2026, 12)
    assert len(weeks) == 6 and a_svc.counts_for_grid(weeks)[d] == 2
    services.people.delete(person.id)  # ON DELETE SET NULL
    assert a_svc.repo.get(a.id).person_id is None
    a = a_svc.repo.get(a.id)
    a.title = "Ceia de Natal"
    a_svc.save(a)
    assert a_svc.repo.get(a.id).title == "Ceia de Natal"
    a_svc.delete(a.id)
    assert len(a_svc.by_day(d)) == 1
    with pytest.raises(ValidationError):
        a_svc.build("X", "", d, "25:00")


def test_finance(services):
    f = services.finance
    today = date.today()
    f.save(f.build(INCOME, "Salário", "5.000,00", "Salário", today))
    t = f.save(f.build(EXPENSE, "Mercado", "R$ 450,90", "Alimentação", today))
    f.save(f.build(EXPENSE, "Uber", "30", "Transporte", today))
    s = f.overall()
    assert (s.income_cents, s.expense_cents, s.balance_cents) == (500000, 48090, 451910)
    assert f.expenses_by_category(today.year, today.month)[0] == ("Alimentação", 45090)
    assert len(f.list_month(today.year, today.month, EXPENSE)) == 2
    assert len(f.list_month(today.year, today.month, term="uber")) == 1
    bars = f.last_months(today.year, today.month)
    assert len(bars) == 6 and bars[-1].income_cents == 500000
    t.amount_cents = 10000
    f.save(t)
    assert f.overall().expense_cents == 13000
    f.delete(t.id)
    assert f.overall().expense_cents == 3000
    with pytest.raises(ValidationError):
        f.build(EXPENSE, "X", "0", "Alimentação", today)
    with pytest.raises(ValidationError):
        f.build(EXPENSE, "X", "10", "Salário", today)


def test_parse_money():
    assert parse_money("1.234,56") == 123456
    assert parse_money("45.9") == 4590
    assert parse_money("3.500") == 350000


def test_whatsapp_flow(services):
    wa = services.whatsapp
    items = wa.simulate_incoming("Gastei R$ 45,00 no mercado hoje")
    assert len(items) == 1 and items[0].suggestion.amount_cents == 4500
    assert services.finance.overall().expense_cents == 0  # nada salvo sem confirmação
    sug = items[0].suggestion
    tx = services.finance.build(sug.kind, sug.description, "45,00", sug.category, sug.date)
    saved = wa.confirm(items[0].message.id, tx)
    assert saved.source == "whatsapp" and services.finance.overall().expense_cents == 4500
    with pytest.raises(ValueError):
        wa.confirm(items[0].message.id, tx)  # não confirma duas vezes
    wa.simulate_incoming("oi tudo bem")  # sem valor -> resposta automática
    hist = wa.history()
    assert [m.message.direction for m in hist] == ["in", "out", "in", "out"]
    # webhook repetido é ignorado (idempotência)
    payload = wa.gateway.build_incoming_payload("Paguei 10 de pão")
    assert len(wa.handle_webhook(payload)) == 1 and wa.handle_webhook(payload) == []


def test_persistence_across_restart(tmp_path):
    from app.services.container import build_services
    s1 = build_services(tmp_path / "p.db", tmp_path / "ph")
    s1.people.save(s1.people.build("Carlos Mendes", "", "", "", ""))
    s1.calc_history.add("1+1", "2")
    s2 = build_services(tmp_path / "p.db", tmp_path / "ph")
    assert s2.people.count() == 1 and s2.calc_history.recent()[0].result == "2"
