"""Regression tests for metadata extraction heuristics.

Every case here reproduces a real page that shaped the heuristics; the
site it came from is named in the comment. If a new site needs a new
strategy, add its minimal reproduction here.
"""

from capture.extract import (
    body_date,
    normalize,
    page_slug,
    page_title,
    published_date,
    slugify,
    strip_site_suffix,
)
from capture.resolvers import arxiv_id, arxiv_published, original_url


def test_slugify_drops_apostrophes():
    # austinhenley.com: "Baby's" must not become "baby-s"
    assert slugify("Baby's first type checker") == "babys-first-type-checker"


def test_slugify_transliterates_accents():
    # dynomight.net: "Bourdieu's Theory of Taste: A Grumbling Abrégé"
    assert slugify("A Grumbling Abrégé") == "a-grumbling-abrege"


def test_slugify_collapses_punctuation():
    assert (
        slugify("Mapping latitude and longitude to country, state, or city")
        == "mapping-latitude-and-longitude-to-country-state-or-city"
    )


def test_strip_site_suffix_matching_domain():
    # bloomberg.com via archive.is
    assert (
        strip_site_suffix("Why Is Spoofing Bad? - Bloomberg", "bloomberg.com")
        == "Why Is Spoofing Bad?"
    )


def test_strip_site_suffix_keeps_unrelated_tail():
    assert (
        strip_site_suffix("Attention - What It Means", "example.com")
        == "Attention - What It Means"
    )


def test_title_og_with_apostrophe():
    # austinhenley.com: og:title content ends at the closing quote, not at "'"
    html = '<meta property="og:title" content="Baby\'s first type checker">'
    assert page_title(html) == "Baby's first type checker"


def test_title_prefers_h1_over_title_tag():
    # austinhenley.com/blog/favwikiarticles.html: <title> disagrees with h1
    html = (
        "<title>Favorite Wikipedia pages about science - Austin Z. Henley</title>"
        "<h1>My favorite Wikipedia articles about science</h1>"
    )
    assert page_title(html) == "My favorite Wikipedia articles about science"


def test_title_forum_section_prefix():
    # artofproblemsolving.com: h1 is the blog name, <title> holds the post
    html = "<title>Turtle Math : The Emoji Problem:  Part I</title><h1>Turtle Math</h1>"
    assert page_title(html) == "The Emoji Problem: Part I"


def test_title_og_with_name_attribute():
    # eev.ee: <meta name="og:title"> rather than property=, with a
    # non-breaking space in the content
    html = '<meta name="og:title" content="Dark corners of\xa0Unicode">'
    assert page_title(html) == "Dark corners of Unicode"


def test_title_og_content_before_property():
    # bitmath.blogspot.com: Blogger writes content= first, single-quoted
    html = "<meta content='Propagating bounds' property='og:title'/>"
    assert page_title(html) == "Propagating bounds"


def test_title_h1_containing_link():
    # h1s wrapping a permalink are titles; h1s linking to the site
    # ROOT are mastheads (see test_title_strips_masthead_prefix)
    html = (
        '<h1 class="title"><a href="/2023/07/bounds.html">Propagating bounds</a></h1>'
    )
    assert page_title(html) == "Propagating bounds"


def test_title_skips_masthead_h1():
    # beepb00p.xyz: the h1 is the site name; the real title is in <title>
    html = "<title>Map of my personal data infrastructure | beepb00p</title><h1>beepb00p</h1>"
    assert page_title(html, "beepb00p.xyz") == "Map of my personal data infrastructure"


def test_title_prefers_classed_h1_over_masthead_h1():
    # WordPress themes with a site-title h1 before the entry-title h1
    html = (
        '<h1 class="site-title">Headlands Technologies LLC Blog</h1>'
        '<h1 class="entry-title">Opinion: Rationalizing Latency Competition</h1>'
    )
    assert page_title(html) == "Opinion: Rationalizing Latency Competition"


