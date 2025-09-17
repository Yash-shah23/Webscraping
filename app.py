import streamlit as st
from firecrawl import Firecrawl
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
import json

# --- Page Config ---
st.set_page_config(
    page_title="Full Site Scraper for Model Training",
    page_icon="🌐",
    layout="centered"
)

# --- App State ---
if 'scrape_result' not in st.session_state:
    st.session_state.scrape_result = []

# --- Initialize Firecrawl ---
try:
    app = Firecrawl(api_key=st.secrets["FIRECRAWL_API_KEY"])
except (FileNotFoundError, KeyError):
    app = Firecrawl(api_key="fc-cc62b8b1db4741ed88d1546b516d55fb")

# --- Helper Functions ---
def clean_text(text):
    """Preprocess text for model training."""
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^a-zA-Z0-9.,!?;:()\-\'\"]+", " ", text)
    return text.strip().lower()

def scrape_page(url):
    """Scrape a single page using Firecrawl."""
    try:
        data = app.scrape(
            url=url,
            formats=["markdown"],
            only_main_content=True,
            timeout=120000
        )

        if hasattr(data, "dict"):
            data = data.dict()

        pages = []
        if isinstance(data, dict) and "pages" in data:
            for page in data["pages"]:
                content = page.get("markdown") or page.get("text") or ""
                pages.append({
                    "url": page.get("url"),
                    "content": clean_text(content)
                })
        else:
            content = data.get("markdown") if isinstance(data, dict) else str(data)
            pages.append({
                "url": url,
                "content": clean_text(content)
            })

        return pages
    except Exception as e:
        st.warning(f"Scraping error for {url}: {e}")
        return []

def crawl_site(start_url):
    """Automatically crawl all internal links from the site."""
    visited = set()
    to_visit = [start_url]
    domain = urlparse(start_url).netloc
    all_urls = []

    while to_visit:
        url = to_visit.pop(0)
        if url in visited:
            continue
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                continue
            visited.add(url)
            all_urls.append(url)

            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                link = urljoin(url, a['href'])
                if urlparse(link).netloc == domain and link not in visited:
                    to_visit.append(link)
        except:
            continue
    return all_urls

# --- Streamlit UI ---
st.title("🌐 Full Website Scraper for Model Training")
st.markdown("Automatically scrape all internal pages of a website, clean the text, and download a JSON corpus ready for NLP model training.")

# Input
site_url = st.text_input("Enter the website URL", placeholder="https://example.com")

# Action button
if st.button("Scrape & Prepare Corpus"):
    if not site_url:
        st.warning("Please enter a URL.")
    else:
        with st.spinner("Crawling website and scraping pages... This may take a few minutes."):
            all_urls = crawl_site(site_url)
            st.write(f"Found {len(all_urls)} pages to scrape.")

            all_pages = []
            for i, url in enumerate(all_urls, start=1):
                st.text(f"Scraping page {i}/{len(all_urls)}: {url}")
                pages = scrape_page(url)
                all_pages.extend(pages)

            if all_pages:
                st.session_state.scrape_result = all_pages
                # Prepare corpus without chunking
                corpus = [{"url": p["url"], "text": p["content"]} for p in all_pages]
                filename = "training_corpus.json"
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(corpus, f, indent=4, ensure_ascii=False)

                st.success(f"Scraped {len(all_pages)} pages and saved {filename} corpus!")
                st.download_button(
                    label="Download JSON Corpus",
                    data=json.dumps(corpus, indent=4, ensure_ascii=False),
                    file_name=filename,
                    mime="application/json"
                )
            else:
                st.error("No pages were scraped.")
