import os
from llama_index.core import (
    VectorStoreIndex,
    SimpleDirectoryReader,
    StorageContext,
    load_index_from_storage,
    Settings
)
from llama_index.vector_stores.faiss import FaissVectorStore
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.openai import OpenAIEmbedding
import faiss
from telecom_assistant.config.config import Config

# Configure global settings
Settings.llm = OpenAI(model=Config.OPENAI_MODEL_NAME, temperature=0)
Settings.embed_model = OpenAIEmbedding()

def load_documents(persist_dir: str = "data/storage"):
    """
    Load documents from the data directory and create/load a FAISS index.
    
    Args:
        persist_dir (str): Directory to persist the index.
        
    Returns:
        VectorStoreIndex: The loaded or created vector index.
    """
    # Ensure persist directory is absolute
    if not os.path.isabs(persist_dir):
        persist_dir = str(Config.PROJECT_ROOT / persist_dir)
        
    documents_dir = Config.DOCUMENTS_DIR
    
    print(f"Checking for existing index in {persist_dir}...")
    
    # Check if storage context exists
    if os.path.exists(persist_dir) and os.path.exists(os.path.join(persist_dir, "docstore.json")):
        print("Loading existing index...")
        try:
            # Reconstruct the storage context
            # For FAISS, we need to reload the vector store specifically if we want to add to it,
            # but for simple loading, load_index_from_storage is usually sufficient if the vector store was persisted correctly.
            # However, FAISS vector store persistence in LlamaIndex can be tricky. 
            # Standard load_index_from_storage might expect a simple vector store.
            # Let's try the standard way first.
            storage_context = StorageContext.from_defaults(persist_dir=persist_dir)
            index = load_index_from_storage(storage_context)
            return index
        except Exception as e:
            print(f"Error loading existing index: {e}. Recreating...")
    
    print(f"Creating new index from documents in {documents_dir}...")
    
    if not os.path.exists(documents_dir):
        os.makedirs(documents_dir, exist_ok=True)
        print(f"Created documents directory at {documents_dir}. Please add documents.")
        return None

    # Load documents
    documents = SimpleDirectoryReader(str(documents_dir)).load_data()
    
    if not documents:
        print("No documents found to index.")
        return None
        
    print(f"Loaded {len(documents)} documents.")

    # Create FAISS index
    # Dimensions for OpenAI text-embedding-ada-002 is 1536
    d = 1536
    faiss_index = faiss.IndexFlatL2(d)
    
    # Create VectorStore
    vector_store = FaissVectorStore(faiss_index=faiss_index)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    
    # Create Index
    index = VectorStoreIndex.from_documents(
        documents, 
        storage_context=storage_context
    )
    
    # Persist Index
    print(f"Persisting index to {persist_dir}...")
    index.storage_context.persist(persist_dir=persist_dir)
    
    return index

if __name__ == "__main__":
    try:
        index = load_documents()
        if index:
            print("Successfully loaded/created index.")
            # Test query
            query_engine = index.as_query_engine()
            response = query_engine.query("What are the service plans?")
            print(f"\nTest Query Response:\n{response}")
    except Exception as e:
        print(f"Error in document loader: {e}")