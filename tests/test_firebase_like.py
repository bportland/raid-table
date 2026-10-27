"""Multiplayer under Firebase-like timing: conflicting moves, retries and delayed updates.

These reproduce bugs that only showed up with real Firebase: extra cards when drawing quickly
while a teammate acts, healing that was never shared, and the cursor jumping out of the damage box.
"""
from playwright.sync_api import sync_playwright

from helpers import offline_context, serve, step_boss_draws, two_players, watch_errors


def test_quick_draws_during_teammate_moves():
    errors = []
    with serve(firebase_like=True) as url, sync_playwright() as p:
        b = p.chromium.launch()
        a, m = two_players(offline_context(b), url)
        watch_errors(a, "Ash", errors); watch_errors(m, "Misty", errors)
        for _ in range(6):
            before = a.evaluate("S.hand.length")
            m.evaluate("toggleBossStatus('Poisoned')"); a.evaluate("draw()")
            m.evaluate("toggleBossStatus('Burned')"); a.evaluate("draw()")
            m.evaluate("toggleBossStatus('Asleep')"); a.evaluate("draw()")
            a.wait_for_timeout(1500)
            assert a.evaluate("S.hand.length") - before == 3, "three draws must give exactly three cards"
        before = a.evaluate("S.hand.length")
        a.evaluate("undo()"); a.wait_for_timeout(500)
        assert a.evaluate("S.hand.length") == before - 1, "one Undo takes back exactly one draw"
        b.close()
    assert not errors, errors


def test_shared_self_damage():
    errors = []
    with serve(firebase_like=True) as url, sync_playwright() as p:
        b = p.chromium.launch()
        a, m = two_players(offline_context(b), url)
        watch_errors(a, "Ash", errors); watch_errors(m, "Misty", errors)
        a.fill("#calcP0", "100"); m.fill("#calcP1", "100"); a.wait_for_timeout(1200)
        a.evaluate("toggleReady()"); a.wait_for_timeout(400); m.evaluate("toggleReady()"); a.wait_for_timeout(1200)
        step_boss_draws(a)
        a.evaluate("S.bt && S.bt.phase === 'attack' && bossSkipAttack('test')"); a.wait_for_timeout(600)
        # Ash enters 200 and marks it as damage the boss did to itself.
        a.fill("#stageHeal", "200"); a.wait_for_timeout(100)
        a.get_by_role("button", name="It damaged itself…").click(); a.wait_for_timeout(1200)
        assert a.evaluate("S.bt.healed") == -200 and m.evaluate("S.bt.healed") == -200
        # Misty ends the turn: (200 + 200) / (10 x 2) = 20 cards.
        m.locator("#stageEndBtn").click(); m.wait_for_timeout(1000)
        assert a.evaluate("S.blost.length") == 20
        b.close()
    assert not errors, errors


def test_typing_damage_while_teammate_moves():
    errors = []
    with serve(firebase_like=True) as url, sync_playwright() as p:
        b = p.chromium.launch()
        a, m = two_players(offline_context(b), url)
        watch_errors(a, "Ash", errors); watch_errors(m, "Misty", errors)
        a.click("#calcP0"); a.keyboard.press("Control+A")
        for ch in "250":
            a.keyboard.type(ch); m.evaluate("draw()")
            a.wait_for_timeout(700)
            assert a.evaluate("document.activeElement && document.activeElement.id") == "calcP0", "the cursor must stay in the box"
        a.wait_for_timeout(900)
        assert a.input_value("#calcP0") == "250"
        assert m.evaluate("S.dmg")[0] == 250
        b.close()
    assert not errors, errors


if __name__ == "__main__":
    test_quick_draws_during_teammate_moves(); print("quick draws: PASS")
    test_shared_self_damage(); print("shared self-damage: PASS")
    test_typing_damage_while_teammate_moves(); print("typing damage: PASS")
