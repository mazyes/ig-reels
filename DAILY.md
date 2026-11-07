# Daily reel run

The scheduled task follows these steps once a day. Work in this folder. Stop and log if any step fails; never post a half-made reel.

1. **News:** `python fetch_news.py > news.json`. If it returns 0 stories, run it again with `--hours 72`.
2. **Pick:** score every story with the "Story picking" rules in `content-rules.md` and take the highest. Skip anything already in `posted.json`. Read the article at its link before writing. Only use facts from it.
3. **Hook:** write 5 hooks, save them one per line in `hooks.txt`, then run
   `python ~/.claude/skills/ig-reel/hookscore.py hooks.txt`. Use the top hook. If it scores under 55, write 5 more and score again.
4. **Script:** write `reels/YYYY-MM-DD-<slug>.json` in the shape of the existing reel files: 5-7 slides, each with `say`, `broll` and `highlight`, plus `handle`, `source`, `link`, `hook_score` and `caption`. 70-90 spoken words total. Follow `content-rules.md` exactly. Run the caption through `/ig-human` rules: no em dashes, no slop words.
5. **Render:** `python render.py reels/<file>.json reels/<file>.mp4`. It must print a length of 20-45 seconds. If it is longer, cut words and render again.
6. **Publish the file:** `git add reels/<file>.* && git commit -m "reel: <slug>" && git push`. The public URL is
   `https://cdn.jsdelivr.net/gh/mazyes/ig-reels@<commit-sha>/reels/<file>.mp4`. Use the commit SHA, not `main`, so the CDN never serves a stale file. Check it returns `200` and `video/mp4` with `curl -sI`.
7. **Post:** Windsor `execute_action`, connector `instagram`, action `create_video_post`, with `video_url` = the URL above, `caption` from the JSON and `share_to_feed: true`.
8. **Log:** append `{"date", "link", "title", "file", "hook_score", "media_id"}` to `posted.json`, then commit and push.
9. **LinkedIn draft:** write the same story as a short LinkedIn text post (hook line, 4-6 short lines, one question at the end, no hashtags beyond 3) to `linkedin/YYYY-MM-DD-<slug>.md`. Do not post it.
