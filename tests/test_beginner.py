"""Beginner mode: only the beginner decks and bosses, Easy difficulty, rules always on with no override,
and the deck and boss tools hidden. In a room it applies to everyone."""
from playwright.sync_api import sync_playwright

from helpers import offline_context, open_app, serve, watch_errors

OPTIONS = "s => [...document.querySelectorAll(s + ' option')].map(o => o.textContent)"


def _start_beginner(pg, deck="Beginner: Quaxly (Water)", boss="Dugtrio (intermediate)"):
    pg.check("#setupBeginner")
    pg.select_option("#setupDeckSel", label=deck)
    pg.select_option("#setupBossSel", label=boss)
    pg.click("#setupGo")
    pg.wait_for_function("document.getElementById('setupBack').hidden && S.beginner && hasBoss()", timeout=10000)


def test_beginner_mode_solo():
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = offline_context(b).new_page()
        watch_errors(pg, "beginner", errors)
        open_app(pg)
        pg.evaluate("setRules(false)")   # even with Rule help switched off beforehand
        pg.click("#btnNew")

        # Ticking Beginner mode leaves only the beginner choices, with Easy and the Gentle deck fixed.
        pg.check("#setupBeginner")
        assert pg.evaluate(OPTIONS, "#setupDeckSel") == ["Beginner: Fuecoco (Fire)", "Beginner: Quaxly (Water)", "Beginner: Sprigatito (Grass)"]
        assert pg.evaluate(OPTIONS, "#setupBossSel") == ["Ponyta (beginner)", "Dugtrio (intermediate)"]
        assert pg.evaluate(OPTIONS, "#setupBossDeck") == ["Gentle (beginner)"]
        assert pg.input_value("#setupDiff") == "easy" and pg.is_disabled("#setupDiff") and pg.is_disabled("#setupHarsh")
        assert pg.evaluate("document.getElementById('setupDeckText').readOnly")
        assert "Fuecoco SVI 36" in pg.input_value("#setupDeckText")
        _start_beginner(pg)

        assert pg.evaluate("[S.deckName, bossName(), S.bossCfg.difficulty, S.bossCfg.harsh, S.bossCfg.list === GENTLE_BOSS_DECK]") == \
            ["Beginner: Quaxly (Water) sample", "Dugtrio", "easy", False, True]
        assert "beginner" in pg.inner_text("#bossDiff").lower()
        # Deck and boss changes and the Rule help switch are hidden; Rule help applies anyway.
        for btn in ("#btnImport", "#btnBossSetup", "#btnRules"):
            assert not pg.is_visible(btn), btn
        assert pg.evaluate("rulesOn")
        # A move against the rules is stopped with no "Do it anyway".
        pg.evaluate("(() => { const u = S.hand.find(x => D(x).supertype === 'Energy') || S.deck.find(x => D(x).supertype === 'Energy');"
                    " act(null, () => { S.deck = S.deck.filter(x => x !== u); if (!S.hand.includes(u)) S.hand.push(u); }, { noUndo: true });"
                    " move({ zone: 'hand', uid: u }, { zone: 'slot', slot: 'bench4' }); })()")
        assert pg.is_visible("#ruleNote") and not pg.is_visible("#ruleOverride")

        # New game keeps Beginner mode ticked; unticking it brings everything back.
        pg.click("#ruleOk"); pg.click("#btnNew")
        assert pg.is_checked("#setupBeginner")
        pg.uncheck("#setupBeginner")
        assert len(pg.evaluate(OPTIONS, "#setupDeckSel")) > 3 and not pg.is_disabled("#setupDiff")
        assert not pg.evaluate("document.getElementById('setupDeckText').readOnly")
        pg.click("#setupGo")
        pg.wait_for_function("document.getElementById('setupBack').hidden && !S.beginner", timeout=10000)
        assert pg.is_visible("#btnImport") and pg.is_visible("#btnRules")
        assert not pg.evaluate("rulesOn")   # back to the player's own setting
        b.close()
    assert not errors, errors


def test_beginner_room_switches_joiners_deck():
    errors = []
    with serve() as url, sync_playwright() as p:
        b = p.chromium.launch()
        ctx = offline_context(b)
        host, guest = ctx.new_page(), ctx.new_page()
        watch_errors(host, "host", errors); watch_errors(guest, "guest", errors)
        host.goto(url + "?local=1"); host.wait_for_selector("#setupBack:not([hidden])")
        _start_beginner(host)
        open_app(guest, url + "?local=1")   # the guest starts with a regular deck
        assert guest.evaluate("S.deckName") == "Mega Lucario ex sample"
        host.click("#btnRoom"); host.fill("#roomName", "Ash"); host.click("#roomCreate"); host.wait_for_timeout(800); host.click("#roomClose")
        guest.click("#btnRoom"); guest.fill("#roomName", "Misty"); guest.fill("#roomCode", host.evaluate("MP.code")); guest.click("#roomJoin")
        guest.wait_for_timeout(1500); guest.click("#roomClose")
        # The room is in Beginner mode, so the guest is moved onto a beginner deck.
        guest.wait_for_function("S.beginner && S.deckName === 'Beginner: Fuecoco (Fire) sample'", timeout=10000)
        assert guest.evaluate("isBeginnerList(S.list) && Object.keys(S.keys).length") == 60
        assert not guest.is_visible("#btnImport")
        b.close()
    assert not errors, errors


if __name__ == "__main__":
    test_beginner_mode_solo(); print("beginner solo: PASS")
    test_beginner_room_switches_joiners_deck(); print("beginner room: PASS")
