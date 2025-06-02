# Project Ethel
# Agent for ADA3large embedding of a file
#
# Copyright (C) 2025  Gerd Kortemeyer, ETH Zurich
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# agent_pool/agents/emb_file_ada3large/agent.py

import os
import time
import tempfile
import traceback
from datetime import datetime

import requests
import gridfs
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from langchain_community.document_loaders import UnstructuredPDFLoader
from langchain.document_loaders import TextLoader, UnstructuredWordDocumentLoader, UnstructuredPowerPointLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter

from pymilvus import (
    connections,
    FieldSchema,
    CollectionSchema,
    DataType,
    Collection,
    utility,
)

from agent_pool.base_agent_server import run_server


class EmbFileAda3LargeAgent:
    """
    Agent that:
      1. Accepts a single string `file_id` of the form "collection/path/to/file.ext"
      2. Fetches the file from MongoDB/GridFS
      3. Chooses the correct LangChain loader & splits it into chunks
      4. Calls Azure OpenAI's Ada-3-large embeddings endpoint (with retries) for each chunk
      5. Connects to Milvus (using pymilvus), with a retry loop:
           • If Milvus isn’t reachable yet, waits and retries
           • Once connected, checks if a collection named `collection` exists
             – If it exists, deletes any old chunks for the same file path
             – If it doesn’t exist, will create it on the first embedding
      6. Stores each chunk’s embedding **and** its raw text (for RAG later)
      7. Returns a JSON‐compatible dict with "status" (HTTP‐style code) and either "message" or "error".
    """

    def __init__(self):
        # === 1) MongoDB/GridFS setup ===
        MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongodb:27017")
        MONGO_DB = os.getenv("MONGO_DB", "ethel_files")
        try:
            self.mongo_client = MongoClient(MONGO_URI)
            self.mongo_db = self.mongo_client[MONGO_DB]
            self.fs = gridfs.GridFS(self.mongo_db)
        except PyMongoError as e:
            raise RuntimeError(f"Could not connect to MongoDB: {e}")

        # === 2) Milvus setup with retry logic ===
        MILVUS_HOST = os.getenv("MILVUS_HOST", "milvus")
        MILVUS_PORT = os.getenv("MILVUS_PORT", "19530")

        # How many times to retry (default: 10 attempts, i.e. ~50 seconds total if using 5s backoff)
        max_retries = int(os.getenv("MILVUS_CONNECT_RETRIES", "10"))
        backoff_seconds = int(os.getenv("MILVUS_CONNECT_BACKOFF", "5"))

        connected = False
        last_err = None
        for attempt in range(1, max_retries + 1):
            try:
                print(f"[EmbFileAda3LargeAgent] Attempting to connect to Milvus at {MILVUS_HOST}:{MILVUS_PORT} "
                      f"(attempt {attempt}/{max_retries})...", flush=True)
                connections.connect("default", host=MILVUS_HOST, port=MILVUS_PORT)
                print("[EmbFileAda3LargeAgent] Successfully connected to Milvus.", flush=True)
                connected = True
                break
            except Exception as e:
                last_err = e
                print(f"[EmbFileAda3LargeAgent] Milvus connection failed: {e}", flush=True)
                if attempt < max_retries:
                    print(f"[EmbFileAda3LargeAgent] Retrying in {backoff_seconds} seconds...", flush=True)
                    time.sleep(backoff_seconds)
                else:
                    # Final attempt also failed
                    break

        if not connected:
            raise RuntimeError(
                f"Could not connect to Milvus at {MILVUS_HOST}:{MILVUS_PORT} "
                f"after {max_retries} attempts. Last error: {last_err}"
            )

        # === 3) Azure OpenAI Ada-3-large config ===
        self.azure_endpoint = os.environ["AZURE_ENDPOINT"]
        self.azure_key = os.environ["AZURE_KEY"]
        self.azure_deployment = os.environ["AZURE_ADA3LARGE_DEPLOYMENT"]
        self.api_version = "2023-05-15"

        self.azure_url = (
            f"{self.azure_endpoint}/openai/deployments/"
            f"{self.azure_deployment}/embeddings?api-version={self.api_version}"
        )
        self.headers = {
            "Content-Type": "application/json",
            "api-key": self.azure_key,
        }

        # === 4) Chunker parameters (can be overridden via env) ===
        self.chunk_size = int(os.getenv("CHUNK_SIZE", "2000"))
        self.chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "400"))

    def embed_text(self, text: str) -> list[float]:
        """
        Call Azure OpenAI Ada-3-large embeddings endpoint with retries on rate-limit (429).
        Returns the embedding vector as a list of floats.
        Raises Exception on non-429 errors or if max retries exceeded.
        """
        max_retries = 5
        backoff = 1

        for attempt in range(max_retries):
            try:
                payload = {"input": text}
                resp = requests.post(self.azure_url, json=payload, headers=self.headers, timeout=30)

                if resp.status_code == 429:
                    # Rate-limited: wait & retry
                    time.sleep(backoff)
                    backoff *= 2
                    continue

                resp.raise_for_status()
                data = resp.json()
                return data["data"][0]["embedding"]

            except requests.exceptions.HTTPError as http_err:
                if resp.status_code == 429:
                    # Another 429 caught by raise_for_status
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                else:
                    # Non-429 HTTP error
                    raise RuntimeError(f"HTTP error during embedding: {http_err} (status {resp.status_code})")
            except Exception as exc:
                # Some other network/error—bubble up
                raise RuntimeError(f"Error calling embedding endpoint: {exc}")

        raise RuntimeError("Exceeded max retries for embedding call (rate-limited)")

    def load_and_chunk(self, local_path: str, extension: str) -> list:
        """
        Given a local file path and its extension, load it with the appropriate LangChain loader
        and split it into chunks using RecursiveCharacterTextSplitter.
        Returns a list of Document objects (each with .page_content).
        """
        ext = extension.lower()
        if ext == ".pdf":
            loader = UnstructuredPDFLoader(local_path)
        elif ext in [".txt", ".md", ".text"]:
            loader = TextLoader(local_path, encoding="utf-8")
        elif ext in [".docx", ".doc"]:
            loader = UnstructuredWordDocumentLoader(local_path)
        elif ext in [".pptx", ".ppt"]:
            loader = UnstructuredPowerPointLoader(local_path)
        else:
            raise ValueError(f"Unsupported file extension: '{extension}'")

        docs = loader.load()
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            add_start_index=True,
        )
        splits = splitter.split_documents(docs)
        return splits

    def handle(self, request_json: dict) -> dict:
        """
        Main entry point for incoming requests. Expects:
          request_json = { "file_id": "collection/path/to/file.ext" }

        Returns a dict:
          { "id": "...", "object": "...", "created": <timestamp>,
            "status": <HTTP-code>, "message": "...", ... }
          or
          { "id": "...", "object": "...", "created": <timestamp>,
            "status": <HTTP-code>, "error": "..." } on failure.
        """
        result = {
            "id":      "emb_file_ada3large_response",
            "object":  "task_result",
            "created": int(datetime.utcnow().timestamp()),
        }

        # 1) Validate input
        file_identifier = request_json.get("file_id")
        if not file_identifier or not isinstance(file_identifier, str):
            result.update({
                "status": 400,
                "error": "Missing or invalid 'file_id'. Expected a string like 'collection/path/to/file.ext'."
            })
            return result

        # Split into collection and path
        if "/" not in file_identifier:
            result.update({
                "status": 400,
                "error": "Invalid file_id format. Must be 'collection/path/to/file.ext'."
            })
            return result

        collection_name, file_path = file_identifier.split("/", 1)

        # 2) Retrieve the file from GridFS
        try:
            gf = self.fs.get_last_version(
                {"metadata.collection": collection_name, "metadata.path": file_path}
            )
            file_bytes = gf.read()
            filename = gf.filename  # for reference, though file_path already includes it
        except gridfs.NoFile:
            result.update({
                "status": 404,
                "error": f"File not found in GridFS for collection='{collection_name}', path='{file_path}'."
            })
            return result
        except Exception as exc:
            traceback.print_exc()
            result.update({
                "status": 500,
                "error": f"Error retrieving file from GridFS: {exc}"
            })
            return result

        # 3) Write bytes to a temporary local file so LangChain loaders can read it
        _, extension = os.path.splitext(file_path)
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as tmp:
                tmp.write(file_bytes)
                local_path = tmp.name
        except Exception as exc:
            traceback.print_exc()
            result.update({
                "status": 500,
                "error": f"Failed to write temp file: {exc}"
            })
            return result

        # 4) Load + chunk the file
        try:
            splits = self.load_and_chunk(local_path, extension)
        except Exception as exc:
            traceback.print_exc()
            try:
                os.remove(local_path)
            except OSError:
                pass
            result.update({
                "status": 500,
                "error": f"Error during chunking: {exc}"
            })
            return result

        # 5) Begin Milvus operations (delete old, maybe create schema, then insert)
        try:
            if utility.has_collection(collection_name):
                milvus_collection = Collection(collection_name)
                # Delete any existing embeddings for this same file_path
                delete_expr = f'path == "{file_path}"'
                milvus_collection.delete(delete_expr)
                milvus_collection.flush()
                collection_preexisted = True
            else:
                collection_preexisted = False

            # === 5a) Embed all chunks (retry on 429) ===
            embeddings: list[list[float]] = []
            for idx, doc in enumerate(splits):
                text = doc.page_content or ""
                try:
                    emb_vec = self.embed_text(text)
                except Exception as exc:
                    raise RuntimeError(f"Failed to embed chunk {idx}: {exc}")
                embeddings.append(emb_vec)

                # On first chunk for a brand-new collection, create schema + index
                if idx == 0 and not collection_preexisted:
                    dim = len(emb_vec)
                    fields = [
                        FieldSchema(
                            name="id",
                            dtype=DataType.VARCHAR,
                            max_length=1024,
                            is_primary=True,
                            description="unique chunk ID (collection/file_path-chunk_number)"
                        ),
                        FieldSchema(
                            name="path",
                            dtype=DataType.VARCHAR,
                            max_length=2048,
                            description="the file path (collection-relative)"
                        ),
                        FieldSchema(
                            name="filename",
                            dtype=DataType.VARCHAR,
                            max_length=512,
                            description="filename (last segment of path)"
                        ),
                        FieldSchema(
                            name="chunk_number",
                            dtype=DataType.INT64,
                            description="chunk index within the file"
                        ),
                        FieldSchema(
                            name="emb_method",
                            dtype=DataType.VARCHAR,
                            max_length=64,
                            description="embedding method identifier, e.g. 'ada3large'"
                        ),
                        FieldSchema(
                            name="content",
                            dtype=DataType.VARCHAR,
                            max_length=65535,
                            description="the raw text of this chunk"
                        ),
                        FieldSchema(
                            name="vector",
                            dtype=DataType.FLOAT_VECTOR,
                            dim=dim,
                            description="the embedding vector"
                        ),
                    ]
                    schema = CollectionSchema(
                        fields,
                        description=f"Embeddings + text-chunks for collection '{collection_name}'"
                    )
                    milvus_collection = Collection(name=collection_name, schema=schema)
                    milvus_collection.create_index(
                        field_name="vector",
                        params={
                            "index_type": "IVF_FLAT",
                            "params": {"nlist": 128},
                            "metric_type": "L2"
                        }
                    )
                    milvus_collection.load()

            # === 5b) Prepare and insert all chunks ===
            num_chunks = len(splits)
            ids = []
            paths = []
            filenames = []
            chunk_numbers = []
            emb_methods = []
            contents = []
            vectors = []

            for idx, (doc, vec) in enumerate(zip(splits, embeddings)):
                chunk_id = f"{collection_name}/{file_path}-{idx}"
                ids.append(chunk_id)
                paths.append(file_path)
                filenames.append(os.path.basename(file_path))
                chunk_numbers.append(idx)
                emb_methods.append("ada3large")
                contents.append(doc.page_content or "")
                vectors.append(vec)

            milvus_collection.insert([
                ids,
                paths,
                filenames,
                chunk_numbers,
                emb_methods,
                contents,
                vectors
            ])
            milvus_collection.flush()

        except Exception as exc:
            traceback.print_exc()
            try:
                os.remove(local_path)
            except OSError:
                pass
            result.update({
                "status": 500,
                "error": f"Error during Milvus operations: {exc}"
            })
            return result

        # 6) Cleanup temp file
        try:
            os.remove(local_path)
        except OSError:
            pass

        # 7) Success
        result.update({
            "status": 200,
            "message": (
                f"Successfully embedded and inserted {num_chunks} chunk(s) "
                f"into Milvus collection '{collection_name}'."
            )
        })
        return result


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    run_server(port=port, handler_instance=EmbFileAda3LargeAgent())