def test_title_h1_kept_when_title_tag_appends_site_name():
    # blog.headlandstech.com: <title> is "h1 – Site Name"; the h1 must
    # not be replaced by the shorter site-name remainder
    html = (
        "<title>Opinion: Rationalizing Latency Competition in High-Frequency"
        " Trading &#8211; Headlands Technologies LLC Blog</title>"
        '<h1 class="entry-title">Opinion: Rationalizing Latency Competition'
        " in High-Frequency Trading</h1>"
    )
    assert (
        page_title(html, "blog.headlandstech.com")
        == "Opinion: Rationalizing Latency Competition in High-Frequency Trading"
    )


def test_title_site_name_h1_stripped_from_title_tag_suffix():
    html = "<title>Great Post &#8211; Some Site</title><h1>Some Site</h1>"
    assert page_title(html) == "Great Post"


def test_title_obsidian_publish_h2_heading():
    # chadnauseam.com: no h1 or og:title; the title is a classed h2
    html = (
        "<title>calculator-app - Chad Nauseam Home</title>"
        '<h2 class="publish-article-heading">"A calculator app?'
        ' Anyone could make that."</h2>'
    )
    assert page_title(html, "chadnauseam.com") == (
        '"A calculator app? Anyone could make that."'
    )


def test_strip_site_suffix_starting_with_domain_label():
    # chadnauseam.com: suffix is "Chad Nauseam Home", not an exact
    # domain match
    assert (
        strip_site_suffix("calculator-app - Chad Nauseam Home", "chadnauseam.com")
        == "calculator-app"
    )


def test_title_strips_masthead_prefix():
    # eli.li: the site bakes "Oatmeal - " into og:title and <title>;
    # the masthead h1 (linking to the root) reveals the site name
    html = (
        '<meta property="og:title" content="Oatmeal - To the surprise'
        ' of literally no one">'
        '<h1><a href="/">« Oatmeal</a></h1>'
    )
    assert page_title(html, "eli.li") == "To the surprise of literally no one"


def test_title_strips_og_site_name_suffix():
    # dervis.de: og:site_name "Cem Dervis" matches neither the domain
    # nor any masthead, but the site declares it explicitly
    html = (
        '<meta property="og:title" content="The Case for Physical Media'
        ' Ownership | Cem Dervis">'
        '<meta property="og:site_name" content="Cem Dervis">'
    )
    assert page_title(html, "dervis.de") == "The Case for Physical Media Ownership"


def test_title_strips_comma_separated_site_name():
    # nightingaledvs.com: og:title "Post, Nightingale" with the site
    # name declared in og:site_name
    html = (
        '<meta property="og:title" content="I Stopped Using Box Plots:'
        ' The Aftermath, Nightingale">'
        '<meta property="og:site_name" content="Nightingale">'
    )
    assert page_title(html, "nightingaledvs.com") == (
        "I Stopped Using Box Plots: The Aftermath"
    )


def test_title_url_slug_disambiguates_wrapped_h1():
    # gameprogrammingpatterns.com: <title> is "H1 · Section · Site" and
    # the section is longer than the true title; the URL slug decides
    html = (
        "<title>Game Loop · Sequencing Patterns · Game Programming Patterns</title>"
        "<h1>Game Loop</h1>"
    )
    url = "https://gameprogrammingpatterns.com/game-loop.html"
    assert page_title(html, "gameprogrammingpatterns.com", url) == "Game Loop"


def test_slug_affinity_survives_truncated_slugs():
    from capture.extract import slug_affinity

    # buttondown.com/hillelwayne: the slug drops the final word
    assert slug_affinity(
        "Many Hard Leetcode Problems are Easy Constraint Problems",
        "many-hard-leetcode-problems-are-easy-constraint",
    )
    assert not slug_affinity("Turtle Math", "c2532359h2760821-the-emoji-problem-part-i")


def test_best_hn_submission_prefers_discussion():
    from capture.pipeline import best_submission

    drive_by = {"objectID": "1", "points": 50, "num_comments": 3}
    debated = {"objectID": "2", "points": 30, "num_comments": 400}
    assert best_submission([drive_by, debated]) == debated
    tied = {"objectID": "3", "points": 80, "num_comments": 3}
    assert best_submission([drive_by, tied]) == tied


