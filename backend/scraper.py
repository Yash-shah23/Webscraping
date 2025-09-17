import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from dotenv import load_dotenv
from firecrawl import Firecrawl

load_dotenv()

def crawl_and_get_content(start_url: str):
    """
    Crawls an entire site using a hybrid approach:
    - BeautifulSoup for fast link discovery.
    - Firecrawl for high-quality content scraping of each discovered page.
    """
    try:
        # Initialize Firecrawl once
        firecrawl_app = Firecrawl(api_key=os.getenv("FIRECRAWL_API_KEY"))

        domain_name = urlparse(start_url).netloc
        if not domain_name:
            raise ValueError("Invalid start URL provided.")

        to_visit = [start_url]
        visited_urls = set()
        all_pages_content = []
        
        title = "Untitled"
        is_first_page = True

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        print(f"Starting hybrid crawl for domain: {domain_name}")

        while to_visit:
            current_url = to_visit.pop(0)
            if current_url in visited_urls:
                continue
            
            print(f"Processing: {current_url}")
            visited_urls.add(current_url)

            # --- Part 1: Find all links on the page (using BeautifulSoup) ---
            try:
                response = requests.get(current_url, headers=headers, timeout=10)
                response.raise_for_status() # Raise an exception for bad status codes
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                for a_tag in soup.find_all("a", href=True):
                    href = a_tag['href']
                    # Create an absolute URL from a relative one
                    full_url = urljoin(current_url, href)
                    # Clean URL by removing fragments
                    full_url = urlparse(full_url)._replace(fragment="").geturl()

                    # Check if the link is internal and not visited yet
                    if urlparse(full_url).netloc == domain_name and full_url not in visited_urls:
                        to_visit.append(full_url)
            
            except requests.RequestException as e:
                print(f"  - Could not fetch {current_url} for link discovery: {e}")
                # Continue to the next URL in the queue
                continue

            # --- Part 2: Scrape the clean content of THIS page (using Firecrawl) ---
            try:
                scraped_data = firecrawl_app.scrape(url=current_url, timeout=30000)
                
                if scraped_data and scraped_data.markdown:
                    all_pages_content.append(scraped_data.markdown)

                    # If this is the first page, grab the title
                    if is_first_page:
                        if scraped_data.metadata and scraped_data.metadata.title:
                            title = scraped_data.metadata.title
                        else: # Fallback title from domain
                            parsed_url = urlparse(start_url)
                            domain = parsed_url.netloc.replace("www.", "")
                            title = domain.split('.')[0].capitalize()
                        is_first_page = False
                        
            except Exception as e:
                print(f"  - Firecrawl failed to scrape {current_url}: {e}")
        
        if not all_pages_content:
            raise ValueError("Crawl completed, but no content was scraped from any page.")
            
        # Combine content from all pages into a single document
        full_content = "\n\n--- End of Page ---\n\n".join(all_pages_content)
        return full_content, title

    except Exception as e:
        print(f"An error occurred during the hybrid crawl: {e}")
        raise