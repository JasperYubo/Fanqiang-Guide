"""Presentation-only restructuring for the public guide."""
import re

DESIGN_CSS = "assets/guide-design-v3.0-2026-11-02.css"

def refresh_home(raw):
    # Move the existing search/chat intact into its own first-screen column.
    pattern = r'(<div class="guide-chat" id="guide-chat">.*?</section></div>)'
    chat = re.search(pattern, raw, re.S)
    card = re.search(r'<aside class="start-card".*?</aside>', raw, re.S)
    if not chat or not card:
        raise ValueError("Home search and introduction must remain available")
    chat_html, card_html = chat[0], card[0]
    raw = raw.replace(chat_html, "", 1)
    raw = raw.replace(card_html, '<div class="hero-help">'+chat_html+'</div>', 1)
    marker = '</div></section><section class="autosetup-callout'
    if marker not in raw:
        raise ValueError("Home setup entry boundary missing")
    raw = raw.replace(marker, '</div></section>'+card_html.replace('class="start-card"', 'class="start-card wrap"')+'<section class="autosetup-callout', 1)
    return raw