def test_youtube_id_from_url_forms():
    from capture.resolvers import youtube_id

    for url in [
        "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        "https://www.youtube.com/watch?list=PL123&v=jNQXAC9IVRw",
        "https://youtu.be/jNQXAC9IVRw?t=10",
        "https://www.youtube.com/shorts/jNQXAC9IVRw",
        "https://www.youtube.com/live/jNQXAC9IVRw",
    ]:
        assert youtube_id(url) == "jNQXAC9IVRw"
    assert youtube_id("https://www.youtube.com/@somechannel") is None


def test_existing_capture_resolves_youtube_forms(tmp_path, monkeypatch):
    import capture.pipeline as module

    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    folder = tmp_path / "data" / "youtube.com - 2005-04-23 - me-at-the-zoo"
    folder.mkdir(parents=True)
    (folder / "youtube.com - 2005-04-23 - me-at-the-zoo.info.json").write_text(
        '{"id": "jNQXAC9IVRw", "title": "Me at the zoo"}'
    )
    assert module.existing_capture("https://youtu.be/jNQXAC9IVRw") == folder
    assert module.existing_capture("https://youtu.be/AAAAAAAAAAA") is None


def test_localize_images(tmp_path, monkeypatch):
    from pathlib import Path

    import capture.pipeline as pipeline

    def fake_curl(cmd, capture_output=True, **kwargs):
        class Result:
            returncode = 0

        output = Path(cmd[cmd.index("-o") + 1])
        output.write_bytes(b"png bytes" if "good" in cmd[-1] else b"")
        return Result()

    monkeypatch.setattr(pipeline.subprocess, "run", fake_curl)
    text = (
        "![figure](https://example.com/good.png)\n"
        '<img width="400" src="https://example.com/good.png">\n'
        "![broken](https://example.com/bad.png)\n"
    )
    out = pipeline.localize_images(text, tmp_path)
    assert out.count("media/") == 2  # markdown and img forms localized
    assert "https://example.com/bad.png" in out  # failure keeps remote
    assert len(list((tmp_path / "media").iterdir())) == 1  # deduped


def test_markdown_heading_atx_and_setext():
    from capture.resolvers.github import markdown_heading

    assert markdown_heading("# Why CORDIC\n\nbody") == "Why CORDIC"
    # quchen/articles: setext underline headings
    assert markdown_heading("Algebraic blindness\n===================\n\nbody") == (
        "Algebraic blindness"
    )
    assert markdown_heading("no heading here\n") is None


def test_github_repo_url_forms():
    from capture.resolvers.github import github_repo

    for url in [
        "https://github.com/scandum/rotate",
        "https://github.com/scandum/rotate/",
        "https://github.com/scandum/rotate.git",
    ]:
        assert github_repo(url) == ("scandum", "rotate")
    # Deeper paths and non-repo routes are not repo captures
    assert github_repo("https://github.com/o/r/blob/main/x.md") is None
    assert github_repo("https://github.com/o/r/issues/5") is None
    assert github_repo("https://github.com/topics/compression") is None
    # Gists are not repos (their user/id shape looks like owner/repo)
    assert github_repo("https://gist.github.com/erincandescent/8a10eee") is None


def test_github_blob_markdown(monkeypatch):
    import capture.resolvers.base as base
    import capture.resolvers as module

    monkeypatch.setattr(base, "fetch_html", lambda u: "# CORDIC\n![d](img.png)")
    gh = module.github_markdown("https://github.com/o/r/blob/main/2024/5/10/cordic.md")
    assert gh is not None
    assert gh["publish"] == "2024-05-10"
    assert gh["domain"] == "github.com - o"
    assert (
        "https://raw.githubusercontent.com/o/r/main/2024/5/10/img.png"
        in (gh["markdown"])
    )
    assert module.github_markdown("https://github.com/o/r/issues/5") is None


def test_reddit_thread_url_forms():
    from capture.resolvers import reddit_thread

    for url in [
        "https://old.reddit.com/r/SlateStarCodex/comments/1il904v/crazy_nonobvious/",
        "https://www.reddit.com/r/slatestarcodex/comments/1il904v/",
        "https://reddit.com/r/slatestarcodex/comments/1il904v",
    ]:
        assert reddit_thread(url) == ("slatestarcodex", "1il904v")
    assert reddit_thread("https://old.reddit.com/r/slatestarcodex/") is None


