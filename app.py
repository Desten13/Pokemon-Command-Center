import json
import random
import html
from pathlib import Path

import requests
from flask import Flask, request, redirect, url_for, render_template_string
from markupsafe import Markup

app = Flask(__name__)
API = "https://pokeapi.co/api/v2"
DB_FILE = Path(__file__).resolve().parent / "pokemon_data.json"

GAMES = [
    "Pokemon Red / Blue", "Pokemon Yellow",
    "Pokemon Gold / Silver", "Pokemon Crystal",
    "Pokemon Ruby / Sapphire", "Pokemon Emerald",
    "Pokemon FireRed / LeafGreen", "Pokemon Diamond / Pearl",
    "Pokemon Platinum", "Pokemon HeartGold / SoulSilver",
    "Pokemon Black / White", "Pokemon Black 2 / White 2",
    "Pokemon X / Y", "Pokemon Omega Ruby / Alpha Sapphire",
    "Pokemon Sun / Moon", "Pokemon Ultra Sun / Ultra Moon",
    "Pokemon Sword / Shield",
    "Pokemon Brilliant Diamond / Shining Pearl",
    "Pokemon Legends: Arceus", "Pokemon Scarlet / Violet",
]

def load_db():
    try:
        data = json.loads(DB_FILE.read_text())
        return {
            "collection": data.get("collection", []),
            "team": data.get("team", []),
            "games": data.get("games", []),
        }
    except (OSError, json.JSONDecodeError):
        return {"collection": [], "team": [], "games": []}

db = load_db()

def save_db():
    DB_FILE.write_text(json.dumps(db, indent=2))

def esc(value):
    return html.escape(str(value))

def api_get(url):
    try:
        response = requests.get(url, timeout=12)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError):
        return None

def get_pokemon(name):
    name = str(name).strip().lower()
    if not name:
        return None
    return api_get(f"{API}/pokemon/{name}")

