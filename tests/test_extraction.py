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


def test_transcript_from_json3_dedupes_and_joins():
    from capture.resolvers import transcript_from_json3

    text = (
        '{"events": ['
        '{"segs": [{"utf8": "Alright, so here "}, {"utf8": "we are"}]},'
        '{"segs": [{"utf8": "\\n"}]},'
        '{"segs": [{"utf8": "Alright, so here we are"}]},'
        '{"segs": [{"utf8": "in front of the elephants"}]}'
        "]}"
    )
    assert transcript_from_json3(text) == (
        "Alright, so here we are\nin front of the elephants"
    )


def test_existing_capture_resolves_youtube_forms(tmp_path, monkeypatch):
    import capture.pipeline as module

    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    folder = tmp_path / "data" / "youtube.com - 2005-04-23 - me-at-the-zoo"
    folder.mkdir(parents=True)
    (folder / "youtube.com - 2005-04-23 - me-at-the-zoo.md").write_text(
        "---\nurl: https://www.youtube.com/watch?v=jNQXAC9IVRw\n---\n"
    )
    assert module.existing_capture("https://youtu.be/jNQXAC9IVRw") == folder


def test_github_blob_markdown(monkeypatch):
    import capture.resolvers as module

    monkeypatch.setattr(module, "fetch_html", lambda u: "# CORDIC\n![d](img.png)")
    gh = module.github_markdown("https://github.com/o/r/blob/main/2024/5/10/cordic.md")
    assert gh is not None
    assert gh["publish"] == "2024-05-10"
    assert (
        "https://raw.githubusercontent.com/o/r/main/2024/5/10/img.png"
        in (gh["markdown"])
    )
    assert module.github_markdown("https://github.com/o/r/issues/5") is None


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