def test_reddit_markdown_nests_comments_by_score():
    from capture.resolvers import reddit_markdown

    post = {
        "id": "p1",
        "title": "T",
        "author": "op",
        "subreddit": "test",
        "selftext": "body",
        "num_comments": 3,
    }
    comments = [
        {"id": "a", "parent_id": "t3_p1", "author": "low", "score": 1, "body": "meh"},
        {"id": "b", "parent_id": "t3_p1", "author": "high", "score": 9, "body": "top"},
        {"id": "c", "parent_id": "t1_b", "author": "kid", "score": 2, "body": "reply"},
    ]
    md = reddit_markdown(post, comments)
    assert md.index("u/high") < md.index("u/low")  # score order
    assert "> > **u/kid** (2 points)\n> > reply" in md  # nested under b


def test_refused_fetch_falls_back_to_browser_but_missing_stays_fatal(monkeypatch):
    import pytest

    import capture.resolvers.base as base
    from capture.resolvers.default import resolve_default

    def refuse(url):
        raise base.FetchError(429, url)

    monkeypatch.setattr(base, "fetch_html", refuse)
    resolution = resolve_default("https://quarter--mile.com/post")
    assert resolution.use_browser and resolution.html == ""

    def missing(url):
        raise base.FetchError(404, url)

    monkeypatch.setattr(base, "fetch_html", missing)
    with pytest.raises(base.FetchError):
        resolve_default("https://predictionmarkets.miraheze.org/wiki/Gone")


def test_lesswrong_post_url_forms():
    from capture.resolvers import lesswrong_post

    for url in [
        "https://www.lesswrong.com/posts/7X2j8HAkWdmMoS8PE/disputing-definitions",
        "https://www.greaterwrong.com/posts/7X2j8HAkWdmMoS8PE/disputing-definitions",
        "https://www.alignmentforum.org/posts/7X2j8HAkWdmMoS8PE/disputing-definitions",
    ]:
        assert lesswrong_post(url) == ("7X2j8HAkWdmMoS8PE", "disputing-definitions")
    assert lesswrong_post("https://www.lesswrong.com/tag/rationality") is None


def test_lesswrong_metadata_from_greaterwrong(monkeypatch):
    import capture.resolvers.base as base
    from capture.resolvers.lesswrong import resolve_lesswrong

    page = (
        '<a class="author" href="/users/eliezer_yudkowsky" data-userid="x">'
        "Eliezer Yudkowsky</a>"
        '<span class="date hide-until-init" data-js-date=1202775311000>'
        "12 Feb 2008 0:15 UTC</span>"
    )
    monkeypatch.setattr(base, "fetch_html", lambda u: page)
    resolution = resolve_lesswrong(
        "https://www.lesswrong.com/posts/7X2j8HAkWdmMoS8PE/disputing-definitions"
    )
    assert resolution is not None
    assert resolution.publish == "2008-02-12"
    assert resolution.domain == "lesswrong.com - eliezer-yudkowsky"
    assert resolution.extra["author"] == "Eliezer Yudkowsky"


def test_lesswrong_wiki_urls():
    from capture.resolvers.lesswrong import lesswrong_post, lesswrong_wiki

    assert lesswrong_wiki("https://www.lesswrong.com/w/bayes-rule-log-odds-form") == (
        "bayes-rule-log-odds-form"
    )
    assert lesswrong_wiki("https://www.greaterwrong.com/tag/forecasting") == (
        "forecasting"
    )
    assert (
        lesswrong_post("https://www.lesswrong.com/w/bayes-rule-log-odds-form") is None
    )


def test_wikipedia_article_url_forms():
    from capture.resolvers import wikipedia_article

    assert wikipedia_article("https://en.wikipedia.org/wiki/Ulysses_pact") == (
        "en",
        "Ulysses_pact",
    )
    assert wikipedia_article("https://en.m.wikipedia.org/wiki/Ulysses_pact") == (
        "en",
        "Ulysses_pact",
    )
    assert wikipedia_article(
        "https://de.wikipedia.org/wiki/Kognitive_Dissonanz#Geschichte"
    ) == ("de", "Kognitive_Dissonanz")
    assert wikipedia_article("https://en.wikipedia.org/wiki/Special:Random") is not None
    assert wikipedia_article("https://wikipedia.org/") is None


