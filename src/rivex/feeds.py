from __future__ import annotations

from datetime import datetime
from typing import Any

# ---------------------------------------------------------------------------
# Try Rust-backed implementations from rivex_core
# ---------------------------------------------------------------------------

try:
    from rivex_core import PySitemap as _RustSitemap
    from rivex_core import PySitemapIndex as _RustSitemapIndex
    from rivex_core import PyRssFeed as _RustRssFeed
    from rivex_core import PyAtomFeed as _RustAtomFeed

    _HAS_RUST = True
except ImportError:
    _HAS_RUST = False


class Sitemap:
    """Generates a Sitemap XML document.

    Delegates to Rust ``PySitemap`` when available.
    """

    def __init__(self):
        if _HAS_RUST:
            self._rust = _RustSitemap()
        else:
            self._rust = None
        self._urls: list[dict] = []

    def add_url(
        self,
        loc: str,
        lastmod: str | None = None,
        changefreq: str | None = None,
        priority: float | None = None,
        images: list[str] | None = None,
    ) -> None:
        if self._rust:
            prio_str = f"{priority:.1f}" if priority is not None else None
            self._rust.add_url(loc, lastmod, changefreq, prio_str, images)
            return
        entry: dict = {"loc": loc}
        if lastmod:
            entry["lastmod"] = lastmod
        if changefreq:
            entry["changefreq"] = changefreq
        if priority is not None:
            entry["priority"] = f"{priority:.1f}"
        if images:
            entry["images"] = images
        self._urls.append(entry)

    def render(self) -> str:
        if self._rust:
            return self._rust.render()
        from xml.sax.saxutils import escape

        parts = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
            ' xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">',
        ]
        for url in self._urls:
            parts.append("  <url>")
            parts.append(f"    <loc>{escape(url['loc'])}</loc>")
            if "lastmod" in url:
                parts.append(f"    <lastmod>{url['lastmod']}</lastmod>")
            if "changefreq" in url:
                parts.append(f"    <changefreq>{url['changefreq']}</changefreq>")
            if "priority" in url:
                parts.append(f"    <priority>{url['priority']}</priority>")
            for img in url.get("images", []):
                parts.append(f'    <image:image><image:loc>{escape(img)}</image:loc></image:image>')
            parts.append("  </url>")
        parts.append("</urlset>")
        return "\n".join(parts)

    def __len__(self) -> int:
        return len(self._urls)


class SitemapIndex:
    """Generates a Sitemap index XML document (>50k URLs).

    Delegates to Rust ``PySitemapIndex`` when available.
    """

    def __init__(self):
        if _HAS_RUST:
            self._rust = _RustSitemapIndex()
        else:
            self._rust = None
        self._sitemaps: list[dict] = []

    def add_sitemap(self, loc: str, lastmod: str | None = None) -> None:
        if self._rust:
            self._rust.add_sitemap(loc, lastmod)
            return
        entry: dict = {"loc": loc}
        if lastmod:
            entry["lastmod"] = lastmod
        self._sitemaps.append(entry)

    def render(self) -> str:
        if self._rust:
            return self._rust.render()
        from xml.sax.saxutils import escape

        parts = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        ]
        for sm in self._sitemaps:
            parts.append("  <sitemap>")
            parts.append(f"    <loc>{escape(sm['loc'])}</loc>")
            if "lastmod" in sm:
                parts.append(f"    <lastmod>{sm['lastmod']}</lastmod>")
            parts.append("  </sitemap>")
        parts.append("</sitemapindex>")
        return "\n".join(parts)


