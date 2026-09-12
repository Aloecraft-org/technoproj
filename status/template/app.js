/* Status board renderer.
 *
 * Reads data/status.json and renders it. The page holds no opinion about
 * what a profile may show -- collect.py decided that before this file ever
 * saw the data, so a field the public profile excludes is simply absent
 * here. Do not add client-side filtering: it would imply the data is
 * present and merely hidden, which is the mistake this design avoids.
 */
'use strict';

// Beyond this, data is "stale" and its pill goes hollow. The collector runs
// every 10 minutes, so three missed runs is the threshold -- long enough not
// to flicker on one slow run, short enough that a frozen source is obvious
// the same morning.
var STALE_S = 30 * 60;
// Beyond this the freshness line itself turns red rather than amber.
var DEAD_S = 6 * 60 * 60;

function el(tag, cls, text) {
  var n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

function ago(seconds) {
  if (seconds == null) return 'unknown';
  var s = Math.max(0, seconds);
  if (s < 90) return s + 's ago';
  if (s < 5400) return Math.round(s / 60) + 'm ago';
  if (s < 172800) return Math.round(s / 3600) + 'h ago';
  return Math.round(s / 86400) + 'd ago';
}

function ageOf(stamp, given) {
  if (typeof given === 'number') return given;
  if (!stamp) return null;
  var t = Date.parse(stamp);
  if (isNaN(t)) return null;
  return Math.round((Date.now() - t) / 1000);
}

/* How long ago a named source was last collected. This, not the age of the
 * event it reports, is what decides whether a pill is trusted. */
function sourceAge(doc, name) {
  var s = (doc.sources || []).filter(function (x) { return x.name === name; })[0];
  if (!s) return null;
  if (!s.ok) return Infinity;          // could not be collected at all
  return ageOf(s.fetched_at, null);
}

/* Build conclusions -> the four states this page has. */
function buildTone(status) {
  switch (String(status || '').toLowerCase()) {
    case 'success':   return 'ok';
    case 'failure':
    case 'timed_out': return 'fail';
    case 'cancelled':
    case 'action_required':
    case 'in_progress':
    case 'queued':    return 'warn';
    default:          return 'idle';
  }
}

function pill(text, tone, stale) {
  var p = el('span', 'pill ' + tone + (stale ? ' hollow' : ''), text);
  if (stale) p.title = 'stale: nothing has confirmed this recently';
  return p;
}

function renderFreshness(doc) {
  var line = document.getElementById('freshness');
  var text = document.getElementById('fresh-text');
  var age = ageOf(doc.generated_at, null);
  var tone = age == null ? 'is-fail'
           : age > DEAD_S ? 'is-fail'
           : age > STALE_S ? 'is-warn' : 'is-ok';
  line.className = 'freshness ' + tone;
  text.textContent = 'collected ' + ago(age);
  if (age != null && age > STALE_S) {
    text.textContent += ' — the collector may have stopped';
  }
}

function renderSources(doc) {
  var box = document.getElementById('sources');
  box.textContent = '';
  (doc.sources || []).forEach(function (s) {
    var chip = el('div', 'src' + (s.ok ? '' : ' bad'));
    chip.appendChild(el('b', null, s.name));
    chip.appendChild(pill(s.ok ? 'ok' : 'unavailable', s.ok ? 'ok' : 'warn', false));
    if (s.note) chip.appendChild(el('span', 'why', s.note));
    box.appendChild(chip);
  });
}

function cellRelease(rel, note) {
  var td = el('td');
  if (!rel) {
    td.appendChild(el('span', 'none', note || 'not collected'));
    return td;
  }
  var v = el('span', 'val', rel.version || '—');
  td.appendChild(v);
  // The age of the MIRROR's data, where the profile publishes it. This is
  // the number that was invisible while the mirror sat frozen for nine days.
  if ('mirror_age_s' in rel || rel.mirror_generated_at) {
    var age = ageOf(rel.mirror_generated_at, rel.mirror_age_s);
    var sub = el('span', 'sub' + (age != null && age > STALE_S ? ' warn' : ''),
                 'mirror ' + ago(age));
    td.appendChild(sub);
  }
  if (rel.releases != null) {
    td.appendChild(el('span', 'sub', rel.releases + ' mirrored'));
  }
  return td;
}

function cellBuild(b, sourceStale) {
  var td = el('td');
  if (!b) { td.appendChild(el('span', 'none', 'not collected')); return td; }
  if (b.note && !b.status) { td.appendChild(el('span', 'none', b.note)); return td; }
  var age = ageOf(b.at, b.age_s);
  // Hollow means "nobody has confirmed this recently", which is a fact about
  // the COLLECTOR, not about the build. A build that succeeded five hours
  // ago and was checked three minutes ago is current; the same build
  // unchecked since yesterday is not, even though its own age never moved.
  var p = pill(b.status || 'unknown', buildTone(b.status), sourceStale);
  if (b.url) {
    var a = el('a'); a.href = b.url; a.rel = 'noreferrer';
    a.appendChild(p); td.appendChild(a);
  } else {
    td.appendChild(p);
  }
  var bits = [];
  if (b.workflow) bits.push(b.workflow);
  if (b.at) bits.push(ago(age));
  if (bits.length) td.appendChild(el('span', 'sub', bits.join(' · ')));
  if (b.branch) td.appendChild(el('span', 'sub', b.branch));
  if (b.note) td.appendChild(el('span', 'sub warn', b.note));
  return td;
}

function cellActivity(a) {
  var td = el('td', 'act-col');
  if (!a) { td.appendChild(el('span', 'none', '—')); return td; }
  if (a.note) { td.appendChild(el('span', 'none', a.note)); return td; }
  var age = ageOf(a.at, a.age_s);
  td.appendChild(el('span', 'val', ago(age)));
  if (a.subject) {
    var s = el('span', 'subject', a.subject);
    td.appendChild(s);
  }
  if (a.sha) {
    var sub = el('span', 'sub', a.sha);
    td.appendChild(sub);
  }
  return td;
}

function render(doc) {
  document.title = doc.title || 'Status';
  document.getElementById('title').textContent = doc.title || 'Status';
  var prof = document.getElementById('profile');
  if (doc.profile) { prof.textContent = doc.profile; prof.hidden = false; }

  renderFreshness(doc);
  renderSources(doc);

  var body = document.getElementById('rows');
  body.textContent = '';
  var rows = doc.projects || [];
  if (!rows.length) {
    var tr = el('tr');
    var td = el('td', 'empty', 'no projects in this profile');
    td.colSpan = 4; tr.appendChild(td); body.appendChild(tr);
    return;
  }
  var buildAge = sourceAge(doc, 'builds');
  var buildStale = buildAge === null || buildAge === Infinity || buildAge > STALE_S;

  rows.forEach(function (p) {
    var tr = el('tr');
    var first = el('td');
    first.appendChild(el('span', 'name', p.title || p.name));
    var repo = (p.release && p.release.repo) || null;
    if (repo) first.appendChild(el('span', 'repo', repo));
    tr.appendChild(first);
    tr.appendChild(cellRelease(p.release, p.release_note));
    tr.appendChild(cellBuild(p.build, buildStale));
    tr.appendChild(cellActivity(p.activity));
    body.appendChild(tr);
  });

  document.getElementById('foot-meta').textContent =
    'generated ' + (doc.generated_at || 'unknown');
}

function fail(message) {
  var line = document.getElementById('freshness');
  line.className = 'freshness is-fail';
  document.getElementById('fresh-text').textContent = message;
  var body = document.getElementById('rows');
  body.textContent = '';
  var tr = el('tr');
  var td = el('td', 'empty', 'No data. ' + message);
  td.colSpan = 4; tr.appendChild(td); body.appendChild(tr);
}

function load() {
  // Cache-bust: this file is rewritten in place by the collector, and a
  // status board showing a cached copy is worse than one showing nothing.
  fetch('data/status.json?t=' + Date.now(), { cache: 'no-store' })
    .then(function (r) {
      if (!r.ok) throw new Error('status.json returned HTTP ' + r.status);
      return r.json();
    })
    .then(render)
    .catch(function (e) { fail(String(e.message || e)); });
}

load();
setInterval(load, 60000);
