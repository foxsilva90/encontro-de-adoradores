#!/usr/bin/env python3
"""
Funções compartilhadas para publicar na Página do Facebook via Graph API.

Credenciais vêm de variáveis de ambiente (secrets do GitHub Actions):
- FB_PAGE_ID    : ID numérico da Página
- FB_PAGE_TOKEN : token de acesso permanente da Página
                  (permissões pages_manage_posts + pages_read_engagement)

Se as credenciais não estiverem presentes, as funções fazem SKIP em vez de
falhar — assim o workflow não quebra antes dos secrets serem configurados.
"""
import os
import sys
import requests

GRAPH_VERSION = "v21.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"


def _creds():
    page_id = os.environ.get("FB_PAGE_ID")
    token = os.environ.get("FB_PAGE_TOKEN")
    if not page_id or not token:
        print("SKIP: FB_PAGE_ID ou FB_PAGE_TOKEN não configurados.")
        sys.exit(0)
    return page_id, token


def post_text(message):
    """Publica um post só de texto na Página. Retorna o ID do post."""
    page_id, token = _creds()
    url = f"{GRAPH_BASE}/{page_id}/feed"
    data = {"message": message, "access_token": token}
    return _send(url, data)


def post_link(message, link):
    """Publica um post com link (o Facebook gera o preview do link)."""
    page_id, token = _creds()
    url = f"{GRAPH_BASE}/{page_id}/feed"
    data = {"message": message, "link": link, "access_token": token}
    return _send(url, data)


def _send(url, data):
    try:
        r = requests.post(url, data=data, timeout=30)
    except requests.exceptions.RequestException as e:
        print(f"ERRO: falha de conexão com o Facebook ({e})")
        sys.exit(1)

    if r.status_code != 200:
        # Não vaza o token no log de erro.
        print(f"ERRO {r.status_code}: {r.text[:300]}")
        sys.exit(1)

    post_id = r.json().get("id", "?")
    print(f"OK: post publicado ({post_id})")
    return post_id