def test_wayback_snapshot_url_forms():
    from capture.resolvers import wayback_snapshot

    assert wayback_snapshot(
        "https://web.archive.org/web/20140617202930/http://www.playfuljs.com/a-first-person-engine-in-265-lines/"
    ) == (
        "20140617202930",
        "http://www.playfuljs.com/a-first-person-engine-in-265-lines/",
    )
    # id_ form (raw original bytes) parses to the same snapshot
    assert wayback_snapshot(
        "https://web.archive.org/web/20160819141717id_/http://www.ofb.net/~egnor/iocaine.html"
    ) == ("20160819141717", "http://www.ofb.net/~egnor/iocaine.html")
    assert wayback_snapshot("https://web.archive.org/") is None


def test_path_identity_platforms():
    from capture.resolvers import path_identity_domain

    assert path_identity_domain(
        "https://medium.com/digital-gamma-blog/everything-88cfcb5e83a"
    ) == ("medium.com - digital-gamma-blog")
    assert path_identity_domain("https://medium.com/@author/some-post-123abc") == (
        "medium.com - @author"
    )
    assert path_identity_domain(
        "https://buttondown.com/hillelwayne/archive/many-hard/"
    ) == ("buttondown.com - hillelwayne")
    # A bare profile page has no post segment; ordinary sites never match
    assert path_identity_domain("https://medium.com/@author") is None
    assert path_identity_domain("https://example.com/a/b") is None


def test_title_drops_leading_date_from_heading():
    # mazzo.li: <h1><em class="date">2022-06-01</em> How fast ...</h1>
    html = (
        "<title>How fast are Linux pipes anyway?</title>"
        '<h1><em class="date"><span>2022-06-01</span></em>'
        " How fast are Linux pipes anyway?</h1>"
    )
    assert page_title(html, "mazzo.li") == "How fast are Linux pipes anyway?"


def test_title_empty_when_absent():
    assert page_title("<title></title>") == ""


def test_slug_falls_back_to_url_segment():
    # A shell page with no title must not produce the slug "untitled"
    url = "https://example.com/posts/some-post/"
    assert page_slug(url, "<html></html>") == "some-post"


def test_date_url_path_beats_metadata():
    # archive.is snapshot of bloomberg: snapshot metadata carries the
    # archive date, the original URL carries the publish date
    html = '<meta property="article:published_time" content="2020-09-29T20:31:25Z">'
    url = "https://www.bloomberg.com/opinion/articles/2015-04-22/why-is-spoofing-bad-"
    assert published_date(url, html) == "2015-04-22"


def test_date_url_slug():
    # arch.dog/bark/2025-03-30-infrastructure
    assert published_date("https://arch.dog/bark/2025-03-30-infrastructure", "") == (
        "2025-03-30"
    )


def test_date_published_time_meta():
    html = '<meta property="article:published_time" content="2025-07-23T10:00:00Z">'
    assert published_date("https://aaronson.org/blog/x", html) == "2025-07-23"


def test_date_json_ld():
    # substack embeds JSON-LD
    html = '{"datePublished":"2021-09-17T13:14:15.000Z"}'
    assert published_date("https://x.substack.com/p/y", html) == "2021-09-17"


def test_date_time_element():
    html = '<time datetime="2024-10-15T00:00:00-04:00">'
    assert published_date("https://bernsteinbear.com/blog/type-inference/", html) == (
        "2024-10-15"
    )


def test_body_date_named_month():
    # alexanderell.is: date only as prose
    assert body_date("<p>Posted on May 8, 2022</p>") == "2022-05-08"


def test_body_date_iso():
    # analog-hors.github.io
    assert body_date("<footer>2022-09-24</footer>") == "2022-09-24"


def test_body_date_us_slashes():
    # austinhenley.com: <small>8/31/2025</small>
    assert body_date("<small>8/31/2025</small>") == "2025-08-31"


def test_body_date_ignores_html_comments():
    # single-file stamps its save date into a comment; the real post date
    # (aops) must win even though the comment comes first
    html = (
        "<!-- Page saved with SingleFile Jul 13 2026 --><h2>Jan 18, 2022, 8:40 PM</h2>"
    )
    assert body_date(html) == "2022-01-18"


