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


def test_title_landing_page_keeps_site_name():
    # airport.apunen.com: a game's root page whose <title>, og:title, and
    # og:site_name are all identically the site name. With no URL slug to
    # fall back on, the site name is the page's real identity.
    html = (
        "<title>Airport Simulator</title>"
        '<meta property="og:title" content="Airport Simulator">'
        '<meta property="og:site_name" content="Airport Simulator">'
    )
    root = "https://airport.apunen.com/"
    assert page_title(html, "airport.apunen.com", root) == "Airport Simulator"
    # The same site-name-only page at a path stays suppressed, so naming
    # falls through to the URL slug rather than repeating the site name.
    deep = "https://airport.apunen.com/blog/some-post"
    assert page_title(html, "airport.apunen.com", deep) == ""


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


def test_hackernews_threads_keeps_every_discussed_submission(monkeypatch):
    # arxiv.org/abs/1706.03762 has 16 HN submissions; the old "one best
    # submission" rule kept exactly one however many were discussed.
    import capture.discussions as disc

    url = "https://arxiv.org/abs/1706.03762"
    monkeypatch.setattr(
        disc,
        "_get_json",
        lambda api: {
            "hits": [
                {"objectID": "34649113", "url": url, "num_comments": 55},
                {"objectID": "20000000", "url": url, "num_comments": 9},
                {"objectID": "14542830", "url": url, "num_comments": 3},
                {"objectID": "14553119", "url": url, "num_comments": 0},
                {"objectID": "99999999", "url": "https://elsewhere.example/"},
            ]
        },
    )
    # Both discussed submissions survive; the 3-comment drive-by, the
    # silent repost, and the hit for another URL do not.
    assert disc.hackernews_threads(url) == [
        ("https://news.ycombinator.com/item?id=34649113", 55),
        ("https://news.ycombinator.com/item?id=20000000", 9),
    ]


def test_reddit_threads_drop_hn_mirror_bots(monkeypatch):
    # The same paper on reddit: r/MachineLearning is the discussion.
    # r/hackernews and friends mirror the HN front page, so they are
    # dropped even when a mirror draws a crowd; u_* is a profile page.
    import capture.discussions as disc

    def post(subreddit, comments, thread="abc123"):
        return {
            "subreddit": subreddit,
            "num_comments": comments,
            "permalink": f"/r/{subreddit}/comments/{thread}/t/",
        }

    monkeypatch.setattr(
        disc,
        "_get_json",
        lambda api: {
            "data": [
                post("MachineLearning", 58),
                post("hackernews", 40),
                post("patient_hackernews", 1),
                post("h_n", 1),
                post("u_MrDCP2", 30),
                post("todayilearned", 400),
                post("compsci", 5, "quiet"),
                post("compsci", 7, "busy"),
            ]
        },
    )
    # Five comments is still drive-by; six is the bar. r/todayilearned
    # is dropped however busy it gets: it discusses the headline fact,
    # not the piece.
    assert disc.reddit_threads("https://arxiv.org/abs/1706.03762") == [
        ("https://www.reddit.com/r/MachineLearning/comments/abc123/t/", 58),
        ("https://www.reddit.com/r/compsci/comments/busy/t/", 7),
    ]


def test_reddit_threads_keep_one_per_subreddit(monkeypatch):
    # en.wikipedia.org/wiki/Low-background_steel drew 25 r/todayilearned
    # threads over a decade — the same fact reposted, not 25 discussions.
    # Whatever the subreddit, the busiest thread stands for it.
    import capture.discussions as disc

    monkeypatch.setattr(
        disc,
        "_get_json",
        lambda api: {
            "data": [
                {
                    "subreddit": "rust",
                    "num_comments": n,
                    "permalink": f"/r/rust/comments/{n}/t/",
                }
                for n in (9, 41, 12)
            ]
        },
    )
    assert disc.reddit_threads("https://example.com/x") == [
        ("https://www.reddit.com/r/rust/comments/41/t/", 41)
    ]


