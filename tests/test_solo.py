"""Solo play: the boss loads, damage math, a full boss turn, and Undo."""
from playwright.sync_api import sync_playwright

from helpers import APP, give_boss_energy, offline_context, open_app, start_raid, step_boss_draws, watch_errors


def test_solo_boss_round():
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = offline_context(b).new_page()
        watch_errors(pg, "solo", errors)
        pg.goto(APP.as_uri())

        # A first visit asks for the boss and deck before dealing anything, with no way to skip it.
        pg.wait_for_selector("#setupBack:not([hidden])")
        assert pg.evaluate("allUids().length") == 0 and not pg.is_visible("#setupCancel")
        # Picking a sample deck fills the list box; typing your own switches the picker to "Your own list".
        pg.select_option("#setupDeckSel", label="Mega Manectric ex")
        assert "Mega Manectric ex MEG 50" in pg.input_value("#setupDeckText")
        pg.fill("#setupDeckText", pg.input_value("#setupDeckText") + "\n1 Switch MEG 130")
        assert pg.input_value("#setupDeckSel") == "custom"
        pg.select_option("#setupDeckSel", index=0)
        # Gengar VMAX is one of the bosses; start with the defaults (first deck, first boss, 3 players).
        assert "Gengar VMAX" in pg.inner_text("#setupBossSel")
        start_raid(pg)

        # The first sample deck and the first boss are loaded, and turn 1's draw is done.
        assert pg.evaluate("allUids().length") == 60
        assert pg.evaluate("hasBoss() && S.bdeck.length") == 60
        assert pg.evaluate("S.hand.length") == 8 and pg.evaluate("S.prizes.length") == 6

        # Damage this turn: (120 + 200 + 90) / (10 x 3 players) = 13 cards.
        pg.evaluate("(() => { const u = S.hand.find(x => isBasic(x)); move({ zone: 'hand', uid: u }, { zone: 'slot', slot: 'active' }); })()")
        pg.fill("#calcP0", "120"); pg.fill("#calcP1", "200"); pg.fill("#calcP2", "90")
        assert pg.inner_text("#calcOut") == "13"

        # A boss turn: draws, attack (100 to your Active Pokémon), then 60 healed: (410 - 60) / 30 = 11 cards.
        pg.click("#btnEndTurn"); pg.wait_for_timeout(200)
        assert pg.evaluate("S.bt.phase") == "draw"
        step_boss_draws(pg)
        give_boss_energy(pg)
        pg.locator("#bossStage .stage-acts .primary").click(); pg.wait_for_timeout(150)
        assert pg.evaluate("S.active.dmg") == 100
        assert pg.evaluate("S.bt.phase") == "end"
        pg.fill("#stageHeal", "60"); pg.wait_for_timeout(100)
        pg.locator("#stageEndBtn").click(); pg.wait_for_timeout(200)
        assert pg.evaluate("S.blost.length") == 11
        assert pg.evaluate("S.turn") == 2 and pg.evaluate("S.bt") is None

        # Undo takes the whole end of the boss turn back.
        pg.click("#btnUndo"); pg.wait_for_timeout(150)
        assert pg.evaluate("S.blost.length") == 0 and pg.evaluate("S.bt.phase") == "end"

        # Negative healing is damage the boss did to itself: (410 + 200) / 30 = 20 cards.
        pg.fill("#stageHeal", "-200"); pg.wait_for_timeout(100)
        pg.locator("#stageEndBtn").click(); pg.wait_for_timeout(200)
        assert pg.evaluate("S.blost.length") == 20

        # The phone layout never scrolls sideways.
        pg.set_viewport_size({"width": 390, "height": 844}); pg.wait_for_timeout(200)
        assert pg.evaluate("document.documentElement.scrollWidth") <= 390
        b.close()
    assert not errors, errors


def test_new_game_asks_for_boss_and_deck():
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = offline_context(b).new_page()
        watch_errors(pg, "new game", errors)
        open_app(pg)
        # New game opens the dialog with this game's choices, and it can be cancelled now.
        pg.click("#btnNew")
        assert pg.is_visible("#setupBack") and pg.is_visible("#setupCancel")
        assert pg.input_value("#setupDeckSel") == "0" and pg.input_value("#setupBossSel") == "0"
        pg.click("#setupCancel")
        assert not pg.is_visible("#setupBack")
        # A different boss, boss deck, difficulty, player count and deck.
        pg.click("#btnNew")
        pg.select_option("#setupBossSel", label="Gengar VMAX")
        pg.select_option("#setupBossDeck", label="Gentle (beginner)")
        pg.select_option("#setupDiff", "easy")
        pg.select_option("#setupPlayers", "2")
        pg.select_option("#setupDeckSel", label="Mega Manectric ex")
        pg.click("#setupGo")
        pg.wait_for_function("document.getElementById('setupBack').hidden", timeout=10000)
        assert pg.evaluate("bossName()") == "Gengar VMAX"
        assert pg.evaluate("[S.bossCfg.difficulty, S.players, S.deckName, S.bdeck.length, S.hand.length]") == ["easy", 2, "Mega Manectric ex sample", 60, 8]
        assert pg.evaluate("allUids().length") == 60
        # Nothing to undo: the new raid is the starting point.
        assert pg.evaluate("undoStack.length") == 0
        b.close()
    assert not errors, errors


def test_basic_energy_art_without_card_databases():
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = offline_context(b)
        # TCGdex knows the card but has no picture for it, like the real modern basic Energy; pokemontcg.io is down.
        ctx.route("https://api.tcgdex.net/**", lambda r: r.fulfill(json=[{"id": "mee-004", "localId": "004", "name": "Lightning Energy"}]
                                                              if "?name=" in r.request.url else {"category": "Energy", "name": "Lightning Energy"}))
        pg = ctx.new_page()
        watch_errors(pg, "energy art", errors)
        open_app(pg)
        for line, n in (("Lightning Energy MEE 12", 4), ("Basic {D} Energy SVE 7", 7), ("Basic Grass Energy", 1)):
            d = pg.evaluate("async l => { const e = parseDeck('1 ' + l)[0]; e.section = 'Energy'; return await lookupCard(e); }", line)
            assert d["img"] == f"https://images.pokemontcg.io/sve/{n}.png", (line, d)
            assert d["types"] and d["supertype"] == "Energy"
        b.close()
    assert not errors, errors


if __name__ == "__main__":
    test_basic_energy_art_without_card_databases(); print("energy art: PASS")
    test_solo_boss_round(); print("solo: PASS")
    test_new_game_asks_for_boss_and_deck(); print("new game: PASS")
