"""Dados de demonstração (usados pelo seed e pela versão web de demonstração).

Passam pelos mesmos serviços da interface (validação + SQLite + Pillow).
"""
from __future__ import annotations

import io
import random
from datetime import date, timedelta

from PIL import Image, ImageDraw, ImageFilter

from app.database.models import EXPENSE, INCOME
from app.services.appointment_service import shift_month


def portrait(seed: int) -> bytes:
    """Ilustração abstrata de retrato (sem uso de fotos reais de pessoas)."""
    rnd = random.Random(seed)
    w, h = 900, 1100
    bg = rnd.choice([(31, 77, 58), (140, 36, 52), (201, 165, 92), (47, 93, 140), (110, 139, 61)])
    img = Image.new("RGB", (w, h), tuple(min(255, c + 60) for c in bg))
    d = ImageDraw.Draw(img)
    skin = rnd.choice([(241, 204, 177), (224, 172, 135), (198, 134, 94), (141, 85, 54)])
    d.ellipse((w * 0.18, h * 0.62, w * 0.82, h * 1.25), fill=bg)  # ombros
    d.ellipse((w * 0.32, h * 0.22, w * 0.68, h * 0.60), fill=skin)  # rosto
    hair = rnd.choice([(40, 30, 25), (90, 60, 30), (200, 170, 110), (20, 20, 20)])
    d.pieslice((w * 0.30, h * 0.17, w * 0.70, h * 0.50), 180, 360, fill=hair)
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def seed(s) -> bool:
    """Insere dados de demonstração se o banco estiver vazio. Retorna True se inseriu."""
    if s.people.count() or s.finance.overall().income_cents or s.finance.overall().expense_cents:
        return False
    today = date.today()
    people_data = [
        ("Ana Beatriz Souza", "11987654321", "ana.souza@email.com", "12/03/1994", "Rua das Flores, 120 — São Paulo/SP"),
        ("Carlos Eduardo Lima", "21991234567", "carlos.lima@email.com", "05/07/1988", "Av. Atlântica, 845 — Rio de Janeiro/RJ"),
        ("Mariana Costa", "31998887766", "mariana.costa@email.com", f"{today.day:02d}/{today.month:02d}/1999",
         "Rua da Bahia, 1500 — Belo Horizonte/MG"),
        ("Rafael Nogueira", "41996665544", "rafael.n@email.com", "25/12/1985", "Rua XV de Novembro, 300 — Curitiba/PR"),
        ("Juliana Martins", "51993332211", "", "18/09/2001", "Av. Ipiranga, 77 — Porto Alegre/RS"),
    ]
    ids = []
    for i, (name, phone, email, birth, address) in enumerate(people_data):
        person = s.people.build(name, phone, email, birth, address)
        ids.append(s.people.save(person, new_photo=portrait(i) if i != 4 else None).id)

    appts = [
        (0, "09:30", "Reunião de planejamento", "Revisar metas de dezembro", ids[1]),
        (0, "14:00", "Entrega do projeto", "Apresentação acadêmica do Visual Office Manager", None),
        (2, "19:00", "Amigo secreto da equipe", "Levar presente até R$ 80", None),
        (5, "10:00", "Consulta médica", "", ids[0]),
        (9, "16:30", "Compras de Natal", "Shopping — lista de presentes", None),
    ]
    for offset, hhmm, title, desc, pid in appts:
        s.appointments.save(s.appointments.build(title, desc, today + timedelta(days=offset), hhmm, pid))
    xmas = date(today.year, 12, 24)
    s.appointments.save(s.appointments.build("Ceia de Natal", "Jantar em família", xmas, "20:00", ids[3]))

    rnd = random.Random(7)
    for back in range(5, -1, -1):
        y, m = shift_month(today.year, today.month, -back)
        last_day = today.day if back == 0 else 28
        def d(day):
            return date(y, m, min(day, last_day))
        s.finance.save(s.finance.build(INCOME, "Salário", f"{rnd.randint(4800, 5200)},00", "Salário", d(5)))
        if rnd.random() < 0.6:
            s.finance.save(s.finance.build(INCOME, "Projeto freelance", f"{rnd.randint(600, 1500)},00", "Serviços", d(18)))
        for desc, cat, lo, hi, day in [
            ("Aluguel", "Moradia", 1400, 1400, 6), ("Supermercado", "Alimentação", 450, 820, 9),
            ("Conta de luz", "Contas e serviços", 140, 230, 12), ("Internet", "Contas e serviços", 110, 110, 12),
            ("Combustível", "Transporte", 180, 320, 15), ("Farmácia", "Saúde", 40, 160, 17),
            ("Cinema e jantar", "Lazer", 90, 260, 20), ("Curso online", "Educação", 89, 89, 22),
        ]:
            if d(day) <= today:
                s.finance.save(s.finance.build(EXPENSE, desc, f"{rnd.randint(lo, hi)},{rnd.randint(0, 99):02d}", cat, d(day)))
    return True

