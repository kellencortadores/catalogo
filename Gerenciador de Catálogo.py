# -*- coding: utf-8 -*-
"""
Gerador de índices do Catálogo Kellen Cortadores
------------------------------------------------
Estrutura esperada (a raiz é a pasta "Catálogo"):

    Catálogo/
        index-main.html          <- gerado (cards dos temas)
        catalog.json             <- configuração deste programa
        _capas/                  <- imagens copiadas (logo e capas dos cards)
        Natal/
            index-natal.html     <- gerado (cards dos subtemas)
            arvore_de_natal.html ...
        Páscoa/
            index-pascoa.html    <- gerado
            Coelhos.html ...

Uso: python gerador_indices_catalogo.py
"""
import base64
import json
import os
import re
import shutil
import unicodedata
import webbrowser
from html import escape
from pathlib import Path
from urllib.parse import quote
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

# ----------------------------------------------------------------- config
CFG_FILE = Path(__file__).with_name("gerador_indices_catalogo.cfg.json")
CATALOG_FILE = "catalog.json"
MAIN_NAME = "index-main.html"
INDEX_PATTERN = "index-{slug}.html"   # troque para "index.html" se preferir
ASSETS = "_capas"
# Endereço público do catálogo (com / no final). Serve para a prévia no WhatsApp.
# Se deixar vazio, as páginas saem sem a prévia com imagem.
SITE_URL = "https://kellencortadores.github.io/catalogo/"
SHARE_NAME = "compartilhar"   # imagem gerada para a prévia (ex.: compartilhar.jpg)
MARK_A, MARK_B = "<!--VOLTAR-MAIN-->", "<!--/VOLTAR-MAIN-->"
IMG_TYPES = [("Imagens", "*.png *.jpg *.jpeg *.webp *.gif"), ("Todos", "*.*")]


# ---------------------------------------------------------------- helpers
def slugify(txt):
    txt = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", txt.lower()).strip("-") or "tema"


def url(path_from, path_to):
    """Caminho relativo (com / e escapado) de uma pasta até um arquivo."""
    rel = os.path.relpath(path_to, path_from).replace("\\", "/")
    return quote(rel, safe="/")


def pretty_title(stem):
    stem = re.sub(r"\.html?$", "", stem, flags=re.I)  # "x.html.html"
    if "_" not in stem:
        return stem[:1].upper() + stem[1:]
    small = {"de", "da", "do", "das", "dos", "e", "a", "o"}
    words = stem.replace("_", " ").split()
    return " ".join(w if (i and w in small) else w.capitalize()
                    for i, w in enumerate(words))


def scan_subpages(folder):
    out = []
    for f in sorted(Path(folder).glob("*.htm*"), key=lambda p: p.name.lower()):
        if f.name.lower().startswith("index"):
            continue
        out.append(f)
    return out


def read_text(path):
    for enc in ("utf-8", "cp1252"):
        try:
            return Path(path).read_text(encoding=enc), enc
        except UnicodeDecodeError:
            continue
    return Path(path).read_text(encoding="utf-8", errors="replace"), "utf-8"


def first_image_of(html_path):
    """Primeira <img> local da subpágina (usada como capa automática)."""
    try:
        txt, _ = read_text(html_path)
    except OSError:
        return None
    for m in re.finditer(r"<img[^>]+src=[\"']([^\"']+)[\"']", txt, re.I):
        src = m.group(1)
        if src.startswith(("http", "data:", "//")):
            continue
        p = (Path(html_path).parent / Path(src.replace("%20", " "))).resolve()
        if p.exists():
            return p
    return None


def copy_asset(src, dest_dir, new_stem):
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / (new_stem + Path(src).suffix.lower())
    if Path(src).resolve() != dest.resolve():
        shutil.copy2(src, dest)
    return dest


