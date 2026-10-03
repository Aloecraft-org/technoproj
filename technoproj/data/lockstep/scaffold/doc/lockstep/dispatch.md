# Dispatch

What this repo asks of other repos. The operator never writes another
repo to get work done there; it appends an item here, and the router
named by `dispatch.inbox` in the target's sources.yaml delivers it.
Append only: a past item is never edited. A reply is a new item in the
replying repo's own dispatch.md, with `Re:` naming this one.

Item format:

    ## D-000 To: <target's dispatch name>. Title
    Why: what happened here that makes this needed
    Ask: what the target should do, specific enough to act on
    Approval: a link to text the owner wrote or merged, or none
    Re: the item this answers, as <repo dispatch name> D-000, or none
