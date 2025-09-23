
import os
import json
import time
import faiss
import numpy as np
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

# --- LANGCHAIN IMPORTS ---
from langchain_community.llms import Ollama
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate
from langchain.docstore.document import Document

class RAGPipeline:
    def __init__(self, chromedriver_path: str):
        print("Initializing RAG Pipeline with separate models...")
        self.chromedriver_path = chromedriver_path
        
        # --- THE FIX: USE TWO DIFFERENT MODELS ---
        # 1. Use a dedicated model for creating embeddings.
        print("Loading embedding model: nomic-embed-text")
        self.embedding_model = OllamaEmbeddings(model="nomic-embed-text")
        
        # 2. Use a powerful model for generating answers.
        print("Loading generation model: gemma3:latest")
        self.llm = Ollama(model="gemma3:latest")
        
        system_prompt = (
            "You are an assistant for question-answering tasks. Use the following pieces of retrieved context to answer the question. "
            "If you don't know the answer, just say that you don't know. Use three sentences maximum and keep the answer concise.\n\n"
            "{context}"
        )
        prompt = ChatPromptTemplate.from_messages(
            [("system", system_prompt), ("human", "{input}")]
        )
        
        self.rag_chain = None
        self.question_answer_chain = create_stuff_documents_chain(self.llm, prompt)
        self.vector_store = None
        self.is_ready = False
        print("RAG Pipeline initialized successfully.")

    def _get_data_path(self, url: str):
        domain_name = urlparse(url).netloc
        safe_domain_name = "".join(c for c in domain_name if c.isalnum() or c in ('-', '.'))
        data_dir = os.path.join("scraped_data", safe_domain_name)
        return os.path.join(data_dir, "content.json")

    def _setup_driver(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--log-level=3")
        service = Service(executable_path=self.chromedriver_path)
        return webdriver.Chrome(service=service, options=chrome_options)

    def _scrape_site_with_selenium(self, start_url: str):
        driver = self._setup_driver()
        domain_name = urlparse(start_url).netloc
        urls_to_scrape = [start_url]
        visited_urls = set()
        all_page_data = []

        while urls_to_scrape:
            current_url = urls_to_scrape.pop(0)
            if current_url in visited_urls: continue
            print(f"  -> Scraping page: {current_url}")
            visited_urls.add(current_url)

            try:
                driver.get(current_url)
                time.sleep(2)
                page_source = driver.page_source
                soup = BeautifulSoup(page_source, 'html.parser')
            except Exception as e:
                print(f"   ! Could not fetch {current_url} with Selenium: {e}")
                continue

            page_title = soup.title.string.strip() if soup.title else "No Title Found"
            if soup.body:
                raw_text = soup.body.get_text(separator='\n', strip=True)
                lines = (line.strip() for line in raw_text.splitlines())
                page_content = "\n".join(line for line in lines if len(line.split()) > 3)
            else:
                page_content = ""
            if page_content:
                all_page_data.append({
                    "source_url": current_url, "title": page_title, "content": page_content
                })

            for link_tag in soup.find_all('a', href=True):
                href = link_tag['href']
                absolute_url = urljoin(current_url, href).split('#')[0]
                if (urlparse(absolute_url).netloc == domain_name and 
                    absolute_url not in visited_urls and 
                    absolute_url not in urls_to_scrape):
                    urls_to_scrape.append(absolute_url)
        
        driver.quit()
        return all_page_data

    def load_url(self, start_url: str):
        data_path = self._get_data_path(start_url)
        
        if os.path.exists(data_path):
            print(f"✅ Cache hit! Loading data from {data_path}")
            with open(data_path, 'r', encoding='utf-8') as f:
                page_data = json.load(f)
        else:
            print(f"❌ Cache miss! Starting new Selenium crawl for {start_url}")
            page_data = self._scrape_site_with_selenium(start_url)
            if not page_data: self.is_ready = False; return False
            print(f"💾 Saving scraped data to {data_path}")
            os.makedirs(os.path.dirname(data_path), exist_ok=True)
            with open(data_path, 'w', encoding='utf-8') as f:
                json.dump(page_data, f, indent=2, ensure_ascii=False)

        documents = []
        for page in page_data:
            doc = Document(page_content=page.get("content", ""), metadata={"source": page.get("source_url", ""), "title": page.get("title", "")})
            documents.append(doc)

        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        split_docs = text_splitter.split_documents(documents)
        
        print(f"Creating vector store with {len(split_docs)} chunks...")
        self.vector_store = FAISS.from_documents(split_docs, self.embedding_model)
        
        retriever = self.vector_store.as_retriever()
        self.rag_chain = create_retrieval_chain(retriever, self.question_answer_chain)
        
        self.is_ready = True
        print(f"✅ Pipeline is ready. Indexed {len(split_docs)} chunks from {len(page_data)} pages.")
        return True

    def query(self, question: str) -> str:
        if not self.is_ready: 
            return "Pipeline not ready. Please load a URL."
        
        print(f"Invoking RAG chain for question: {question}")
        response = self.rag_chain.invoke({"input": question})
        
        return response.get("answer", "No answer could be generated.")