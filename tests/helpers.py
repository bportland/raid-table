"""Shared helpers for the Raid Table browser tests.

The tests drive the real app (index.html at the repository root) in headless Chromium with
Playwright. All internet access is blocked, and stand-in card data is generated from the app's
own sample decks, boss decks and bosses, so results don't depend on pokemontcg.io or TCGdex.
"""
import contextlib
import functools
import http.server
import json
import pathlib
import re
import shutil
import socketserver
import tempfile
import threading
import urllib.parse

REPO = pathlib.Path(__file__).resolve().parent.parent
APP = REPO / "index.html"

# Names used to give stand-in Trainer cards the right kind (the app treats them differently).
SUPPORTERS = {"Avery", "Boss's Orders", "Boss's Orders (Ghetsis)", "Bug Catcher", "Cook", "Doctor", "Flannery",
              "Gordie", "Leon", "Schoolboy", "Schoolgirl", "Sidney", "Team Yell Grunt", "Lillie's Determination",
              "Iris's Fighting Spirit", "Surfer", "Iono", "Arven", "Professor's Research", "Misty's Vitality",
              "Ciphermaniac's Codebreaking", "Hilda", "Team Rocket's Petrel", "Judge", "Gwynn",
              "Wally's Compassion", "Carmine", "Urbain"}
STADIUMS = {"Collapsed Stadium", "Galar Mine", "Old Cemetery", "Path to the Peak", "Spikemuth",
            "Gravity Mountain", "Surfing Beach", "Prism Tower"}
TOOLS = {"Rocky Helmet", "Lucky Helmet", "Spirit Mask", "Air Balloon", "Defiance Band", "Heavy Baton",
         "Forest Seal Stone"}


def _img(name, color):
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 63 88'><rect width='63' height='88' rx='3' "
           f"fill='{color}'/><text x='5' y='14' font-size='5.5' font-family='sans-serif' fill='white'>{name[:22]}</text></svg>")
    return "data:image/svg+xml," + urllib.parse.quote(svg)


def _stand_in(name, section):
    if section == "Energy" or name.endswith("Energy"):
        d = dict(name=name, supertype="Energy", subtypes=["Basic"], types=[name.split()[-2]] if len(name.split()) > 1 else [])
    elif section == "Pokémon":
        d = dict(name=name, supertype="Pokémon", subtypes=["Basic"] + (["ex"] if name.endswith(" ex") else []), hp=120)
    else:
        kind = ("Supporter" if name in SUPPORTERS else "Stadium" if name in STADIUMS
                else "Pokémon Tool" if name in TOOLS else "Item")
        d = dict(name=name, supertype="Trainer", subtypes=[kind], text=f"{name}: stand-in card text for testing.")
    color = {"Pokémon": "#7a4b2a", "Trainer": "#2a4b7a", "Energy": "#4b2a7a"}[d["supertype"]]
    d.update(img=_img(name, color), imgLg=_img(name, color), exact=True)
    return d


_CARDS = None


def stand_in_cards(browser):
    """Builds {card key: stand-in data} for every card the app ships with, using the app's own parser.
    Uses the test's own browser (Playwright can't start a second one inside the first)."""
    global _CARDS
    if _CARDS is not None:
        return _CARDS
    if True:
        pg = browser.new_page()
        pg.route("**/*", lambda r: r.continue_() if r.request.url.startswith(("file:", "data:")) else r.abort())
        pg.goto(APP.as_uri())
        entries = pg.evaluate("""() => {
          const lists = [...SAMPLE_DECKS.map(d => d.list), ...BOSS_DECKS.map(d => d.list)];
          const out = [];
          for (const l of lists) for (const e of parseDeck(l)) out.push({ key: entryKey(e), name: e.name, section: e.section });
          for (const bc of BOSS_CHOICES) { const e = parseDeck('1 ' + bc.line)[0]; out.push({ key: entryKey(e), name: e.name, section: 'Boss' }); }
          return out;
        }""")
        pg.close()
    cards = {}
    for e in entries:
        if e["section"] == "Boss":
            # Every boss gets the same two simple attacks: one it can't use for damage, one that does 100.
            d = dict(name=e["name"], supertype="Pokémon", subtypes=["Basic", "ex"], hp=230,
                     attacks=[dict(name="Stand-in Strike", cost=["Colorless"] * 3, damage="", text="Stand-in effect text."),
                              dict(name="Stand-in Storm", cost=["Colorless"] * 3, damage="100", text="")])
            d.update(img=_img(e["name"], "#5a2a4a"), imgLg=_img(e["name"], "#5a2a4a"), exact=True)
            cards[e["key"]] = d
        else:
            cards[e["key"]] = _stand_in(e["name"], e["section"])
    _CARDS = cards
    return cards


