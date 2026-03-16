#!/usr/bin/env python3
"""
Knicks Score Bot - Request-driven version for Render free tier
Each HTTP request checks the score and sends to GroupMe if changed.
Cron-job.org hits the URL every minute to trigger checks.

Setup:  pip install nba_api requests flask pandas
Run:    python3 knicks_score_bot.py
"""

import os
import json
import random
import requests
from datetime import datetime
from flask import Flask
from nba_api.live.nba.endpoints import scoreboard, boxscore
from nba_api.stats.endpoints import teamgamelog, leaguegamefinder

GROUPME_BOT_ID  = "2443fc8d8dd5281ceb9acc3f65"
GROUPME_API_URL = "https://api.groupme.com/v3/bots/post"
KNICKS_TEAM_ID  = 1610612752
LAKERS_TEAM_ID  = 1610612747
STATE_FILE      = "/tmp/knicks_state.json"

app = Flask(__name__)

# ── Trash talk ─────────────────────────────────────────────────────────────────

FALLBACK_TRAIL = ["Classic Knicks. Classic.", "The Garden is quiet tonight.", "Thibodeau playing starters 40 min again."]
FALLBACK_WIN   = ["Good win. Lakers are still better.", "A win is a win. Even a Knicks win.", "Enjoy it. Won't last."]
FALLBACK_HYPE  = ["Lakers quietly cooking this season.", "Crypto.com Arena > Madison Square Garden."]
FALLBACK_H2H   = ["Lakers own the Knicks. History says so.", "This matchup always ends the same way."]

def get_recent_games(team_id, n=5):
    try:
        log = teamgamelog.TeamGameLog(team_id=team_id, season="2024-25")
        df  = log.get_data_frames()[0].head(n)
        return [{"matchup": r["MATCHUP"], "wl": r["WL"], "pts": int(r["PTS"]),
                 "opp_pts": int(r["PTS"] - r["PLUS_MINUS"])} for _, r in df.iterrows()]
    except:
        return []

def get_head_to_head(n=3):
    try:
        finder = leaguegamefinder.LeagueGameFinder(team_id_nullable=LAKERS_TEAM_ID, season_nullable="2024-25")
        df = finder.get_data_frames()[0]
        h2h = df[df["MATCHUP"].str.contains("NYK")].head(n)
        return [{"wl": r["WL"], "pts": int(r["PTS"]), "opp_pts": int(r["PTS"] - r["PLUS_MINUS"]),
                 "date": r["GAME_DATE"]} for _, r in h2h.iterrows()]
    except:
        return []

def build_trash_talk():
    lakers = get_recent_games(LAKERS_TEAM_ID, 5)
    knicks = get_recent_games(KNICKS_TEAM_ID, 5)
    h2h    = get_head_to_head(3)

    trail, win, hype, h2h_lines = [], [], [], []

    if lakers:
        wins = sum(1 for g in lakers if g["wl"] == "W")
        if wins >= 4:
            hype.append(f"Lakers are {wins}-{5-wins} in their last 5. Just saying.")
        best = max((g for g in lakers if g["wl"] == "W"), key=lambda g: g["pts"]-g["opp_pts"], default=None)
        if best:
            hype.append(f"Lakers beat {best['matchup'].split()[-1]} by {best['pts']-best['opp_pts']} recently.")

    if knicks:
        losses = sum(1 for g in knicks if g["wl"] == "L")
        if losses >= 3:
            trail.append(f"The Knicks are {5-losses}-{losses} in their last 5. Rough.")
            win.append(f"Good win. The Knicks needed that after going {5-losses}-{losses} recently.")
        worst = max((g for g in knicks if g["wl"] == "L"), key=lambda g: g["opp_pts"]-g["pts"], default=None)
        if worst:
            trail.append(f"They just lost to {worst['matchup'].split()[-1]} by {worst['opp_pts']-worst['pts']}.")

    for g in h2h:
        if g["wl"] == "W":
            h2h_lines.append(f"Lakers beat the Knicks {g['pts']}-{g['opp_pts']} on {g['date']}.")
        else:
            h2h_lines.append(f"Knicks got lucky {g['opp_pts']}-{g['pts']} last time. Won't happen again.")

    trail    = trail    or FALLBACK_TRAIL
    win      = win      or FALLBACK_WIN
    hype     = hype     or FALLBACK_HYPE
    h2h_lines= h2h_lines or FALLBACK_H2H

    trail    += ["MSG is the most overrated arena in the league.", "Brunson is tired."]
    win      += ["Good for them. Still not winning a title.", "Alert the media. The Knicks won."]
    hype     += ["The Lakers have more titles than the Knicks have rings.", "Crypto.com > MSG."]

    return trail, win, hype, h2h_lines