def test_lobsters_threads_match_url_not_just_title(monkeypatch):
    # Lobsters is searched by title because it has no URL lookup, so
    # the story's own u-url has to confirm the hit.
    import capture.discussions as disc

    def block(short_id, url, comments):
        return (
            f'<li id="story_{short_id}" data-shortid="{short_id}">'
            f'<a class="u-url" href="{url}">t</a>'
            f'<a href="/s/{short_id}/slug" class="mobile_comments">'
            f"<span>{comments}</span></a>"
        )

    wanted = "https://danluu.com/everything-is-broken/"
    monkeypatch.setattr(
        disc,
        "_get_html",
        lambda page: "<ol>"
        + block("aaaaaa", "https://elsewhere.example/same-title", 90)
        + block("bbbbbb", wanted, 31)
        + block("cccccc", wanted, 2)
        + "</ol>",
    )
    # Only the URL match above the comment bar survives: not the
    # same-titled story elsewhere, not the two-comment one.
    assert disc.lobsters_threads(wanted, "Everything is broken") == [
        ("https://lobste.rs/s/bbbbbb", 31)
    ]
    # No title, no search: lobsters has nothing else to go on.
    assert disc.lobsters_threads(wanted, "") == []


def test_discussions_sorts_across_sources_and_drops_self(monkeypatch):
    import capture.discussions as disc

    hn = "https://news.ycombinator.com/item?id=1"
    monkeypatch.setattr(disc, "hackernews_threads", lambda u: [(hn, 20)])
    monkeypatch.setattr(
        disc,
        "reddit_threads",
        lambda u: [("https://www.reddit.com/r/a/comments/b/c/", 90)],
    )
    # Reddit's 90 outranks HN's 20: the list is ordered by discussion,
    # not by source.
    assert disc.discussions("https://example.com/post") == [
        "https://www.reddit.com/r/a/comments/b/c/",
        hn,
    ]
    # Capturing the HN thread itself must not list it as its own
    # discussion.
    assert disc.discussions(hn) == ["https://www.reddit.com/r/a/comments/b/c/"]


def test_discussions_survive_a_dead_source(monkeypatch):
    import capture.discussions as disc

    def die(url, retry=True):
        raise disc.FetchError(403, url)

    # The real failure path: Arctic Shift answers automated clients 403.
    monkeypatch.setattr(disc, "fetch_html", die)
    # A source that fails contributes nothing rather than failing the
    # capture built around it.
    assert disc.discussions("https://example.com/post") == []


def test_discussions_survive_a_junk_response(monkeypatch):
    import capture.discussions as disc

    # Well-formed JSON that is not the shape either API documents:
    # missing keys must not raise past the lookup.
    monkeypatch.setattr(disc, "_get_json", lambda api: {"hits": [{}], "data": [{}]})
    assert disc.discussions("https://example.com/post") == []


def test_discussion_lines_empty_list_is_explicit():
    from capture.pipeline import discussion_lines

    assert discussion_lines([]) == ["discussions: []"]
    assert discussion_lines(["https://a.example/1", "https://b.example/2"]) == [
        "discussions:",
        "  - https://a.example/1",
        "  - https://b.example/2",
    ]


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


def test_existing_capture_resolves_youtube_forms(tmp_path):
    import capture.pipeline as module

    folder = tmp_path / "data" / "youtube.com - 2005-04-23 - me-at-the-zoo"
    folder.mkdir(parents=True)
    (folder / "youtube.com - 2005-04-23 - me-at-the-zoo.info.json").write_text(
        '{"id": "jNQXAC9IVRw", "title": "Me at the zoo"}'
    )
    assert (
        module.existing_capture("https://youtu.be/jNQXAC9IVRw", tmp_path / "data")
        == folder
    )
    assert (
        module.existing_capture("https://youtu.be/AAAAAAAAAAA", tmp_path / "data")
        is None
    )


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


