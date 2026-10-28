"""Rule help: moves that break the game rules are stopped with a reason and a "Do it anyway" button,
picking a card shows where it can go, and the setting turns it all off.

The stand-in cards are all Basic Pokémon and plain Items, so each test first turns a few of them into
what it needs: an evolution, a Pokémon Tool and a Stadium with two copies.
"""
from playwright.sync_api import sync_playwright

from helpers import offline_context, open_app, serve, step_boss_draws, two_players, watch_errors

# Empties the board, then makes the cards the tests need and returns their ids:
# a, a2: Basic "A" Pokémon; b: evolves from A; c: another Basic; e1, e2: Energy;
# t1, t2: Pokémon Tools; st1, st2: two copies of one Stadium; item: an Item; sup: a Supporter.
SETUP = """() => {
  act(null, () => {
    S.deck = allUids(); S.hand = []; S.prizes = []; S.discard = []; S.lost = []; S.active = null; S.bench = [null, null, null, null, null];
    S.stadium = null; S.stadiumOwner = null; S.turn = 1; S.supportersUsed = 0; S.energyTurn = 0;
  }, { noUndo: true });
  const groups = {};
  for (const u of allUids()) (groups[keyOf(u)] ||= []).push(u);
  const keys = Object.keys(groups);
  const pk = keys.filter(k => CARDS[k].supertype === 'Pokémon');
  const multiItems = keys.filter(k => CARDS[k].supertype === 'Trainer' && groups[k].length >= 2 && (CARDS[k].subtypes || []).includes('Item'));
  const aKey = pk.find(k => groups[k].length >= 2), bKey = pk.find(k => k !== aKey), cKey = pk.find(k => k !== aKey && k !== bKey);
  const [toolKey, stadKey] = multiItems;
  const itemKey = keys.find(k => k !== toolKey && k !== stadKey && CARDS[k].supertype === 'Trainer' && (CARDS[k].subtypes || []).includes('Item'));
  const supKey = keys.find(k => (CARDS[k].subtypes || []).includes('Supporter'));
  const energy = allUids().filter(u => D(u).supertype === 'Energy');
  if (!aKey || !bKey || !cKey || !toolKey || !stadKey || !itemKey || !supKey || energy.length < 2) throw new Error('the sample deck is missing a card type the test needs');
  Object.assign(CARDS[bKey], { evolvesFrom: CARDS[aKey].name, subtypes: ['Stage 1'] });
  CARDS[toolKey].subtypes = ['Pokémon Tool'];
  CARDS[stadKey].subtypes = ['Stadium'];
  const ids = { a: groups[aKey][0], a2: groups[aKey][1], b: groups[bKey][0], c: groups[cKey][0], e1: energy[0], e2: energy[1],
    t1: groups[toolKey][0], t2: groups[toolKey][1], st1: groups[stadKey][0], st2: groups[stadKey][1], item: groups[itemKey][0], sup: groups[supKey][0],
    aName: CARDS[aKey].name, bName: CARDS[bKey].name };
  const cards = Object.values(ids).filter(v => allUids().includes(v));
  act(null, () => { S.deck = S.deck.filter(u => !cards.includes(u)); S.hand.push(...cards); }, { noUndo: true });
  return ids;
}"""


def _open(p, errors):
    b = p.chromium.launch()
    pg = offline_context(b).new_page()
    watch_errors(pg, "solo", errors)
    open_app(pg)
    return b, pg


def _play(pg, uid, dst, opts=None):
    """Moves a card the way a drag does. Returns the reason shown if Rule help stopped it, or None."""
    pg.evaluate("([u, d, o]) => { hideRuleNote(); const s = locate(u); move(s, d, o || {}); }", [uid, dst, opts])
    if pg.is_visible("#ruleNote"):
        return pg.inner_text("#ruleMsg")
    return None


def _slot(n):
    return {"zone": "slot", "slot": n}


def _next_turn(pg):
    pg.evaluate("act(null, () => { S.turn++; S.supportersUsed = 0; }, { noUndo: true })")


