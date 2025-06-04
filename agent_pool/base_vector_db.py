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
from typing import Optional, Tuple

# ← NEW: import PersistentClient instead of Client
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
) -> Optional[Tuple[PersistentClient, object]]:
    """
    Open (or create) a Chroma “chunks” collection inside a sharded folder for `collection_name`.
    - If the sharded folder/Chroma DB does not exist, create it and then create a new Chroma collection
      named "chunks" with metadata {"emb_method": emb_method}.
    - If it does exist:
        • If the existing collection’s metadata["emb_method"] == emb_method, return (client, collection).
        • Otherwise, return None (indicating a mismatch).

    Returns:
        (chroma_client, chroma_collection)  on success,
        None                               if the collection already exists with a different emb_method.
    """
    # 1) Compute the sharded directory on disk
    base_dir = os.getenv("CHROMA_BASE_DIR", "/chroma_db")
    folder = os.path.join(base_dir, sharded_path(collection_name))
    os.makedirs(folder, exist_ok=True)

    # 2) Instantiate a *PersistentClient* pointing at that folder
    #    The “path” argument tells Chroma where to place its on-disk SQLite/Parquet files.
    try:
        client = PersistentClient(path=folder)
    except Exception as e:
        # If something goes wrong here, it’s often because the directory
        # isn’t writeable or the format is wrong.
        print(f"[DEBUG] Failed to create PersistentClient at {folder}: {e}", flush=True)
        return None

    # 3) List existing collections. Newer Chroma returns a list; older returned {"collections": [...]}
    resp = client.list_collections()
    if isinstance(resp, dict) and "collections" in resp:
        # old style
        existing_names = [c["name"] for c in resp["collections"]]
    else:
        # new style returns a list of metadata objects, each having a "name" key
        existing_names = [c["name"] for c in resp]  # type: ignore[list-item]

    # 4) If a "chunks" collection is already there, open it and check metadata
    if "chunks" in existing_names:
        coll = client.get_collection("chunks")
        existing_method = coll.metadata.get("emb_method")
        if existing_method == emb_method:
            print(f"[DEBUG] Opening existing 'chunks' in {folder} with emb_method={emb_method}", flush=True)
            return client, coll
        else:
            # Mismatch: the folder/collection exists but uses a different embedding method
            print(f"[DEBUG] Metadata mismatch in {folder}: had emb_method={existing_method}, expected {emb_method}", flush=True)
            return None

    # 5) Otherwise, create a fresh "chunks" collection with the given embedding method
    coll = client.create_collection(
        name="chunks",
        metadata={"emb_method": emb_method}
    )
    print(f"[DEBUG] Created new 'chunks' in {folder} with emb_method={emb_method}", flush=True)
    return client, coll

