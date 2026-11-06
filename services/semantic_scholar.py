import logging
import requests


def _reconstruct_abstract(inverted_index):
    """
    Reconstructs abstract text from OpenAlex's abstract_inverted_index dictionary format.
    Format: {"word": [pos1, pos2, ...], ...}
    """
    if not inverted_index or not isinstance(inverted_index, dict):
        return None

    index_word_map = {}
    for word, positions in inverted_index.items():
        if isinstance(positions, list):
            for pos in positions:
                index_word_map[pos] = word

    if not index_word_map:
        return None

    sorted_positions = sorted(index_word_map.keys())
    return " ".join(index_word_map[pos] for pos in sorted_positions)


def search_papers(topic, source_count=5):
    """
    Searches OpenAlex API for academic research papers matching a given topic.

    OpenAlex API endpoint:
    https://api.openalex.org/works

    Note: OpenAlex works without an API key. Including a polite pool mailto parameter
    ensures faster and more reliable requests.
    """
    url = "https://api.openalex.org/works"

    # Query parameters requested from OpenAlex API
    params = {
        "search": topic,
        "per_page": source_count,
        "mailto": "student@example.com"
    }

    papers = []

    try:
        # Send HTTP GET request with a 10-second timeout
        response = requests.get(url, params=params, timeout=10)

        # Debug logs immediately after API request
        logging.debug(f"[OPENALEX DEBUG] Request URL: {response.url}")
        logging.debug(f"[OPENALEX DEBUG] Status Code: {response.status_code}")
        logging.debug(f"[OPENALEX DEBUG] Response Text (first 500 chars): {response.text[:500]}")

        # HTTP Status 200 means successful API response
        if response.status_code == 200:
            data = response.json()
            raw_papers = data.get("results", [])

            for item in raw_papers:
                # Format authors list into a readable comma-separated string
                authorships = item.get("authorships", [])
                author_names = []
                for a in authorships:
                    if isinstance(a, dict):
                        author_obj = a.get("author", {})
                        if isinstance(author_obj, dict):
                            name = author_obj.get("display_name")
                            if name:
                                author_names.append(name)
                authors_str = ", ".join(author_names) if author_names else "Unknown Authors"

                # Reconstruct abstract from abstract_inverted_index
                abstract_text = _reconstruct_abstract(item.get("abstract_inverted_index"))

                # Format paper URL using doi or fallback to OpenAlex work ID
                raw_doi = item.get("doi")
                if raw_doi:
                    if raw_doi.startswith("https://doi.org/"):
                        paper_url = raw_doi
                    elif raw_doi.startswith("http://doi.org/"):
                        paper_url = "https://" + raw_doi[7:]
                    elif raw_doi.startswith("http://") or raw_doi.startswith("https://"):
                        paper_url = raw_doi
                    else:
                        paper_url = f"https://doi.org/{raw_doi.lstrip('/')}"
                else:
                    paper_url = item.get("id") or f"https://openalex.org/works"

                # Standardize paper data dictionary with default fallbacks
                paper_info = {
                    "title": item.get("title") or item.get("display_name") or "Untitled Paper",
                    "authors": authors_str,
                    "abstract": abstract_text or "No abstract available for this paper.",
                    "url": paper_url,
                    "year": item.get("publication_year") or 2024
                }
                papers.append(paper_info)

            logging.debug(f"[OPENALEX] Retrieved {len(papers)} paper(s) for topic: '{topic}'")
        else:
            logging.error(f"[OPENALEX ERROR] HTTP {response.status_code}: {response.text}")

    except Exception as e:
        # Gracefully handle network errors, timeouts, or JSON decoding failures
        logging.error(f"[OPENALEX EXCEPTION] Failed to search papers: {str(e)}", exc_info=True)

    return papers