def test_pokemon_rules():
    errors = []
    with sync_playwright() as p:
        b, pg = _open(p, errors)
        ids = pg.evaluate(SETUP)
        assert pg.inner_text("#btnRules") == "Rule help: on"   # on by default

        # An evolution can't go in an empty spot.
        why = _play(pg, ids["b"], _slot("active"))
        assert why and f"evolves from {ids['aName']}" in why
        assert pg.evaluate("S.active") is None

        # A Basic can.
        assert _play(pg, ids["a"], _slot("active")) is None
        assert _play(pg, ids["c"], _slot("bench0")) is None

        # Picking the evolution shows where it could go, and the card panel says why it can't yet.
        pg.evaluate(f"select({{ zone: 'hand', uid: '{ids['b']}' }})")
        assert "first turn" in pg.inner_text("#inspector")
        assert "no-go" in pg.get_attribute('[data-dropslot="bench1"]', "class")   # empty spot

        # No evolving on the first turn, and "Do it anyway" overrides it.
        why = _play(pg, ids["b"], _slot("active"))
        assert why == "Pokémon can't evolve on the first turn."
        pg.click("#ruleOverride")
        assert pg.evaluate("S.active.stack.length") == 2
        assert "(rules overridden)" in pg.evaluate("S.log[0].msg")
        pg.click("#btnUndo")
        assert pg.evaluate("S.active.stack.length") == 1

        # Turn 2: it evolves from the right Pokémon only.
        _next_turn(pg)
        pg.evaluate(f"select({{ zone: 'hand', uid: '{ids['b']}' }})")
        assert "can-go" in pg.get_attribute('[data-dropslot="active"]', "class")
        assert "no-go" in pg.get_attribute('[data-dropslot="bench0"]', "class")   # that's C, not A
        assert pg.locator("#inspector button", has_text=f"Evolve {ids['aName']}").count() == 1
        assert pg.locator("#inspector button", has_text="(Bench 1)").count() == 0
        why = _play(pg, ids["b"], _slot("bench0"))
        assert why and f", not " in why

        # A Pokémon that came into play this turn can't evolve yet.
        assert _play(pg, ids["a2"], _slot("bench1")) is None
        why = _play(pg, ids["b"], _slot("bench1"))
        assert why and "came into play or evolved this turn" in why
        assert _play(pg, ids["b"], _slot("active")) is None
        assert pg.evaluate("S.active.stack.length") == 2

        # A Basic doesn't go on top of another Pokémon.
        pg.evaluate("act(null, () => { const u = S.bench[1].stack[0]; S.bench[1] = null; S.hand.push(u); }, { noUndo: true })")
        why = _play(pg, ids["a2"], _slot("bench0"))
        assert why and "Basic Pokémon" in why
        b.close()
    assert not errors, errors


def test_attach_and_play_rules():
    errors = []
    with sync_playwright() as p:
        b, pg = _open(p, errors)
        ids = pg.evaluate(SETUP)

        # Energy and Tools need a Pokémon to attach to.
        assert "attaches to a Pokémon" in _play(pg, ids["e1"], _slot("active"))
        assert "attaches to a Pokémon" in _play(pg, ids["t1"], _slot("active"))
        assert _play(pg, ids["a"], _slot("active")) is None
        assert _play(pg, ids["c"], _slot("bench0")) is None

        # One Energy from your hand per turn.
        assert _play(pg, ids["e1"], _slot("active")) is None
        assert _play(pg, ids["e2"], _slot("bench0")) == "You've already attached an Energy from your hand this turn."
        _next_turn(pg)
        assert _play(pg, ids["e2"], _slot("bench0")) is None

        # One Tool per Pokémon.
        assert _play(pg, ids["t1"], _slot("active")) is None
        assert "already has a Pokémon Tool" in _play(pg, ids["t2"], _slot("active"))
        assert _play(pg, ids["t2"], _slot("bench0")) is None

        # Items and Supporters don't go on a Pokémon.
        assert "Use Play Item" in _play(pg, ids["item"], _slot("active"))
        assert "Use Play Supporter" in _play(pg, ids["sup"], _slot("active"))

        # Stadiums: only a Stadium goes in the spot, and not one with the same name as the one in play.
        assert _play(pg, ids["item"], {"zone": "stadium"}) == "Only a Stadium card goes in the Stadium spot."
        assert _play(pg, ids["st1"], {"zone": "stadium"}) is None
        assert "same name" in _play(pg, ids["st2"], {"zone": "stadium"})

        # The team's Supporter limit; discarding one as a cost still works.
        pg.evaluate("setSupporters(S.players)")
        assert "that's the limit" in _play(pg, ids["sup"], {"zone": "discard"})
        assert _play(pg, ids["sup"], {"zone": "discard"}, {"noCount": True}) is None
        assert pg.evaluate("S.discard.length") == 1
        b.close()
    assert not errors, errors


