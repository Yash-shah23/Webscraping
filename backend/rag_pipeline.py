import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_community.llms import Ollama
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import SupabaseVectorStore
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate
from langchain.docstore.document import Document
from supabase.client import Client

class RAGPipeline:
    def __init__(self):
        model_name = "all-MiniLM-L6-v2"
        model_kwargs = {'device': 'cpu'}
        encode_kwargs = {'normalize_embeddings': False}
        self.embedding_model = HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs=model_kwargs,
            encode_kwargs=encode_kwargs
        )

        # CRITICAL: Switched to a smaller, faster model to meet the 10-sec target.
        self.llm = Ollama(model="gemma2:2b")
        print("RAG Pipeline instance initialized with fast CPU embeddings and 'gemma2:2b' model.")


    def _fetch_and_parse(self, url: str, domain_name: str):
        """Fetches a single URL, parses it, and returns content and new links."""
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            response = requests.get(url, timeout=5, headers=headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            page_title = soup.title.string.strip() if soup.title else "Untitled"
            
            if soup.body:
                page_content = "\n".join(line.strip() for line in soup.body.get_text(separator='\n', strip=True).splitlines() if len(line.split()) > 3)
            else:
                return None, []

            links = set()
            for link_tag in soup.find_all('a', href=True):
                absolute_url = urljoin(url, link_tag['href']).split('#')[0]
                if urlparse(absolute_url).netloc == domain_name:
                    links.add(absolute_url)
            
            return {"source_url": url, "title": page_title, "content": page_content}, list(links)
        except requests.RequestException:
            return None, []

    def scrape_concurrently(self, start_url: str, max_pages: int = 20):
        """
        Scrapes a site concurrently using a thread pool for maximum speed.
        It scrapes the landing page, then all unique links found on it.
        """
        print(f"Starting concurrent scrape for {start_url}...")
        domain_name = urlparse(start_url).netloc
        
        # First, scrape the entry point to get the initial set of links
        initial_data, initial_links = self._fetch_and_parse(start_url, domain_name)
        if not initial_data:
            return []

        all_page_data = [initial_data]
        urls_to_scrape = [link for link in initial_links if link != start_url]
        visited_urls = {start_url}

        # Use a thread pool to fetch all other pages concurrently
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_url = {executor.submit(self._fetch_and_parse, url, domain_name): url for url in urls_to_scrape[:max_pages-1]}
            
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                if url in visited_urls:
                    continue
                
                page_data, _ = future.result()
                if page_data:
                    all_page_data.append(page_data)
                visited_urls.add(url)
                print(f"  -> Finished scraping page: {url}")
        
        print(f"Concurrent scrape finished. Total pages scraped: {len(all_page_data)}")
        return all_page_data

    def create_and_store_embeddings(self, session_id: str, page_data: list, supabase_client: Client):
        if not page_data: return
        for p in page_data: p['session_id'] = session_id
            
        documents = [
            Document(page_content=p.get("content", ""), metadata={"source": p.get("source_url", ""), "title": p.get("title", ""), "session_id": p.get("session_id")})
            for p in page_data
        ]
        split_docs = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200).split_documents(documents)
        
        print(f"Storing {len(split_docs)} document chunks in Supabase...")
        SupabaseVectorStore.from_documents(
            documents=split_docs, embedding=self.embedding_model, client=supabase_client,
            table_name="documents", query_name="match_documents"
        )
        print("Embeddings stored successfully.")

    def answer_question(self, session_id: str, question: str, supabase_client: Client):
        vector_store = SupabaseVectorStore(
            client=supabase_client, embedding=self.embedding_model,
            table_name="documents", query_name="match_documents"
        )

        # OPTIMIZATION: Retrieve fewer documents (k=3) to create a smaller prompt for the LLM.
        retriever = vector_store.as_retriever(
            search_kwargs={'k': 3, 'filter': {'session_id': session_id}}
        )

        system_prompt = (
            "You are an assistant for question-answering tasks. Use the following pieces of retrieved context to answer the question. "
            "If you don't know the answer, just say that you don't know. Use three sentences maximum and keep the answer concise.\n\n"
            "{context}"
        )
        prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", "{input}")])
        
        question_answer_chain = create_stuff_documents_chain(self.llm, prompt)
        rag_chain = create_retrieval_chain(retriever, question_answer_chain)
        
        response = rag_chain.invoke({"input": question})
        return response.get("answer", "No answer could be generated.")