def test_github_wiki_page(monkeypatch):
    import capture.resolvers.base as base
    import capture.resolvers.github as github

    fetched = []

    def fake_fetch(url: str) -> str:
        fetched.append(url)
        # stickfigure/blog: the h1 is the post DATE, not the title
        return "# Oct 30, 2023\n\nbody\n\n![d](assets/img.png)"

    monkeypatch.setattr(base, "fetch_html", fake_fetch)
    monkeypatch.setattr(github, "wiki_first_commit", lambda o, r, f: "2023-10-30")

    wiki = github.github_wiki(
        "https://github.com/stickfigure/blog/wiki/How-to-%28and-how-not-to%29-design-REST-APIs"
    )
    assert wiki is not None
    # Percent-escapes survive the round trip to the raw wiki host
    assert fetched == [
        "https://raw.githubusercontent.com/wiki/stickfigure/blog/"
        "How-to-%28and-how-not-to%29-design-REST-APIs.md"
    ]
    # The page name is the title; the first heading would give "Oct 30, 2023"
    assert wiki["title"] == "How to (and how not to) design REST APIs"
    assert wiki["publish"] == "2023-10-30"
    assert wiki["domain"] == "github.com - stickfigure"
    # Wiki uploads live at the wiki repo root, beside the page
    assert (
        "https://raw.githubusercontent.com/wiki/stickfigure/blog/assets/img.png"
        in wiki["markdown"]
    )


def test_github_wiki_url_forms(monkeypatch):
    import capture.resolvers.base as base
    import capture.resolvers.github as github

    monkeypatch.setattr(base, "fetch_html", lambda u: u)
    monkeypatch.setattr(github, "wiki_first_commit", lambda o, r, f: None)

    # A bare /wiki is the Home page, as GitHub's own redirect has it
    for url in ["https://github.com/o/r/wiki", "https://github.com/o/r/wiki/"]:
        home = github.github_wiki(url)
        assert home is not None and home["title"] == "Home"
    # `?` in a page name must not become a query string
    wiki = github.github_wiki("https://github.com/o/r/wiki/What-Is-Similarity%3F")
    assert wiki is not None
    assert wiki["markdown"].endswith("What-Is-Similarity%3F.md")
    # GitHub's own wiki UI routes are not pages
    assert github.github_wiki("https://github.com/o/r/wiki/_history") is None
    # Non-wiki GitHub URLs stay with their own resolvers
    assert github.github_wiki("https://github.com/o/r") is None
    assert github.github_wiki("https://github.com/o/r/blob/main/x.md") is None


def test_github_repo_ignores_wiki_urls():
    from capture.resolvers.github import github_repo

    # The wiki resolver runs first, but a wiki URL is not a repo capture
    assert github_repo("https://github.com/o/r/wiki") is None
    assert github_repo("https://github.com/o/r/wiki/Some-Page") is None


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


def test_extensionless_pdf_urls_sniffed_by_content(monkeypatch):
    import capture.resolvers.base as base
    import capture.resolvers.default as default

    monkeypatch.setattr(base, "fetch_html", lambda u: "%PDF-1.7 mangled binary")
    sentinel = object()
    monkeypatch.setattr(default, "pdf_resolution", lambda u: sentinel)
    assert default.resolve_default("https://journal.example/download?id=42") is sentinel


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


def test_greaterwrong_markdown_keeps_comments_after_main():
    from capture.resolvers.lesswrong import greaterwrong_markdown

    # Pandoc drops content after a closing </main>; GreaterWrong puts the
    # comment thread there, so the wrapper must be demoted to survive.
    page = (
        '<main class="post"><div class="body-text post-body">'
        "<p>The post body.</p></div></main>"
        '<div id="comments"><div class="comment-body">'
        "<p>An insightful comment.</p></div></div>"
    )
    markdown = greaterwrong_markdown(page)
    assert markdown is not None
    assert "The post body." in markdown
    assert "An insightful comment." in markdown


