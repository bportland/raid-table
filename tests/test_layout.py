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


def test_fits_laptop_and_desktop_without_scrolling():
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for w, h in ((1366, 657), (1440, 789), (1920, 961)):
            pg = _page(b, w, h, errors)
            size = f"{w}x{h}"
            assert pg.evaluate("document.documentElement.scrollHeight") <= h, f"the page scrolls at {size}"
            assert pg.evaluate("document.documentElement.scrollWidth") <= w, f"the page scrolls sideways at {size}"
            assert pg.evaluate("(t => t.scrollHeight - t.clientHeight)(document.querySelector('.table-col'))") <= 1, f"the table doesn't fit at {size}"
            # The hand is on the playmat, inside the window.
            assert pg.evaluate("!!document.querySelector('.mat section.hand')")
            assert pg.evaluate("document.querySelector('section.hand').getBoundingClientRect().bottom") <= h
            pg.close()
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
        b.close()
    assert not errors, errors


if __name__ == "__main__":
    test_fits_laptop_and_desktop_without_scrolling(); print("laptop and desktop fit: PASS")
    test_phone_never_scrolls_sideways(); print("phone: PASS")
