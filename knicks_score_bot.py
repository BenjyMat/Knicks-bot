#!/usr/bin/env python3
"""
Knicks Score Bot for GroupMe - with dynamic Lakers bias
Trash talk pulls real recent game results and builds lines from them.
Runs forever.

Setup:  pip install nba_api requests pandas
Run:    python3 knicks_score_bot.py
"""

import requests
import time
import random
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from nba_api.live.nba.endpoints import scoreboard, boxscore
from nba_api.stats.endpoints import teamgamelog, leaguegamefinder

GROUPME_BOT_ID  = "2443fc8d8dd5281ceb9acc3f65"
GROUPME_API_URL = "https://api.groupme.com/v3/bots/post"
KNICKS_TEAM_ID  = 1610612752
LAKERS_TEAM_ID  = 1610612747

# ── Fetch recent results ───────────────────────────────────────────────────────

def get_recent_games(team_id, n=5):
    """Returns list of recent game dicts: {matchup, wl, pts, opp_pts}"""
    try:
        log = teamgamelog.TeamGameLog(team_id=team_id, season="2024-25")
        df = log.get_data_frames()[0].head(n)
        games = []
        for _, row in df.iterrows():
            games.append({
                "matchup": row["MATCHUP"],
                "wl": row["WL"],
                "pts": int(row["PTS"]),
                "opp_pts": int(row["PTS"] - row["PLUS_MINUS"]),
                "date": row["GAME_DATE"],
            })
        return games
    except Exception as e:
        print(f"Game log error: {e}")
        return []

def get_head_to_head(n=3):
    """Find recent Lakers vs Knicks games."""
    try:
        finder = leaguegamefinder.LeagueGameFinder(team_id_nullable=LAKERS_TEAM_ID, season_nullable="2024-25")
        df = finder.get_data_frames()[0]
        h2h = df[df["MATCHUP"].str.contains("NYK")].head(n)
        games = []
        for _, row in h2h.iterrows():
            games.append({
                "date": row["GAME_DATE"],
                "wl": row["WL"],
                "pts": int(row["PTS"]),
                "opp_pts": int(row["PTS"] - row["PLUS_MINUS"]),
            })
        return games
    except Exception as e:
        print(f"H2H error: {e}")
        return []

# ── Build dynamic trash talk from real data ────────────────────────────────────

def build_trash_talk():
    """Pull real results and build trash talk lines from them."""
    lakers  = get_recent_games(LAKERS_TEAM_ID, 5)
    knicks  = get_recent_games(KNICKS_TEAM_ID, 5)
    h2h     = get_head_to_head(3)

    trail_lines = []
    win_lines   = []
    hype_lines  = []
    h2h_lines   = []

    # Lakers recent form
    if lakers:
        wins  = sum(1 for g in lakers if g["wl"] == "W")
        losses = len(lakers) - wins
        biggest_win = max((g for g in lakers if g["wl"] == "W"), key=lambda g: g["pts"] - g["opp_pts"], default=None)
        if wins >= 4:
            hype_lines.append(f"Lakers are {wins}-{losses} in their last {len(lakers)}. Just saying.")
        if biggest_win:
            diff = biggest_win["pts"] - biggest_win["opp_pts"]
            opp = biggest_win["matchup"].split(" ")[-1]
            hype_lines.append(f"Lakers beat {opp} by {diff} recently. The league is scared.")

    # Knicks recent form
    if knicks:
        wins  = sum(1 for g in knicks if g["wl"] == "W")
        losses = len(knicks) - wins
        worst_loss = max((g for g in knicks if g["wl"] == "L"), key=lambda g: g["opp_pts"] - g["pts"], default=None)
        if losses >= 3:
            trail_lines.append(f"The Knicks are {wins}-{losses} in their last {len(knicks)}. Rough.")
            win_lines.append(f"Good win. The Knicks needed that after going {wins}-{losses} recently.")
        if worst_loss:
            diff = worst_loss["opp_pts"] - worst_loss["pts"]
            opp = worst_loss["matchup"].split(" ")[-1]
            trail_lines.append(f"They just lost to {opp} by {diff}. Hard to watch.")

    # Head to head
    if h2h:
        lakers_h2h_wins = sum(1 for g in h2h if g["wl"] == "W")
        for g in h2h:
            diff = abs(g["pts"] - g["opp_pts"])
            if g["wl"] == "W":
                h2h_lines.append(f"Lakers beat the Knicks {g['pts']}-{g['opp_pts']} on {g['date']}. Recent history doesn't lie.")
            else:
                h2h_lines.append(f"Knicks got lucky {g['pts']}-{g['opp_pts']} last time. Won't happen again.")
        if lakers_h2h_wins == len(h2h):
            h2h_lines.append(f"Lakers are {lakers_h2h_wins}-0 against the Knicks this season.")

    # Fallbacks if API returned nothing
    if not trail_lines:
        trail_lines = ["Classic Knicks. Classic.", "The Garden is quiet tonight.", "Brunson is tired."]
    if not win_lines:
        win_lines = ["Good win. Lakers are still better.", "A win is a win. Even a Knicks win.", "Enjoy it. Won't last."]
    if not hype_lines:
        hype_lines = ["Lakers quietly cooking this season.", "The Lakers exist and are better."]
    if not h2h_lines:
        h2h_lines = ["Lakers own the Knicks. History says so.", "This matchup always ends the same way."]

    # Always-true lines mixed in
    trail_lines += ["MSG is the most overrated arena in the league.", "Thibodeau playing his starters 40 min again."]
    win_lines   += ["Good for them. Still not winning a title.", "Alert the media. The Knicks won a game."]
    hype_lines  += ["Crypto.com Arena > Madison Square Garden.", "The Lakers have more titles than the Knicks have playoff wins this decade."]

    return trail_lines, win_lines, hype_lines, h2h_lines

