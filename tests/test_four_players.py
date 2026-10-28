"""Four players in one room: joining, the Supporter limit, shared damage, the boss turn and the Lost Zone math.

Runs twice: with the normal same-computer connection, and with Firebase-like delays and retries.
"""
from playwright.sync_api import sync_playwright

from helpers import give_boss_energy, offline_context, room_of, serve, step_boss_draws, watch_errors

NAMES = ["Ash", "Misty", "Brock", "Gary"]


def _four_player_round(firebase_like):
    errors = []
    with serve(firebase_like=firebase_like) as url, sync_playwright() as p:
        b = p.chromium.launch()
        pages = room_of(offline_context(b), url, NAMES)
        for pg, name in zip(pages, NAMES):
            watch_errors(pg, name, errors)
        ash = pages[0]

        for pg in pages:
            assert pg.evaluate("S.players") == 4
            assert pg.evaluate("seatList().map(s => s.name)") == NAMES
        for pg in pages[1:]:
            assert pg.evaluate("S.prizes.length") == 6   # each joiner got a fresh board

        # Everyone puts a Basic Pokémon in the Active spot; everyone sees all four.
        for pg in pages:
            pg.evaluate("(() => { const u = S.hand.find(x => isBasic(x)); move({ zone: 'hand', uid: u }, { zone: 'slot', slot: 'active' }); })()")
        for pg in pages:
            pg.wait_for_function("seatList().every(s => s.id === MP.seat ? !!S.active : !!s.board.active)", timeout=5000)

        # Four players means four Supporters a turn, counted across the team.
        for pg in pages:
            pg.evaluate("""(() => { let u = S.hand.find(x => isSupporter(x));
              if (!u) { u = S.deck.find(x => isSupporter(x)); act(null, () => { S.deck = S.deck.filter(y => y !== u); S.hand.push(u); }, { noUndo: true }); }
              move({ zone: 'hand', uid: u }, { zone: 'discard' }); })()""")
            pg.wait_for_timeout(300)
        for pg in pages:
            pg.wait_for_function("S.supportersUsed === 4", timeout=5000)
        assert ash.evaluate("S.supportersUsed >= S.players")   # the team is at its limit

        # Each player types their own damage, and everyone sees all of it.
        dmg = [100, 120, 140, 160]
        for i, (pg, d) in enumerate(zip(pages, dmg)):
            pg.fill(f"#calcP{i}", str(d))
        for pg in pages:
            pg.wait_for_function(f"JSON.stringify(S.dmg) === '{dmg}'.replace(/ /g, '')", timeout=5000)

        # The boss turn waits for all four to be ready.
        for pg in pages[:3]:
            pg.click("#btnEndTurn"); pg.wait_for_timeout(300)
        ash.wait_for_timeout(600)
        assert ash.evaluate("!S.bt"), "the boss turn must not start until everyone is ready"
        pages[3].click("#btnEndTurn")
        for pg in pages:
            pg.wait_for_function("S.bt && S.bt.phase === 'draw'", timeout=5000)
        assert ash.evaluate("S.bt.pending") == sum(dmg)

        # The boss draws one card per player plus one: five.
        step_boss_draws(pages[2])
        ash.wait_for_function("S.bt.phase !== 'draw'", timeout=5000)
        assert ash.evaluate("S.bt.drawn") == 5

        # The boss's attack lands on all four Active Pokémon, once each.
        give_boss_energy(ash)
        ash.wait_for_timeout(500)
        ash.locator("#bossStage .stage-acts .primary").click()
        for pg in pages:
            pg.wait_for_function("S.active && S.active.dmg === 100", timeout=5000)
        ash.wait_for_function("S.log.filter(e => /did 100 damage to/.test(e.msg)).length === 4", timeout=5000)

        # Lost Zone: (520 - 40 healed) / (10 x 4) = 12 cards, for everyone.
        pages[1].fill("#stageHeal", "40"); pages[1].wait_for_timeout(150)
        pages[1].locator("#stageEndBtn").click()
        for pg in pages:
            pg.wait_for_function("S.blost.length === 12 && S.turn === 2", timeout=5000)
        assert ash.evaluate("S.supportersUsed") == 0 and ash.evaluate("S.ready") == {}
        b.close()
    assert not errors, errors


def test_four_player_round():
    _four_player_round(firebase_like=False)


def test_four_player_round_firebase_like():
    _four_player_round(firebase_like=True)


if __name__ == "__main__":
    test_four_player_round(); print("four players: PASS")
    test_four_player_round_firebase_like(); print("four players, Firebase-like: PASS")