def test_greaterwrong_markdown_absolutizes_relative_urls():
    from capture.resolvers.lesswrong import greaterwrong_markdown

    # Site-relative image src must become absolute so the pipeline localizes
    # it; protocol-relative // and already-absolute URLs are left untouched.
    page = (
        "<p><img src='/proxy-assets/ABC123' alt=\"chart\">"
        '<a href="/users/someone">someone</a></p>'
    )
    markdown = greaterwrong_markdown(page)
    assert markdown is not None
    assert "https://www.greaterwrong.com/proxy-assets/ABC123" in markdown
    assert "https://www.greaterwrong.com/users/someone" in markdown


def test_hackernews_item_url_forms():
    from capture.resolvers import hackernews_item

    assert (
        hackernews_item("https://news.ycombinator.com/item?id=40765183") == "40765183"
    )
    assert (
        hackernews_item("https://news.ycombinator.com/item?id=123&p=2#40000") == "123"
    )
    assert hackernews_item("https://news.ycombinator.com/newest") is None
    assert hackernews_item("https://example.com/item?id=5") is None


def test_hackernews_markdown_threads_comments():
    from capture.resolvers.hackernews import hackernews_markdown

    story = {
        "id": 1,
        "type": "story",
        "title": "A neat post",
        "url": "https://example.com/post",
        "author": "alice",
        "points": 42,
        "created_at_i": 1719100800,  # 2024-06-23
        "text": None,
        "children": [
            {
                "id": 2,
                "type": "comment",
                "author": "bob",
                "created_at_i": 1719104400,
                # HN bodies are escaped HTML: entities and <p>/<a> markup.
                "text": 'See <a href="https:&#x2F;&#x2F;x.test&#x2F;a" rel="nofollow">'
                "the link</a>.<p>Second para with 2 &gt; 1.",
                "children": [
                    {
                        "id": 3,
                        "type": "comment",
                        "author": "carol",
                        "created_at_i": 1719108000,
                        "text": "A reply.",
                        "children": [],
                    }
                ],
            },
            # Deleted comments carry null text but keep their place.
            {
                "id": 4,
                "type": "comment",
                "author": None,
                "created_at_i": 1719108000,
                "text": None,
                "children": [],
            },
        ],
    }
    markdown = hackernews_markdown(story)
    assert "# A neat post" in markdown
    assert "Discussion of <https://example.com/post>" in markdown
    assert "Submitted by alice on 2024-06-23 — 42 points" in markdown
    assert "## Comments (3)" in markdown
    # Top-level comment: one blockquote level, links and entities resolved.
    assert "> **bob** (2024-06-23)" in markdown
    assert "> See [the link](https://x.test/a)." in markdown
    assert "> Second para with 2 > 1." in markdown
    # Nested reply sits one level deeper.
    assert "> > **carol** (2024-06-23)" in markdown
    assert "> > A reply." in markdown
    # Deleted comment still rendered.
    assert "> **[deleted]**" in markdown
    assert "*[deleted]*" in markdown


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


def test_existing_capture_matches_frontmatter_url(tmp_path):
    import capture.pipeline as module

    folder = tmp_path / "data" / "example.com - 2025-01-01 - post"
    folder.mkdir(parents=True)
    (folder / "example.com - 2025-01-01 - post.md").write_text(
        '---\ntitle: "Post"\nurl: https://example.com/post/\n---\n'
    )
    assert (
        module.existing_capture("https://www.example.com/post", tmp_path / "data")
        == folder
    )
    assert (
        module.existing_capture("https://example.com/other", tmp_path / "data") is None
    )


def test_existing_capture_resolves_arxiv_forms(tmp_path):
    import capture.pipeline as module

    folder = tmp_path / "data" / "arxiv.org - 2026-03-23 - paper"
    folder.mkdir(parents=True)
    (folder / "arxiv.org - 2026-03-23 - paper.md").write_text(
        "---\nurl: https://arxiv.org/abs/2603.21852\n---\n"
    )
    assert (
        module.existing_capture("https://arxiv.org/pdf/2603.21852v2", tmp_path / "data")
        == folder
    )
