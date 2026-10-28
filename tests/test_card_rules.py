"""Rule help: moves that break the game rules are stopped with a reason and a "Do it anyway" button,
picking a card shows where it can go, and the setting turns it all off.

The stand-in cards are all Basic Pokémon and plain Items, so each test first turns a few of them into
what it needs: an evolution, a Pokémon Tool and a Stadium with two copies.
"""
from playwright.sync_api import sync_playwright

from helpers import APP, offline_context, watch_errors

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
    pg.goto(APP.as_uri())
    pg.wait_for_timeout(1500)
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


if __name__ == "__main__":
    test_pokemon_rules(); print("Pokémon rules: PASS")
    test_attach_and_play_rules(); print("attach and play rules: PASS")
    test_rule_help_setting(); print("Rule help setting: PASS")
