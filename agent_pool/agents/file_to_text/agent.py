# Project Ethel
# Agent to convert files to text
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
import os
import tempfile
import traceback
from datetime import datetime
from typing import Any, Dict

import gridfs
import pytesseract
import requests  # (only needed if you want to test calling another service—keep it in case)
from pdf2image import convert_from_path
from pymongo import MongoClient
from pymongo.errors import PyMongoError

# We pull *all* of the Unstructured loaders from langchain_community to avoid
# “deprecated import” warnings. We will use them to load text (or detect empty).
from langchain_community.document_loaders import (
    UnstructuredPDFLoader,
    UnstructuredWordDocumentLoader,
    UnstructuredPowerPointLoader,
)
from langchain_community.document_loaders import TextLoader
from langchain.schema import Document

from agent_pool.base_agent_server import run_server


class FileToTextAgent:
    """
    Agent that:
      1. Accepts a JSON body with either:
           { "tenant": "...", "collection": "...", "path": "..." }
         or the legacy:
           { "file_id": "tenant/collection/path/to/file.ext" }
      2. Fetches the file from MongoDB/GridFS under metadata.tenant,
         metadata.collection, metadata.path.
      3. If it's a PDF, tries UnstructuredPDFLoader first. If the
         extracted text is extremely short (<50 chars), falls back
         to per-page OCR via pdf2image + pytesseract.
      4. If it's .txt/.md/.docx/.doc/.pptx/.ppt, uses the appropriate
         Unstructured loader.
      5. Returns a JSON with task_result structure on success or failure.
    """

    def __init__(self):
        # === MongoDB / GridFS setup ===
        MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongodb:27017")
        MONGO_DB = os.getenv("MONGO_DB", "ethel_files")
        try:
            self.mongo_client = MongoClient(MONGO_URI)
            self.mongo_db = self.mongo_client[MONGO_DB]
            self.fs = gridfs.GridFS(self.mongo_db)
        except PyMongoError as e:
            raise RuntimeError(f"Could not connect to MongoDB: {e}")

    def handle(self, request_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Expects either:
          { "tenant": "...", "collection": "...", "path": "..." }
        or:
          { "file_id": "tenant/collection/path/to/file.ext" }

        Returns a dict:
          {
            "id":      "file_to_text_response",
            "object":  "task_result",
            "created": <timestamp>,
            "status":  <HTTP code>,
            "text":    "<extracted text>"    # if status==200
            "error":   "<error message>"     # if status!=200
          }
        """
        result: Dict[str, Any] = {
            "id":      "file_to_text_response",
            "object":  "task_result",
            "created": int(datetime.utcnow().timestamp()),
        }

        # 1) Extract tenant, collection, and path
        tenant     = request_json.get("tenant")
        collection = request_json.get("collection")
        file_path  = request_json.get("path")

        if not (tenant and collection and file_path):
            # Fallback to legacy single field "file_id"
            fid = request_json.get("file_id")
            if not fid or not isinstance(fid, str):
                result.update({
                    "status": 400,
                    "error": "Missing 'tenant'/'collection'/'path' or 'file_id'."
                })
                return result
            parts = fid.split("/", 2)
            if len(parts) != 3:
                result.update({
                    "status": 400,
                    "error": "Invalid 'file_id'. Expected 'tenant/collection/path'."
                })
                return result
            tenant, collection, file_path = parts

        # 2) Retrieve the file from GridFS using all three metadata fields
        try:
            gf = self.fs.get_last_version(
                metadata={
                    "tenant":     tenant,
                    "collection": collection,
                    "path":       file_path
                }
            )
            file_bytes = gf.read()
        except gridfs.NoFile:
            result.update({
                "status": 404,
                "error": (
                    f"File not found in GridFS for "
                    f"tenant='{tenant}', collection='{collection}', path='{file_path}'."
                )
            })
            return result
        except Exception as exc:
            traceback.print_exc()
            result.update({
                "status": 500,
                "error": f"Error retrieving file from GridFS: {exc}"
            })
            return result

        # 3) Write bytes to a temporary local file so that loaders/OCR can read it
        _, extension = os.path.splitext(file_path)
        extension = extension.lower()
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

        # 4) Load/extract text based on extension (with PDF→OCR fallback)
        try:
            extracted_docs: list[Document]

            if extension == ".pdf":
                loader = UnstructuredPDFLoader(local_path)
                try:
                    extracted_docs = loader.load()
                except Exception:
                    extracted_docs = []

                total_text = "".join(d.page_content or "" for d in extracted_docs).strip()
                if len(total_text) < 50:
                    # Fallback to OCR
                    page_images = convert_from_path(local_path)
                    ocr_docs: list[Document] = []
                    for img in page_images:
                        page_text = pytesseract.image_to_string(img)
                        ocr_docs.append(Document(page_content=page_text))
                    extracted_docs = ocr_docs

            elif extension in [".txt", ".md", ".text"]:
                loader = TextLoader(local_path, encoding="utf-8")
                extracted_docs = loader.load()

            elif extension in [".docx", ".doc"]:
                loader = UnstructuredWordDocumentLoader(local_path)
                extracted_docs = loader.load()

            elif extension in [".pptx", ".ppt"]:
                loader = UnstructuredPowerPointLoader(local_path)
                extracted_docs = loader.load()

            else:
                raise ValueError(f"Unsupported file extension: '{extension}'")

        except Exception as exc:
            traceback.print_exc()
            try:
                os.remove(local_path)
            except OSError:
                pass
            result.update({
                "status": 500,
                "error": f"Error extracting text from file: {exc}"
            })
            return result

        # 5) Concatenate all page_content into one big string
        full_text = "\n\n".join(d.page_content or "" for d in extracted_docs).strip()

        # 6) Clean up local temp file
        try:
            os.remove(local_path)
        except OSError:
            pass

        # 7) Return success
        result.update({
            "status": 200,
            "text":   full_text
        })
        return result


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    run_server(port=port, handler_instance=FileToTextAgent())