def init_script(browser):
    """Seeds the app's card cache with the stand-in data before any page script runs."""
    return "localStorage.setItem('raidtable.cards.v6', " + json.dumps(json.dumps(stand_in_cards(browser))) + ");"


# Same-computer multiplayer (?local=1) normally talks through this browser's storage, which never
# conflicts like real Firebase does. firebase_like() swaps in a connection that behaves like Firebase:
# transactions start from this tab's (possibly stale) copy and retry with the real value, and updates
# arrive after a short delay. That is what exposed the extra-cards-on-draw bug.
FIREBASE_LIKE_TRANSPORT = r'''function localTransport(code) {
  const KEY = "raidtable.localroom." + code;
  const ch = new BroadcastChannel("raidtable-" + code);
  const watchers = []; let cache = {};
  const read = () => { try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch { return {}; } };
  const at = (tree, path) => path.split("/").reduce((o, k) => (o == null ? null : o[k]), tree) ?? null;
  const put = (tree, path, v) => { const ks = path.split("/"); let o = tree; for (const k of ks.slice(0, -1)) { if (o[k] == null || typeof o[k] !== "object") o[k] = {}; o = o[k]; } if (v == null) delete o[ks[ks.length - 1]]; else o[ks[ks.length - 1]] = v; };
  const fire = () => { for (const w of watchers) { const v = at(cache, w.path); const sv = JSON.stringify(v); if (sv !== w.last) { w.last = sv; w.cb(v); } } };
  const pull = () => setTimeout(() => { cache = read(); fire(); }, 30 + Math.random() * 60);
  ch.onmessage = pull;
  const lock = fn => navigator.locks.request(KEY, async () => fn());
  return {
    kind: "local",
    watch(path, cb) { watchers.push({ path, cb, last: undefined }); pull(); },
    get: async path => { await new Promise(r => setTimeout(r, 40)); return at(read(), path); },
    set(path, v) { put(cache, path, v); fire(); return lock(() => { const t = read(); put(t, path, v); localStorage.setItem(KEY, JSON.stringify(t)); }).then(() => ch.postMessage(1)); },
    async transact(path, fn) {
      let cur = at(cache, path);
      for (let i = 0; i < 25; i++) {
        const r = fn(cur);
        const nv = r !== undefined ? r : (cur === null ? null : undefined);
        if (nv === undefined) return { committed: false, value: cur };
        const res = await lock(() => { const t = read(); const real = at(t, path); if (real !== cur) return { ok: false, real }; put(t, path, nv); localStorage.setItem(KEY, JSON.stringify(t)); return { ok: true }; });
        if (res.ok) { ch.postMessage(1); put(cache, path, nv); fire(); return { committed: nv !== null, value: nv }; }
        cur = res.real;
      }
      return { committed: false, value: cur };
    },
    presence(seat) { this.set("presence/" + seat, true); },
    close() { ch.close(); }
  };
}
'''