def test_body_date_ignores_dates_inside_attributes():
    # jaykmody.com: an ISO date in a link URL to someone else's post
    # must not beat the visible "January 30, 2023" text
    html = (
        '<a href="https://lilianweng.github.io/posts/2018-06-24-attention/">'
        "Attention</a><p>January 30, 2023</p>"
    )
    assert body_date(html) == "2023-01-30"


def test_body_date_with_ordinal_suffix():
    # ridiculousfish.com: "October 19th, 2011"
    assert body_date("<p>October 19th, 2011</p>") == "2011-10-19"
    assert body_date("<p>3rd May 2020</p>") == "2020-05-03"


def test_body_date_rejects_impossible_months():
    assert body_date("<p>Foobar 99, 2022</p>") is None


def test_date_none_when_unknown():
    # blog.vortan.dev: no date in the page, its metadata, or the URL.
    # The folder falls back to the capture date and the frontmatter
    # omits publish_date.
    assert published_date("https://example.com/post", "") is None


def test_original_url_archive_canonical():
    # archive.is/tJpJO
    html = (
        '<link rel="canonical" href="https://archive.is/2020.09.29-203125/'
        'https://www.bloomberg.com/opinion/articles/2015-04-22/why-is-spoofing-bad-"/>'
    )
    assert original_url("https://archive.is/tJpJO", html) == (
        "https://www.bloomberg.com/opinion/articles/2015-04-22/why-is-spoofing-bad-"
    )


def test_original_url_passthrough():
    assert original_url("https://example.com/post", "<html>") == (
        "https://example.com/post"
    )


def test_arxiv_id_from_url_forms():
    for url in [
        "https://arxiv.org/abs/2603.21852",
        "https://arxiv.org/pdf/2603.21852v2",
        "https://arxiv.org/html/2603.21852",
        "https://ar5iv.labs.arxiv.org/html/2603.21852",
    ]:
        assert arxiv_id(url) == "2603.21852"
    assert arxiv_id("https://example.com/post") is None


def test_arxiv_published_from_abs_page():
    html = "<p>[v1] Submitted on 27 Mar 2026 (this version)</p>"
    assert arxiv_published(html) == "2026-03-27"


def test_challenge_page_detection():
    from capture.extract import challenge_page

    # steamdb.info serves its bot check with HTTP 200
    assert challenge_page("<title>Checking your browser</title><p>steamdb</p>")
    assert challenge_page("<title>Just a moment...</title>")
    assert not challenge_page("<title>A post about Cloudflare</title><p>body</p>")


def test_paywalled_detects_substack_marker():
    from capture.extract import paywalled

    # leetarxiv.substack.com: escaped marker inside the preload JSON
    assert paywalled('{"post":{"audience\\":\\"only_paid\\"}}')
    assert paywalled('"audience":"only_paid"')
    assert not paywalled('"audience":"everyone"')


def test_normalize_ignores_www_scheme_and_trailing_slash():
    assert normalize("https://www.example.com/a/b/") == normalize(
        "http://example.com/a/b"
    )


def test_existing_capture_matches_frontmatter_url(tmp_path, monkeypatch):
    import capture.pipeline as module

    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    folder = tmp_path / "data" / "example.com - 2025-01-01 - post"
    folder.mkdir(parents=True)
    (folder / "example.com - 2025-01-01 - post.md").write_text(
        '---\ntitle: "Post"\nurl: https://example.com/post/\n---\n'
    )
    assert module.existing_capture("https://www.example.com/post") == folder
    assert module.existing_capture("https://example.com/other") is None


def test_existing_capture_resolves_arxiv_forms(tmp_path, monkeypatch):
    import capture.pipeline as module

    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    folder = tmp_path / "data" / "arxiv.org - 2026-03-23 - paper"
    folder.mkdir(parents=True)
    (folder / "arxiv.org - 2026-03-23 - paper.md").write_text(
        "---\nurl: https://arxiv.org/abs/2603.21852\n---\n"
    )
    assert module.existing_capture("https://arxiv.org/pdf/2603.21852v2") == folder
