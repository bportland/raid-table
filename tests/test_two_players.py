"""Two players in one room (same-computer mode): joining, shared counters, the boss turn, rejoining."""
from playwright.sync_api import sync_playwright

from helpers import give_boss_energy, offline_context, serve, step_boss_draws, two_players, watch_errors


def test_two_player_round():
    errors = []
    with serve() as url, sync_playwright() as p:
        b = p.chromium.launch()
        ctx = offline_context(b)
        a, m = two_players(ctx, url)   # Ash created the room, Misty joined
        watch_errors(a, "Ash", errors); watch_errors(m, "Misty", errors)

        assert a.evaluate("S.players") == 2 and m.evaluate("S.players") == 2
        assert a.evaluate("seatList().map(s => s.name)") == ["Ash", "Misty"]
        assert m.evaluate("S.hand.length") == 7 and m.evaluate("S.prizes.length") == 6   # Misty got a fresh board

        # Both put a Basic Pokémon in the Active spot; each sees the other's.
        for pg in (a, m):
            pg.evaluate("(() => { const u = S.hand.find(x => isBasic(x)); move({ zone: 'hand', uid: u }, { zone: 'slot', slot: 'active' }); })()")
        # Wait for the sync rather than a fixed time: it sometimes takes longer than 600 ms.
        a.wait_for_function("!!seatList().find(s => s.name === 'Misty').board.active", timeout=5000)

        # The Supporter counter is shared, and Undo after a teammate's move still takes yours back.
        for pg in (m, a):
            pg.evaluate("""(() => { let u = S.hand.find(x => isSupporter(x));
              if (!u) { u = S.deck.find(x => isSupporter(x)); act(null, () => { S.deck = S.deck.filter(y => y !== u); S.hand.push(u); }, { noUndo: true }); }
              move({ zone: 'hand', uid: u }, { zone: 'discard' }); })()""")
            pg.wait_for_timeout(400)
        assert a.evaluate("S.supportersUsed") == 2 and m.evaluate("S.supportersUsed") == 2
        m.click("#btnUndo"); m.wait_for_timeout(600)
        assert a.evaluate("S.supportersUsed") == 1 and m.evaluate("S.supportersUsed") == 1

        # Each player types their own damage, and it's shared.
        a.fill("#calcP0", "150"); m.fill("#calcP1", "200"); a.wait_for_timeout(1300)
        assert a.evaluate("S.dmg") == [150, 200] and m.evaluate("S.dmg") == [150, 200]

        # Ready-up starts the boss turn for both.
        a.click("#btnEndTurn"); a.wait_for_timeout(400)
        assert a.evaluate("!S.bt")
        m.click("#btnEndTurn"); m.wait_for_timeout(900)
        assert a.evaluate("S.bt.phase") == "draw" and m.evaluate("S.bt.phase") == "draw"
        assert m.evaluate("S.bt.pending") == 350

        # The boss's attack lands on both Active Pokémon, once each.
        step_boss_draws(m)
        a.wait_for_timeout(400)
        give_boss_energy(a)
        a.wait_for_timeout(500)
        a.locator("#bossStage .stage-acts .primary").click(); a.wait_for_timeout(900)
        assert a.evaluate("S.active.dmg") == 100 and m.evaluate("S.active.dmg") == 100
        hits = a.evaluate("S.log.filter(e => /did 100 damage to/.test(e.msg)).length")
        assert hits == 2, f"expected one hit message per player, got {hits}"

        # Healing typed and End pressed straight away still counts: (350 - 50) / 20 = 15.
        m.fill("#stageHeal", "50"); m.wait_for_timeout(150)
        m.locator("#stageEndBtn").click(); m.wait_for_timeout(800)
        assert a.evaluate("S.blost.length") == 15 and m.evaluate("S.blost.length") == 15
        assert a.evaluate("S.turn") == 2 and a.evaluate("S.ready") == {}

        # Two players changing the table at once both get through.
        a.evaluate("toggleBossStatus('Poisoned')"); m.evaluate("toggleBossStatus('Burned')"); a.wait_for_timeout(900)
        assert sorted(a.evaluate("S.bstatus")) == ["Burned", "Poisoned"] == sorted(m.evaluate("S.bstatus"))

        # A replaced Stadium goes back to its owner's discard pile. Both players have the same deck, so this
        # is the same Stadium twice, which Rule help stops; force: true is its "Do it anyway".
        for pg in (a, m):
            pg.evaluate("""(() => { const u = S.deck.find(x => isStadium(x)) || S.hand.find(x => isStadium(x));
              act(null, () => { S.deck = S.deck.filter(y => y !== u); if (!S.hand.includes(u)) S.hand.push(u); }, { noUndo: true });
              move({ zone: 'hand', uid: u }, { zone: 'stadium' }, { force: true }); })()""")
            pg.wait_for_timeout(700)
        assert a.evaluate("S.discard.some(u => isStadium(u))")
        assert a.evaluate("S.returns") == []

        # Reloading rejoins the room with the same board.
        hand = m.evaluate("S.hand.length")
        m.reload(); m.wait_for_timeout(1800)
        assert m.evaluate("MP && MP.code") == a.evaluate("MP.code")
        assert m.evaluate("S.hand.length") == hand
        b.close()
    assert not errors, errors


if __name__ == "__main__":
    test_two_player_round()
    print("two players: PASS")