class RssFeed:
    """Generates an RSS 2.0 feed.

    Delegates to Rust ``PyRssFeed`` when available.
    """

    def __init__(self, title: str, link: str, description: str = "", language: str = "en-us"):
        if _HAS_RUST:
            self._rust = _RustRssFeed(title, link, description, language)
        else:
            self._rust = None
        self._channel = {
            "title": title,
            "link": link,
            "description": description,
            "language": language,
        }
        self._items: list[dict] = []

    def add_item(
        self,
        title: str,
        link: str,
        description: str = "",
        pub_date: str | None = None,
        author: str | None = None,
        guid: str | None = None,
        category: str | None = None,
    ) -> None:
        if self._rust:
            self._rust.add_item(title, link, description, pub_date, author, guid, category)
            return
        item: dict = {"title": title, "link": link, "description": description}
        if pub_date:
            item["pubDate"] = self._format_date(pub_date)
        if author:
            item["author"] = author
        if guid:
            item["guid"] = guid
        if category:
            item["category"] = category
        self._items.append(item)

    def _format_date(self, date_str: str) -> str:
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return dt.strftime("%a, %d %b %Y %H:%M:%S %z")
        except Exception:
            return date_str

    def render(self) -> str:
        if self._rust:
            return self._rust.render()
        from xml.sax.saxutils import escape

        parts = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<rss version="2.0">',
            "  <channel>",
            f"    <title>{escape(self._channel['title'])}</title>",
            f"    <link>{escape(self._channel['link'])}</link>",
            f"    <description>{escape(self._channel['description'])}</description>",
            f"    <language>{self._channel['language']}</language>",
        ]
        for item in self._items:
            parts.append("    <item>")
            parts.append(f"      <title>{escape(item['title'])}</title>")
            parts.append(f"      <link>{escape(item['link'])}</link>")
            parts.append(f"      <description>{escape(item['description'])}</description>")
            if "pubDate" in item:
                parts.append(f"      <pubDate>{item['pubDate']}</pubDate>")
            if "author" in item:
                parts.append(f"      <author>{escape(item['author'])}</author>")
            if "guid" in item:
                parts.append(f"      <guid>{escape(item['guid'])}</guid>")
            if "category" in item:
                parts.append(f"      <category>{escape(item['category'])}</category>")
            parts.append("    </item>")
        parts.append("  </channel>")
        parts.append("</rss>")
        return "\n".join(parts)


class AtomFeed:
    """Generates an Atom feed.

    Delegates to Rust ``PyAtomFeed`` when available.
    """

    def __init__(self, title: str, link: str, feed_id: str = "", subtitle: str = ""):
        if _HAS_RUST:
            self._rust = _RustAtomFeed(title, link, feed_id, subtitle)
        else:
            self._rust = None
        self._feed = {
            "title": title,
            "link": link,
            "id": feed_id or f"urn:uuid:{__import__('uuid').uuid4()}",
            "subtitle": subtitle,
            "updated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        self._entries: list[dict] = []

    def add_item(
        self,
        title: str,
        link: str,
        summary: str = "",
        updated: str | None = None,
        published: str | None = None,
        author_name: str | None = None,
        author_email: str | None = None,
        category: str | None = None,
    ) -> None:
        if self._rust:
            updated_str = updated or datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
            self._rust.add_entry(title, link, summary, updated_str, published, author_name, author_email, category)
            return
        entry: dict = {"title": title, "link": link, "summary": summary}
        entry["id"] = link
        entry["updated"] = updated or datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        if published:
            entry["published"] = published
        if author_name or author_email:
            entry["author"] = {}
            if author_name:
                entry["author"]["name"] = author_name
            if author_email:
                entry["author"]["email"] = author_email
        if category:
            entry["category"] = category
        self._entries.append(entry)

    def render(self) -> str:
        if self._rust:
            return self._rust.render()
        from xml.sax.saxutils import escape

        parts = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<feed xmlns="http://www.w3.org/2005/Atom">',
            f"  <title>{escape(self._feed['title'])}</title>",
            f"  <link href=\"{escape(self._feed['link'])}\"/>",
            f"  <id>{escape(self._feed['id'])}</id>",
            f"  <updated>{self._feed['updated']}</updated>",
        ]
        if self._feed.get("subtitle"):
            parts.append(f"  <subtitle>{escape(self._feed['subtitle'])}</subtitle>")
        for entry in self._entries:
            parts.append("  <entry>")
            parts.append(f"    <title>{escape(entry['title'])}</title>")
            parts.append(f"    <link href=\"{escape(entry['link'])}\"/>")
            parts.append(f"    <id>{escape(entry['id'])}</id>")
            parts.append(f"    <updated>{entry['updated']}</updated>")
            if "published" in entry:
                parts.append(f"    <published>{entry['published']}</published>")
            if "summary" in entry:
                parts.append(f"    <summary>{escape(entry['summary'])}</summary>")
            if "author" in entry:
                parts.append(f"    <author>")
                if "name" in entry["author"]:
                    parts.append(f"      <name>{escape(entry['author']['name'])}</name>")
                if "email" in entry["author"]:
                    parts.append(f"      <email>{escape(entry['author']['email'])}</email>")
                parts.append(f"    </author>")
            if "category" in entry:
                parts.append(f"    <category term=\"{escape(entry['category'])}\"/>")
            parts.append("  </entry>")
        parts.append("</feed>")
        return "\n".join(parts)
