import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
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
        self.chromedriver_path = chromedriver_path
        self.embedding_model = OllamaEmbeddings(model="nomic-embed-text")
        self.llm = Ollama(model="gemma3:latest")
        self.vector_store = None
        self.rag_chain = None
        self.is_ready = False
        print("RAG Pipeline instance initialized.")

    def _setup_driver(self):
        chrome_options = Options(); chrome_options.add_argument("--headless"); chrome_options.add_argument("--log-level=3")
        service = Service(executable_path=self.chromedriver_path)
        return webdriver.Chrome(service=service, options=chrome_options)

    def scrape_url(self, start_url: str):
        """Scrapes a site and returns the raw content."""
        driver = self._setup_driver()
        domain_name = urlparse(start_url).netloc
        urls_to_scrape = [start_url]; visited_urls = set(); all_page_data = []
        while urls_to_scrape:
            current_url = urls_to_scrape.pop(0)
            if current_url in visited_urls: continue
            print(f"  -> Scraping page: {current_url}")
            visited_urls.add(current_url)
            try:
                driver.get(current_url); time.sleep(2)
                soup = BeautifulSoup(driver.page_source, 'html.parser')
            except Exception as e:
                print(f"   ! Could not fetch {current_url}: {e}"); continue
            page_title = soup.title.string.strip() if soup.title else "Untitled"
            if soup.body:
                page_content = "\n".join(line.strip() for line in soup.body.get_text(separator='\n', strip=True).splitlines() if len(line.split()) > 3)
            else: page_content = ""
            if page_content:
                all_page_data.append({"source_url": current_url, "title": page_title, "content": page_content})
            for link_tag in soup.find_all('a', href=True):
                absolute_url = urljoin(current_url, link_tag['href']).split('#')[0]
                if (urlparse(absolute_url).netloc == domain_name and absolute_url not in visited_urls and absolute_url not in urls_to_scrape):
                    urls_to_scrape.append(absolute_url)
        driver.quit()
        return all_page_data

    def build_index_from_data(self, page_data: list):
        """Builds the in-memory FAISS index from scraped content."""
        if not page_data: return
        documents = [Document(page_content=p.get("content", ""), metadata={"source": p.get("source_url", ""), "title": p.get("title", "")}) for p in page_data]
        split_docs = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200).split_documents(documents)
        
        print(f"Creating in-memory vector store with {len(split_docs)} chunks...")
        self.vector_store = FAISS.from_documents(split_docs, self.embedding_model)
        
        system_prompt = ("You are an assistant for question-answering tasks. Use the following pieces of retrieved context to answer the question. "
                         "If you don't know the answer, just say that you don't know. Use three sentences maximum and keep the answer concise.\n\n"
                         "{context}")
        prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", "{input}")])
        question_answer_chain = create_stuff_documents_chain(self.llm, prompt)
        retriever = self.vector_store.as_retriever()
        self.rag_chain = create_retrieval_chain(retriever, question_answer_chain)
        self.is_ready = True
        print("Pipeline is ready with in-memory index.")

    def query(self, question: str):
        if not self.is_ready: return "Pipeline not ready."
        response = self.rag_chain.invoke({"input": question})
        return response.get("answer", "No answer could be generated.")