def make_share_image(src, dest_dir, bg_hex, banner=False, name=None):
    """Cria compartilhar.jpg (1200x630). src = caminho ou bytes.
    banner=True: a imagem ocupa a largura toda e as sobras de cima e de baixo
    são completadas esticando a borda da própria imagem."""
    import io
    dest_dir = Path(dest_dir)
    try:
        from PIL import Image
        with Image.open(io.BytesIO(src) if isinstance(src, bytes) else src) as im:
            im = im.convert("RGBA")
            if banner:
                im = im.resize((1200, max(1, round(im.height * 1200 / im.width))))
                if im.height > 630:
                    top = (im.height - 630) // 2
                    im = im.crop((0, top, 1200, top + 630))
                base = Image.new("RGBA", im.size, "white")
                base.alpha_composite(im)
                im = base.convert("RGB")
                canvas = Image.new("RGB", (1200, 630))
                y = (630 - im.height) // 2
                if y > 0:
                    canvas.paste(im.crop((0, 0, 1200, 1)).resize((1200, y)), (0, 0))
                    canvas.paste(im.crop((0, im.height - 1, 1200, im.height)).resize((1200, 630 - y - im.height)), (0, y + im.height))
                canvas.paste(im, (0, y))
            else:
                im.thumbnail((1040, 550))
                canvas = Image.new("RGB", (1200, 630), bg_hex)
                canvas.paste(im, ((1200 - im.width) // 2, (630 - im.height) // 2), im)
            dest = dest_dir / ((name or SHARE_NAME) + ".jpg")
            canvas.save(dest, "JPEG", quality=85)
            return dest
    except Exception:
        pass
    try:   # sem Pillow: usa a imagem original
        if isinstance(src, bytes):
            dest = dest_dir / ((name or SHARE_NAME) + ".png")
            dest.write_bytes(src)
        else:
            dest = dest_dir / ((name or SHARE_NAME) + Path(src).suffix.lower())
            shutil.copy2(src, dest)
        return dest
    except Exception:
        return None


_URI_CACHE = {}


def data_uri(path, max_side=420):
    """Imagem embutida no HTML (base64). Reduz o tamanho se o Pillow estiver instalado."""
    path = Path(path)
    try:
        key = (str(path), path.stat().st_mtime)
    except OSError:
        return ""
    if key in _URI_CACHE:
        return _URI_CACHE[key]
    mime, raw = None, None
    try:
        from PIL import Image
        import io
        with Image.open(path) as im:
            im.thumbnail((max_side, max_side))
            buf = io.BytesIO()
            if im.mode in ("RGBA", "LA", "P"):
                im.convert("RGBA").save(buf, "WEBP", quality=85)
            else:
                im.convert("RGB").save(buf, "WEBP", quality=85)
            mime, raw = "image/webp", buf.getvalue()
    except Exception:
        pass
    if raw is None:
        ext = path.suffix.lower().lstrip(".")
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "svg": "image/svg+xml"}.get(ext, "image/" + (ext or "png"))
        try:
            raw = path.read_bytes()
        except OSError:
            return ""
    uri = "data:%s;base64,%s" % (mime, base64.b64encode(raw).decode("ascii"))
    _URI_CACHE[key] = uri
    return uri


# ------------------------------------------------------------------- HTML
CSS = """
*{box-sizing:border-box}
body{margin:0;font-family:'Segoe UI',Arial,sans-serif;background:var(--bg);color:var(--txt)}
header{position:relative;overflow:hidden;text-align:center;padding:24px 10px 84px;
 background:linear-gradient(120deg,var(--h1),var(--h2),var(--h3),var(--h2),var(--h1));
 background-size:300% 300%;animation:bg 14s ease-in-out infinite}
@keyframes bg{0%,100%{background-position:0 50%}50%{background-position:100% 50%}}
.hin{position:relative;z-index:2}
.deco{position:absolute;inset:0;z-index:1;pointer-events:none}
.deco svg{position:absolute;fill:currentColor;overflow:visible}
.f{opacity:.55;animation:flt var(--d,7s) ease-in-out var(--l,0s) infinite}
@keyframes flt{0%,100%{transform:translateY(0) rotate(var(--a,-8deg))}
 50%{transform:translateY(-16px) rotate(var(--b,8deg))}}
.sp{color:var(--spk);animation:tw 2.6s ease-in-out var(--l,0s) infinite}
@keyframes tw{0%,100%{transform:scale(.2) rotate(0);opacity:0}
 50%{transform:scale(1) rotate(90deg);opacity:1}}
.wave{position:absolute;left:-5%;bottom:-1px;width:110%;height:46px;z-index:3;display:block}
.wave.w1{fill:var(--w1);height:56px;animation:sway 9s ease-in-out infinite}
.wave.w2{fill:var(--bg);animation:sway 6s ease-in-out infinite reverse}
@keyframes sway{0%,100%{transform:translateX(-3%)}50%{transform:translateX(3%)}}
.logo-w{position:relative;display:inline-block;animation:pop .7s cubic-bezier(.2,.9,.3,1.4) both}
.logo-w::before{content:"";position:absolute;inset:-9px;border-radius:50%;
 border:2px dashed var(--c1);opacity:.55;animation:spin 20s linear infinite}
.logo-w::after{content:"";position:absolute;inset:-2px;border-radius:50%;
 box-shadow:0 0 0 0 rgba(var(--rgb),.35);animation:pulse 2.8s ease-out infinite}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes pulse{to{box-shadow:0 0 0 26px rgba(var(--rgb),0)}}
.logo{display:block;width:140px;height:140px;border-radius:50%;
 object-fit:cover;box-shadow:0 4px 14px rgba(var(--rgb),.3);
 animation:bob 4.5s ease-in-out infinite}
@keyframes bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}
@keyframes pop{from{opacity:0;transform:scale(.6)}}
@keyframes up{from{opacity:0;transform:translateY(14px)}}
h1{margin:12px 0 2px;font-size:2.1rem;color:var(--c1);
 background:linear-gradient(90deg,var(--c1) 0%,var(--c1) 30%,var(--c3) 50%,var(--c1) 70%,var(--c1) 100%);background-size:250% 100%;
 -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;
 animation:up .8s .1s both,shine 6s linear infinite}
@keyframes shine{to{background-position:250% 0}}
.sub{margin:0;letter-spacing:.5px;animation:up .8s .3s both}
.sub::before,.sub::after{content:"✦";color:var(--c2);margin:0 10px;display:inline-block;
 animation:tw 2.6s ease-in-out infinite}
.sub::after{animation-delay:1.3s}
@media(max-width:640px){.deco .f:nth-child(n+5){display:none}.f{opacity:.35}
 h1{font-size:1.6rem}}
@media(prefers-reduced-motion:reduce){*{animation:none!important}.sp{opacity:1}}
.search{display:block;margin:-28px auto 0;width:min(600px,90%);padding:16px 22px;
 font-size:1.05rem;border:3px solid var(--c2);border-radius:40px;outline:none;
 box-shadow:0 4px 12px rgba(0,0,0,.12);position:relative;z-index:5;background:#fff}
.count{text-align:center;margin:18px 0 12px;font-size:.95rem}
.grid{display:flex;flex-wrap:wrap;gap:16px;justify-content:center;
 max-width:1250px;margin:0 auto;padding:0 16px 40px}
.card{animation:pop .5s cubic-bezier(.2,.9,.3,1.3) backwards;width:200px;background:#fff;border-radius:18px;text-decoration:none;
 color:inherit;text-align:center;padding-bottom:12px;overflow:hidden;
 box-shadow:0 3px 10px rgba(var(--rgb),.12);transition:transform .15s}
.card:hover{transform:translateY(-4px)}
.card .img{height:195px;background:var(--img);display:flex;align-items:center;justify-content:center}
.card img{max-width:100%;max-height:100%;object-fit:contain;transition:transform .25s}
.card:hover img{transform:rotate(-3deg) scale(1.06)}
.card b{display:block;color:var(--c1);font-size:1.1rem;margin-top:10px}
.card small{color:#8a6a75}
.back{position:fixed;top:10px;left:10px;z-index:50;background:var(--c1);color:#fff;
 text-decoration:none;font-weight:700;padding:10px 18px;border-radius:30px;
 box-shadow:0 3px 10px rgba(0,0,0,.25)}
.back:hover{background:var(--c2)}
"""

JS = """
const q=document.getElementById('q'),cards=[...document.querySelectorAll('.card')],
 c=document.getElementById('count'),word=c.dataset.word;
function f(){const t=q.value.toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'');
 let n=0;cards.forEach(k=>{const s=k.dataset.t.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'');
 const ok=s.includes(t);k.style.display=ok?'':'none';if(ok)n++});
 c.textContent=n+' '+word}
cards.forEach((k,i)=>k.style.animationDelay=Math.min(i*40,600)+'ms');
q.addEventListener('input',f);f();
"""


# ------------------------------------------------- formas e dicionário de temas
# Formas de cortadores/biscoitos desenhadas em SVG (nenhum arquivo externo)
SHAPES = {
    'heart': r'''<path d="M50 90C10 60 4 32 22 19c12-8 24-3 28 9 4-12 16-17 28-9 18 13 12 41-28 71z"/>''',
    'star': r'''<path d="M50 5l12 32h34L68 58l11 35-29-21-29 21 11-35L4 37h34z"/>''',
    'house': r'''<path fill-rule="evenodd" d="M50 8l44 38H80v44H20V46H6zM42 90V62h16v28z"/>''',
    'flower': r'''<circle cx="76" cy="50" r="17"/><circle cx="63" cy="73" r="17"/><circle cx="37" cy="73" r="17"/><circle cx="24" cy="50" r="17"/><circle cx="37" cy="27" r="17"/><circle cx="63" cy="27" r="17"/><circle cx="50" cy="50" r="16"/>''',
    'cookie': r'''<path fill-rule="evenodd" d="M14 50a36 36 0 1 0 72 0a36 36 0 1 0-72 0zM33 38a5 5 0 1 0 10 0a5 5 0 1 0-10 0zM57 42a5 5 0 1 0 10 0a5 5 0 1 0-10 0zM40 62a5 5 0 1 0 10 0a5 5 0 1 0-10 0zM60 64a5 5 0 1 0 10 0a5 5 0 1 0-10 0z"/>''',
    'man': r'''<circle cx="50" cy="17" r="14"/><rect x="34" y="33" width="32" height="32" rx="12"/><path d="M38 42L16 54M62 42l22 12M43 64L33 90M57 64l10 26" stroke="currentColor" stroke-width="14" stroke-linecap="round" fill="none"/>''',
    'spark': r'''<path d="M50 0Q54 46 100 50Q54 54 50 100Q46 54 0 50Q46 46 50 0z"/>''',
    'tree': r'''<path d="M50 4L74 34H62L84 60H68L92 84H8L32 60H16L38 34H26z"/><rect x="43" y="84" width="14" height="12" rx="2"/>''',
    'bell': r'''<path d="M50 6a6 6 0 0 1 6 6v3c14 4 22 16 22 32v16l8 10H14l8-10V47c0-16 8-28 22-32v-3a6 6 0 0 1 6-6z"/><path d="M40 84a10 10 0 0 0 20 0z"/>''',
    'cane': r'''<path d="M58 94V36a17 17 0 0 0-34 0v6" stroke-width="14" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" fill="none"/>''',
    'snowflake': r'''<path d="M50 8V92M14 29L86 71M14 71L86 29M38 14l12 10 12-10M38 86l12-10 12 10" stroke-width="8" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" fill="none"/>''',
    'gift': r'''<path d="M10 34h80v18H10zM16 56h68v36H16z"/><path d="M50 34C28 34 20 14 34 11c10-2 16 10 16 23zM50 34C72 34 80 14 66 11c-10-2-16 10-16 23z"/>''',
    'rabbit': r'''<ellipse cx="36" cy="26" rx="9" ry="23"/><ellipse cx="64" cy="26" rx="9" ry="23"/><circle cx="50" cy="66" r="28"/>''',
    'egg': r'''<path d="M50 5C72 5 86 40 86 63a36 32 0 0 1-72 0C14 40 28 5 50 5z"/>''',
    'carrot': r'''<path d="M50 34C40 22 34 14 30 6c12 2 18 8 20 18 2-10 8-16 20-18-4 8-10 16-20 28z"/><path d="M30 38Q50 30 70 38L50 96z"/>''',
    'pumpkin': r'''<ellipse cx="30" cy="60" rx="20" ry="30"/><ellipse cx="70" cy="60" rx="20" ry="30"/><ellipse cx="50" cy="60" rx="20" ry="32"/><path d="M44 12h10l4 16H42z"/>''',
    'ghost': r'''<path fill-rule="evenodd" d="M16 92V44C16 22 28 6 50 6s34 16 34 38v48l-11-9-12 9-11-9-11 9-12-9zM34 40a6 8 0 1 0 12 0a6 8 0 1 0-12 0zM54 40a6 8 0 1 0 12 0a6 8 0 1 0-12 0z"/>''',
    'bat': r'''<path d="M50 28L56 14L60 30C72 20 90 20 98 28C92 36 94 46 92 56C84 50 76 52 70 60C66 54 58 52 50 56z"/><path d="M50 28L56 14L60 30C72 20 90 20 98 28C92 36 94 46 92 56C84 50 76 52 70 60C66 54 58 52 50 56z" transform="translate(100 0) scale(-1 1)"/>''',
    'sun': r'''<circle cx="50" cy="50" r="20"/><path d="M50 8v14M50 78v14M8 50h14M78 50h14M20 20l10 10M70 70l10 10M80 20L70 30M30 70L20 80" stroke-width="8" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" fill="none"/>''',
    'flag': r'''<path d="M10 14h80L50 88z"/>''',
    'corn': r'''<ellipse cx="50" cy="42" rx="17" ry="38"/><path d="M50 94C28 94 16 72 18 48c10 12 22 18 32 18zM50 94c22 0 34-22 32-46-10 12-22 18-32 18z"/>''',
    'flame': r'''<path d="M50 4c4 20 28 32 28 56a28 28 0 0 1-56 0c0-14 8-22 14-32 2 8 6 12 10 12-2-14-2-22 4-36z"/>''',
    'balloon': r'''<ellipse cx="50" cy="38" rx="28" ry="33"/><path d="M44 70h12l-6 9z"/><path d="M50 79q-9 8 0 17" stroke-width="3" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" fill="none"/>''',
    'cake': r'''<path d="M12 56h76v34H12zM22 34h56v18H22zM46 8h8v22h-8z"/>''',
    'hat': r'''<path d="M50 10L84 90H16z"/><circle cx="50" cy="9" r="7"/>''',
    'mask': r'''<path fill-rule="evenodd" d="M8 30c14-8 28-8 42 0 14-8 28-8 42 0 0 24-8 40-26 40-8 0-12-6-16-12-4 6-8 12-16 12-18 0-26-16-26-40zM22 42a10 7 0 1 0 20 0a10 7 0 1 0-20 0zM58 42a10 7 0 1 0 20 0a10 7 0 1 0-20 0z"/>''',
    'note': r'''<ellipse cx="30" cy="78" rx="16" ry="12"/><ellipse cx="72" cy="68" rx="16" ry="12"/><path d="M40 78V22l44-10v56h-8V24l-28 7v47z"/>''',
    'ball': r'''<path fill-rule="evenodd" d="M50 6a44 44 0 1 0 0 88a44 44 0 1 0 0-88zM50 32l16 12-6 19H40l-6-19z"/>''',
    'trophy': r'''<path d="M28 8h44v30c0 16-10 26-22 26S28 54 28 38z"/><path d="M28 16H12c0 16 6 24 18 26M72 16h16c0 16-6 24-18 26" stroke-width="6" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" fill="none"/><rect x="43" y="62" width="14" height="14"/><rect x="28" y="78" width="44" height="14" rx="3"/>''',
    'pencil': r'''<path d="M68 6l26 26-12 12-26-26zM54 20l26 26-46 46-30 8 8-30z"/>''',
    'book': r'''<path d="M6 20c16-6 30-6 44 4v66C36 80 22 80 6 86zM94 20c-16-6-30-6-44 4v66c14-10 28-10 44-4z"/>''',
    'tie': r'''<path d="M38 6h24l-4 16H42z"/><path d="M42 26h16l12 58-20 12-20-12z"/>''',
    'cap': r'''<path d="M50 14L96 38 50 62 4 38z"/><path d="M24 52v20c0 10 52 10 52 0V52L50 66z"/>''',
    'cross': r'''<path d="M40 6h20v30h30v20H60v38H40V56H10V36h30z"/>''',
    'cloud': r'''<path d="M26 74a18 18 0 0 1 2-36 24 24 0 0 1 46-4 20 20 0 0 1 2 40z"/>''',
    'ribbon': r'''<path d="M50 56C26 40 8 18 22 8c14-8 26 10 28 48zM50 56C74 40 92 18 78 8c-14-8-26 10-28 48z"/><path d="M50 52L26 94h18l6-20 6 20h18z"/>''',
    'leaf': r'''<path d="M10 90C6 46 34 12 92 8c2 54-28 82-82 82z"/>''',
    'crown': r'''<path d="M8 84V24l26 30 16-36 16 36 26-30v60z"/>''',
    'fish': r'''<path d="M6 50C24 22 56 22 72 50 56 78 24 78 6 50z"/><path d="M68 50L94 28v44z"/>''',
    'paw': r'''<ellipse cx="50" cy="68" rx="22" ry="18"/><circle cx="20" cy="46" r="9"/><circle cx="38" cy="28" r="9"/><circle cx="62" cy="28" r="9"/><circle cx="80" cy="46" r="9"/>''',
    'rainbow': r'''<path d="M8 78a42 42 0 0 1 84 0M24 78a26 26 0 0 1 52 0" stroke-width="12" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" fill="none"/>''',
}

# Ordem de cores usada nas formas flutuantes: a=cor1, b=cor2, c=cor3, w=branco
THEME_COLS = ["a", "c", "b", "w", "a", "b", "c", "w"]
DEFAULT_PAL = {
    "label": "padrão", "c1": "#d6203f", "c2": "#ff5a7e", "c3": "#ff8fb3",
    "bg": "#ffeefa", "h": ("#ffc2ee", "#ffd9e6", "#ffb3d9"), "img": "#fde3ef",
    "txt": "#7a2a45", "spk": "#fff", "w1": "rgba(255,255,255,.55)",
    "shapes": ["heart", "man", "star", "house", "flower", "cookie", "star", "heart"],
    "cols": ["a", "a", "w", "a", "w", "a", "w", "w"],
}

# Cada linha: (nome, palavras que o programa reconhece no nome do tema (regex, sem acento),
#              cor1 = títulos e botões, cor2 = detalhes, cor3 = brilho,
#              fundo da página, (3 tons do cabeçalho), fundo da imagem dos cards,
#              cor do texto, formas, [ajustes extras])
# A primeira linha que combinar vence; por isso as mais específicas vêm antes.
# Para criar um tema novo, copie uma linha e mude as palavras, cores e formas.
THEMES = [
    ("Natal", r"natal\b|natalin|noel|presepio", "#c1121f", "#2e7d32", "#d4a017", "#fff8ee",
     ("#ffe3e0", "#e3f3e0", "#fff0c2"), "#fdeedd", "#5a2a1f",
     ["tree", "star", "man", "bell", "cane", "snowflake", "gift"], {"spk": "#e0b100"}),
    ("Páscoa", r"pascoa|coelh", "#8e44ad", "#e56fb0", "#f4a6d7", "#fbf3ff",
     ("#ead7ff", "#ffd9ee", "#f3e3ff"), "#f5e6ff", "#5b3a72",
     ["rabbit", "egg", "carrot", "flower"]),
    ("Dia das Mães", r"maes?\b|mamae", "#c2185b", "#f06292", "#ffab91", "#fff1f3",
     ("#ffd1dc", "#ffe3d6", "#ffc9e0"), "#ffe4ea", "#6b2840",
     ["flower", "heart", "spark", "star"]),
    ("Dia dos Pais", r"pais\b|papai", "#1e4e8c", "#3b82c4", "#f2b134", "#eef5fc",
     ("#cfe3f7", "#e3eefa", "#bcd7f1"), "#e1edf9", "#1f3a5c",
     ["tie", "star", "trophy", "cookie"]),
    ("Dia dos Namorados", r"namorad|\bamor|cupido|apaixon", "#b3122f", "#ff4d6d", "#ff9bb0", "#fff0f3",
     ("#ffd0d9", "#ffe0e6", "#ffc2cf"), "#ffe1e7", "#6a1a2c",
     ["heart", "flower", "spark", "heart"]),
    ("Dia das Crianças", r"crianc|infantil|kids", "#e8590c", "#1c7ed6", "#f5b700", "#fffbea",
     ("#ffe8cc", "#d0ebff", "#fff3bf"), "#fff4d6", "#5c3b12",
     ["balloon", "star", "cookie", "hat", "rainbow"]),
    ("Dia dos Professores", r"professor|mestre|docente", "#2b6e4f", "#d97706", "#f2c94c", "#f3faf5",
     ("#d3efdc", "#fdf0c9", "#c8e6d2"), "#e3f4e9", "#1f4a36",
     ["pencil", "book", "star", "cap"]),
    ("Dia da Mulher", r"mulher|mulheres|feminin", "#8e24aa", "#e91e63", "#ffb300", "#fbf2fd",
     ("#f1d4f7", "#ffd6e4", "#ffe9b0"), "#f6e4fa", "#58206a",
     ["flower", "heart", "spark", "crown"]),
    ("Festa Junina", r"junin|sao joao|arraial|quadrilha|caipira", "#c0392b", "#e67e22", "#f1c40f", "#fff6e5",
     ("#ffe0b2", "#ffd6d0", "#fff0b3"), "#ffecc9", "#6a2f12",
     ["flag", "corn", "flame", "star", "cookie"]),
    ("Halloween", r"halloween|bruxa|terror|assombr|monstro", "#e0620a", "#a855f7", "#9be15d", "#2b1b3d",
     ("#3b2354", "#4a2b6b", "#2f1c45"), "#f6ecff", "#f3e5ff",
     ["pumpkin", "ghost", "bat", "star"], {"spk": "#ffd27a", "w1": "rgba(255,255,255,.12)"}),
    ("Aniversário", r"aniversari|parabens|niver|bolo|festinha", "#d6336c", "#1c9bd7", "#fcc419", "#fff5fb",
     ("#ffd6e8", "#d6f0ff", "#fff0b8"), "#ffe6f1", "#6b2a48",
     ["balloon", "cake", "hat", "star", "gift"]),
    ("Carnaval", r"carnaval|folia|fantasia|baile", "#7b1fa2", "#00a86b", "#ffc107", "#fbf1ff",
     ("#e8c7ff", "#c7f5df", "#fff0b0"), "#f3e2ff", "#4d1a63",
     ["mask", "note", "star", "hat"]),
    ("Copa / Brasil", r"copa\b|futebol|brasil|selecao|mundial|torcida|independencia|patria", "#1b8a3a", "#0b4fa3", "#f6c500", "#f1fbef",
     ("#c9f0c4", "#fff3a8", "#c5dcf7"), "#e1f6dd", "#1c4a27",
     ["ball", "trophy", "star", "flag"]),
    ("Volta às aulas", r"aulas|escola|escolar|estudante|colegio", "#1d4ed8", "#f59e0b", "#f87171", "#f1f6ff",
     ("#cfe0ff", "#ffeccb", "#d5e7ff"), "#e0ebff", "#1f3166",
     ["pencil", "book", "star", "cloud"]),
    ("Ano Novo", r"ano novo|reveillon|virada", "#8a6d00", "#475569", "#d4af37", "#fbf8ee",
     ("#f3ead0", "#e3e8ef", "#f7edc0"), "#f5efd8", "#4a3f12",
     ["star", "trophy", "balloon", "bell"], {"spk": "#d4af37"}),
    ("Outubro Rosa", r"outubro rosa|laco rosa", "#d6336c", "#ff7aa8", "#ffb3cf", "#fff0f6",
     ("#ffd3e4", "#ffe3ee", "#ffc4da"), "#ffe3ee", "#6b2a48",
     ["ribbon", "heart", "flower", "spark"]),
    ("Novembro Azul", r"novembro azul|saude do homem", "#1c5db5", "#4aa3e8", "#9ad0f5", "#eef6ff",
     ("#cfe3fa", "#e1effc", "#bcd9f5"), "#dcebfb", "#1b3a66",
     ["ribbon", "star", "tie", "heart"]),
    ("Bebê / Chá", r"bebe|cha revelacao|maternidade|gestante|recem nascid|baby", "#4a90c2", "#f48fb1", "#ffd966", "#f4faff",
     ("#d6ecff", "#ffe0ec", "#fff3c4"), "#e4f2ff", "#2e4a63",
     ["cloud", "star", "heart", "cookie", "balloon"]),
    ("Casamento", r"casamento|noiv|nupcia|bodas|cha de panela", "#a8556b", "#c9a227", "#e8c4cf", "#fffaf6",
     ("#fde8ec", "#f6ecd4", "#f9e0e6"), "#fbe9ed", "#5e3140",
     ["heart", "flower", "spark", "bell"]),
    ("Formatura", r"formatura|formando|graduacao|diploma|concluin", "#14213d", "#c9a227", "#8d99ae", "#f4f6fb",
     ("#d9e1f2", "#f5ecc8", "#cfd8ea"), "#e3e9f5", "#14213d",
     ["cap", "star", "book", "trophy"]),
    ("Religioso", r"batizad|batismo|comunhao|crisma|eucaristia|religios|igreja", "#3b6fb6", "#c9a227", "#a8c8ee", "#f5f9ff",
     ("#d9e8fb", "#f6ecc8", "#cfe0f6"), "#e4eefb", "#25416b",
     ["cross", "star", "cloud", "heart"]),
    ("Verão / Praia", r"verao|praia|piscina|ferias|tropical|sol\b", "#e67700", "#0ca5c8", "#ffd43b", "#fffbe8",
     ("#ffe9a8", "#c9f0f7", "#ffd9b0"), "#fff3cc", "#6a3f0a",
     ["sun", "fish", "flower", "star"]),
    ("Primavera / Flores", r"primavera|flores|jardim|floral|borboleta", "#2f9e44", "#e64980", "#fcc419", "#f6fff3",
     ("#d3f9d8", "#ffdeeb", "#fff3bf"), "#e5fbe8", "#24502e",
     ["flower", "leaf", "spark", "heart"]),
    ("Outono", r"outono", "#b45309", "#d97706", "#f2a65a", "#fff7ed",
     ("#fde4c4", "#fbd9b5", "#fff0c9"), "#fdebd3", "#5e3510",
     ["leaf", "pumpkin", "cookie", "star"]),
    ("Inverno", r"inverno|frio|neve", "#2563a8", "#5aa9e6", "#9ad0f5", "#f0f8ff",
     ("#d4e9fb", "#e6f3ff", "#c4def5"), "#e2f0fc", "#1d3b5e",
     ["snowflake", "star", "cloud", "cookie"]),
    ("Princesa", r"princesa|realeza|rainha|castelo|coroa|principe|rei\b", "#a64ac9", "#f06ca8", "#ffc857", "#fdf3ff",
     ("#f0d5ff", "#ffd9ec", "#ffeab3"), "#f7e5ff", "#5a2a70",
     ["crown", "heart", "star", "flower"]),
    ("Sereia / Fundo do mar", r"sereia|fundo do mar|oceano|marinho|peixe|mar\b", "#0f8b8d", "#9b5de5", "#5fd3bc", "#effcfb",
     ("#bff1ee", "#e3d3fb", "#c9f5ee"), "#dcf7f4", "#0f4a4b",
     ["fish", "star", "heart", "flower"]),
    ("Safari / Bichinhos", r"safari|animais|bichinho|dinossauro|fazend|zoo|pets?\b|cachorro|gato", "#5f7a1f", "#c77d2a", "#f2c14e", "#f8f9ec",
     ("#e0ebc2", "#f6e3c2", "#eef2c5"), "#eef3d6", "#3a4a12",
     ["paw", "leaf", "star", "cookie"]),
    ("Circo", r"circo|palhaco|carrossel", "#d62828", "#1d6fd1", "#f4b400", "#fff7ec",
     ("#ffd6d0", "#d3e5ff", "#fff0b3"), "#ffe9d6", "#6a1a1a",
     ["hat", "balloon", "star", "mask"]),
    ("Unicórnio / Magia", r"unicornio|arco iris|magia|fada|encant", "#9d4edd", "#ff70a6", "#70d6ff", "#fcf4ff",
     ("#f0d5ff", "#ffd9ec", "#d4f0ff"), "#f6e6ff", "#512a73",
     ["rainbow", "star", "heart", "cloud"]),
    ("Dia dos Avós", r"avos?\b|vovo", "#a1473a", "#d08a3c", "#e9c46a", "#fff6ee",
     ("#fde1d3", "#f9e4c0", "#fbe9c8"), "#fde9da", "#5e2a22",
     ["heart", "flower", "house", "cookie"]),
    ("Amizade", r"amigo|amiga|amizade", "#e8590c", "#12a4b8", "#fcc419", "#fff8ec",
     ("#ffe3c9", "#cdf3f8", "#fff1b8"), "#ffeddb", "#6a3210",
     ["heart", "star", "cookie", "man"]),
    ("Saúde / Profissões", r"saude|enfermag|medic|dentist|hospital|doutor", "#0b7a75", "#3b82c4", "#8ad1c2", "#f0fbf9",
     ("#c9f0ea", "#d6e8f9", "#c0ece3"), "#dcf5f1", "#0f4a47",
     ["cross", "heart", "star", "cookie"]),
]


def _norm(txt):
    txt = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", txt.lower()).strip()


def match_theme(name):
    """Reconhece palavras no nome do tema e devolve a paleta pronta (ou a padrão)."""
    n = _norm(name)
    for row in THEMES:
        label, pat, c1, c2, c3, bg, h, img, txt, shapes = row[:10]
        if re.search(r"\b(?:" + pat + ")", n):
            pal = dict(DEFAULT_PAL, label=label, c1=c1, c2=c2, c3=c3, bg=bg, h=h,
                       img=img, txt=txt, shapes=shapes, cols=THEME_COLS)
            if len(row) > 10:
                pal.update(row[10])
            return pal
    return dict(DEFAULT_PAL)


def _rgb(hexcolor):
    h = hexcolor.lstrip("#")
    return ",".join(str(int(h[i:i + 2], 16)) for i in (0, 2, 4))


def css_vars(pal):
    return (":root{--c1:%s;--c2:%s;--c3:%s;--bg:%s;--h1:%s;--h2:%s;--h3:%s;--img:%s;"
            "--txt:%s;--spk:%s;--w1:%s;--rgb:%s}" % (
                pal["c1"], pal["c2"], pal["c3"], pal["bg"], *pal["h"], pal["img"],
                pal["txt"], pal["spk"], pal["w1"], _rgb(pal["c1"])))


# posições das formas flutuantes: (esq%, topo%, tamanho, duração, atraso, ang1, ang2)
SLOTS = [(5, 14, 56, 7, 0, -10, 8), (22, 8, 62, 8.5, -2, 6, -9), (15, 56, 38, 6, -1, -8, 8),
         (83, 12, 58, 7.5, -3, 8, -6), (72, 54, 46, 9, -4, -8, 8), (91, 50, 50, 6.5, -2.5, -8, 8),
         (68, 6, 30, 5.5, -1.5, -8, 8), (3, 62, 32, 8, -5, -8, 8)]
SPARKS = [(12, 30, 18, 0), (30, 68, 14, .8), (60, 24, 16, 1.6),
          (78, 70, 20, .4), (93, 28, 14, 2), (44, 10, 12, 1.2)]
WAVES = (
    '<svg class="wave w1" viewBox="0 0 1440 60" preserveAspectRatio="none"><path d="M0 28C160 62 340 6 540 30s380 34 560 6 240-14 340-2v28H0z"/></svg>\n'
    '<svg class="wave w2" viewBox="0 0 1440 60" preserveAspectRatio="none"><path d="M0 38C200 6 380 56 600 34s420-30 600-8 180 14 240 8v28H0z"/></svg>')


def build_deco(pal):
    names = pal["shapes"]
    used = sorted(set(names) | {"spark"})
    defs = "".join(f'<symbol id="s-{n}" viewBox="0 0 100 100">{SHAPES[n]}</symbol>' for n in used)
    colors = {"a": pal["c1"], "b": pal["c2"], "c": pal["c3"], "w": "#fff"}
    out = ['<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>'
           + defs + '</defs></svg>', '<div class="deco" aria-hidden="true">']
    for i, (x, y, s, d, l, a, b) in enumerate(SLOTS):
        col = colors[pal["cols"][i % len(pal["cols"])]]
        out.append(f'<svg class="f" style="left:{x}%;top:{y}%;width:{s}px;height:{s}px;color:{col};'
                   f'--d:{d}s;--l:{l}s;--a:{a}deg;--b:{b}deg"><use href="#s-{names[i % len(names)]}"/></svg>')
    for x, y, s, l in SPARKS:
        out.append(f'<svg class="sp" style="left:{x}%;top:{y}%;width:{s}px;height:{s}px;--l:{l}s">'
                   f'<use href="#s-spark"/></svg>')
    out.append("</div>")
    out.append(WAVES)
    return "\n".join(out)


def build_page(title, subtitle, logo_url, cards, back_url, placeholder, count_word,
               pal=None, og=None):
    pal = pal or DEFAULT_PAL
    og_tags = ""
    if og:
        og_tags = (
            '<meta property="og:type" content="website">'
            f'<meta property="og:title" content="{escape(og["title"], True)}">'
            f'<meta property="og:description" content="{escape(og["desc"], True)}">'
            f'<meta property="og:url" content="{escape(og["url"], True)}">'
            + (f'<meta property="og:image" content="{escape(og["image"], True)}">'
               '<meta name="twitter:card" content="summary_large_image">' if og.get("image") else ""))
    items = []
    for ctitle, csub, img_url, href in cards:
        img = (f'<img src="{img_url}" alt="{escape(ctitle)}">' if img_url
               else '<span style="font-size:3rem">🍪</span>')
        items.append(
            f'<a class="card" href="{href}" data-t="{escape(ctitle.lower())}">'
            f'<div class="img">{img}</div><b>{escape(ctitle)}</b>'
            f'<small>{escape(csub)}</small></a>')
    back = (f'<a class="back" href="{back_url}">← Temas</a>' if back_url else "")
    logo = (f'<div class="logo-w"><img class="logo" src="{logo_url}" alt="logo"></div>'
            if logo_url else "")
    return f"""<!DOCTYPE html>
<html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title>{og_tags}<style>{css_vars(pal)}{CSS}</style></head><body>
{back}
<header>{build_deco(pal)}<div class="hin">{logo}<h1>{escape(title)}</h1><p class="sub">{escape(subtitle)}</p></div></header>
<input id="q" class="search" type="search" placeholder="🔍 {escape(placeholder)}">
<div id="count" class="count" data-word="{count_word}"></div>
<div class="grid">{''.join(items)}</div>
<script>{JS}</script></body></html>"""


def inject_back_button(html_file, main_href, index_href, theme_name, pal=None):
    pal = pal or DEFAULT_PAL
    txt, enc = read_text(html_file)
    txt = re.sub(re.escape(MARK_A) + r".*?" + re.escape(MARK_B), "", txt, flags=re.S)
    block = (
        f'{MARK_A}<div style="position:fixed;top:10px;left:10px;z-index:99999;'
        f'display:flex;gap:6px;font-family:Segoe UI,Arial,sans-serif">'
        f'<a href="{main_href}" style="background:{pal["c1"]};color:#fff;text-decoration:none;'
        f'font-weight:700;padding:9px 14px;border-radius:30px;box-shadow:0 2px 8px rgba(0,0,0,.3)">'
        f'🏠 Temas</a>'
        f'<a href="{index_href}" style="background:{pal["c2"]};color:#fff;text-decoration:none;'
        f'font-weight:700;padding:9px 14px;border-radius:30px;box-shadow:0 2px 8px rgba(0,0,0,.3)">'
        f'↩ {escape(theme_name)}</a></div>{MARK_B}')
    idx = txt.lower().rfind("</body>")
    txt = txt[:idx] + block + txt[idx:] if idx >= 0 else txt + block
    Path(html_file).write_text(txt, encoding=enc)


OG_A, OG_B = "<!--OG-PREVIA-->", "<!--/OG-PREVIA-->"


def inject_og(html_file, og):
    """Coloca as meta tags de prévia (WhatsApp etc.) no <head> da subpágina."""
    txt, enc = read_text(html_file)
    txt = re.sub(re.escape(OG_A) + r".*?" + re.escape(OG_B), "", txt, flags=re.S)
    # remove og:/twitter: antigas (evita duplicidade/conflito)
    txt = re.sub(r"<meta[^>]+(?:property|name)=[\"']?(?:og:|twitter:)[^>]*>\s*", "", txt, flags=re.I)
    tags = (f'{OG_A}<meta property="og:type" content="website">'
            f'<meta property="og:title" content="{escape(og["title"], True)}">'
            f'<meta property="og:description" content="{escape(og["desc"], True)}">'
            f'<meta property="og:url" content="{escape(og["url"], True)}">'
            + (f'<meta property="og:image" content="{escape(og["image"], True)}">'
               '<meta property="og:image:width" content="1200">'
               '<meta property="og:image:height" content="630">'
               '<meta name="twitter:card" content="summary_large_image">' if og.get("image") else "")
            + OG_B)
    m = re.search(r"</head>", txt, re.I)
    if m:
        txt = txt[:m.start()] + tags + txt[m.start():]
    else:
        m = re.search(r"<body[^>]*>", txt, re.I)
        txt = (txt[:m.start()] + tags + txt[m.start():]) if m else tags + txt
    Path(html_file).write_text(txt, encoding=enc)


# --------------------------------------------------------------- catálogo
class Catalog:
    def __init__(self, root):
        self.root = Path(root)
        self.file = self.root / CATALOG_FILE
        self.data = {"logo": "", "themes": []}
        if self.file.exists():
            try:
                self.data = json.loads(self.file.read_text(encoding="utf-8"))
            except Exception:
                pass

    def save(self):
        self.file.write_text(json.dumps(self.data, ensure_ascii=False, indent=2),
                             encoding="utf-8")

    def logo_uri(self):
        """Logo embutida: usa a configurada ou a logomarca do próprio programa."""
        lg = self.abs(self.data.get("logo"))
        if lg and lg.exists():
            return data_uri(lg, 300)
        return "data:image/png;base64," + LOGO_B64

    def og_for(self, folder, rel_url, title, desc, src, bg, banner=False):
        """Gera compartilhar.jpg em `folder` e devolve os dados da prévia (ou None)."""
        if not SITE_URL:
            return None
        img = make_share_image(src, folder, bg, banner)
        base = SITE_URL if SITE_URL.endswith("/") else SITE_URL + "/"
        return {"title": title, "desc": desc, "url": base + rel_url,
                "image": base + url(self.root, img) if img else ""}

    def og_for_sub(self, t, page, pal):
        """Prévia da subpágina: imagem própria (<nome>-compartilhar.jpg) ao lado do HTML."""
        if not SITE_URL:
            return None
        title = self.sub_title(t, page)
        src = self.sub_cover(t, page) or self.logo_src()
        img = make_share_image(src, page.parent, pal["bg"], False, name=page.stem + "-compartilhar")
        base = SITE_URL if SITE_URL.endswith("/") else SITE_URL + "/"
        return {"title": f"{title} - Catálogo Kellen Cortadores",
                "desc": f"Modelos de cortadores de {title}. Toque para ver!",
                "url": base + url(self.root, page),
                "image": base + url(self.root, img) if img else ""}

    def banner_src(self):
        """Banner próprio para a prévia: coloque 'banner-compartilhar.png' (ou .jpg) na raiz."""
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            p = self.root / ("banner-compartilhar" + ext)
            if p.exists():
                return p
        return None

    def logo_src(self):
        lg = self.abs(self.data.get("logo"))
        return lg if lg and lg.exists() else base64.b64decode(LOGO_B64)

    def logo_path(self):
        """Logo configurada; se não houver, grava a logomarca embutida em _capas/logo.png."""
        lg = self.abs(self.data.get("logo"))
        if lg and lg.exists():
            return lg
        dest = self.root / ASSETS / "logo.png"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(base64.b64decode(LOGO_B64))
        self.data["logo"] = self.rel(dest)
        self.save()
        return dest

    def rel(self, p):
        return os.path.relpath(p, self.root).replace("\\", "/")

    def abs(self, rel):
        return (self.root / rel) if rel else None

    def theme_folder(self, t):
        return self.root / t["folder"]

    def index_path(self, t):
        return self.theme_folder(t) / INDEX_PATTERN.format(slug=slugify(t["name"]))

    def sub_title(self, t, page):
        return t.get("titles", {}).get(page.name) or pretty_title(page.stem)

    def sub_cover(self, t, page):
        manual = t.get("subimgs", {}).get(page.name)
        if manual and self.abs(manual).exists():
            return self.abs(manual)
        return first_image_of(page)

    # ---- exportação
    def export_theme(self, t, inject=True):
        folder = self.theme_folder(t)
        out = self.index_path(t)
        pal = match_theme(t["name"])
        cards = []
        pages = scan_subpages(folder)
        for p in pages:
            img = self.sub_cover(t, p)
            cards.append((self.sub_title(t, p), "Ver modelos",
                          data_uri(img) if img else "", quote(p.name)))
        html = build_page(
            t["name"], "Escolha um tema",
            self.logo_uri(),
            cards, url(folder, self.root / MAIN_NAME),
            "Buscar tema...", "temas disponíveis", pal=pal,
            og=self.og_for(folder, url(self.root, out),
                           f"{t['name']} - Catálogo Kellen Cortadores",
                           f"Modelos de cortadores de {t['name']}. Toque para ver!",
                           (self.abs(t.get("cover")) if t.get("cover") and self.abs(t["cover"]).exists()
                            else self.logo_src()), pal["bg"]))
        out.write_text(html, encoding="utf-8")
        if inject:
            for p in pages:
                inject_back_button(p, url(p.parent, self.root / MAIN_NAME),
                                   quote(out.name), t["name"], pal)
                og = self.og_for_sub(t, p, pal)
                if og:
                    inject_og(p, og)
        return out, len(pages)

    def export_main(self):
        cards = []
        for t in self.data["themes"]:
            cover = self.abs(t.get("cover"))
            n = len(scan_subpages(self.theme_folder(t)))
            cards.append((t["name"], f"{n} temas",
                          data_uri(cover) if cover and cover.exists() else "",
                          url(self.root, self.index_path(t))))
        html = build_page(
            "Catálogo Kellen Cortadores", "Escolha um tema",
            self.logo_uri(),
            cards, "", "Buscar tema (ex.: natal...)", "temas disponíveis",
            og=self.og_for(self.root, MAIN_NAME, "Catálogo Kellen Cortadores",
                           "Escolha um tema e veja os modelos de cortadores de biscoito.",
                           self.banner_src() or self.logo_src(), DEFAULT_PAL["bg"],
                           banner=bool(self.banner_src())))
        out = self.root / MAIN_NAME
        out.write_text(html, encoding="utf-8")
        return out


# ------------------------------------------------------------------ diálogo
class ThemeDialog(tk.Toplevel):
    def __init__(self, parent, cat, theme=None):
        super().__init__(parent)
        self.cat, self.result = cat, None
        self.title("Editar tema" if theme else "Criar tema")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        theme = theme or {}
        self.v_name = tk.StringVar(value=theme.get("name", ""))
        self.v_folder = tk.StringVar(
            value=str(cat.root / theme["folder"]) if theme.get("folder") else "")
        self.v_cover = tk.StringVar(
            value=str(cat.root / theme["cover"]) if theme.get("cover") else "")
        self._row(0, "Nome do tema:", self.v_name)
        self._row(1, "Pasta do tema:", self.v_folder, self._pick_folder)
        self._row(2, "Imagem do card:", self.v_cover, self._pick_cover)
        bt = ttk.Frame(self)
        bt.grid(row=3, column=0, columnspan=3, pady=10)
        ttk.Button(bt, text="Salvar", command=self._ok).pack(side="left", padx=6)
        ttk.Button(bt, text="Cancelar", command=self.destroy).pack(side="left")
        self.wait_window()

    def _row(self, r, label, var, cmd=None):
        ttk.Label(self, text=label).grid(row=r, column=0, sticky="e", padx=8, pady=6)
        ttk.Entry(self, textvariable=var, width=55).grid(row=r, column=1, pady=6)
        if cmd:
            ttk.Button(self, text="...", width=4, command=cmd).grid(row=r, column=2, padx=6)

    def _pick_folder(self):
        d = filedialog.askdirectory(initialdir=self.cat.root, title="Pasta do tema")
        if d:
            self.v_folder.set(d)
            if not self.v_name.get():
                self.v_name.set(Path(d).name)

    def _pick_cover(self):
        start = self.v_folder.get() or str(self.cat.root)
        f = filedialog.askopenfilename(initialdir=start, filetypes=IMG_TYPES,
                                       title="Imagem do card principal")
        if f:
            self.v_cover.set(f)

    def _ok(self):
        name, folder = self.v_name.get().strip(), self.v_folder.get().strip()
        if not name or not folder:
            messagebox.showwarning("Faltou algo", "Informe nome e pasta.", parent=self)
            return
        try:
            rel = self.cat.rel(folder)
        except ValueError:
            rel = ".."
        if rel.startswith("..") or rel == ".":
            messagebox.showwarning(
                "Pasta inválida",
                "A pasta do tema precisa ficar DENTRO da pasta do catálogo.",
                parent=self)
            return
        self.result = {"name": name, "folder": rel, "cover": self.v_cover.get().strip()}
        self.destroy()


# ----------------------------------------------------------------- janela
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Gerador de índices - Catálogo Kellen Cortadores")
        self.geometry("980x600")
        self.cat = None
        self.v_root = tk.StringVar()
        self.v_inject = tk.BooleanVar(value=True)
        self._build()
        try:
            last = json.loads(CFG_FILE.read_text(encoding="utf-8")).get("root")
            if last and Path(last).is_dir():
                self.open_root(last)
        except Exception:
            pass

    # ---- UI
    def _build(self):
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="Pasta do catálogo:").pack(side="left")
        ttk.Entry(top, textvariable=self.v_root, state="readonly").pack(
            side="left", fill="x", expand=True, padx=6)
        ttk.Button(top, text="Escolher...", command=self.choose_root).pack(side="left")
        ttk.Button(top, text="Logo...", command=self.choose_logo).pack(side="left", padx=6)

        body = ttk.Frame(self, padding=(8, 0))
        body.pack(fill="both", expand=True)

        left = ttk.LabelFrame(body, text="Temas")
        left.pack(side="left", fill="y")
        self.lb = tk.Listbox(left, width=26, exportselection=False, font=("Segoe UI", 11))
        self.lb.pack(fill="both", expand=True, padx=6, pady=6)
        self.lb.bind("<<ListboxSelect>>", lambda e: self.refresh_subs())
        for txt, cmd in [("➕ Criar tema", self.create_theme),
                         ("✏ Editar tema", self.edit_theme),
                         ("🗑 Remover da lista", self.remove_theme)]:
            ttk.Button(left, text=txt, command=cmd).pack(fill="x", padx=6, pady=2)

        right = ttk.LabelFrame(body, text="Subtemas da pasta (duplo clique = escolher imagem do card)")
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        cols = ("arquivo", "titulo", "imagem")
        self.tv = ttk.Treeview(right, columns=cols, show="headings")
        for c, w, t in [("arquivo", 230, "Arquivo"), ("titulo", 200, "Título no card"),
                        ("imagem", 220, "Imagem do card")]:
            self.tv.heading(c, text=t)
            self.tv.column(c, width=w)
        self.tv.pack(fill="both", expand=True, padx=6, pady=6)
        self.tv.bind("<Double-1>", self.on_double_click)
        rb = ttk.Frame(right)
        rb.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Button(rb, text="Editar título...", command=self.edit_sub_title).pack(side="left")
        ttk.Button(rb, text="Imagem do subtema...", command=self.pick_sub_image).pack(side="left", padx=6)
        ttk.Button(rb, text="Voltar para automática", command=self.clear_sub_image).pack(side="left", padx=6)
        ttk.Button(rb, text="Reescanear pasta", command=self.refresh_subs).pack(side="left")

        bot = ttk.Frame(self, padding=8)
        bot.pack(fill="x")
        ttk.Checkbutton(bot, text="Colocar botão 'Voltar' nas subpáginas",
                        variable=self.v_inject).pack(side="left")
        ttk.Button(bot, text="🏠 Abrir main", command=self.open_main).pack(side="right")
        ttk.Button(bot, text="Abrir index do tema", command=self.open_theme).pack(side="right", padx=6)
        ttk.Button(bot, text="Exportar TUDO", command=lambda: self.export(all_=True)).pack(side="right")
        ttk.Button(bot, text="Exportar tema", command=lambda: self.export(all_=False)).pack(side="right", padx=6)

    # ---- raiz / logo
    def choose_root(self):
        d = filedialog.askdirectory(title="Pasta do catálogo (a que tem o index-main)")
        if d:
            self.open_root(d)

    def open_root(self, d):
        self.cat = Catalog(d)
        self.v_root.set(d)
        CFG_FILE.write_text(json.dumps({"root": d}), encoding="utf-8")
        if not self.cat.data["themes"]:
            self.auto_import()
        self.refresh_themes()

    def auto_import(self):
        """Primeira vez: sugere as subpastas que já têm html como temas."""
        found = [p for p in sorted(self.cat.root.iterdir())
                 if p.is_dir() and not p.name.startswith(("_", "."))
                 and scan_subpages(p)]
        if found and messagebox.askyesno(
                "Importar", "Encontrei as pastas: " + ", ".join(p.name for p in found) +
                "\n\nAdicionar como temas? (depois escolha a imagem de cada card)"):
            for p in found:
                self.cat.data["themes"].append(
                    {"name": p.name, "folder": self.cat.rel(p), "cover": "", "subimgs": {}})
            self.cat.save()

    def choose_logo(self):
        if not self.need_cat():
            return
        f = filedialog.askopenfilename(filetypes=IMG_TYPES, title="Logo")
        if f:
            dest = copy_asset(f, self.cat.root / ASSETS, "logo")
            self.cat.data["logo"] = self.cat.rel(dest)
            self.cat.save()
            messagebox.showinfo("Logo", "Logo definida.")

    def need_cat(self):
        if not self.cat:
            messagebox.showinfo("Catálogo", "Escolha primeiro a pasta do catálogo.")
            return False
        return True

    # ---- temas
    def refresh_themes(self, select=None):
        self.lb.delete(0, "end")
        for t in self.cat.data["themes"]:
            self.lb.insert("end", t["name"])
        if self.cat.data["themes"]:
            self.lb.selection_set(select if select is not None else 0)
        self.refresh_subs()

    def current(self):
        sel = self.lb.curselection()
        return self.cat.data["themes"][sel[0]] if sel else None

    def _store_cover(self, t, cover_path):
        if cover_path and Path(cover_path).exists():
            dest = copy_asset(cover_path, self.cat.root / ASSETS, "capa-" + slugify(t["name"]))
            t["cover"] = self.cat.rel(dest)
        else:
            t["cover"] = ""

    def create_theme(self):
        if not self.need_cat():
            return
        r = ThemeDialog(self, self.cat).result
        if not r:
            return
        t = {"name": r["name"], "folder": r["folder"], "cover": "", "subimgs": {}}
        self._store_cover(t, r["cover"])
        self.cat.data["themes"].append(t)
        self.cat.save()
        self.refresh_themes(len(self.cat.data["themes"]) - 1)

    def edit_theme(self):
        t = self.current()
        if not t:
            return
        r = ThemeDialog(self, self.cat, t).result
        if r:
            t["name"], t["folder"] = r["name"], r["folder"]
            if r["cover"] != str(self.cat.abs(t.get("cover")) if t.get("cover") else ""):
                self._store_cover(t, r["cover"])
            self.cat.save()
            self.refresh_themes(self.lb.curselection()[0])

    def remove_theme(self):
        t = self.current()
        if t and messagebox.askyesno("Remover", f"Tirar '{t['name']}' da lista?\n"
                                     "(os arquivos HTML não são apagados)"):
            self.cat.data["themes"].remove(t)
            self.cat.save()
            self.refresh_themes()

    # ---- subtemas
    def refresh_subs(self):
        self.tv.delete(*self.tv.get_children())
        t = self.current() if self.cat else None
        if not t:
            return
        for p in scan_subpages(self.cat.theme_folder(t)):
            manual = t.get("subimgs", {}).get(p.name)
            auto = first_image_of(p)
            img = Path(manual).name if manual else (f"(auto) {auto.name}" if auto else "(sem imagem)")
            self.tv.insert("", "end", iid=p.name, values=(p.name, self.cat.sub_title(t, p), img))

    def on_double_click(self, event):
        # coluna 2 (#2) = título -> edita o título; demais -> escolhe imagem
        if self.tv.identify_column(event.x) == "#2":
            self.edit_sub_title()
        else:
            self.pick_sub_image()

    def edit_sub_title(self):
        t, sel = self.current(), self.tv.selection()
        if not t or not sel:
            return
        page = self.cat.theme_folder(t) / sel[0]
        atual = self.cat.sub_title(t, page)
        novo = simpledialog.askstring(
            "Título do card",
            "Título que aparece no card\n(deixe vazio para voltar ao automático):",
            initialvalue=atual, parent=self)
        if novo is None:
            return
        novo = novo.strip()
        titles = t.setdefault("titles", {})
        if novo:
            titles[sel[0]] = novo
        else:
            titles.pop(sel[0], None)
        self.cat.save()
        self.refresh_subs()
        if self.tv.exists(sel[0]):
            self.tv.selection_set(sel[0])

    def pick_sub_image(self):
        t, sel = self.current(), self.tv.selection()
        if not t or not sel:
            return
        f = filedialog.askopenfilename(initialdir=self.cat.theme_folder(t),
                                       filetypes=IMG_TYPES, title="Imagem do card do subtema")
        if f:
            dest = copy_asset(f, self.cat.theme_folder(t) / ASSETS, slugify(Path(sel[0]).stem))
            t.setdefault("subimgs", {})[sel[0]] = self.cat.rel(dest)
            self.cat.save()
            self.refresh_subs()

    def clear_sub_image(self):
        t, sel = self.current(), self.tv.selection()
        if t and sel:
            t.get("subimgs", {}).pop(sel[0], None)
            self.cat.save()
            self.refresh_subs()

    # ---- exportar / abrir
    def export(self, all_):
        if not self.need_cat():
            return
        themes = self.cat.data["themes"] if all_ else [self.current()]
        if not themes or themes[0] is None:
            return
        lines = []
        try:
            for t in themes:
                out, n = self.cat.export_theme(t, self.v_inject.get())
                lines.append(f"{t['name']}: {out.name} ({n} subtemas, visual {match_theme(t['name'])['label']})")
            main = self.cat.export_main()
            lines.append(f"Main: {main.name}")
        except Exception as e:
            messagebox.showerror("Erro ao exportar", str(e))
            return
        self.cat.save()
        messagebox.showinfo("Exportado", "\n".join(lines))

    def open_main(self):
        if self.need_cat():
            p = self.cat.root / MAIN_NAME
            if p.exists():
                webbrowser.open(p.as_uri())
            else:
                messagebox.showinfo("Main", "Ainda não exportado. Clique em 'Exportar TUDO'.")

    def open_theme(self):
        t = self.current()
        if t and self.cat.index_path(t).exists():
            webbrowser.open(self.cat.index_path(t).as_uri())
        else:
            messagebox.showinfo("Index", "Esse tema ainda não foi exportado.")


# Logomarca Kellen Cortadores (padrão; o botão "Logo..." ainda troca por outra)
LOGO_B64 = (
    "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"
    "TkSuQmCC"
)


if __name__ == "__main__":
    App().mainloop()
