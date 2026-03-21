from __future__ import annotations

import json
import random
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from urllib.error import HTTPError, URLError

BOOKS_PATH = Path("app/domain/seed_data/polish_books_top100.json")
OUTPUT_PATH = Path("tmp/polish_books_isbn_candidates.json")
RESOLVED_PATH = Path("tmp/polish_books_top100_resolved.json")


def slugify(value: str) -> str:
    return " ".join("".join(char.lower() if char.isalnum() else " " for char in value).split())


def score_candidate(seed_title: str, seed_author: str, candidate: dict) -> int:
    score = 0
    title = slugify(candidate.get("title") or "")
    seed_title_slug = slugify(seed_title)
    author_names = [slugify(author) for author in candidate.get("authors", [])]
    seed_author_slug = slugify(seed_author)
    language = candidate.get("language")
    publisher = (candidate.get("publisher") or "").lower()

    if title == seed_title_slug:
        score += 100
    elif seed_title_slug in title:
        score += 30

    if any(seed_author_slug == author for author in author_names):
        score += 100
    elif any(seed_author_slug in author or author in seed_author_slug for author in author_names):
        score += 30

    if language == "pl" or (isinstance(language, list) and "pol" in language):
        score += 20

    if any(token in publisher for token in ["wolne lektury", "bellona", "znak", "czytelnik", "iskry", "literackie", "pwn", "helion", "ossolineum", "piw", "greg"]):
        score += 10

    if any(token in title for token in ["streszczenie", "opracowanie", "część v", "ktore nie spier", "ktore nie spieprzaj", "study guide", "summary"]):
        score -= 100

    return score


def pick_best_candidate(seed_title: str, seed_author: str, candidates: list[dict]) -> dict | None:
    if not candidates:
        return None
    ranked = sorted(
        candidates,
        key=lambda candidate: (score_candidate(seed_title, seed_author, candidate), candidate.get("publishedDate") or ""),
        reverse=True,
    )
    best = ranked[0]
    if score_candidate(seed_title, seed_author, best) < 80:
        return None
    return best


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "LibrariusSeedResolver/1.0 (+https://example.invalid)",
            "Accept": "application/json",
        },
    )
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.load(response)
        except HTTPError as exc:
            last_error = exc
            if exc.code not in {429, 500, 502, 503, 504}:
                raise
        except URLError as exc:
            last_error = exc
        time.sleep((1.5 ** attempt) + random.uniform(0.1, 0.4))

    if last_error is not None:
        raise last_error
    raise RuntimeError("Failed to fetch JSON response.")


def google_candidates(title: str, author: str) -> list[dict]:
    query = urllib.parse.quote(f'intitle:"{title}" inauthor:"{author}"')
    url = (
        "https://www.googleapis.com/books/v1/volumes"
        f"?q={query}&maxResults=5&printType=books"
    )
    payload = fetch_json(url)
    candidates: list[dict] = []
    for item in payload.get("items", []):
        info = item.get("volumeInfo", {})
        identifiers = {entry.get("type"): entry.get("identifier") for entry in info.get("industryIdentifiers", [])}
        isbn13 = identifiers.get("ISBN_13")
        if not isbn13:
            continue
        candidates.append(
            {
                "source": "google",
                "title": info.get("title"),
                "authors": info.get("authors", []),
                "isbn13": isbn13,
                "publishedDate": info.get("publishedDate"),
                "language": info.get("language"),
                "publisher": info.get("publisher"),
            }
        )
    return candidates


def openlibrary_candidates(title: str, author: str) -> list[dict]:
    query = urllib.parse.quote(f'title:{title} author:{author}')
    url = f"https://openlibrary.org/search.json?q={query}&limit=5"
    payload = fetch_json(url)
    candidates: list[dict] = []
    for doc in payload.get("docs", []):
        isbns = doc.get("isbn", [])
        isbn13 = next((value for value in isbns if len(value) == 13 and value.isdigit()), None)
        if not isbn13:
            continue
        candidates.append(
            {
                "source": "openlibrary",
                "title": doc.get("title"),
                "authors": doc.get("author_name", []),
                "isbn13": isbn13,
                "publishedDate": doc.get("first_publish_year"),
                "language": doc.get("language", []),
                "publisher": doc.get("publisher", [None])[0],
            }
        )
    return candidates


def main() -> None:
    books = json.loads(BOOKS_PATH.read_text(encoding="utf-8"))["books"]
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    start_index = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    end_index = int(sys.argv[2]) if len(sys.argv) > 2 else len(books)

    if OUTPUT_PATH.exists() and RESOLVED_PATH.exists() and start_index > 1:
        results = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        resolved_payload = json.loads(RESOLVED_PATH.read_text(encoding="utf-8"))
        resolved_books = resolved_payload.get("books", [])
        unresolved = resolved_payload.get("unresolved", [])
    else:
        results = [{"seed_title": book["title"], "seed_author": book["authors"][0], "google": [], "openlibrary": []} for book in books]
        resolved_books = [book | {"isbn": None, "publisher": None, "language": "pol"} for book in books]
        unresolved = []

    if len(results) < len(books):
        results.extend(
            {"seed_title": book["title"], "seed_author": book["authors"][0], "google": [], "openlibrary": []}
            for book in books[len(results):]
        )
    if len(resolved_books) < len(books):
        resolved_books.extend(
            book | {"isbn": None, "publisher": None, "language": "pol"}
            for book in books[len(resolved_books):]
        )

    for index, book in enumerate(books, start=1):
        if index < start_index or index > end_index:
            continue
        title = book["title"]
        author = book["authors"][0]
        print(f"[{index:03d}/{len(books)}] {title} | {author}")
        try:
            google = google_candidates(title, author)
            time.sleep(0.5)
            openlibrary = openlibrary_candidates(title, author)
            time.sleep(0.5)
        except Exception as exc:
            print(f"ERROR: {title} | {author} | {exc}")
            google = []
            openlibrary = []
        results[index - 1] = {
            "seed_title": title,
            "seed_author": author,
            "google": google,
            "openlibrary": openlibrary,
        }
        best_candidate = pick_best_candidate(title, author, google + openlibrary)
        if best_candidate is None:
            unresolved = [item for item in unresolved if not (item["title"] == title and item["author"] == author)]
            unresolved.append({"title": title, "author": author})
            resolved_books[index - 1] = book | {"isbn": None, "publisher": None, "language": "pol"}
        else:
            unresolved = [item for item in unresolved if not (item["title"] == title and item["author"] == author)]
            resolved_books[index - 1] = book | {
                "isbn": best_candidate["isbn13"],
                "publisher": best_candidate.get("publisher"),
                "language": "pol" if best_candidate.get("language") == "pl" else "pol",
            }
        OUTPUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        RESOLVED_PATH.write_text(
            json.dumps({"dataset": "top-100-famous-polish-books", "books": resolved_books, "unresolved": unresolved}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    OUTPUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    RESOLVED_PATH.write_text(
        json.dumps({"dataset": "top-100-famous-polish-books", "books": resolved_books, "unresolved": unresolved}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote candidates to {OUTPUT_PATH}")
    print(f"Wrote resolved data to {RESOLVED_PATH}")
    print(f"Unresolved: {len(unresolved)}")


if __name__ == "__main__":
    main()
