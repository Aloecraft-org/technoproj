# status — activity, build and release board

A static page plus a collector. Deployed to dart2 for internal use, and
written so the same build serves a public page by changing one argument.

```
status/
  collect.py          a shim; the collector is technoproj/status.py
  build.sh --out DIR  site contract: offline, hermetic, never deploys
  template/           index.html, style.css, app.js

technoproj/
  status.py           fetches; decides what a profile may publish
  profiles/           internal.json, public.json -- one copy, read by
                      the installed collector and by build.sh alike
```

On a host, the collector arrives with the package:

```sh
pip install git+https://github.com/Aloecraft-org/technoproj@v0.1.0
technoproj-status-collect --profile internal --out /var/www/html/status/data
```

**The collector imports only the standard library**, so `--no-deps` is always
safe for it. PyYAML is technoproj's dependency for the changelog engine; a
host that only collects never needs it. That matters on a node whose Python
is provisioned offline from a wheelhouse — see dart2 below.

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

Landed in lk2: `manifest/domains.json` carries `status.aloecraft.org`, and
`manifest/sites.json` carries `status-board` (the static page) and
`status-data` (the directory the collector writes, `serves: server` so
deploy.py's `--delete` stays off it). The nginx drop-in and the autoserv
action are in `ansible/ansible-dart2.yaml` and
`lk_bootstrap/dartvps/autoserv.json`.

```sh
lk_web/stage.py  status-board
lk_web/deploy.py status-board -n      # read the deletions first
lk_web/deploy.py status-board
ansible-playbook ansible/ansible-dart2.yaml -i ./ansible/inventory \
    --limit aloecraft-dart2 --tags install_status -b
```

### Internal-only, and the one carve-out that matters

dart2's nginx is **public on 443** — glance and reportserv are restricted by
firewall because they sit on high ports, but a vhost cannot be. So access is
an nginx drop-in at `/etc/nginx/site-extra/status.aloecraft.org/access.conf`
allowing `192.168.2.0/24`, the DMZ subnet, and denying everything else.

**It must leave `/.well-known/acme-challenge/` open.** dart2 issues
certificates with `certbot --webroot`, so denying that path passes the first
issuance and fails the first *renewal* — ninety days later, when nobody is
looking at this.

This is the fleet's first internal-only vhost; nothing else establishes the
pattern.

### Why dart2 installs it to /opt/status rather than normally

Two facts about that node, both in `bootstrap_dartvps_musl_py.sh`:

- it installs `--no-index` from a wheelhouse tarball, offline by design, so
  a git install is already against the grain and is at least `--no-deps`;
- it begins `rm -rf /usr/local/pyalt`, so anything pip-installed into that
  prefix is destroyed by the next `install_musl_py` — and the collector
  would stop silently, weeks later, with nothing pointing at the cause.

So dart2 installs with `--target /opt/status/lib`, which the wipe does not
reach, and runs it as `PYTHONPATH=/opt/status/lib python3 -m
technoproj.status` rather than through a console script inside the prefix.

Any node with a normal Python can use the plain form above.

### The token

`GITHUB_TOKEN` lives at `/etc/status/github_token`, mode 0600, owned by the
user autoserv runs as. Without it the collector still runs and still writes a
complete `status.json` — builds and activity are skipped and the page says
so, because unauthenticated GitHub allows 60 requests an hour and this would
exhaust that on one run across seven repositories. Release data needs no
token: it comes from the public mirror.

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
