import json
import random
import secrets
import html

from flask import (
    request, redirect, url_for, session, abort
)
from flask_login import login_required, current_user
from sqlalchemy import UniqueConstraint, or_


def register_multiplayer(app, sql_db, User, OwnedPokemon, page,
                         api_get, API, refresh_trainer_level):

    class FriendRequest(sql_db.Model):
        id = sql_db.Column(sql_db.Integer, primary_key=True)
        sender_id = sql_db.Column(
            sql_db.Integer, sql_db.ForeignKey("user.id"), nullable=False
        )
        receiver_id = sql_db.Column(
            sql_db.Integer, sql_db.ForeignKey("user.id"), nullable=False
        )
        status = sql_db.Column(
            sql_db.String(20), nullable=False, default="pending"
        )
        __table_args__ = (
            UniqueConstraint("sender_id", "receiver_id"),
        )

    class Friendship(sql_db.Model):
        id = sql_db.Column(sql_db.Integer, primary_key=True)
        user_a_id = sql_db.Column(
            sql_db.Integer, sql_db.ForeignKey("user.id"), nullable=False
        )
        user_b_id = sql_db.Column(
            sql_db.Integer, sql_db.ForeignKey("user.id"), nullable=False
        )
        __table_args__ = (
            UniqueConstraint("user_a_id", "user_b_id"),
        )

    class Battle(sql_db.Model):
        id = sql_db.Column(sql_db.Integer, primary_key=True)
        challenger_id = sql_db.Column(
            sql_db.Integer, sql_db.ForeignKey("user.id"), nullable=False
        )
        opponent_id = sql_db.Column(
            sql_db.Integer, sql_db.ForeignKey("user.id"), nullable=False
        )
        status = sql_db.Column(
            sql_db.String(20), nullable=False, default="pending"
        )
        state_json = sql_db.Column(sql_db.Text, nullable=False, default="{}")
        current_turn_user_id = sql_db.Column(sql_db.Integer)
        winner_id = sql_db.Column(sql_db.Integer)

    with app.app_context():
        sql_db.create_all()

    type_cache = {}

    def e(value):
        return html.escape(str(value))

    def token_field():
        if "multiplayer_csrf" not in session:
            session["multiplayer_csrf"] = secrets.token_urlsafe(24)
        return (
            '<input type="hidden" name="csrf_token" value="'
            + e(session["multiplayer_csrf"]) + '">'
        )

    def check_token():
        supplied = request.form.get("csrf_token", "")
        expected = session.get("multiplayer_csrf", "")
        if not expected or not secrets.compare_digest(supplied, expected):
            abort(400, "Invalid form token. Reload the page and try again.")

    def friends_with(user_id):
        rows = Friendship.query.filter(
            or_(Friendship.user_a_id == user_id,
                Friendship.user_b_id == user_id)
        ).all()
        ids = {
            r.user_b_id if r.user_a_id == user_id else r.user_a_id
            for r in rows
        }
        return ids

    def are_friends(a, b):
        low, high = sorted((a, b))
        return Friendship.query.filter_by(
            user_a_id=low, user_b_id=high
        ).first() is not None

    def owned_team(owner_id, raw_ids):
        ids = []
        for raw in raw_ids:
            try:
                item_id = int(raw)
            except (ValueError, TypeError):
                continue
            if item_id not in ids:
                ids.append(item_id)
        if not 1 <= len(ids) <= 6:
            return None

        owned = OwnedPokemon.query.filter(
            OwnedPokemon.user_id == owner_id,
            OwnedPokemon.id.in_(ids)
        ).all()
        by_id = {p.id: p for p in owned}
        if len(by_id) != len(ids):
            return None

        result = []
        for item_id in ids:
            mon = by_id[item_id]
            data = api_get(f"{API}/pokemon/{mon.pokemon_id}")
            if not data:
                return None

            stats = {
                s["stat"]["name"]: s["base_stat"]
                for s in data.get("stats", [])
            }
            eligible = []
            for entry in data.get("moves", []):
                learned = [
                    detail.get("level_learned_at", 0)
                    for detail in entry.get("version_group_details", [])
                    if detail.get("move_learn_method", {}).get("name")
                    == "level-up"
                ]
                if learned and min(learned) <= (mon.level or 1):
                    eligible.append((max(learned), entry["move"]["name"]))

            names = []
            for _, name in sorted(eligible):
                if name not in names:
                    names.append(name)
            names = names[-4:] or ["tackle"]

            moves = []
            for name in names:
                move_data = api_get(f"{API}/move/{name}")
                if not move_data:
                    continue
                effect = next(
                    (x.get("short_effect", "") for x in
                     move_data.get("effect_entries", [])
                     if x.get("language", {}).get("name") == "en"),
                    ""
                ).lower()
                status = None
                if name in ("thunder-wave", "stun-spore"):
                    status = "paralysis"
                elif name in ("toxic", "poison-powder"):
                    status = "poison"
                elif name == "will-o-wisp":
                    status = "burn"
                elif name in ("sleep-powder", "hypnosis", "spore"):
                    status = "sleep"
                elif "may paralyze" in effect:
                    status = "paralysis"
                elif "may poison" in effect:
                    status = "poison"
                elif "may burn" in effect:
                    status = "burn"
                elif "may put the target to sleep" in effect:
                    status = "sleep"

                moves.append({
                    "name": name.replace("-", " ").title(),
                    "power": move_data.get("power") or 0,
                    "accuracy": move_data.get("accuracy") or 100,
                    "type": move_data.get("type", {}).get("name", "normal"),
                    "class": move_data.get("damage_class", {}).get("name",
                                                                   "physical"),
                    "status": status,
                    "effect_chance": move_data.get("effect_chance") or 100,
                })

            if not moves:
                moves = [{
                    "name": "Tackle", "power": 40, "accuracy": 100,
                    "type": "normal", "class": "physical",
                    "status": None, "effect_chance": 0
                }]

            result.append({
                "owned_id": mon.id,
                "name": mon.pokemon_name.title(),
                "pokemon_id": mon.pokemon_id,
                "level": max(1, min(100, mon.level or 1)),
                "types": [t["type"]["name"] for t in data.get("types", [])],
                "stats": stats,
                "hp": max(1, (stats.get("hp", 50) * 2 *
                              max(1, mon.level or 1)) // 100 +
                          max(1, mon.level or 1) + 10),
                "moves": moves,
                "status": None,
                "sleep_turns": 0,
            })
            result[-1]["max_hp"] = result[-1]["hp"]
        return result

    def type_multiplier(move_type, defender_types):
        if move_type not in type_cache:
            data = api_get(f"{API}/type/{move_type}")
            type_cache[move_type] = data or {}
        relations = type_cache[move_type].get("damage_relations", {})
        multiplier = 1.0
        for defender_type in defender_types:
            for key, factor in (
                ("double_damage_to", 2.0),
                ("half_damage_to", 0.5),
                ("no_damage_to", 0.0),
            ):
                if any(x["name"] == defender_type
                       for x in relations.get(key, [])):
                    multiplier *= factor
        return multiplier

    def save_state(battle, state):
        battle.state_json = json.dumps(state)

    def finish_battle(battle, state, winner_id):
        if battle.status == "finished":
            return
        battle.status = "finished"
        battle.winner_id = winner_id
        battle.current_turn_user_id = None
        loser_id = (
            battle.opponent_id if winner_id == battle.challenger_id
            else battle.challenger_id
        )
        winner = sql_db.session.get(User, winner_id)
        loser = sql_db.session.get(User, loser_id)
        if winner:
            winner.trainer_xp += 100
            refresh_trainer_level(winner)
        if loser:
            loser.trainer_xp += 25
            refresh_trainer_level(loser)
        save_state(battle, state)

    def alive_team(state, user_id):
        return [
            i for i, mon in enumerate(state["teams"][str(user_id)])
            if mon["hp"] > 0
        ]

    def active_mon(state, user_id):
        team = state["teams"][str(user_id)]
        index = state["active"][str(user_id)]
        return team[index]

    def render_team_picker(owner_id, heading):
        owned = OwnedPokemon.query.filter_by(user_id=owner_id).order_by(
            OwnedPokemon.id.desc()
        ).all()
        if not owned:
            return "<p>Catch a Pokémon before battling.</p>"
        out = f"<h3>{e(heading)}</h3><p>Choose 1–6 Pokémon.</p>"
        for mon in owned:
            out += (
                '<label style="display:block;margin:8px 0">'
                f'<input type="checkbox" name="pokemon_ids" '
                f'value="{mon.id}"> '
                f'{e(mon.pokemon_name.title())} · Lv. {mon.level} · '
                f'{e(mon.rarity)}</label>'
            )
        return out

    @app.route("/friends", methods=["GET", "POST"])
    @login_required
    def friend_page():
        message = ""
        if request.method == "POST":
            check_token()
            action = request.form.get("action", "")
            try:
                target_id = int(request.form.get("user_id", ""))
            except (ValueError, TypeError):
                target_id = -1

            target = sql_db.session.get(User, target_id)
            if action == "send":
                if not target or target.id == current_user.id:
                    message = "Choose another valid trainer."
                elif are_friends(current_user.id, target.id):
                    message = "You're already friends."
                else:
                    existing = FriendRequest.query.filter(
                        FriendRequest.status == "pending",
                        or_(
                            (FriendRequest.sender_id == current_user.id) &
                            (FriendRequest.receiver_id == target.id),
                            (FriendRequest.sender_id == target.id) &
                            (FriendRequest.receiver_id == current_user.id)
                        )
                    ).first()
                    if existing:
                        message = "A request already exists."
                    else:
                        sql_db.session.add(FriendRequest(
                            sender_id=current_user.id,
                            receiver_id=target.id
                        ))
                        sql_db.session.commit()
                        message = "Friend request sent."
            elif action in ("accept", "decline"):
                req = sql_db.session.get(
                    FriendRequest,
                    int(request.form.get("request_id", "0") or 0)
                )
                if req and req.receiver_id == current_user.id \
                        and req.status == "pending":
                    if action == "accept":
                        low, high = sorted((req.sender_id, req.receiver_id))
                        if not are_friends(low, high):
                            sql_db.session.add(Friendship(
                                user_a_id=low, user_b_id=high
                            ))
                    sql_db.session.delete(req)
                    sql_db.session.commit()
            elif action == "remove":
                low, high = sorted((current_user.id, target_id))
                Friendship.query.filter_by(
                    user_a_id=low, user_b_id=high
                ).delete()
                sql_db.session.commit()

        query = request.args.get("q", "").strip()[:40]
        users = []
        if query:
            users = User.query.filter(
                User.username.ilike(f"%{query}%"),
                User.id != current_user.id
            ).limit(20).all()

        incoming = FriendRequest.query.filter_by(
            receiver_id=current_user.id, status="pending"
        ).all()
        friends = [
            sql_db.session.get(User, uid)
            for uid in friends_with(current_user.id)
        ]
        out = (
            f"<h2>👥 Friends</h2><p>{e(message)}</p>"
            '<form method="get"><input name="q" maxlength="40" '
            'placeholder="Search trainer username" value="' + e(query) +
            '"><button class="btn blue">Search</button></form>'
        )
        for user in users:
            out += (
                f'<section class="card"><strong>{e(user.username)}</strong>'
                '<form method="post">' + token_field() +
                f'<input type="hidden" name="user_id" value="{user.id}">'
                '<button class="btn green" name="action" value="send">'
                'Send request</button></form></section>'
            )
        out += "<h3>Incoming requests</h3>"
        if not incoming:
            out += "<p>No pending requests.</p>"
        for req in incoming:
            sender = sql_db.session.get(User, req.sender_id)
            out += (
                f'<section class="card">{e(sender.username if sender else "Trainer")}'
                '<form method="post">' + token_field() +
                f'<input type="hidden" name="request_id" value="{req.id}">'
                '<button class="btn green" name="action" value="accept">'
                'Accept</button><button class="btn red" name="action" '
                'value="decline">Decline</button></form></section>'
            )
        out += "<h3>Your friends</h3>"
        for friend in friends:
            if friend:
                out += (
                    f'<section class="card"><strong>{e(friend.username)}</strong>'
                    '<form method="post">' + token_field() +
                    f'<input type="hidden" name="user_id" value="{friend.id}">'
                    '<button class="btn red" name="action" value="remove">'
                    'Remove friend</button></form></section>'
                )
        out += '<p><a class="btn" href="/battles">Go to battles</a></p>'
        return page("Friends", out)

    @app.route("/battles", methods=["GET", "POST"])
    @login_required
    def battles_page():
        message = ""
        if request.method == "POST":
            check_token()
            try:
                opponent_id = int(request.form.get("opponent_id", ""))
            except (ValueError, TypeError):
                opponent_id = -1
            if not are_friends(current_user.id, opponent_id):
                message = "You can only challenge an accepted friend."
            else:
                team = owned_team(
                    current_user.id, request.form.getlist("pokemon_ids")
                )
                if not team:
                    message = "Choose valid Pokémon you own (1–6)."
                else:
                    battle = Battle(
                        challenger_id=current_user.id,
                        opponent_id=opponent_id,
                        status="pending",
                        state_json=json.dumps({
                            "teams": {str(current_user.id): team},
                            "active": {str(current_user.id): 0},
                            "log": ["Challenge sent!"]
                        })
                    )
                    sql_db.session.add(battle)
                    sql_db.session.commit()
                    return redirect(url_for("battle_page",
                                             battle_id=battle.id))

        friend_ids = friends_with(current_user.id)
        friends = [
            sql_db.session.get(User, uid) for uid in friend_ids
        ]
        owned = OwnedPokemon.query.filter_by(
            user_id=current_user.id
        ).order_by(OwnedPokemon.id.desc()).all()
        out = (
            f"<h2>⚔️ Trainer Battles</h2><p>{e(message)}</p>"
            "<p>Choose up to six Pokémon; only one is active at a time.</p>"
        )
        if not friends:
            out += '<p>Add friends first on <a href="/friends">Friends</a>.</p>'
        elif not owned:
            out += "<p>Catch a Pokémon before challenging someone.</p>"
        else:
            for friend in friends:
                if not friend:
                    continue
                out += (
                    f'<section class="card"><h3>Challenge {e(friend.username)}</h3>'
                    '<form method="post">' + token_field() +
                    f'<input type="hidden" name="opponent_id" value="{friend.id}">'
                )
                out += render_team_picker(current_user.id, "Your team")
                out += (
                    '<button class="btn blue" type="submit">Send challenge</button>'
                    '</form></section>'
                )

        battles = Battle.query.filter(
            or_(Battle.challenger_id == current_user.id,
                Battle.opponent_id == current_user.id)
        ).order_by(Battle.id.desc()).limit(30).all()
        out += "<h3>Your challenges and battles</h3>"
        for b in battles:
            other_id = (
                b.opponent_id if b.challenger_id == current_user.id
                else b.challenger_id
            )
            other = sql_db.session.get(User, other_id)
            out += (
                f'<section class="card">Battle #{b.id} with '
                f'{e(other.username if other else "Trainer")} · '
                f'{e(b.status.title())} '
                f'<a class="btn" href="/battle/{b.id}">Open</a></section>'
            )
        out += '<p><a href="/friends">Manage friends</a></p>'
        return page("Battles", out)

    @app.route("/battle/<int:battle_id>", methods=["GET", "POST"])
    @login_required
    def battle_page(battle_id):
        battle = sql_db.session.get(Battle, battle_id)
        if not battle or current_user.id not in (
            battle.challenger_id, battle.opponent_id
        ):
            abort(404)

        state = json.loads(battle.state_json or "{}")
        uid = str(current_user.id)
        message = ""

        if request.method == "POST":
            check_token()
            action = request.form.get("action", "")

            if battle.status == "pending" and \
                    current_user.id == battle.opponent_id and action == "accept":
                if not are_friends(battle.challenger_id, battle.opponent_id):
                    abort(403)
                team = owned_team(
                    current_user.id, request.form.getlist("pokemon_ids")
                )
                if not team:
                    message = "Choose valid Pokémon you own (1–6)."
                else:
                    state.setdefault("teams", {})[uid] = team
                    state.setdefault("active", {})[uid] = 0
                    state.setdefault("log", []).append(
                        "Both trainers are ready. Battle started!"
                    )
                    battle.status = "active"
                    battle.current_turn_user_id = battle.challenger_id
                    save_state(battle, state)
                    sql_db.session.commit()
                    return redirect(url_for("battle_page", battle_id=battle.id))

            elif battle.status == "pending" and \
                    current_user.id == battle.opponent_id and action == "decline":
                battle.status = "declined"
                sql_db.session.commit()
                return redirect(url_for("battles_page"))

            elif battle.status == "active":
                if battle.current_turn_user_id != current_user.id:
                    message = "It's not your turn yet."
                elif uid not in state.get("teams", {}):
                    abort(403)
                else:
                    team = state["teams"][uid]
                    mon = active_mon(state, current_user.id)

                    if mon["status"] == "poison" or mon["status"] == "burn":
                        mon["hp"] = max(
                            0, mon["hp"] - max(1, mon["max_hp"] // 8)
                        )
                    if mon["hp"] <= 0:
                        if not alive_team(state, current_user.id):
                            finish_battle(
                                battle, state,
                                battle.opponent_id if current_user.id ==
                                battle.challenger_id else battle.challenger_id
                            )
                        else:
                            state["log"].append(
                                f'{mon["name"]} fainted from its status!'
                            )

                    if battle.status != "finished":
                        if action == "switch":
                            try:
                                index = int(request.form.get("index", ""))
                            except (ValueError, TypeError):
                                index = -1
                            if index not in alive_team(state, current_user.id):
                                message = "Choose a living Pokémon to switch to."
                            elif index == state["active"][uid]:
                                message = "That Pokémon is already active."
                            else:
                                state["active"][uid] = index
                                state["log"].append(
                                    f'{current_user.username} switched Pokémon.'
                                )
                        elif action == "move" and mon["hp"] > 0:
                            try:
                                move_index = int(request.form.get("index", ""))
                            except (ValueError, TypeError):
                                move_index = -1
                            if not 0 <= move_index < len(mon["moves"]):
                                message = "Invalid move."
                            else:
                                opponent_id = (
                                    battle.opponent_id
                                    if current_user.id == battle.challenger_id
                                    else battle.challenger_id
                                )
                                enemy = active_mon(state, opponent_id)
                                move = mon["moves"][move_index]
                                log = (
                                    f'{mon["name"]} used {move["name"]}. '
                                )
                                if random.randint(1, 100) > move["accuracy"]:
                                    log += "It missed!"
                                elif move.get("status") and \
                                        random.randint(1, 100) <= \
                                        move.get("effect_chance", 100) and \
                                        not enemy.get("status"):
                                    enemy["status"] = move["status"]
                                    if move["status"] == "sleep":
                                        enemy["sleep_turns"] = random.randint(1, 3)
                                    log += f'{enemy["name"]} got {move["status"]}!'
                                elif move["power"] > 0:
                                    attack_key = (
                                        "special-attack"
                                        if move["class"] == "special"
                                        else "attack"
                                    )
                                    defense_key = (
                                        "special-defense"
                                        if move["class"] == "special"
                                        else "defense"
                                    )
                                    attack = max(1, mon["stats"].get(attack_key, 40))
                                    defense = max(1, enemy["stats"].get(defense_key, 40))
                                    base = (
                                        ((2 * mon["level"] / 5 + 2) *
                                         move["power"] * attack / defense) / 50
                                    ) + 2
                                    mult = type_multiplier(move["type"], enemy["types"])
                                    damage = max(
                                        0, int(base * random.uniform(0.85, 1.0) * mult)
                                    )
                                    enemy["hp"] = max(0, enemy["hp"] - damage)
                                    log += f"It dealt {damage} damage."
                                    if mult > 1:
                                        log += " Super effective!"
                                    elif mult == 0:
                                        log += " It had no effect."
                                    elif mult < 1:
                                        log += " Not very effective."
                                else:
                                    log += "No damage was dealt."
                                state["log"].append(log)

                                if not alive_team(state, opponent_id):
                                    finish_battle(battle, state, current_user.id)

                        else:
                            message = "Choose a move or switch Pokémon."

                    if battle.status == "active" and not message:
                        battle.current_turn_user_id = (
                            battle.opponent_id
                            if current_user.id == battle.challenger_id
                            else battle.challenger_id
                        )
                    save_state(battle, state)
                    sql_db.session.commit()
                    if not message:
                        return redirect(url_for("battle_page",
                                                 battle_id=battle.id))

        challenger = sql_db.session.get(User, battle.challenger_id)
        opponent = sql_db.session.get(User, battle.opponent_id)
        out = (
            f"<h2>Battle #{battle.id}</h2><p>{e(message)}</p>"
            f"<p>{e(challenger.username)} vs. {e(opponent.username)}</p>"
            f"<p>Status: <strong>{e(battle.status.title())}</strong></p>"
        )

        if battle.status == "pending" and current_user.id == battle.opponent_id:
            out += '<section class="card"><h3>Accept challenge</h3>'
            out += '<form method="post">' + token_field()
            out += render_team_picker(current_user.id, "Choose your team")
            out += (
                '<button class="btn green" name="action" value="accept">'
                'Accept battle</button> '
                '<button class="btn red" name="action" value="decline">'
                'Decline</button></form></section>'
            )
        elif battle.status == "pending":
            out += "<p>Waiting for your friend to respond.</p>"
        elif battle.status == "active":
            if uid in state.get("teams", {}):
                my_mon = active_mon(state, current_user.id)
                out += (
                    f'<section class="card"><h3>Your active Pokémon: '
                    f'{e(my_mon["name"])}</h3>'
                    f'<p>Level {my_mon["level"]} · HP '
                    f'{my_mon["hp"]}/{my_mon["max_hp"]} · '
                    f'Status: {e(my_mon["status"] or "healthy")}</p>'
                )
                if battle.current_turn_user_id == current_user.id:
                    out += '<h4>Choose a move</h4>'
                    for i, move in enumerate(my_mon["moves"]):
                        out += (
                            '<form method="post">' + token_field() +
                            f'<input type="hidden" name="index" value="{i}">'
                            '<button class="btn blue" name="action" value="move">'
                            f'{e(move["name"])} · Power {move["power"]} · '
                            f'{e(move["type"].title())}</button></form>'
                        )
                    living = alive_team(state, current_user.id)
                    if len(living) > 1:
                        out += "<h4>Switch Pokémon</h4>"
                        for i in living:
                            if i != state["active"][uid]:
                                bench = state["teams"][uid][i]
                                out += (
                                    '<form method="post">' + token_field() +
                                    f'<input type="hidden" name="index" value="{i}">'
                                    '<button class="btn gold" name="action" '
                                    'value="switch">Switch to '
                                    f'{e(bench["name"])} · HP {bench["hp"]}/'
                                    f'{bench["max_hp"]}</button></form>'
                                )
                else:
                    out += "<p>Waiting for your opponent's turn.</p>"
                out += "</section>"

                other_id = (
                    battle.opponent_id if current_user.id == battle.challenger_id
                    else battle.challenger_id
                )
                if str(other_id) in state.get("teams", {}):
                    foe = active_mon(state, other_id)
                    out += (
                        '<section class="card"><h3>Opponent active Pokémon</h3>'
                        f'<p>{e(foe["name"])} · HP {foe["hp"]}/'
                        f'{foe["max_hp"]} · '
                        f'Status: {e(foe["status"] or "healthy")}</p></section>'
                    )

        elif battle.status == "finished":
            winner = sql_db.session.get(User, battle.winner_id)
            out += (
                '<section class="card"><h3>Battle finished!</h3>'
                f'<p>Winner: {e(winner.username if winner else "Unknown")}</p>'
                '<p>Winner receives 100 trainer XP; the other trainer receives 25.</p>'
                '</section>'
            )

        out += "<h3>Battle log</h3><section class='card'><ul>"
        for entry in state.get("log", [])[-20:]:
            out += f"<li>{e(entry)}</li>"
        out += "</ul></section><p><a href='/battles'>Back to battles</a></p>"
        return page("Battle", out)
