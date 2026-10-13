import json
import random
import html
import os
import secrets
import hashlib
from datetime import datetime
from pathlib import Path

import requests
from flask import Flask, request, redirect, url_for, render_template_string, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash, check_password_hash
from markupsafe import Markup

app = Flask(__name__)
_secret_key = os.environ.get("SECRET_KEY")
if not _secret_key:
    if os.environ.get("PORT"):
        raise RuntimeError(
            "Set a persistent SECRET_KEY environment variable before deploying."
        )
    _secret_key = secrets.token_hex(32)
app.config["SECRET_KEY"] = _secret_key
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///pokemon_accounts_test.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

sql_db = SQLAlchemy(app)
class User(UserMixin, sql_db.Model):
    id = sql_db.Column(sql_db.Integer, primary_key=True)
    username = sql_db.Column(sql_db.String(40), unique=True, nullable=False)
    password_hash = sql_db.Column(sql_db.String(255), nullable=False)
    trainer_xp = sql_db.Column(sql_db.Integer, nullable=False, default=0)
    trainer_level = sql_db.Column(sql_db.Integer, nullable=False, default=1)


class OwnedPokemon(sql_db.Model):
    id = sql_db.Column(sql_db.Integer, primary_key=True)
    user_id = sql_db.Column(
        sql_db.Integer, sql_db.ForeignKey("user.id"), nullable=False
    )
    pokemon_name = sql_db.Column(sql_db.String(80), nullable=False)
    pokemon_id = sql_db.Column(sql_db.Integer, nullable=False)
    level = sql_db.Column(sql_db.Integer, nullable=False, default=1)
    rarity = sql_db.Column(sql_db.String(20), nullable=False, default="Common")
    exp = sql_db.Column(sql_db.Integer, nullable=False, default=0)


class Invitation(sql_db.Model):
    id = sql_db.Column(sql_db.Integer, primary_key=True)
    code_hash = sql_db.Column(sql_db.String(64), unique=True, nullable=False)
    created_by_id = sql_db.Column(sql_db.Integer, sql_db.ForeignKey("user.id"), nullable=False)
    created_at = sql_db.Column(sql_db.DateTime, nullable=False, default=datetime.utcnow)
    used_by_id = sql_db.Column(sql_db.Integer, sql_db.ForeignKey("user.id"))
    used_at = sql_db.Column(sql_db.DateTime)


@login_manager.user_loader
def load_user(user_id):
    try:
        return sql_db.session.get(User, int(user_id))
    except (ValueError, TypeError):
        return None


with app.app_context():
    sql_db.create_all()
    migrations = {
        "user": {
            "trainer_xp": "INTEGER NOT NULL DEFAULT 0",
            "trainer_level": "INTEGER NOT NULL DEFAULT 1",
        },
        "owned_pokemon": {
            "level": "INTEGER NOT NULL DEFAULT 1",
            "rarity": "VARCHAR(20) NOT NULL DEFAULT 'Common'",
            "exp": "INTEGER NOT NULL DEFAULT 0",
        },
    }
    with sql_db.engine.begin() as connection:
        for table, additions in migrations.items():
            existing = {
                column["name"]
                for column in inspect(sql_db.engine).get_columns(table)
            }
            for column, definition in additions.items():
                if column not in existing:
                    connection.execute(text(
                        f'ALTER TABLE "{table}" '
                        f'ADD COLUMN "{column}" {definition}'
                    ))

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


RARITY_POOLS = {
    "Common": [1, 4, 7, 10, 13, 16, 19, 25, 37, 39, 41, 43,
               52, 54, 60, 74, 92, 100, 133, 161, 172, 252, 255,
               258, 263, 265, 280, 300, 387, 390, 393, 396, 495,
               498, 501, 506, 519, 650, 653, 656, 722, 725, 728,
               810, 813, 816, 906, 909, 912, 915, 917, 921, 944],
    "Rare": [94, 130, 143, 196, 197, 212, 248, 257, 282, 303,
             334, 359, 373, 376, 392, 405, 430, 445, 448, 461,
             462, 468, 473, 475, 530, 635, 706, 715, 784, 887,
             899, 908, 923, 934, 943, 980, 998],
    "Epic": [149, 248, 254, 257, 260, 373, 376, 389, 445, 448,
             475, 530, 635, 706, 715, 784, 887, 897, 901, 923,
             934, 943, 980, 998, 1005, 1008, 1011, 1018],
    "Legendary": [144, 145, 146, 150, 243, 244, 245, 249, 250,
                  377, 378, 379, 380, 381, 382, 383, 384, 480,
                  481, 482, 483, 484, 485, 486, 487, 488, 638,
                  639, 640, 641, 642, 643, 644, 645, 646, 716,
                  717, 718, 785, 786, 787, 788, 791, 792, 800,
                  888, 889, 890, 891, 892, 895, 896, 898, 905,
                  1001, 1002, 1003, 1004, 1007, 1009, 1014, 1015,
                  1016, 1024],
    "Mythical": [151, 251, 385, 386, 489, 490, 491, 492, 493,
                 494, 647, 648, 649, 719, 720, 721, 801, 802,
                 807, 808, 809, 893, 1025],
}


