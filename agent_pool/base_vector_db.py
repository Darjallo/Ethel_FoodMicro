# Project Ethel
# Base for connecting to Chroma
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
# agent_pool/base_vector_db.py

import os
from typing import Optional, Tuple, Any, Dict

from chromadb import PersistentClient
from chromadb.config import Settings


def sharded_path(collection_name: str) -> str:
    """
    Given a collection name, return a sharded directory path of the form:
        first_char/second_char/third_char/collection_name
    If the name is shorter than 3 characters, pad with underscores (“_”).

    Examples:
      "foobar" -> "f/o/o/foobar"
      "ba"     -> "b/a/_/ba"
      ""       -> "_/_/_/"
    """
    padded = (collection_name + "___")[:3]
    first, second, third = padded[0], padded[1], padded[2]
    return os.path.join(first, second, third, collection_name)


def open_chroma_for(
    collection_name: str,
    emb_method: str
) -> Optional[Tuple[PersistentClient, Any]]:
    """
    Open (or create) a Chroma “default” collection inside a sharded folder for `collection_name`.
    - If the sharded folder/Chroma DB does not exist, mkdir it and create a new Chroma
      collection named "default" with metadata {"emb_method": emb_method}.
    - If it already exists:
        • If an existing “default” collection’s metadata["emb_method"] == emb_method,
          return (client, coll).
        • Otherwise, return None (indicating a mismatch).

    Returns:
        (chroma_client, chroma_collection)  on success,
        None                               if this folder already had a different emb_method.
    """
    base_dir = os.getenv("CHROMA_BASE_DIR", "/chroma_db")
    folder = os.path.join(base_dir, sharded_path(collection_name))
    os.makedirs(folder, exist_ok=True)

    try:
        client = PersistentClient(path=folder)
    except Exception as e:
        # Often a permissions/format problem
        print(f"[DEBUG] Failed to create PersistentClient at {folder}: {e}", flush=True)
        return None

    # Try to open "default"
    try:
        coll = client.get_collection("default")
        existing_method = coll.metadata.get("emb_method")
        if existing_method == emb_method:
            # exact match; use it
            return client, coll
        else:
            # folder already has a collection under a different embedding method
            print(
                f"[DEBUG] Metadata mismatch in {folder}: "
                f"found emb_method={existing_method}, expected={emb_method}",
                flush=True
            )
            return None
    except Exception:
        # If get_collection("default") failed, it simply doesn’t exist yet → create it
        try:
            coll = client.create_collection(
                name="default",
                metadata={"emb_method": emb_method}
            )
            return client, coll
        except Exception as e:
            print(f"[DEBUG] Failed to create 'default' in {folder}: {e}", flush=True)
            return None


def get_chroma_collection(
    collection_name: str
) -> Optional[Any]:
    """
    Attempt to open the Chroma “default” collection for this `collection_name` shard.
    If no such folder/collection exists, return None.

    Returns:
       Collection  on success
       None        if the folder or "default" is missing.
    """
    base_dir = os.getenv("CHROMA_BASE_DIR", "/chroma_db")
    shard_folder = os.path.join(base_dir, sharded_path(collection_name))

    if not os.path.isdir(shard_folder):
        # No shard folder means nothing was ever created for this collection.
        return None

    try:
        client = PersistentClient(path=shard_folder)
    except Exception:
        return None

    try:
        return client.get_collection("default")
    except Exception:
        return None