_trash_cache = {"data": None, "date": None}

def get_trash():
    today = datetime.now().strftime("%Y-%m-%d")
    if _trash_cache["date"] != today:
        _trash_cache["data"] = build_trash_talk()
        _trash_cache["date"] = today
    return _trash_cache["data"]

def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except:
        return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def send(text):
    try:
        r = requests.post(GROUPME_API_URL, json={"bot_id": GROUPME_BOT_ID, "text": text}, timeout=10)
        return r.status_code == 202
    except:
        return False

def get_knicks_game():
    try:
        games = scoreboard.ScoreBoard().games.get_dict()
        for game in games:
            if game["homeTeam"]["teamId"] == KNICKS_TEAM_ID or \
               game["awayTeam"]["teamId"] == KNICKS_TEAM_ID:
                return game
    except Exception as e:
        print(f"NBA API error: {e}")
    return None

def get_top_performers(game_id):
    try:
        box = boxscore.BoxScore(game_id=game_id)
        game_data = box.game.get_dict()
        lines = []
        best_player = None
        best_pts = -1
        for team_key in ["homeTeam", "awayTeam"]:
            team = game_data[team_key]
            tricode = team["teamTricode"]
            players = [p for p in team.get("players", [])
                       if p["statistics"].get("points", 0) > 0 or p["statistics"].get("reboundsTotal", 0) > 0]
            if not players:
                continue
            top_scorer = max(players, key=lambda p: p["statistics"].get("points", 0))
            top_reb    = max(players, key=lambda p: p["statistics"].get("reboundsTotal", 0))
            top_ast    = max(players, key=lambda p: p["statistics"].get("assists", 0))
            lines.append(
                f"{tricode}\n"
                f"  PTS: {top_scorer['name'].split()[-1]} {top_scorer['statistics']['points']}\n"
                f"  REB: {top_reb['name'].split()[-1]} {top_reb['statistics']['reboundsTotal']}\n"
                f"  AST: {top_ast['name'].split()[-1]} {top_ast['statistics']['assists']}"
            )
            if top_scorer["statistics"]["points"] > best_pts:
                best_pts = top_scorer["statistics"]["points"]
                best_player = (tricode, top_scorer)
        result = ["Top Performers:\n" + "\n".join(lines)]
        if best_player:
            tricode, p = best_player
            s = p["statistics"]
            mins = s.get("minutesCalculated","PT0M").replace("PT","").replace("M"," min")
            fg = f"{s.get('fieldGoalsMade',0)}/{s.get('fieldGoalsAttempted',0)}"
            tp = f"{s.get('threePointersMade',0)}/{s.get('threePointersAttempted',0)}"
            ft = f"{s.get('freeThrowsMade',0)}/{s.get('freeThrowsAttempted',0)}"
            result.append(
                f"\nBest Player: {p['name']} ({tricode})\n"
                f"  {s.get('points',0)} pts | {s.get('reboundsTotal',0)} reb | {s.get('assists',0)} ast\n"
                f"  {s.get('steals',0)} stl | {s.get('blocks',0)} blk | {s.get('turnovers',0)} tov\n"
                f"  FG: {fg} | 3P: {tp} | FT: {ft}\n"
                f"  +/-: {s.get('plusMinusPoints',0)} | {mins}"
            )
        return "\n".join(result)
    except Exception as e:
        print(f"Boxscore error: {e}")
        return None

def score_key(game):
    return f"{game['homeTeam']['score']}-{game['awayTeam']['score']}-Q{game.get('period',0)}"