def refresh_trainer_level(user):
    # XP is total career XP, not XP remaining in the current level.
    level = 1
    xp_remaining = max(0, user.trainer_xp)

    while level < 100:
        xp_needed = level * 100
        if xp_remaining < xp_needed:
            break
        xp_remaining -= xp_needed
        level += 1

    user.trainer_level = level


def make_encounter(trainer_level):
    rarity = random.choices(
        ["Common", "Rare", "Epic", "Legendary", "Mythical"],
        weights=[60, 25, 10, 4, 1],
        k=1,
    )[0]

    for _ in range(3):
        pokemon_id = random.choice(RARITY_POOLS[rarity])
        data = get_pokemon(pokemon_id)
        if data:
            total_stats = sum(
                stat["base_stat"] for stat in data.get("stats", [])
            )
            strength_bonus = max(-3, min(5, (total_stats - 400) // 100))
            level = max(
                1,
                min(100, trainer_level + random.randint(-3, 3)
                    + strength_bonus),
            )
            return data, rarity, level

    return None, None, None


BASE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">\n{% if auto_refresh %}<meta http-equiv="refresh" content="5">{% endif %}
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
<a href="/friends">👥 Friends</a>
<a href="/battles">⚔️ Battles</a>
<a href="/trades">🔁 Trades</a>
<a href="/login">🔑 Login</a>
<a href="/register">📝 Register</a>
{% if current_user.is_authenticated and current_user.username == "Luffy" %}<a href="/owner/invitations">🔐 Owner Invites</a>{% endif %}
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
    auto_refresh = str(title).startswith("Battle · Refresh")
    display_title = str(title).replace("Battle · Refresh", "Battle")
    return render_template_string(
        BASE, title=display_title, content=Markup(content), auto_refresh=auto_refresh
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
            transitions = []
            selected_evolves = False
            def flatten(node):
                nonlocal selected_evolves
                family.append(node["species"]["name"].title())
                if node["species"]["name"].lower() == data["name"].lower():
                    selected_evolves = bool(node.get("evolves_to"))
                for child in node.get("evolves_to", []):
                    details = (child.get("evolution_details") or [{}])[0]
                    conditions = []
                    if details.get("min_level"):
                        conditions.append("Level " + str(details["min_level"]))
                    if details.get("item", {}).get("name"):
                        conditions.append("Use " + details["item"]["name"].replace("-", " ").title())
                    if details.get("trigger", {}).get("name") == "trade":
                        conditions.append("Trade")
                    if details.get("min_happiness"):
                        conditions.append("Friendship " + str(details["min_happiness"]) + "+")
                    if details.get("time_of_day"):
                        conditions.append(details["time_of_day"].title() + " time")
                    if details.get("known_move", {}).get("name"):
                        conditions.append("Knows " + details["known_move"]["name"].replace("-", " ").title())
                    if details.get("location", {}).get("name"):
                        conditions.append("At " + details["location"]["name"].replace("-", " ").title())
                    requirement = ", ".join(conditions) if conditions else "Special condition; see Pokédex"
                    transitions.append(node["species"]["name"].title() + " → " +
                                       child["species"]["name"].title() + " (" + requirement + ")")
                    flatten(child)
            flatten(evo["chain"])
            extra += '<p><strong>Evolution family:</strong> ' + " → ".join(esc(x) for x in family) + '</p>'
            if transitions:
                extra += '<p><strong>Evolution requirements:</strong></p><ul>' + ''.join('<li>' + esc(t) + '</li>' for t in transitions) + '</ul>'
            if not selected_evolves:
                extra += '<p><strong>Evolution:</strong> This Pokémon does not evolve further.</p>'
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
@login_required
def collection():
    if request.method == "POST":
        try:
            instance_id = int(request.form.get("pokemon_instance_id", ""))
        except (ValueError, TypeError):
            instance_id = None
        action = request.form.get("action")
        if instance_id is not None:
            owned = OwnedPokemon.query.filter_by(
                id=instance_id, user_id=current_user.id
            ).first()
            if owned and action == "remove":
                sql_db.session.delete(owned)
                sql_db.session.commit()
            elif owned and action == "train":
                owned.exp = max(0, owned.exp or 0) + 25
                while owned.level < 100:
                    needed = 100 + (owned.level - 1) * 25
                    if owned.exp < needed:
                        break
                    owned.exp -= needed
                    owned.level += 1
                sql_db.session.commit()
        return redirect(url_for("collection"))

    owned_pokemon = OwnedPokemon.query.filter_by(
        user_id=current_user.id
    ).order_by(OwnedPokemon.id.desc()).all()

    items = ""
    for pokemon in owned_pokemon:
        name = esc(pokemon.pokemon_name.title())
        exp_now = max(0, pokemon.exp or 0)
        exp_needed = 100 + (pokemon.level - 1) * 25
        progress = min(100, int(exp_now * 100 / exp_needed))
        sprite = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{pokemon.pokemon_id}.png"
        items += f"""
        <div class="card pokebox-card">
          <img src="{sprite}" alt="{name}" loading="lazy" width="112" height="112">
          <strong>{name} #{pokemon.pokemon_id:03}</strong>
          <p><span class="tag">Level {pokemon.level}</span>
             <span class="tag">{esc(pokemon.rarity)}</span></p>
          <p>EXP: {exp_now} / {exp_needed}</p>
          <div style="height:10px;background:#303b58;border-radius:8px;overflow:hidden">
            <div style="height:10px;width:{progress}%;background:#38d9a9"></div>
          </div>
          <form method="post">
            <input type="hidden" name="pokemon_instance_id" value="{pokemon.id}">
            <button class="btn blue" name="action" value="train">Train +25 EXP</button>
            <button class="btn red" name="action" value="remove">Release Pokémon</button>
          </form>
        </div>
        """

    if not items:
        items = '<p class="card">Your collection is empty. Find a wild encounter to catch your first Pokémon!</p>'

    content = (
        '<h2>🎒 My Collection</h2>'
        f'<div class="card"><h3>🏅 Trainer Profile</h3>'
        f'<p>Trainer: {esc(current_user.username)}</p>'
        f'<p>Level: {current_user.trainer_level} · '
        f'Total XP: {current_user.trainer_xp}</p>'
        f'<p class="muted">Each catch awards 50 XP. XP needed for '
        f'the next level increases with your current level.</p></div>'
        f'<p class="muted">Pokémon owned: {len(owned_pokemon)}</p>'
        f'<div class="grid">{items}</div>'
    )
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
@login_required
def random_pokemon():
    data, rarity, level = make_encounter(current_user.trainer_level)
    content = '<h2>✨ Wild Encounter!</h2>'

    if data:
        session["wild_encounter"] = {
            "pokemon_id": data["id"],
            "level": level,
            "rarity": rarity,
        }
        content += pokemon_card(data)
        content += f"""
        <div class="card">
          <h3>A wild {esc(data["name"].title())} appeared!</h3>
          <p><span class="tag">{esc(rarity)}</span>
             <span class="tag">Level {level}</span></p>
          <p>Base stat total: {sum(x["base_stat"] for x in data.get("stats", []))}</p>
          <form method="post" action="/catch">
            <input type="hidden" name="pokemon_id" value="{data["id"]}">
            <button class="btn green" type="submit">🎯 Guaranteed Catch</button>
          </form>
          <a class="btn" href="/random">Find another Pokémon</a>
        </div>
        """
    else:
        content += '<p class="card">PokéAPI is unavailable. Try again.</p>'
        content += '<a class="btn" href="/random">Try again</a>'

    return page("Wild Encounter", content)


@app.route("/catch", methods=["POST"])
@login_required
def catch_pokemon():
    encounter = session.get("wild_encounter")
    try:
        pokemon_id = int(request.form.get("pokemon_id", ""))
    except (ValueError, TypeError):
        return redirect(url_for("random_pokemon"))

    if not encounter or encounter.get("pokemon_id") != pokemon_id:
        return redirect(url_for("random_pokemon"))

    data = get_pokemon(pokemon_id)
    if not data:
        return redirect(url_for("random_pokemon"))

    owned = OwnedPokemon(
        user_id=current_user.id,
        pokemon_name=data["name"],
        pokemon_id=data["id"],
        level=int(encounter["level"]),
        rarity=str(encounter["rarity"]),
        exp=0,
    )
    current_user.trainer_xp += 50
    refresh_trainer_level(current_user)
    sql_db.session.add(owned)
    sql_db.session.commit()
    session.pop("wild_encounter", None)

    return redirect(url_for("collection"))


@app.route("/register", methods=["GET", "POST"])
def register():
    message = ""

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        invite_code = request.form.get("invite_code", "").strip()
        invitation = None
        if invite_code:
            invite_hash = hashlib.sha256(invite_code.encode("utf-8")).hexdigest()
            invitation = Invitation.query.filter_by(code_hash=invite_hash, used_by_id=None).first()

        if not username or not password:
            message = "Enter both a username and password."
        elif not invitation:
            message = "A valid, unused invitation code is required."
        elif len(username) > 40:
            message = "Username must be 40 characters or fewer."
        elif len(password) < 8:
            message = "Password must be at least 8 characters."
        elif User.query.filter(sql_db.func.lower(User.username) == username.lower()).first():
            message = "That username is already taken."
        else:
            user = User(
                username=username,
                password_hash=generate_password_hash(password)
            )
            sql_db.session.add(user)
            sql_db.session.flush()
            invitation.used_by_id = user.id
            invitation.used_at = datetime.utcnow()
            sql_db.session.commit()
            login_user(user)
            return redirect(url_for("home"))

    content = f"""
    <section class="card">
      <h2>Create Trainer Account</h2>
      <p>{html.escape(message)}</p>
      <p>Registration is invitation-only. Ask the site owner for a code.</p>
      <form method="post">
        <input name="invite_code" placeholder="Invitation code" autocomplete="off" required>
        <input name="username" placeholder="Choose a username"
               maxlength="40" required>
        <input name="password" type="password"
               placeholder="Password (8+ characters)" minlength="8" required>
        <button class="btn green" type="submit">Register</button>
      </form>
      <p>Already registered? <a href="/login">Log in</a></p>
    </section>
    """
    return page("Register", content)


@app.route("/login", methods=["GET", "POST"])
def login():
    message = ""

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for("home"))

        message = "Incorrect username or password."

    content = f"""
    <section class="card">
      <h2>Trainer Login</h2>
      <p>{html.escape(message)}</p>
      <form method="post">
        <input name="username" placeholder="Username" maxlength="40" required>
        <input name="password" type="password" placeholder="Password" required>
        <button class="btn blue" type="submit">Log In</button>
      </form>
      <p>New trainer? <a href="/register">Create an account</a></p>
    </section>
    """
    return page("Login", content)


def is_site_owner(user):
    return bool(user and getattr(user, "is_authenticated", False)
                and user.username == "Luffy")


@app.route("/owner/invitations", methods=["GET", "POST"])
@login_required
def owner_invitations():
    if not is_site_owner(current_user):
        return page("Forbidden", '<section class="card"><h2>Access denied</h2><p>Only the Luffy owner account can manage invitations.</p></section>'), 403
    new_code = None
    owner_csrf = session.get("owner_invite_csrf")
    if not owner_csrf:
        owner_csrf = secrets.token_urlsafe(24)
        session["owner_invite_csrf"] = owner_csrf
    if request.method == "POST":
        supplied = request.form.get("csrf_token", "")
        if not secrets.compare_digest(supplied, owner_csrf):
            return page("Forbidden", "<section class='card'>Invalid form token. Reload and try again.</section>"), 400
        new_code = secrets.token_urlsafe(12)
        code_hash = hashlib.sha256(new_code.encode("utf-8")).hexdigest()
        sql_db.session.add(Invitation(code_hash=code_hash, created_by_id=current_user.id))
        sql_db.session.commit()
    invitations = Invitation.query.order_by(Invitation.id.desc()).limit(30).all()
    rows = "".join(
        f'<li>Invitation #{row.id} — '
        + ("Used" if row.used_by_id else "Unused")
        + f' — created {row.created_at.strftime("%Y-%m-%d %H:%M UTC")}</li>'
        for row in invitations
    ) or "<li>No invitations generated yet.</li>"
    fresh = f'<section class="card"><h3>Copy this new code now</h3><code>{esc(new_code)}</code><p>This code is shown only once. Save it securely.</p></section>' if new_code else ""
    content = f'<h2>Owner invitation manager</h2><p>Signed in as {esc(current_user.username)}. Each invitation can be used once.</p>{fresh}<section class="card"><form method="post"><input type="hidden" name="csrf_token" value="{esc(owner_csrf)}"><button class="btn green">Generate invitation</button></form><h3>Recent invitations</h3><ul>{rows}</ul></section>'
    return page("Owner Invitations", content)


@app.before_request
def invitation_access_gate():
    public_endpoints = {"home", "login", "register", "static"}
    if request.endpoint is None or request.endpoint in public_endpoints:
        return None
    if not current_user.is_authenticated:
        return redirect(url_for("login", next=request.path))
    return None


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("home"))

from multiplayer import register_multiplayer
register_multiplayer(
    app, sql_db, User, OwnedPokemon, page, api_get, API,
    refresh_trainer_level
)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
