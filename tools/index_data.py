import json
import time
import traceback
import hashlib
import re
from pathlib import Path
import os
from elasticsearch import Elasticsearch, helpers
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

ELASTICSEARCH_CONFIG = {
    "url": os.getenv("ELASTICSEARCH_URL"),
    "api_key": os.getenv("ELASTICSEARCH_API_KEY"),
    "index_name": os.getenv("ELASTICSEARCH_INDEX_NAME")
}

OPENAI_CONFIG = {
    "api_key": os.getenv("OPENAI_API_KEY"),
    "model": os.getenv("OPENAI_EMBEDDING_MODEL")
}

class ChunkIndexer:
    def __init__(self, es_config, openai_config):
        self.es_client = Elasticsearch(
            es_config["url"],
            api_key=es_config["api_key"],
            request_timeout=60,
            max_retries=3,
            retry_on_timeout=True
        )
        self.index_name = es_config["index_name"]
        
        self.openai_client = OpenAI(api_key=openai_config["api_key"])
        self.embedding_model = openai_config["model"]
        
        if "text-embedding-3-small" in self.embedding_model:
            self.embedding_dim = 1536
        elif "text-embedding-3-large" in self.embedding_model:
            self.embedding_dim = 3072
        elif "text-embedding-ada-002" in self.embedding_model:
            self.embedding_dim = 1536
        else:
            self.embedding_dim = 1536
        
        print(f"Using OpenAI embedding model: {self.embedding_model}")
        print(f"Embedding dimension: {self.embedding_dim}")
        
        try:
            info = self.es_client.info()
            print(f"Connected to Elasticsearch: {info['name']}")
        except Exception as e:
            print(f"Failed to connect to Elasticsearch: {e}")
            raise
    
    def create_index_if_not_exists(self):
        if self.es_client.indices.exists(index=self.index_name):
            print(f"Index '{self.index_name}' already exists. Using existing index.")
            return
        
        mapping = {
            "mappings": {
                "properties": {
                    "content": {
                        "type": "text",
                        "analyzer": "standard"
                    },
                    "content_embedding": {
                        "type": "dense_vector",
                        "dims": self.embedding_dim,
                        "index": True,
                        "similarity": "cosine"
                    },
                    "document_title": {
                        "type": "text",
                        "analyzer": "standard"
                    },
                    "source": {
                        "type": "keyword"
                    },
                    "page_number": {
                        "type": "integer"
                    },
                    "chunk_seq_id": {
                        "type": "integer"
                    },
                    "chunk_id": {
                        "type": "keyword"
                    },
                    "filename": {
                        "type": "keyword"
                    },
                    "file_path": {
                        "type": "keyword"
                    },
                    "file_hash": {
                        "type": "keyword"
                    },
                    "created_at": {
                        "type": "date"
                    }
                }
            }
        }
        
        try:
            self.es_client.indices.create(index=self.index_name, body=mapping)
            print(f"Created new index: {self.index_name}")
        except Exception as e:
            print(f"Error creating index: {e}")
            raise
    
    def generate_openai_embeddings(self, texts, batch_size=100):
        try:
            all_embeddings = []
            
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                
                response = self.openai_client.embeddings.create(
                    input=batch,
                    model=self.embedding_model
                )
                
                batch_embeddings = [data.embedding for data in response.data]
                all_embeddings.extend(batch_embeddings)
                
                print(f"Generated embeddings for batch {i//batch_size + 1}/{(len(texts)-1)//batch_size + 1}")
                
                if i + batch_size < len(texts):
                    time.sleep(0.1)
            
            return all_embeddings
            
        except Exception as e:
            print(f"Error generating OpenAI embeddings: {e}")
            traceback.print_exc()
            return None
    
    def extract_page_number(self, source):
        match = re.search(r'page_(\d+)', source)
        return int(match.group(1)) if match else 0
    
    def extract_document_title(self, chunks):
        if chunks and len(chunks) > 0:
            first_chunk_text = chunks[0].get('text', '').strip()
            if len(first_chunk_text) < 200 and '\n' not in first_chunk_text[:100]:
                return first_chunk_text
        return "Untitled Document"
    
    def generate_file_hash(self, file_path, chunks):
        content_for_hash = file_path + str(len(chunks))
        if chunks:
            content_for_hash += chunks[0].get('text', '')[:100]
        return hashlib.md5(content_for_hash.encode()).hexdigest()
    
    def load_chunks_from_json(self, json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                chunks_data = json.load(f)
            
            if not isinstance(chunks_data, list):
                print(f"Expected list of chunks, got {type(chunks_data)}")
                return None
            
            print(f"Loaded {len(chunks_data)} chunks from {json_path}")
            return chunks_data
            
        except Exception as e:
            print(f"Error loading chunks from JSON: {e}")
            traceback.print_exc()
            return None
    
    def index_document_chunks(self, chunks_data, json_path):
        try:
            if not chunks_data or not isinstance(chunks_data, list):
                print("Invalid chunks data")
                return False
            
            file_path = str(json_path)
            filename = Path(json_path).name
            file_hash = self.generate_file_hash(file_path, chunks_data)
            document_title = self.extract_document_title(chunks_data)
            
            texts = []
            valid_chunks = []
            
            for chunk in chunks_data:
                if 'text' in chunk and chunk['text'].strip():
                    texts.append(chunk['text'])
                    valid_chunks.append(chunk)
            
            if not texts:
                print(f"No valid text content found in chunks")
                return False
            
            print(f"Prepared {len(texts)} text chunks for embedding")
            print(f"Document title: {document_title}")
            
            print(f"Generating OpenAI embeddings for {len(texts)} chunks...")
            embeddings = self.generate_openai_embeddings(texts)
            
            if not embeddings:
                print(f"Failed to generate embeddings")
                return False
            
            print(f"Generated {len(embeddings)} embeddings")
            
            actions = []
            current_time = int(time.time() * 1000)
            
            for i, (chunk, embedding) in enumerate(zip(valid_chunks, embeddings)):
                chunk_id = chunk.get('chunkId', f"{file_hash}_chunk_{i}")
                
                page_number = self.extract_page_number(chunk.get('Source', ''))
                
                doc = {
                    "content": chunk['text'],
                    "content_embedding": embedding,
                    "document_title": document_title,
                    "source": chunk.get('Source', ''),
                    "page_number": page_number,
                    "chunk_seq_id": chunk.get('chunkSeqId', i),
                    "chunk_id": chunk_id,
                    "filename": filename,
                    "file_path": file_path,
                    "file_hash": file_hash,
                    "created_at": current_time
                }
                
                action = {
                    "_index": self.index_name,
                    "_id": chunk_id,
                    "_source": doc
                }
                actions.append(action)
            
            print(f"Indexing {len(actions)} chunks to Elasticsearch...")
            
            es_client_with_options = self.es_client.options(request_timeout=300)
            response = helpers.bulk(
                es_client_with_options,
                actions,
                chunk_size=100
            )
            
            print(f"Successfully indexed {len(actions)} chunks")
            return True
            
        except Exception as e:
            print(f"Error during document indexing: {e}")
            traceback.print_exc()
            return False
    
    def process_json_file(self, json_path):
        json_path = Path(json_path)
        
        if not json_path.exists():
            print(f"JSON file not found: {json_path}")
            return False
        
        print(f"Processing JSON file: {json_path.name}")
        
        chunks_data = self.load_chunks_from_json(json_path)
        
        if not chunks_data:
            print(f"Failed to load chunks from: {json_path}")
            return False
        
        if self.index_document_chunks(chunks_data, json_path):
            print(f"Successfully indexed chunks from: {json_path.name}")
            return True
        else:
            print(f"Failed to index chunks from: {json_path.name}")
            return False
    
    def process_json_directory(self, json_directory):
        json_dir = Path(json_directory)
        
        if not json_dir.exists():
            print(f"JSON directory not found: {json_dir}")
            return
        
        json_files = list(json_dir.glob("*.json"))
        
        if not json_files:
            print(f"No JSON files found in: {json_dir}")
            return
        
        print(f"Found {len(json_files)} JSON files to process")
        
        successful = 0
        failed = 0
        
        for json_file in json_files:
            print(f"\n{'='*50}")
            print(f"Processing: {json_file.name}")
            print(f"{'='*50}")
            
            if self.process_json_file(json_file):
                successful += 1
            else:
                failed += 1
        
        print(f"\n{'='*50}")
        print(f"Processing complete:")
        print(f"Successfully indexed: {successful} files")
        print(f"Failed to index: {failed} files")
        print(f"{'='*50}")

def main():
    try:
        print("Starting Chunk Indexer with Elasticsearch and OpenAI...")
        
        required_vars = [
            "ELASTICSEARCH_URL", "ELASTICSEARCH_API_KEY", "ELASTICSEARCH_INDEX_NAME",
            "OPENAI_API_KEY", "OPENAI_EMBEDDING_MODEL"
        ]
        
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            print(f"Missing required environment variables: {missing_vars}")
            return
        
        indexer = ChunkIndexer(ELASTICSEARCH_CONFIG, OPENAI_CONFIG)
        
        indexer.create_index_if_not_exists()
        
        json_directory = "data/json"
        indexer.process_json_directory(json_directory)
        
    except Exception as e:
        print(f"Error in main process: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    json_dir = Path("data/json")
    json_dir.mkdir(parents=True, exist_ok=True)
    
    if not list(json_dir.glob("*.json")):
        print(f"No JSON files found in {json_dir}")
        print("Please run your PDF processing script first to generate JSON files")
    else:
        main()