# ── Cache so we only refresh once per day ─────────────────────────────────────
_cache = {"data": None, "date": None}

def get_trash_talk():
    today = datetime.now().date()
    if _cache["date"] != today or _cache["data"] is None:
        print(f"[{now()}] Refreshing trash talk from NBA API...")
        _cache["data"] = build_trash_talk()
        _cache["date"] = today
    return _cache["data"]

def now():
    return datetime.now().strftime("%H:%M:%S")

def send(text):
    try:
        r = requests.post(GROUPME_API_URL, json={"bot_id": GROUPME_BOT_ID, "text": text}, timeout=10)
        if r.status_code == 202:
            print(f"[{now()}] Sent: {text!r}")
        else:
            print(f"GroupMe error {r.status_code}: {r.text}")
    except requests.RequestException as e:
        print(f"Request failed: {e}")

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
            mins = s.get("minutesCalculated", "PT0M").replace("PT","").replace("M"," min")
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
    return f"{game['homeTeam']['score']}-{game['awayTeam']['score']}-Q{game.get('period', 0)}"

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
    trail_lines, win_lines, hype_lines, h2h_lines = get_trash_talk()

    period = game.get("period", "?")
    period_str = f"Q{period}" if isinstance(period, int) and period <= 4 else f"OT{period - 4}"
    clock = game.get("gameClock", "").replace("PT","").replace("M",":").replace("S","").strip()
    clock_str = f" {clock}" if clock else ""

    if knicks > opp:
        quip = random.choice(h2h_lines if vs_lakers else win_lines)
        status = f"NYK LEAD\n{quip}"
    elif knicks < opp:
        quip = random.choice(h2h_lines if vs_lakers else trail_lines)
        status = f"NYK TRAIL\n{quip}"
    else:
        status = "TIED\nDon't get excited. It's a tie."

    return f"{period_str}{clock_str}\nNYK {knicks} - {opp} {opp_name}\n{status}"

def format_final(game):
    knicks, opp, opp_name, vs_lakers = get_knicks_scores(game)
    trail_lines, win_lines, hype_lines, h2h_lines = get_trash_talk()
    if knicks > opp:
        result = f"NYK WIN\n{random.choice(win_lines)}"
    else:
        quip = random.choice(h2h_lines if vs_lakers else trail_lines)
        result = f"NYK LOSS\n{quip}"
    return f"FINAL\nNYK {knicks} - {opp} {opp_name}\n{result}"

def main():
    print(f"Knicks Score Bot started -- {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    send("Knicks bot is live. Lakers are still better.")

    last_score_key   = None
    preview_sent     = False
    final_sent       = False
    last_game_id     = None
    last_period      = None
    quarter_end_sent = set()
    poll_count       = 0

    while True:
        game = get_knicks_game()

        if not game:
            print(f"[{now()}] No Knicks game today. Sleeping 30 min...")
            time.sleep(1800)
            continue

        game_id = game["gameId"]

        if game_id != last_game_id:
            last_score_key   = None
            preview_sent     = False
            final_sent       = False
            last_period      = None
            quarter_end_sent = set()
            poll_count       = 0
            last_game_id     = game_id

        status = game["gameStatus"]

        if status == 1:
            if not preview_sent:
                trail_lines, win_lines, hype_lines, h2h_lines = get_trash_talk()
                home   = game["homeTeam"]["teamName"]
                away   = game["awayTeam"]["teamName"]
                tipoff = game.get("gameStatusText", "TBD")
                vs_lakers = game["homeTeam"]["teamId"] == LAKERS_TEAM_ID or game["awayTeam"]["teamId"] == LAKERS_TEAM_ID
                extra = f" {random.choice(h2h_lines)}" if vs_lakers else ""
                send(f"Knicks game today!\n{away} @ {home}\nTipoff: {tipoff}{extra}")
                preview_sent = True
            else:
                print(f"[{now()}] Waiting for tipoff...")
            time.sleep(60)

        elif status == 2:
            current_period = game.get("period", 0)
            poll_count += 1

            end_of_quarter = (
                current_period > 1 and
                current_period != last_period and
                last_period is not None and
                last_period not in quarter_end_sent
            )
            if end_of_quarter:
                performers = get_top_performers(game_id)
                if performers:
                    period_label = f"Q{last_period}" if last_period <= 4 else f"OT{last_period - 4}"
                    send(f"-- End of {period_label} --\n{performers}")
                quarter_end_sent.add(last_period)

            last_period = current_period

            # Random Lakers hype every ~45 min
            if poll_count % 540 == 0:
                _, _, hype_lines, _ = get_trash_talk()
                send(random.choice(hype_lines))

            key = score_key(game)
            if key != last_score_key:
                send(format_live(game))
                last_score_key = key
            else:
                print(f"[{now()}] Score unchanged ({key})")
            time.sleep(5)

        elif status == 3:
            if not final_sent:
                send(format_final(game))
                performers = get_top_performers(game_id)
                if performers:
                    send(f"-- Final Stats --\n{performers}")
                final_sent = True
                print(f"[{now()}] Game over. Sleeping 8 hours...")
            time.sleep(28800)

class KeepAlive(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Knicks bot running")
    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 10000), KeepAlive)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print("Web server started on port 10000")
    main()