def test_rule_help_setting():
    errors = []
    with sync_playwright() as p:
        b, pg = _open(p, errors)
        ids = pg.evaluate(SETUP)

        # A blocked move on a phone: the popup fits and nothing scrolls sideways.
        pg.set_viewport_size({"width": 390, "height": 844}); pg.wait_for_timeout(200)
        assert _play(pg, ids["b"], _slot("active"))
        box = pg.locator("#ruleNote").bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= 390
        assert pg.evaluate("document.documentElement.scrollWidth") <= 390
        pg.click("#ruleOk")
        assert not pg.is_visible("#ruleNote")

        # Turned off, the same move just happens, nothing glows, and the setting is remembered.
        pg.click("#btnRules")
        assert pg.inner_text("#btnRules") == "Rule help: off"
        assert _play(pg, ids["b"], _slot("active")) is None
        pg.evaluate(f"select({{ zone: 'hand', uid: '{ids['e1']}' }})")
        assert pg.locator(".can-go, .no-go").count() == 0
        pg.reload(); pg.wait_for_timeout(1500)
        assert pg.inner_text("#btnRules") == "Rule help: off"
        pg.click("#btnRules")
        assert pg.inner_text("#btnRules") == "Rule help: on"
        b.close()
    assert not errors, errors


# Puts a Basic in the Active spot and gives it two attacks that cost the type of an Energy in the deck.
# Returns the Energy's id and type.
ATTACKER = """() => {
  const basic = S.hand.find(u => isBasic(u));
  move({ zone: 'hand', uid: basic }, { zone: 'slot', slot: 'active' });
  const e = S.deck.find(u => energyType(u));
  const t = energyType(e);
  CARDS[keyOf(basic)].attacks = [
    { name: 'Jab', cost: [t], damage: '30', text: '' },
    { name: 'Big Punch', cost: [t, 'Colorless'], damage: '100+', text: '' }];
  act(null, () => { S.deck = S.deck.filter(u => u !== e); S.hand.push(e); }, { noUndo: true });
  select({ zone: 'slot', slot: 'active' });
  return { e, t };
}"""


def test_turn_draw_and_attack():
    errors = []
    with sync_playwright() as p:
        b, pg = _open(p, errors)
        # The opening 7, then the draw for turn 1.
        assert pg.evaluate("S.hand.length") == 8 and pg.evaluate("S.drewTurn") == 1
        pg.evaluate("setPlayers(1)")
        en = pg.evaluate(ATTACKER)
        assert "attack (ends your turn)" in pg.inner_text("#inspector").lower()   # section labels show in capitals

        # Not enough Energy: stopped, with the cost spelled out.
        pg.click("#inspector button:has-text('Jab')")
        assert f"It needs 1 {en['t']} Energy" in pg.inner_text("#ruleMsg")
        pg.click("#ruleOk")
        assert pg.evaluate("S.attackTurn") == 0

        # With the Energy, the attack's damage goes in your box and, playing alone, the boss turn starts.
        assert _play(pg, en["e"], _slot("active")) is None
        pg.evaluate("select({ zone: 'slot', slot: 'active' })")
        pg.click("#inspector button:has-text('Jab')")
        assert pg.evaluate("S.dmg[0]") == 30
        assert pg.evaluate("S.bt && S.bt.phase") == "draw"
        assert pg.evaluate("S.log.some(e => /used Jab for 30 damage/.test(e.msg))")

        # When the boss turn ends, turn 2 starts with a draw.
        hand = pg.evaluate("S.hand.length")
        step_boss_draws(pg)
        pg.evaluate("S.bt && S.bt.phase === 'attack' && bossSkipAttack('test')"); pg.wait_for_timeout(100)
        pg.locator("#stageEndBtn").click(); pg.wait_for_timeout(200)
        assert pg.evaluate("S.turn") == 2
        assert pg.evaluate("S.hand.length") == hand + 1 and pg.evaluate("S.drewTurn") == 2
        # Undo of the boss turn's end doesn't give you an extra card when it ends again.
        pg.click("#btnUndo"); pg.wait_for_timeout(100)
        assert pg.evaluate("S.turn") == 1 and pg.evaluate("S.hand.length") == hand
        pg.locator("#stageEndBtn").click(); pg.wait_for_timeout(200)
        assert pg.evaluate("S.hand.length") == hand + 1
        b.close()
    assert not errors, errors