def app_html(firebase_like=False):
    html = APP.read_text(encoding="utf-8")
    if firebase_like:
        a = html.index("function localTransport(code) {")
        b = html.index("const useLocalTransport")
        html = html[:a] + FIREBASE_LIKE_TRANSPORT + html[b:]
    return html


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@contextlib.contextmanager
def serve(firebase_like=False):
    """Serves a copy of the app on localhost (same-computer multiplayer needs http, not file://)."""
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="raidtable-test-"))
    (tmp / "index.html").write_text(app_html(firebase_like), encoding="utf-8")
    handler = functools.partial(_Quiet, directory=str(tmp))
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        try:
            yield f"http://127.0.0.1:{httpd.server_address[1]}/index.html"
        finally:
            httpd.shutdown()
            shutil.rmtree(tmp, ignore_errors=True)


def offline_context(browser, **kw):
    """A browser context with the internet blocked and the stand-in cards seeded."""
    ctx = browser.new_context(viewport=kw.pop("viewport", {"width": 1300, "height": 950}), **kw)
    ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(("http://127.0.0.1", "file:", "data:")) else r.abort())
    ctx.add_init_script(init_script(browser))
    return ctx


def watch_errors(page, label, errors):
    page.on("pageerror", lambda e: errors.append(f"{label}: {e}"))


def two_players(ctx, url):
    """Opens two tabs in same-computer mode: Ash creates a room, Misty joins it."""
    a, b = ctx.new_page(), ctx.new_page()
    a.goto(url + "?local=1"); b.goto(url + "?local=1")
    a.wait_for_timeout(1500)
    a.click("#btnRoom"); a.fill("#roomName", "Ash"); a.click("#roomCreate"); a.wait_for_timeout(800); a.click("#roomClose")
    b.click("#btnRoom"); b.fill("#roomName", "Misty"); b.fill("#roomCode", a.evaluate("MP.code")); b.click("#roomJoin")
    b.wait_for_timeout(1500); b.click("#roomClose")
    # Wait until each tab sees both players and Misty's fresh board is dealt.
    for pg in (a, b):
        pg.wait_for_function("MP && seatList().length === 2", timeout=10000)
    b.wait_for_function("S.myRaidId === S.raidId && S.hand.length === 8", timeout=10000)   # 7, plus the turn's draw
    return a, b


def room_of(ctx, url, names):
    """Opens one tab per name in same-computer mode: the first creates a room, the rest join it one by one."""
    pages = [ctx.new_page() for _ in names]
    for pg in pages:
        pg.goto(url + "?local=1")
    host = pages[0]
    host.wait_for_timeout(1500)
    host.click("#btnRoom"); host.fill("#roomName", names[0]); host.click("#roomCreate"); host.wait_for_timeout(800); host.click("#roomClose")
    code = host.evaluate("MP.code")
    for i, (pg, name) in enumerate(zip(pages[1:], names[1:]), start=2):
        pg.click("#btnRoom"); pg.fill("#roomName", name); pg.fill("#roomCode", code); pg.click("#roomJoin")
        pg.wait_for_timeout(1500); pg.click("#roomClose")
        host.wait_for_function(f"S.players === {i}", timeout=10000)
    # Wait until every tab sees everyone and each joiner's fresh board is dealt.
    for pg in pages:
        pg.wait_for_function(f"MP && seatList().length === {len(names)}", timeout=10000)
    for pg in pages[1:]:
        pg.wait_for_function("S.myRaidId === S.raidId && S.hand.length === 8", timeout=10000)   # 7, plus the turn's draw
    return pages


def step_boss_draws(page, limit=15):
    """Presses the boss panel's main button until the boss has finished drawing."""
    for _ in range(limit):
        if page.evaluate("S.bt && S.bt.phase") != "draw":
            return
        page.locator("#bossStage .stage-acts .primary").click()
        page.wait_for_timeout(250)


def give_boss_energy(page, n=3):
    page.evaluate(f"""act(null, () => {{
      while (S.benergy.length < {n}) {{ const u = S.bdeck.find(x => D(x).supertype === 'Energy'); S.benergy.push(u); S.bdeck = S.bdeck.filter(x => x !== u); }}
      enterBossAttack(); S.bt.attackIdx = 1;
    }})""")