BASE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title }} | Pokemon Command Center</title>
<style>
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:#0b1020;color:#f4f5ff;
font-family:system-ui,sans-serif}
header{padding:25px 5%;background:linear-gradient(120deg,#34116b,#102b65,#086b70);
border-bottom:2px solid #bd63ff}
h1{margin:0;color:#ffe66d;font-size:clamp(24px,4vw,38px)}
header p{color:#cbd7ff;margin:8px 0 0}
nav{display:flex;gap:9px;flex-wrap:wrap;margin-top:20px}
a,button{cursor:pointer}
nav a,.btn{display:inline-block;padding:10px 14px;border:0;
border-radius:10px;background:#6639b9;color:white;text-decoration:none;
font-weight:700}
nav a:hover,.btn:hover{filter:brightness(1.25)}
main{max-width:1100px;margin:auto;padding:26px 18px}
h2{color:#67e8f9}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}
.card{background:#151d34;border:1px solid #38476b;border-radius:16px;
padding:18px;margin-bottom:16px}
.feature{min-height:140px;display:block;text-decoration:none;color:white;
transition:transform .15s,border-color .15s}
.feature:hover{transform:translateY(-3px);border-color:#e879f9}
.feature h3{color:#f0abfc;margin-top:0}
.muted{color:#aebbd8}
input,select{padding:12px;border-radius:9px;border:1px solid #65749b;
background:#0d1428;color:white;max-width:100%}
form{display:flex;gap:9px;flex-wrap:wrap;align-items:center;margin:12px 0}
.btn.green{background:#14845e}.btn.red{background:#b73558}
.btn.blue{background:#2368c7}.btn.gold{background:#967014}
.pokemon{display:grid;grid-template-columns:minmax(130px,220px) 1fr;
gap:20px;align-items:start}
.pokemon img{width:100%;image-rendering:auto}
.stat{display:flex;justify-content:space-between;border-bottom:1px solid #34415e;
padding:7px 0}
.tag{display:inline-block;border-radius:20px;padding:5px 10px;
margin:3px;background:#35305c;color:#e9d5ff}
li{margin:7px 0}
footer{text-align:center;color:#8695b5;padding:25px}
@media(max-width:520px){.pokemon{grid-template-columns:1fr}
.pokemon img{max-width:180px}}
</style>
</head>
<body>
<header>
<h1>⚡ Pokémon Command Center</h1>
<p>Catch · Train · Explore · Discover</p>
<nav>
<a href="/">🏠 Home</a>
<a href="/pokedex">📘 Pokédex</a>
<a href="/games">🎮 Game Library</a>
<a href="/team">⭐ Team Builder</a>
<a href="/collection">🎒 Collection</a>
<a href="/types">⚔️ Type Chart</a>
<a href="/random">✨ Random Pokémon</a>
</nav>
</header>
<main>
{{ content }}
</main>
<footer>Pokémon Command Center · Trainer HQ</footer>
</body>
</html>
"""

def page(title, content):
    return render_template_string(
        BASE, title=title, content=Markup(content)
    )

def pokemon_card(data):
    name = esc(data["name"].title())
    pid = data["id"]
    artwork = data["sprites"]["other"]["official-artwork"]["front_default"]
    image = (
        f'<img src="{esc(artwork)}" alt="{name}" loading="lazy">'
        if artwork else '<p class="muted">Artwork unavailable</p>'
    )
    types = "".join(
        f'<span class="tag">{esc(t["type"]["name"].title())}</span>'
        for t in data["types"]
    )
    abilities = ", ".join(
        esc(x["ability"]["name"].replace("-", " ").title())
        for x in data["abilities"]
    )
    stats = "".join(
        f'<div class="stat"><span>{esc(s["stat"]["name"].replace("-", " ").title())}</span>'
        f'<strong>{s["base_stat"]}</strong></div>'
        for s in data["stats"]
    )
    moves = ", ".join(
        esc(x["move"]["name"].replace("-", " ").title())
        for x in data["moves"][:12]
    )
    species = api_get(data["species"]["url"])
    extra = ""
    if species:
        entries = [
            x["flavor_text"].replace("\n", " ").replace("\f", " ")
            for x in species.get("flavor_text_entries", [])
            if x["language"]["name"] == "en"
        ]
        if entries:
            extra += f'<p class="muted">{esc(entries[0])}</p>'
        evo_url = species.get("evolution_chain", {}).get("url")
        evo = api_get(evo_url) if evo_url else None
        if evo:
            family = []
            def flatten(node):
                family.append(node["species"]["name"].title())
                for child in node.get("evolves_to", []):
                    flatten(child)
            flatten(evo["chain"])
            extra += '<p><strong>Evolution family:</strong> ' + \
                " → ".join(esc(x) for x in family) + '</p>'
    return f"""
    <section class="card pokemon">
      <div>{image}</div>
      <div><h2>{name} <span class="muted">#{pid:03}</span></h2>
      {types}
      <p><strong>Abilities:</strong> {abilities}</p>
      <p><strong>Height:</strong> {data["height"]/10:.1f} m</p>
      <p><strong>Weight:</strong> {data["weight"]/10:.1f} kg</p>
      <h3>Base stats</h3>{stats}
      <p><strong>Base experience:</strong> {data.get("base_experience")}</p>
      {extra}
      <p><strong>Example moves:</strong> {moves}</p></div>
    </section>
    """

@app.route("/")
def home():
    content = f"""
    <h2>Welcome, Trainer!</h2>
    <p class="muted">Your colorful Pokémon HQ, now in your browser.</p>
    <div class="grid">
      <a class="card feature" href="/pokedex"><h3>📘 National Pokédex</h3>
      Search Pokémon, stats, artwork and evolution families.</a>
      <a class="card feature" href="/games"><h3>🎮 Game Library</h3>
      Games owned: {len(db["games"])} of {len(GAMES)}.</a>
      <a class="card feature" href="/team"><h3>⭐ Team Builder</h3>
      Team slots filled: {len(db["team"])}/6.</a>
      <a class="card feature" href="/collection"><h3>🎒 My Collection</h3>
      Tracked Pokémon: {len(db["collection"])}.</a>
      <a class="card feature" href="/types"><h3>⚔️ Type Matchups</h3>
      Look up defensive weaknesses and resistances.</a>
      <a class="card feature" href="/random"><h3>✨ Wild Encounter</h3>
      Discover a random Pokémon.</a>
    </div>
    <p class="muted">Saved game, team and collection data is shared by this website.</p>
    """
    return page("Home", content)


@app.route("/pokedex", methods=["GET", "POST"])
def pokedex():
    limit = 50
    page_num = max(1, request.args.get("page", 1, type=int) or 1)
    offset = (page_num - 1) * limit

    content = """
    <h2>📘 National Pokédex</h2>
    <p class="muted">Browse Pokémon in Pokédex number order.</p>
    <div class="card">
      <form method="post">
        <input name="pokemon" placeholder="Search by name or number" required>
        <button class="btn" type="submit">Search Pokémon</button>
      </form>
    </div>
    """

    if request.method == "POST":
        query = request.form.get("pokemon", "").strip()
        data = get_pokemon(query) if query else None
        if data:
            content += pokemon_card(data)
        else:
            content += '<p class="card">Pokémon not found, or the API is unavailable. Try again.</p>'

    listing = api_get(f"{API}/pokemon?limit={limit}&offset={offset}")

    if listing and listing.get("results"):
        total = listing.get("count", 0)
        total_pages = max(1, (total + limit - 1) // limit)

        content += f"""
        <div class="card">
          <strong>Pokédex</strong>
          <p class="muted">Showing entries {offset + 1}–{min(offset + limit, total)} of {total:,}</p>
        </div>
        <div class="grid">
        """

        for item in listing["results"]:
            try:
                number = int(item["url"].rstrip("/").split("/")[-1])
            except (ValueError, KeyError, IndexError):
                continue

            name = item["name"]
            sprite = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{number}.png"

            content += f"""
            <div class="card" style="text-align:center">
              <img src="{sprite}" alt="{esc(name)}"
                   loading="lazy" style="width:100px;height:100px;object-fit:contain">
              <h3>#{number:04d} {esc(name.title())}</h3>
              <form method="post">
                <input type="hidden" name="pokemon" value="{esc(name)}">
                <button class="btn" type="submit">View Details</button>
              </form>
            </div>
            """

        content += "</div><div class='card' style='display:flex;gap:12px;justify-content:center;align-items:center;flex-wrap:wrap'>"

        if page_num > 1:
            content += f'<a class="btn" href="{url_for("pokedex", page=page_num - 1)}">← Previous</a>'

        content += f"<span>Page {page_num} of {total_pages}</span>"

        if page_num < total_pages:
            content += f'<a class="btn" href="{url_for("pokedex", page=page_num + 1)}">Next →</a>'

        content += "</div>"
    else:
        content += '<p class="card">Could not load the Pokédex. Check your internet connection and try again.</p>'

    return page("Pokédex", content)


@app.route("/games", methods=["GET", "POST"])
def games():
    if request.method == "POST":
        name = request.form.get("game", "")
        action = request.form.get("action", "")
        if name in GAMES:
            if action == "add" and name not in db["games"]:
                db["games"].append(name)
            elif action == "remove" and name in db["games"]:
                db["games"].remove(name)
            save_db()
        return redirect(url_for("games"))
    rows = ""
    for game in GAMES:
        owned = game in db["games"]
        rows += f'<div class="card"><strong>{esc(game)}</strong><p>{"✅ Owned" if owned else "⬜ Not marked owned"}</p>'
        rows += f'<form method="post"><input type="hidden" name="game" value="{esc(game)}">'
        if owned:
            rows += '<button class="btn red" name="action" value="remove">Remove</button>'
        else:
            rows += '<button class="btn green" name="action" value="add">Mark owned</button>'
        rows += '</form></div>'
    return page("Game Library", '<h2>🎮 Game Library</h2><div class="grid">'+rows+'</div>')

@app.route("/collection", methods=["GET", "POST"])
def collection():
    message = ""
    if request.method == "POST":
        name = request.form.get("pokemon", "").strip().lower()
        action = request.form.get("action", "")
        if action == "add":
            data = get_pokemon(name)
            if data:
                if data["name"] not in db["collection"]:
                    db["collection"].append(data["name"])
                    save_db()
                    message = "Pokémon added!"
                else:
                    message = "Already in your collection."
            else:
                message = "Pokémon not found or API unavailable."
        elif action == "remove" and name in db["collection"]:
            db["collection"].remove(name)
            save_db()
            message = "Pokémon removed."
        return redirect(url_for("collection"))
    items = "".join(
        f'<div class="card"><strong>{esc(name.title())}</strong>'
        f'<form method="post"><input type="hidden" name="pokemon" value="{esc(name)}">'
        f'<button class="btn red" name="action" value="remove">Remove</button></form></div>'
        for name in db["collection"]
    ) or '<p class="card">Your collection is empty.</p>'
    content = """
    <h2>🎒 My Collection</h2>
    <div class="card"><form method="post">
    <input name="pokemon" placeholder="Pokémon name" required>
    <button class="btn green" name="action" value="add">Add Pokémon</button>
    </form></div>
    """ + f'<p class="muted">Tracked: {len(db["collection"])}</p><div class="grid">{items}</div>'
    return page("My Collection", content)

@app.route("/team", methods=["GET", "POST"])
def team():
    if request.method == "POST":
        action = request.form.get("action", "")
        name = request.form.get("pokemon", "").strip().lower()
        if action == "clear":
            db["team"] = []
            save_db()
        elif action == "remove" and name in db["team"]:
            db["team"].remove(name)
            save_db()
        elif action == "add" and len(db["team"]) < 6 and name:
            data = get_pokemon(name)
            if data and data["name"] not in db["team"]:
                db["team"].append(data["name"])
                save_db()
        return redirect(url_for("team"))
    members = ""
    for name in db["team"]:
        data = get_pokemon(name)
        if data:
            image = data["sprites"]["other"]["official-artwork"]["front_default"]
            pic = f'<img style="width:110px" src="{esc(image)}" alt="{esc(name)}">' if image else ""
        else:
            pic = ""
        members += f'<div class="card">{pic}<h3>{esc(name.title())}</h3>'
        members += f'<form method="post"><input type="hidden" name="pokemon" value="{esc(name)}">'
        members += '<button class="btn red" name="action" value="remove">Remove</button></form></div>'
    if not members:
        members = '<p class="card">Your team is empty. Add your first Pokémon!</p>'
    content = f"""
    <h2>⭐ Team Builder ({len(db["team"])}/6)</h2>
    <div class="card"><form method="post">
    <input name="pokemon" placeholder="Pokémon name" required>
    <button class="btn green" name="action" value="add">Add Pokémon</button>
    </form>
    <form method="post"><button class="btn red" name="action" value="clear">Clear team</button></form>
    <p class="muted">Your team can have up to six Pokémon.</p></div>
    <div class="grid">{members}</div>
    """
    return page("Team Builder", content)


@app.route("/types", methods=["GET", "POST"])
def types():
    type_names = [
        "normal", "fire", "water", "electric", "grass", "ice",
        "fighting", "poison", "ground", "flying", "psychic",
        "bug", "rock", "ghost", "dragon", "dark", "steel", "fairy"
    ]

    colors = {
        "normal": "#A8A77A", "fire": "#EE8130", "water": "#6390F0",
        "electric": "#F7D02C", "grass": "#7AC74C", "ice": "#96D9D6",
        "fighting": "#C22E28", "poison": "#A33EA1", "ground": "#E2BF65",
        "flying": "#A98FF3", "psychic": "#F95587", "bug": "#A6B91A",
        "rock": "#B6A136", "ghost": "#735797", "dragon": "#6F35FC",
        "dark": "#705746", "steel": "#B7B7CE", "fairy": "#D685AD"
    }

    selected = request.args.get("type", "fire").lower()
    if selected not in type_names:
        selected = "fire"

    # Offensive damage multipliers: attacking type -> defending type
    chart = {name: {target: 1 for target in type_names} for name in type_names}
    failed = False

    for attacking in type_names:
        info = api_get(f"{API}/type/{attacking}")
        if not info:
            failed = True
            break
        rel = info["damage_relations"]
        for key, multiplier in [
            ("double_damage_to", 2),
            ("half_damage_to", 0.5),
            ("no_damage_to", 0)
        ]:
            for target in rel[key]:
                if target["name"] in chart[attacking]:
                    chart[attacking][target["name"]] = multiplier

    content = """
    <h2>⚔️ Pokémon Type Chart</h2>
    <p class="muted">Choose a type to see its offensive matchups. No Pokémon names needed.</p>
    """

    content += '<div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(105px,1fr));gap:8px">'
    for name in type_names:
        border = "3px solid white" if name == selected else "2px solid transparent"
        content += (
            f'<a href="{url_for("types", type=name)}" '
            f'style="display:block;text-align:center;padding:12px 5px;'
            f'border:{border};border-radius:12px;text-decoration:none;'
            f'background:{colors[name]};color:#fff;font-weight:bold">'
            f'{name.title()}</a>'
        )
    content += '</div>'

    if failed:
        content += '<div class="card">Could not load matchup data. Check your internet connection and refresh.</div>'
    else:
        strong = [n for n, m in chart[selected].items() if m == 2]
        weak = [n for n, m in chart[selected].items() if m == 0.5]
        immune = [n for n, m in chart[selected].items() if m == 0]

        def type_pills(names, label, color):
            if not names:
                return f'<div class="card"><strong>{label}</strong><p>None</p></div>'
            pills = "".join(
                f'<span style="display:inline-block;margin:4px;padding:7px 10px;'
                f'border-radius:20px;background:{colors[n]};color:white;font-weight:bold">'
                f'{n.title()}</span>' for n in names
            )
            return f'<div class="card"><strong style="color:{color}">{label}</strong><div>{pills}</div></div>'

        content += f'<h3 style="margin-top:22px">{selected.title()} attacking matchups</h3>'
        content += type_pills(strong, "Super effective · 2×", "#e05260")
        content += type_pills(weak, "Not very effective · ½×", "#429e72")
        content += type_pills(immune, "No effect · 0×", "#888888")

        content += """
        <div class="card">
          <h3>Full Type Matchup Grid</h3>
          <p class="muted">Rows are attacking types. Columns are defending types.
          Select a type above to highlight its row.</p>
          <div style="overflow-x:auto">
            <table style="border-collapse:collapse;font-size:12px;white-space:nowrap">
              <thead><tr><th style="padding:5px">ATK ↓ / DEF →</th>
        """
        for target in type_names:
            content += (
                f'<th style="padding:5px;background:{colors[target]};color:white">'
                f'{target[:3].upper()}</th>'
            )
        content += "</tr></thead><tbody>"

        for attacking in type_names:
            row_style = "outline:2px solid white;" if attacking == selected else ""
            content += (
                f'<tr style="{row_style}"><th style="padding:5px;text-align:left;'
                f'background:{colors[attacking]};color:white">{attacking.title()}</th>'
            )
            for target in type_names:
                mult = chart[attacking][target]
                if mult == 2:
                    bg, symbol = "#b9f2cf", "2"
                elif mult == 0.5:
                    bg, symbol = "#ffd0d5", "½"
                elif mult == 0:
                    bg, symbol = "#c9c9c9", "0"
                else:
                    bg, symbol = "#eeeeee", "·"

                if attacking == selected:
                    bg = "#fff1a8" if mult == 1 else bg

                content += (
                    f'<td title="{attacking.title()} into {target.title()}: {mult:g}x" '
                    f'style="padding:6px;text-align:center;background:{bg};'
                    f'color:#222;border:1px solid #ccc;font-weight:bold">{symbol}</td>'
                )
            content += "</tr>"
        content += "</tbody></table></div><p class='muted'>2 = super effective · ½ = resisted · 0 = immune · · = normal damage</p></div>"

    return page("Type Matchups", content)


@app.route("/random")
def random_pokemon():
    data = get_pokemon(str(random.randint(1, 1025)))
    content = '<h2>✨ Wild Encounter!</h2>'
    content += pokemon_card(data) if data else '<p class="card">Could not reach PokéAPI. Try again.</p>'
    content += '<a class="btn" href="/random">Find another Pokémon</a>'
    return page("Random Pokémon", content)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
