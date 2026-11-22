import chromadb
from chromadb.utils import embedding_functions
from tree_sitter_languages import get_language, get_parser

embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection(name="codebase", embedding_function=embed_fn)

def chunk_code_by_ast(code: str, file_path: str = ""):
    if file_path.endswith('.py'): lang = "python"
    elif file_path.endswith('.js') or file_path.endswith('.ts'): lang = "javascript"
    elif file_path.endswith('.go'): lang = "go"
    elif file_path.endswith('.rs'): lang = "rust"
    else: return code.split('\n\n')

    try:
        parser = get_parser(lang)
        tree = parser.parse(bytes(code, "utf8"))
    except: return code.split('\n\n')

    query_str = "(function_declaration) @chunk (class_declaration) @chunk (method_definition) @chunk"
    try:
        lang_obj = get_language(lang)
        query = lang_obj.query(query_str)
        captures = query.captures(tree.root_node)
    except: return code.split('\n\n')

    chunks = [code[node.start_byte:node.end_byte] for node, name in captures]
    return chunks if chunks else [code]

def index_codebase(files: list):
    collection.delete(where={"source": "local_codebase"})
    documents, metadatas, ids = [], [], []
    for file in files:
        chunks = chunk_code_by_ast(file["content"], file["path"])
        for i, chunk in enumerate(chunks):
            if len(chunk.strip()) > 20:
                documents.append(chunk)
                metadatas.append({"file_path": file["path"], "chunk_id": i, "source": "local_codebase"})
                ids.append(f"{file['path']}_chunk_{i}")
    if documents: collection.add(documents=documents, metadatas=metadatas, ids=ids)
    return f"Indexed {len(documents)} AST chunks."

def search_codebase(query: str, n_results: int = 3):
    results = collection.query(query_texts=[query], n_results=n_results, where={"source": "local_codebase"})
    context = ""
    for i, doc in enumerate(results['documents'][0]):
        meta = results['metadatas'][0][i]
        context += f"File: {meta['file_path']}\n```\n{doc}\n```\n\n"
    return context