def get_knicks_scores(game):
    home, away = game["homeTeam"], game["awayTeam"]
    vs_lakers = home["teamId"] == LAKERS_TEAM_ID or away["teamId"] == LAKERS_TEAM_ID
    if home["teamId"] == KNICKS_TEAM_ID:
        knicks, opp, opp_name = home["score"], away["score"], away["teamName"]
    else:
        knicks, opp, opp_name = away["score"], home["score"], home["teamName"]
    return knicks, opp, opp_name, vs_lakers

def format_live(game):
    knicks, opp, opp_name, vs_lakers = get_knicks_scores(game)
    trail, win, hype, h2h_lines = get_trash()
    period = game.get("period", "?")
    period_str = f"Q{period}" if isinstance(period, int) and period <= 4 else f"OT{period-4}"
    clock = game.get("gameClock","").replace("PT","").replace("M",":").replace("S","").strip()
    clock_str = f" {clock}" if clock else ""
    if knicks > opp:
        quip = random.choice(h2h_lines if vs_lakers else win)
        status = f"NYK LEAD\n{quip}"
    elif knicks < opp:
        quip = random.choice(h2h_lines if vs_lakers else trail)
        status = f"NYK TRAIL\n{quip}"
    else:
        status = "TIED\nDon't get excited. It's a tie."
    return f"{period_str}{clock_str}\nNYK {knicks} - {opp} {opp_name}\n{status}"

def format_final(game):
    knicks, opp, opp_name, vs_lakers = get_knicks_scores(game)
    trail, win, hype, h2h_lines = get_trash()
    if knicks > opp:
        result = f"NYK WIN\n{random.choice(win)}"
    else:
        quip = random.choice(h2h_lines if vs_lakers else trail)
        result = f"NYK LOSS\n{quip}"
    return f"FINAL\nNYK {knicks} - {opp} {opp_name}\n{result}"

@app.route("/")
def check_score():
    state = load_state()
    game  = get_knicks_game()

    if not game:
        return "No Knicks game today", 200

    game_id = game["gameId"]
    status  = game["gameStatus"]

    if state.get("game_id") != game_id:
        state = {"game_id": game_id}

    messages_sent = []

    if status == 1 and not state.get("preview_sent"):
        trail, win, hype, h2h_lines = get_trash()
        home   = game["homeTeam"]["teamName"]
        away   = game["awayTeam"]["teamName"]
        tipoff = game.get("gameStatusText", "TBD")
        vs_lakers = game["homeTeam"]["teamId"] == LAKERS_TEAM_ID or game["awayTeam"]["teamId"] == LAKERS_TEAM_ID
        extra = f" {random.choice(h2h_lines)}" if vs_lakers else ""
        send(f"Knicks game today!\n{away} @ {home}\nTipoff: {tipoff}{extra}")
        state["preview_sent"] = True
        messages_sent.append("preview")

    elif status == 2:
        key = score_key(game)
        if state.get("last_score") != key:
            send(format_live(game))
            state["last_score"] = key
            messages_sent.append(f"score: {key}")

        current_period = game.get("period", 0)
        last_period    = state.get("last_period", 0)
        sent_quarters  = state.get("sent_quarters", [])

        if current_period > last_period and last_period > 0 and last_period not in sent_quarters:
            performers = get_top_performers(game_id)
            if performers:
                period_label = f"Q{last_period}" if last_period <= 4 else f"OT{last_period-4}"
                send(f"-- End of {period_label} --\n{performers}")
            sent_quarters.append(last_period)
            state["sent_quarters"] = sent_quarters
            messages_sent.append(f"quarter end Q{last_period}")

        # Random Lakers hype once per game (at Q2)
        if current_period == 2 and not state.get("hype_sent"):
            _, _, hype, _ = get_trash()
            send(random.choice(hype))
            state["hype_sent"] = True

        state["last_period"] = current_period

    elif status == 3 and not state.get("final_sent"):
        send(format_final(game))
        performers = get_top_performers(game_id)
        if performers:
            send(f"-- Final Stats --\n{performers}")
        state["final_sent"] = True
        messages_sent.append("final")

    save_state(state)
    now = datetime.now().strftime("%H:%M:%S")
    return f"[{now}] OK - {', '.join(messages_sent) if messages_sent else 'no change'}", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