def test_attack_ends_your_turn():
    errors = []
    with sync_playwright() as p:
        b, pg = _open(p, errors)
        en = pg.evaluate(ATTACKER)   # 3 players (the default): the turn ends, but the boss waits for End turn
        assert _play(pg, en["e"], _slot("active")) is None
        pg.click("#inspector button:has-text('Jab')")
        assert pg.evaluate("S.dmg[0]") == 30 and pg.evaluate("S.bt") is None
        assert "teammates' damage" in pg.inner_text("#toast")

        # After attacking you can't attack again or play more cards, unless you override.
        pg.evaluate("select({ zone: 'slot', slot: 'active' })")
        pg.click("#inspector button:has-text('Jab')")
        assert pg.inner_text("#ruleMsg") == "You've already attacked this turn."
        pg.click("#ruleOk")
        basic = pg.evaluate("S.hand.find(u => isBasic(u)) || null")
        if basic:
            assert _play(pg, basic, _slot("bench0")) == "You've attacked this turn, and attacking ends your turn."
            pg.click("#ruleOverride")
            assert pg.evaluate("!!S.bench[0]")

        # A "+" attack adds its base damage and says you may need to add more.
        pg.evaluate("act(null, () => { S.attackTurn = 0; S.active.att.push(S.deck.find(u => D(u).supertype === 'Energy')); S.deck = S.deck.filter(u => !S.active.att.includes(u)); }, { noUndo: true })")
        pg.evaluate("select({ zone: 'slot', slot: 'active' })")
        pg.click("#inspector button:has-text('Big Punch')")
        assert pg.evaluate("S.dmg[0]") == 130
        assert "If its effect adds more" in pg.inner_text("#toast")

        # With Rule help off, attacking only adds the damage, and nothing draws for you.
        pg.click("#btnRules")
        pg.evaluate("act(null, () => { S.attackTurn = 0; S.dmg = [0, 0, 0]; }, { noUndo: true }); setPlayers(1)")
        pg.evaluate("select({ zone: 'slot', slot: 'active' })")
        assert "attack (ends your turn)" not in pg.inner_text("#inspector").lower()
        pg.click("#inspector button:has-text('Jab')")
        assert pg.evaluate("S.dmg[0]") == 30 and pg.evaluate("S.bt") is None
        hand = pg.evaluate("S.hand.length")
        pg.evaluate("act(null, () => { S.turn++; }, { noUndo: true })"); pg.wait_for_timeout(100)
        assert pg.evaluate("S.hand.length") == hand
        # Turning it back on mid-turn doesn't draw: you were drawing by hand this turn.
        pg.click("#btnRules"); pg.wait_for_timeout(100)
        assert pg.evaluate("S.hand.length") == hand
        b.close()
    assert not errors, errors


def test_attack_marks_you_ready_in_a_room():
    errors = []
    with serve(firebase_like=True) as url, sync_playwright() as p:
        b = p.chromium.launch()
        a, m = two_players(offline_context(b), url)
        watch_errors(a, "Ash", errors); watch_errors(m, "Misty", errors)
        en = m.evaluate(ATTACKER)
        assert _play(m, en["e"], _slot("active")) is None
        m.evaluate("select({ zone: 'slot', slot: 'active' })")
        m.click("#inspector button:has-text('Jab')")
        # Misty's 30 is Player 2's damage, and she's Ready; the boss waits for Ash.
        for pg in (a, m):
            pg.wait_for_function("S.dmg[1] === 30 && Object.keys(S.ready).length === 1", timeout=5000)
        assert a.evaluate("S.bt") is None
        a.click("#btnEndTurn")
        for pg in (a, m):
            pg.wait_for_function("S.bt && S.bt.phase === 'draw'", timeout=5000)
        b.close()
    assert not errors, errors


if __name__ == "__main__":
    test_pokemon_rules(); print("Pokémon rules: PASS")
    test_attach_and_play_rules(); print("attach and play rules: PASS")
    test_rule_help_setting(); print("Rule help setting: PASS")
    test_turn_draw_and_attack(); print("turn draw and attack: PASS")
    test_attack_ends_your_turn(); print("attack ends your turn: PASS")
    test_attack_marks_you_ready_in_a_room(); print("attack marks you Ready in a room: PASS")
