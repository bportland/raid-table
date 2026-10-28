"""Solo play: the boss loads, damage math, a full boss turn, and Undo."""
from playwright.sync_api import sync_playwright

from helpers import APP, give_boss_energy, offline_context, step_boss_draws, watch_errors


def test_solo_boss_round():
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = offline_context(b).new_page()
        watch_errors(pg, "solo", errors)
        pg.goto(APP.as_uri())
        pg.wait_for_timeout(1500)

        # A first visit loads the first sample deck and the first boss on its own, then draws for turn 1.
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


if __name__ == "__main__":
    test_solo_boss_round()
    print("solo: PASS")
