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
from chromadb import Client
from chromadb.config import Settings
from typing import Optional, Tuple, Union, Dict, List, Any

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
) -> Optional[Tuple[Client, object]]:
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

    # 2) Instantiate a Chroma client pointing at that folder
    #    Note: remove the deprecated `chroma_db_impl` argument and only pass valid fields.
    client = Client(
        settings=Settings(
            persist_directory=folder,
            anonymized_telemetry=False
        )
    )

    # 3) List existing collections. Newer Chroma returns a list; older returned {"collections": [...]}
    resp = client.list_collections()
    if isinstance(resp, dict) and "collections" in resp:
        # old style
        existing_names = [c["name"] for c in resp["collections"]]
    else:
        # new style returns a List of metadata objects, each having a "name" key
        existing_names = [c["name"] for c in resp]  # type: ignore[list-item]

    # 4) If a "chunks" collection is already there, open it and check metadata
    if "chunks" in existing_names:
        coll = client.get_collection("chunks")
        existing_method = coll.metadata.get("emb_method")
        if existing_method == emb_method:
            return client, coll
        else:
            # Mismatch: the folder/collection exists but uses a different embedding method
            return None

    # 5) Otherwise, create a fresh "chunks" collection with the given embedding method
    coll = client.create_collection(
        name="chunks",
        metadata={"emb_method": emb_method}
    )
    return client, coll

