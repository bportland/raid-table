"""The whole table fits a laptop or desktop window without scrolling, and a phone never scrolls sideways.

Sizes are the part of the window a browser shows pages in: 1366x657 is a 1366x768 laptop, 1920x961 a
1080p monitor. The board is a busy one: an Active with two Energy and a Special Condition, three Benched,
a hand of 10 and a card picked so the card panel is open.
"""
from playwright.sync_api import sync_playwright

from helpers import APP, offline_context, watch_errors

BUSY_BOARD = """() => {
  const basics = S.hand.filter(u => isBasic(u)).concat(S.deck.filter(u => isBasic(u))).slice(0, 4);
  act(null, () => {
    for (const u of basics) { S.hand = S.hand.filter(x => x !== u); S.deck = S.deck.filter(x => x !== u); }
    const en = S.deck.filter(u => D(u).supertype === 'Energy').slice(0, 3);
    S.deck = S.deck.filter(u => !en.includes(u));
    S.active = { stack: [basics[0]], att: [en[0], en[1]], dmg: 30, status: ['Poisoned'] };
    for (let i = 1; i < basics.length; i++) S.bench[i - 1] = { stack: [basics[i]], att: i === 1 ? [en[2]] : [], dmg: 0, status: [] };
    while (S.hand.length < 10) S.hand.push(S.deck.shift());
  }, { noUndo: true });
  select({ zone: 'hand', uid: S.hand[0] });
}"""


def _page(b, w, h, errors):
    pg = offline_context(b, viewport={"width": w, "height": h}).new_page()
    watch_errors(pg, f"{w}x{h}", errors)
    pg.goto(APP.as_uri()); pg.wait_for_timeout(1500)
    pg.evaluate(BUSY_BOARD); pg.wait_for_timeout(200)
    return pg


# The tallest card panel: your Active, with two attacks, two Energy and a Special Condition.
PICK_ACTIVE = """() => {
  CARDS[keyOf(slotTop(S.active))].attacks = [{ name: 'Jab', cost: ['Fighting'], damage: '30', text: '' }, { name: 'Big Punch', cost: ['Fighting', 'Colorless'], damage: '100+', text: '' }];
  select({ zone: 'slot', slot: 'active' });
}"""
SCROLLS = "(s => (e => e.scrollHeight - e.clientHeight)(document.querySelector(s)))"


def test_fits_laptop_and_desktop_without_scrolling():
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for w, h in ((1366, 657), (1440, 789), (1920, 961)):
            pg = _page(b, w, h, errors)
            for picked in ("a hand card", "your Active"):
                if picked == "your Active":
                    pg.evaluate(PICK_ACTIVE); pg.wait_for_timeout(150)
                where = f"at {w}x{h} with {picked} picked"
                assert pg.evaluate("document.documentElement.scrollHeight") <= h, f"the page scrolls {where}"
                assert pg.evaluate("document.documentElement.scrollWidth") <= w, f"the page scrolls sideways {where}"
                assert pg.evaluate(f"{SCROLLS}('.table-col')") <= 1, f"the table doesn't fit {where}"
                # The right column fits too, card panel and all; only the game log may scroll inside itself.
                assert pg.evaluate(f"{SCROLLS}('.side')") <= 1, f"the side column doesn't fit {where}"
                assert pg.evaluate(f"{SCROLLS}('#inspector')") <= 1, f"the card panel doesn't fit {where}"
            # The Active's two copies of the same Energy show as one chip with ×2.
            assert pg.evaluate("[...document.querySelectorAll('#activeSlot .chip')].map(c => c.textContent)") == [pg.evaluate("D(S.active.att[0]).name.replace(/^Basic /, '')") + "×2"]
            # HP shows only on a damaged Pokémon: the Active (30 damage) has it, the undamaged Bench doesn't.
            assert pg.evaluate("!!document.querySelector('#activeSlot .hpline')")
            assert pg.evaluate("document.querySelectorAll('#bench .hpline').length") == 0
            # The hand is on the playmat, inside the window, running under the Prizes as well as the Bench.
            assert pg.evaluate("!!document.querySelector('.mat section.hand')")
            assert pg.evaluate("document.querySelector('section.hand').getBoundingClientRect().bottom") <= h
            assert pg.evaluate("document.querySelector('section.hand').getBoundingClientRect().left <= document.querySelector('.prizes').getBoundingClientRect().left + 1")
            # The Prize cards fill most of the left side of the mat.
            filled = pg.evaluate("(() => { const p = document.querySelector('.prizes').getBoundingClientRect(), c = [...document.querySelectorAll('#prizes .card')].map(e => e.getBoundingClientRect());"
                                 " return (Math.max(...c.map(r => r.bottom)) - Math.min(...c.map(r => r.top))) / p.height; })()")
            assert filled > .8, f"the Prize cards fill only {filled:.0%} of their column at {w}x{h}"
            pg.close()
        b.close()
    assert not errors, errors


def test_grouped_attachments_move_one_copy_at_a_time():
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = _page(b, 1440, 789, errors)
        # Dragging the "×2" chip to the discard pile takes one copy; the chip then shows no multiplier.
        chip = pg.locator("#activeSlot .chip").first
        target = pg.locator('[data-dropzone="discard"]').bounding_box()
        box = chip.bounding_box()
        pg.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2); pg.mouse.down()
        pg.mouse.move(target["x"] + 20, target["y"] + 20, steps=8)
        pg.mouse.move(target["x"] + target["width"] / 2, target["y"] + target["height"] / 2, steps=4); pg.mouse.up()
        pg.wait_for_timeout(200)
        assert pg.evaluate("S.active.att.length") == 1
        assert "×" not in pg.inner_text("#activeSlot .chip")
        # The card panel's Attached section groups copies too, and discards one at a time.
        pg.evaluate("act(null, () => { S.active.att.push(S.deck.find(u => D(u).name === D(S.active.att[0]).name)); S.deck = S.deck.filter(u => !S.active.att.includes(u)); }, { noUndo: true }); select({ zone: 'slot', slot: 'active' })")
        pg.click("#inspector button:has-text('(1 of 2)')")
        assert pg.evaluate("S.active.att.length") == 1
        b.close()
    assert not errors, errors


def test_phone_never_scrolls_sideways():
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = _page(b, 390, 844, errors)
        assert pg.evaluate("document.documentElement.scrollWidth") <= 390
        pg.evaluate("select(null)"); pg.wait_for_timeout(100)
        assert pg.evaluate("document.documentElement.scrollWidth") <= 390
        # A Pokémon's HP line stays within its (narrow) card.
        assert pg.evaluate("[...document.querySelectorAll('.pkm')].filter(p => { const h = p.querySelector('.hpline'); return h && h.getBoundingClientRect().width > p.getBoundingClientRect().width + 1; }).length") == 0
        b.close()
    assert not errors, errors


if __name__ == "__main__":
    test_fits_laptop_and_desktop_without_scrolling(); print("laptop and desktop fit: PASS")
    test_grouped_attachments_move_one_copy_at_a_time(); print("grouped attachments: PASS")
    test_phone_never_scrolls_sideways(); print("phone: PASS")
