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
import json
from datetime import datetime

import requests
import gridfs
from pymongo import MongoClient
from pymongo.errors import PyMongoError

# Pull **all** of the Unstructured loaders from langchain_community to avoid
# the new “deprecated import” warnings.
from langchain_community.document_loaders import (
    UnstructuredPDFLoader,
    UnstructuredWordDocumentLoader,
    UnstructuredPowerPointLoader,
)
from langchain_community.document_loaders import TextLoader
#from langchain.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document

# If PDFMiner yields almost no text (i.e. scanned PDF), do per‐page OCR:
from pdf2image import convert_from_path
import pytesseract

from chromadb import Client
from chromadb.config import Settings

from agent_pool.base_agent_server import run_server
from agent_pool.base_vector_db import open_chroma_for, sharded_path


class EmbFileAda3LargeAgent:
    """
    Agent that:
      1. Accepts a single string `file_id` of the form "collection/path/to/file.ext"
      2. Fetches the file from MongoDB/GridFS
      3. Splits into chunks via LangChain (trying PDFMiner first for .pdf, then OCR if needed)
      4. Calls Azure OpenAI's Ada‐3‐large embeddings endpoint (with retries) for each chunk
      5. Connects to Chroma (one folder per collection, sharded). If the Chroma collection
         already exists with a matching emb_method, open it; if it exists but emb_method
         mismatches, return an error; if it doesn’t exist, create it.
      6. Deletes any existing vectors in that Chroma collection for the same file path
         (so new versions overwrite old embeddings).
      7. Inserts each chunk’s embedding vector, raw text, and metadata (path, filename,
         chunk_number, emb_method) into Chroma.
      8. Returns a JSON‐compatible dict with "status" (HTTP‐style code) and either
         "message" or "error". Also prints debug info to container logs.
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

        # === 2) Azure OpenAI Ada‐3‐large config ===
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

        # === 3) Chunker parameters (can be overridden via env) ===
        self.chunk_size = int(os.getenv("CHUNK_SIZE", "2000"))
        self.chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "400"))

    def embed_text(self, text: str) -> list[float]:
        """
        Call Azure OpenAI Ada‐3‐large embeddings endpoint with retries on rate‐limit (429).
        Returns the embedding vector as a list of floats.
        Raises Exception on non‐429 errors or if max retries exceeded.
        """
        max_retries = 5
        backoff = 1

        for attempt in range(max_retries):
            try:
                payload = {"input": text}
                resp = requests.post(self.azure_url, json=payload, headers=self.headers, timeout=30)

                if resp.status_code == 429:
                    # Rate‐limited: wait & retry
                    time.sleep(backoff)
                    backoff *= 2
                    continue

                resp.raise_for_status()
                data = resp.json()
                return data["data"][0]["embedding"]

            except requests.exceptions.HTTPError as http_err:
                if resp.status_code == 429:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                else:
                    raise RuntimeError(f"HTTP error during embedding: {http_err} (status {resp.status_code})")
            except Exception as exc:
                raise RuntimeError(f"Error calling embedding endpoint: {exc}")

        raise RuntimeError("Exceeded max retries for embedding call (rate‐limited)")

    def load_and_chunk(self, local_path: str, extension: str) -> list[Document]:
        """
        Given a local file path and its extension, load it with:
          - For .pdf: first attempt UnstructuredPDFLoader (PDFMiner); if the extracted text is
            almost empty, fall back to OCR on each page via pdf2image + pytesseract.
          - For .txt/.md/.text: TextLoader
          - For .docx/.doc: UnstructuredWordDocumentLoader
          - For .pptx/.ppt: UnstructuredPowerPointLoader

        Then split the resulting list of Document(page_content=...) objects using
        RecursiveCharacterTextSplitter. Returns a list of chunk‐Documents.
        """
        ext = extension.lower()
        docs: list[Document]

        if ext == ".pdf":
            # 1) Try text‐based extraction via UnstructuredPDFLoader
            loader = UnstructuredPDFLoader(local_path)
            try:
                docs = loader.load()
            except Exception:
                # If that fails, treat as empty so we can fall back to OCR
                docs = []

            # 2) If the total text is essentially empty, do a quick OCR pass page by page
            total_text = "".join(d.page_content or "" for d in docs).strip()
            if len(total_text) < 50:
                print("[DEBUG] PDFMiner extracted too little text (len < 50); falling back to OCR", flush=True)
                try:
                    page_images = convert_from_path(local_path)
                except Exception as e:
                    raise RuntimeError(f"Failed to convert PDF to images for OCR: {e}")

                ocr_docs: list[Document] = []
                for img in page_images:
                    page_text = pytesseract.image_to_string(img)
                    ocr_docs.append(Document(page_content=page_text))
                docs = ocr_docs

        elif ext in [".txt", ".md", ".text"]:
            loader = TextLoader(local_path, encoding="utf-8")
            docs = loader.load()

        elif ext in [".docx", ".doc"]:
            loader = UnstructuredWordDocumentLoader(local_path)
            docs = loader.load()

        elif ext in [".pptx", ".ppt"]:
            loader = UnstructuredPowerPointLoader(local_path)
            docs = loader.load()

        else:
            raise ValueError(f"Unsupported file extension: '{extension}'")

        # 3) Now split all loaded Documents into chunks using RecursiveCharacterTextSplitter
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            add_start_index=True,
        )
        chunked = splitter.split_documents(docs)
        return chunked

    def handle(self, request_json: dict) -> dict:
        """
        Main entry point for incoming requests. Expects:
          request_json = { "file_id": "collection/path/to/file.ext" }

        Returns a dict:
          { "id": "...", "object": "...", "created": <timestamp>,
            "status": <HTTP‐code>, "message": "...", ... }
          or
          { "id": "...", "object": "...", "created": <timestamp>,
            "status": <HTTP‐code>, "error": "..." } on failure.
        Debug prints appear in container logs (stdout).
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
                metadata={"collection": collection_name, "path": file_path}
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

        # 3) Write bytes to a temporary local file for LangChain loaders
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

        # 4) Load + chunk the file (with text→OCR fallback for PDFs)
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

        # 5) Open (or create) Chroma collection for this `collection_name`
        #    If it exists but with a different embedder, return an error.
        chroma_result = open_chroma_for(collection_name, emb_method="ada3large")
        if chroma_result is None:
            try:
                os.remove(local_path)
            except OSError:
                pass
            result.update({
                "status": 400,
                "error": (
                    f"Chroma folder exists for collection '{collection_name}' "
                    f"with a different embedding method."
                )
            })
            return result

        client, chr_collection = chroma_result

        # --- DEBUG: print out which folder we are writing into and whether we opened or created ---
        base_dir = os.getenv("CHROMA_BASE_DIR", "/chroma_db")
        folder   = os.path.join(base_dir, sharded_path(collection_name))
        print(f"[DEBUG] Chroma folder path: {folder}", flush=True)

        # 6) Delete any existing embeddings for this same file_path
        try:
            print(f"[DEBUG] Deleting existing embeddings for path '{file_path}' in collection '{collection_name}'", flush=True)
            chr_collection.delete(where={"path": file_path})
        except Exception:
            # If the collection was just created and is empty, delete() might raise
            # or simply do nothing. Ignore any errors here.
            print("[DEBUG] delete(...) on newly created collection may have failed or had nothing to delete.", flush=True)

        # 7) Embed each chunk and collect data for insertion
        embeddings = []
        metadatas = []
        documents = []
        ids = []

        for idx, doc in enumerate(splits):
            text = doc.page_content or ""
            try:
                emb_vec = self.embed_text(text)
            except Exception as exc:
                traceback.print_exc()
                try:
                    os.remove(local_path)
                except OSError:
                    pass
                result.update({
                    "status": 500,
                    "error": f"Failed to embed chunk {idx}: {exc}"
                })
                return result

            chunk_id = f"{collection_name}/{file_path}-{idx}"
            embeddings.append(emb_vec)
            documents.append(text)

            # Metadata for this chunk
            metadatas.append({
                "path": file_path,
                "filename": os.path.basename(file_path),
                "chunk_number": idx,
                "emb_method": "ada3large"
            })

            ids.append(chunk_id)

        # 8) Insert into Chroma
        try:
            print(f"[DEBUG] Adding {len(embeddings)} chunks to Chroma collection '{collection_name}'", flush=True)
            chr_collection.add(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=documents
            )
        except Exception as exc:
            traceback.print_exc()
            try:
                os.remove(local_path)
            except OSError:
                pass
            result.update({
                "status": 500,
                "error": f"Error inserting into Chroma: {exc}"
            })
            return result

        # 9) Show folder contents before persist
        try:
            before = []
            for root, dirs, files in os.walk(folder):
                for f in files:
                    before.append(os.path.relpath(os.path.join(root, f), folder))
            print(f"[DEBUG] Contents of {folder} BEFORE persist(): {before}", flush=True)
        except Exception as e:
            print(f"[DEBUG] Failed to list {folder} before persist: {e}", flush=True)

        # 10) Force‐write to disk before returning
        try:
            print("[DEBUG] Calling client.persist()", flush=True)
            client.persist()
        except Exception as e:
            print(f"[DEBUG] Exception during client.persist(): {e}", flush=True)

        # 11) Show folder contents after persist
        try:
            after = []
            for root, dirs, files in os.walk(folder):
                for f in files:
                    after.append(os.path.relpath(os.path.join(root, f), folder))
            print(f"[DEBUG] Contents of {folder} AFTER persist(): {after}", flush=True)
        except Exception as e:
            print(f"[DEBUG] Failed to list {folder} after persist: {e}", flush=True)

        # 12) Cleanup temp file
        try:
            os.remove(local_path)
        except OSError:
            pass

        # 13) Success
        num_chunks = len(splits)
        result.update({
            "status": 200,
            "message": (
                f"Successfully embedded and inserted {num_chunks} chunk(s) "
                f"into Chroma collection '{collection_name}'."
            )
        })
        return result


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    run_server(port=port, handler_instance=EmbFileAda3LargeAgent())

