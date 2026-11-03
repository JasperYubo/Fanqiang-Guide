# Router upstream observation

The separate [Router upstream observations workflow](../.github/workflows/check-router-upstream.yml) checks daily at 22:41 UTC (06:41 the following day in Beijing). It can also be run with **Run workflow**. Pull requests run offline tests only. Scheduled execution starts after this workflow reaches the repository's default branch; a local check is not evidence that a scheduled GitHub run has occurred.

## What it observes

- The current default branch and commit of `hq450/fancyss`; the branch name is discovered, not assumed to be `main`.
- Changes in `README.md`, `fancyss/install.sh`, `packages/version.json.js`, and all `packages/fancyss_*_full.tar.gz` / `*_lite.tar.gz` Git objects, compared with the reviewed commit in `data/router-compatibility.json`. Added or removed package paths also require review.
- Advertised package version and MD5 values from the current manifest. Git object identity is observed, but archive bytes and installer behavior are **not reverified** by this job.
- Every publisher source already recorded in the reviewed matrix: KoolCenter release first-post title/edit time, firmware/model directory page hashes, root listing hashes, and recorded naming evidence. Changes to forum view/reply counters alone do not raise a release-change report. A new model or firmware directory changes its watched parent listing; it is flagged for review, not automatically joined to a supported model.

This is a change detector with bounded requests. It does not search the entire publisher site, discover unrelated new release topics, or claim that an unchanged source proves compatibility. Changed directory HTML can reflect a publisher presentation change; the report identifies it as a source change for a human to assess.

## Results and review

Each run writes `router-upstream-observation.json` and `router-upstream-summary.md`, publishes the summary in the Actions run, and retains the `router-upstream-review` artifact for 30 days. There are three outcomes:

| Outcome | Meaning |
| --- | --- |
| `unchanged` | All watched checks succeeded and matched the reviewed baseline. |
| `changes_pending_review` | One or more observations differ; each change is `pending_manual_review`. |
| `partial_failure` | Some checks were unavailable or invalid. Other observations remain useful, but an unavailable check is unknown. The job exits unsuccessfully so the failure stays visible. |

Every run compares with the **reviewed matrix**, not the preceding run. An unreviewed change remains pending until a maintainer reviews evidence and deliberately updates the baseline. Routine successful no-change checks do not create issues, comments, email, Slack messages, commits, or other external notifications. GitHub's account-level workflow notifications are controlled by the account owner.

The watcher never rewrites `data/router-compatibility.json`, changes the reviewed `PIN`/`INSTALL_SHA`, installs packages, or marks a model as tested. It uses read-only repository permission. Observed upstream commits, package checksums, model text or firmware files are not approval, a signature check, or a hardware test.

Before accepting a new fancyss baseline, a maintainer reviews installer gates, platform/full/lite metadata, model and firmware evidence, and any exceptions. The manual evidence builder deliberately rejects an unreviewed commit. Updating the reviewed constants and matrix remains an explicit reviewed source change. Firmware source changes alone likewise require review before they alter compatibility facts.

## Run and test on Linux

```sh
python3 -m unittest discover -s tests -p test_router_upstream_watch.py -v
python3 scripts/check_router_upstream.py --output-dir /tmp/router-upstream-review
```

The collector uses a fresh temporary cache for this job. The manual `developer/update_router_compatibility.py` now fetches sources again in online mode even if cache files exist; `--offline` alone reuses cached bytes and their original observation timestamps. A failed online request does not silently claim cached evidence is fresh. No long-running process or Windows scheduled task is involved.
