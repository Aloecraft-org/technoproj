# status — activity, build and release board

A static page plus a collector. Deployed to dart2 for internal use, and
written so the same build serves a public page by changing one argument.

```
status/
  collect.py          fetches; decides what a profile may publish
  build.sh --out DIR  site contract: offline, hermetic, never deploys
  profiles/           internal.json, public.json
  template/           index.html, style.css, app.js
```

## Two rules that shape everything else

**Filtering happens at collection, never in the browser.** A public page that
renders only some fields still *ships* the rest, and anyone can read
`status.json`. So a profile's `include` block is an allowlist applied before
anything is written. Verify it the way you would any other claim:

```sh
./status/collect.py --profile public --out /tmp/p/data
grep -c 'branch\|html_url\|subject' /tmp/p/data/status.json   # expect 0
```

**Every fact carries the age of the thing that confirmed it.** This board
exists partly because the release mirror sat frozen for nine days while its
index rewrote itself on schedule with a fresh timestamp — nothing looked
wrong. So:

- the header shows when the *collector* last ran, not when the page rendered;
- each source chip shows whether it was collected at all, and says why not;
- a release row shows the age of the *mirror's* data, which is a different
  number from the index that wraps it — the difference is what hid the outage;
- a **filled** pill is a fact confirmed recently; a **hollow** one is the same
  value with nothing recent behind it. Fill rather than hue, so it survives
  greyscale and colour blindness.

Hollow tracks the *collector's* freshness, not the event's. A build that
succeeded five hours ago and was checked three minutes ago is current; the
same build unchecked since yesterday is not.

## Running it

```sh
./status/build.sh --out /var/www/html/status          # the page
./status/collect.py --profile internal \
    --out /var/www/html/status/data                   # the data
```

`collect.py` exits non-zero when any source degraded, so autoserv records it.
It still writes a complete `status.json` — a degraded source is shown, not
hidden.

`GITHUB_TOKEN` is required for builds and activity. Without it the collector
skips them and says so on the page, because unauthenticated GitHub allows 60
requests an hour and this would exhaust that on one run across seven
repositories. Release data needs no token: it comes from the public mirror.

## Deploying to dart2

The page is a normal site under the lk_web contract; the data directory is
server-generated, exactly like `/releases/`. **These two manifest entries need
Michael's approval — `manifest/` is not edited without it.**

```json
// manifest/domains.json
{"node": "dart2", "domain": "status.aloecraft.org",
 "www_root": "/var/www/html/status/"}
```

```json
// manifest/sites.json
{
  "name": "status-board", "vhost": "status.aloecraft.org", "path": "/",
  "serves": "static",
  "source": {"repo": "Aloecraft-org/technoproj", "ref": "main"},
  "build": {"kind": "cmd", "cmd": ["./status/build.sh"], "output": "status/_out"},
  "note": "Internal only, enforced in nginx (site-extra/status.aloecraft.org/access.conf) rather than by port -- dart2's nginx is public on 443. data/ below is server-generated."
},
{
  "name": "status-data", "vhost": "status.aloecraft.org", "path": "/data/",
  "serves": "server", "generator": "status/collect.py",
  "schedule": "autoserv on dart2, every 10m",
  "note": "Written on the box by collect.py. Declared so deploy.py keeps --delete off it."
}
```

### Internal-only, and the one carve-out that matters

dart2's nginx is **public on 443** — glance and reportserv are restricted by
firewall because they sit on high ports, but a vhost cannot be. So access is
an nginx drop-in at `/etc/nginx/site-extra/status.aloecraft.org/access.conf`:

```nginx
# The DMZ is the only network dart2 is on; 192.168.2.0/24 is its subnet.
location / {
    allow 192.168.2.0/24;
    deny  all;
}

# Load-bearing: dart2 issues certificates with `certbot --webroot`, so the
# ACME challenge must stay reachable from the public internet. Deny it and
# the first renewal fails -- ninety days after everything looked fine.
location /.well-known/acme-challenge/ {
    allow all;
    root /var/www/html/status;
}
```

This is the fleet's first internal-only vhost; nothing else establishes the
pattern.

### autoserv

One action and one trigger in `lk_bootstrap/dartvps/autoserv.json`:

```json
{"name": "status_collect",
 "command": "GITHUB_TOKEN=$(cat /etc/status/github_token) /home/ansibleusr/scripts/collect.py --profile internal --out /var/www/html/status/data",
 "timeout": 300, "enabled": true}
```

```json
{"action": "status_collect", "type": "cron",
 "cron_expr": "*/10 * * * *", "enabled": true}
```

## Becoming the public page

`--profile public` is the whole change to the build. What is left to decide
is not in this directory:

- **Where it is served.** cloud1 already serves `software.aloecraft.org`
  publicly; a public status page probably belongs there rather than on dart2.
- **Service status.** This board covers *projects*. The fleet's own services
  are `glance`'s subject, generated from the manifests. A public "dev and
  service status" page is those two joined — the table here plus a services
  section fed by glance or reportserv. The page is laid out to take a second
  section without rework.
- **What the public profile says when something is failing.** It currently
  publishes `build.status`, on the grounds that a status page which cannot
  say a build is failing is not a status page. That is a real choice and the
  comment block in `profiles/public.json` records it.
