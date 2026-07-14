#!/usr/bin/env python3
"""
Publica o Top 10 Gospel da semana na Página do Facebook. Roda segunda de manhã.

O ranking abaixo espelha o que está em radio.html (seção Top 10).
Ao atualizar o Top 10 no site, atualize esta lista também.
"""
from facebook_lib import post_text

# (posição implícita pela ordem) — mesma lista da seção Top 10 do site
TOP10 = [
    ("Se eu Somente Te Tocar", "Nilson Junior"),
    ("Deus de Moisés", "Bruna Karla"),
    ("Que Jesus Seja o Nome", "Aline Freire"),
    ("Quem Poderá? (Ao Vivo)", "Valesca Mayssa"),
    ("Espírito Santo (Inhabit)", "Thalles Roberto"),
    ("Filho Pródigo (Ao Vivo)", "Nilson Junior"),
    ("Oh Vem Me Avivar", "Ana Nóbrega"),
    ("Sou Grato Por Seu Amor", "Get Worship"),
    ("Fiel é Deus", "Isaias Saad"),
    ("Deus Provedor", "Nilson Junior"),
]

MEDALHAS = {1: "🥇", 2: "🥈", 3: "🥉"}

linhas = []
for i, (musica, artista) in enumerate(TOP10, start=1):
    marca = MEDALHAS.get(i, f"{i}.")
    linhas.append(f"{marca} {musica} — {artista}")

mensagem = (
    "🏆 TOP 10 GOSPEL DA SEMANA\n"
    "As mais tocadas na Rádio Encontro de Adoradores 🎶\n\n"
    + "\n".join(linhas)
    + "\n\n🎧 Ouça ao vivo, 24h: https://encontrodeadoradores.com\n\n"
    "#TopGospel #EncontroDeAdoradores #MúsicaGospel"
)

print("Publicando Top 10 da semana")
post_text(mensagem)
